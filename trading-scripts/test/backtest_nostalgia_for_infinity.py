#!/usr/bin/env python3
"""
NostalgiaForInfinity 风格策略专用回测脚本（独立文件）。

说明:
- 该脚本仅用于回测 NFI 风格策略，不依赖现有 backtest.py。
- 逻辑对齐 scripts/auto_trader_nostalgia_for_infinity.py 的核心入场条件。

用法示例:
  python trading-scripts/test/backtest_nostalgia_for_infinity.py --symbol BTC
  python trading-scripts/test/backtest_nostalgia_for_infinity.py --symbol ETH --start-date 2025-08-01 --end-date 2026-02-20
"""

import argparse
from datetime import datetime
from typing import Dict, List, Tuple

import requests

INITIAL_CAPITAL = 100.0
TAKER_FEE = 0.00035
MIN_PROFIT_AFTER_FEE = 0.005
DEFAULT_LEVERAGE = 2
MAX_LEVERAGE = 3
MAX_POSITION_USD = 294.0
MIN_ORDER_VALUE = 10.0
DEFAULT_COOLDOWN_CANDLES = 4
DEFAULT_MAX_HOLD_CANDLES = 72

NFI_DEFAULTS = {
    "ema_fast": 20,
    "ema_trend": 50,
    "ema_long": 200,
    "rsi_fast": 4,
    "rsi_main": 14,
    "atr_period": 14,
    "bb_period": 20,
    "bb_stddev": 2.0,
    "volume_sma_period": 30,
    "rsi_fast_buy": 23.0,
    "rsi_main_buy": 36.0,
    "bb_touch_buffer": 1.01,
    "ema_pullback_buffer": 0.985,
    "regime_price_floor": 0.95,
    "max_breakdown_pct": 0.10,
    "enable_short": True,
    "rsi_fast_sell": 79.0,
    "rsi_main_sell": 62.0,
    "bb_reject_buffer": 0.99,
    "ema_bounce_buffer": 1.015,
    "regime_price_ceiling": 1.05,
    "max_breakout_pct": 0.10,
    "min_volume_ratio": 0.65,
    "stop_loss_atr_mult": 2.4,
    "take_profit_atr_mult": 4.0,
}

NFI_SYMBOL_OVERRIDES = {
    "ETH": {
        "rsi_fast_buy": 21.0,
        "rsi_main_buy": 34.0,
        "rsi_fast_sell": 75.0,
        "rsi_main_sell": 62.0,
        "stop_loss_atr_mult": 2.8,
        "take_profit_atr_mult": 2.8,
    }
}


def resolve_nfi_params(symbol: str) -> Dict[str, float]:
    params = dict(NFI_DEFAULTS)
    params.update(NFI_SYMBOL_OVERRIDES.get(symbol.upper(), {}))
    return params


def ema(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    mult = 2 / (period + 1)
    out = [values[0]]
    for price in values[1:]:
        out.append(price * mult + out[-1] * (1 - mult))
    return out


def sma(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    out = []
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= period:
            running -= values[i - period]
        count = period if i >= period - 1 else i + 1
        out.append(running / count)
    return out


def rolling_std(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    out = []
    for i in range(len(values)):
        start = max(0, i - period + 1)
        win = values[start : i + 1]
        mean = sum(win) / len(win)
        var = sum((x - mean) ** 2 for x in win) / len(win)
        out.append(var ** 0.5)
    return out


def bollinger_bands(values: List[float], period: int, std_mult: float) -> Tuple[List[float], List[float], List[float]]:
    mid = sma(values, period)
    std = rolling_std(values, period)
    upper = [m + std_mult * s for m, s in zip(mid, std)]
    lower = [m - std_mult * s for m, s in zip(mid, std)]
    return mid, upper, lower


def rsi_wilder(values: List[float], period: int) -> List[float]:
    if len(values) < 2:
        return [50.0] * len(values)

    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(c, 0.0) for c in changes]
    losses = [max(-c, 0.0) for c in changes]

    out = [50.0] * len(values)
    if len(changes) < period:
        return out

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(changes)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period
        if avg_loss == 0:
            out[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i + 1] = 100.0 - (100.0 / (1 + rs))
    return out


def atr_wilder(highs: List[float], lows: List[float], closes: List[float], period: int) -> List[float]:
    if len(closes) < 2:
        return [0.0] * len(closes)

    tr = [0.0] * len(closes)
    for i in range(1, len(closes)):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

    out = [0.0] * len(closes)
    running = 0.0
    for i in range(1, len(closes)):
        if i <= period:
            running += tr[i]
            out[i] = running / i
        else:
            out[i] = ((out[i - 1] * (period - 1)) + tr[i]) / period
    return out


def calc_confidence_long(
    price: float,
    bb_lower_v: float,
    ema_trend_v: float,
    ema_long_v: float,
    rsi_fast_v: float,
    rsi_main_v: float,
    volume_v: float,
    volume_sma_v: float,
) -> float:
    confidence = 0.45
    if price <= bb_lower_v:
        confidence += 0.15
    if ema_trend_v > ema_long_v:
        confidence += 0.10
    if rsi_main_v <= 33:
        confidence += 0.10
    if rsi_fast_v <= 18:
        confidence += 0.10
    if volume_sma_v > 0 and volume_v >= volume_sma_v:
        confidence += 0.10
    return min(confidence, 1.0)


def calc_confidence_short(
    price: float,
    bb_upper_v: float,
    ema_trend_v: float,
    ema_long_v: float,
    rsi_fast_v: float,
    rsi_main_v: float,
    volume_v: float,
    volume_sma_v: float,
) -> float:
    confidence = 0.45
    if price >= bb_upper_v:
        confidence += 0.15
    if ema_trend_v < ema_long_v:
        confidence += 0.10
    if rsi_main_v >= 67:
        confidence += 0.10
    if rsi_fast_v >= 82:
        confidence += 0.10
    if volume_sma_v > 0 and volume_v >= volume_sma_v:
        confidence += 0.10
    return min(confidence, 1.0)


def check_profit_after_fees(position_size: float, entry_price: float, take_profit: float) -> Tuple[bool, float]:
    price_change_pct = abs(take_profit - entry_price) / entry_price
    gross_profit = position_size * price_change_pct
    open_fee = position_size * TAKER_FEE
    close_fee = position_size * (1 + price_change_pct) * TAKER_FEE
    total_fees = open_fee + close_fee
    net_profit = gross_profit - total_fees
    net_profit_pct = net_profit / position_size if position_size > 0 else 0.0
    return net_profit_pct >= MIN_PROFIT_AFTER_FEE, net_profit_pct


def fetch_klines_chunk(symbol: str, start_ms: int, end_ms: int, interval: str = "1h") -> List[Dict]:
    url = "https://api.hyperliquid.xyz/info"
    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": symbol,
            "interval": interval,
            "startTime": start_ms,
            "endTime": end_ms,
        },
    }
    resp = requests.post(url, json=payload, timeout=30)
    if resp.status_code != 200:
        return []
    raw = resp.json()
    return [
        {
            "timestamp": c["t"],
            "open": float(c["o"]),
            "high": float(c["h"]),
            "low": float(c["l"]),
            "close": float(c["c"]),
            "volume": float(c["v"]),
        }
        for c in raw
    ]


def fetch_historical_klines(symbol: str, start_date: datetime, end_date: datetime, interval: str = "1h") -> List[Dict]:
    start_ms = int(start_date.timestamp() * 1000)
    end_ms = int(end_date.timestamp() * 1000)
    chunk_hours = 4000
    chunk_ms = chunk_hours * 60 * 60 * 1000

    all_klines = []
    cur = start_ms

    while cur < end_ms:
        nxt = min(cur + chunk_ms, end_ms)
        chunk = fetch_klines_chunk(symbol, cur, nxt, interval)
        if not chunk:
            break
        all_klines.extend(chunk)
        if len(chunk) < 4000:
            break
        cur = chunk[-1]["timestamp"] + 3600 * 1000

    seen = set()
    out = []
    for k in sorted(all_klines, key=lambda x: x["timestamp"]):
        if k["timestamp"] not in seen:
            seen.add(k["timestamp"])
            out.append(k)
    return out


def max_drawdown(equity_curve: List[float]) -> float:
    peak = equity_curve[0] if equity_curve else 0.0
    mdd = 0.0
    for v in equity_curve:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak
            if dd > mdd:
                mdd = dd
    return mdd * 100.0


def run_backtest(
    klines: List[Dict],
    symbol: str = "BTC",
    cooldown_candles: int = DEFAULT_COOLDOWN_CANDLES,
    max_hold_candles: int = DEFAULT_MAX_HOLD_CANDLES,
    initial_capital: float = INITIAL_CAPITAL,
    allow_long: bool = True,
    allow_short: bool = True,
    params_override: Dict[str, float] = None,
) -> Dict:
    params = resolve_nfi_params(symbol)
    if params_override:
        params.update(params_override)
    warmup = int(max(params["ema_long"], params["volume_sma_period"], params["bb_period"]) + 5)
    if len(klines) < warmup + 1:
        return {"error": f"数据不足，至少需要 {warmup + 1} 根 K 线"}

    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    volumes = [k["volume"] for k in klines]

    ema_fast = ema(closes, int(params["ema_fast"]))
    ema_trend = ema(closes, int(params["ema_trend"]))
    ema_long = ema(closes, int(params["ema_long"]))
    rsi_fast = rsi_wilder(closes, int(params["rsi_fast"]))
    rsi_main = rsi_wilder(closes, int(params["rsi_main"]))
    atr_vals = atr_wilder(highs, lows, closes, int(params["atr_period"]))
    _, bb_upper, bb_lower = bollinger_bands(closes, int(params["bb_period"]), float(params["bb_stddev"]))
    volume_sma = sma(volumes, int(params["volume_sma_period"]))

    balance = initial_capital
    equity_curve = [balance]
    trades = []

    has_position = False
    position_side = "LONG"
    entry_price = 0.0
    position_usd = 0.0
    stop_loss = 0.0
    take_profit = 0.0
    entry_idx = -1
    cooldown_until = -1

    for i in range(warmup, len(klines)):
        k = klines[i]
        ts = k["timestamp"]
        h = k["high"]
        l = k["low"]
        c = k["close"]

        if has_position:
            exit_type = None
            exit_price = c

            if position_side == "LONG":
                if l <= stop_loss:
                    exit_type = "STOP_LOSS"
                    exit_price = stop_loss
                elif h >= take_profit:
                    exit_type = "TAKE_PROFIT"
                    exit_price = take_profit
                elif i - entry_idx >= max_hold_candles:
                    exit_type = "TIME_EXIT"
                    exit_price = c
            else:
                if h >= stop_loss:
                    exit_type = "STOP_LOSS"
                    exit_price = stop_loss
                elif l <= take_profit:
                    exit_type = "TAKE_PROFIT"
                    exit_price = take_profit
                elif i - entry_idx >= max_hold_candles:
                    exit_type = "TIME_EXIT"
                    exit_price = c

            if exit_type is not None:
                if position_side == "LONG":
                    pnl_pct = (exit_price - entry_price) / entry_price
                else:
                    pnl_pct = (entry_price - exit_price) / entry_price
                fee = position_usd * TAKER_FEE + position_usd * (1 + pnl_pct) * TAKER_FEE
                pnl = position_usd * pnl_pct - fee
                balance += pnl
                trades.append(
                    {
                        "side": position_side,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "pnl": pnl,
                        "balance": balance,
                        "entry_idx": entry_idx,
                        "exit_idx": i,
                        "exit": exit_type,
                        "timestamp": ts,
                    }
                )
                has_position = False
                if pnl < 0:
                    cooldown_until = i + cooldown_candles

        if (not has_position) and i >= cooldown_until:
            atr_now = atr_vals[i]
            if atr_now <= 0:
                equity_curve.append(balance)
                continue

            regime_ok = (
                ema_trend[i] > ema_long[i]
                and c > ema_long[i] * float(params["regime_price_floor"])
            )
            pullback_ok = (
                c <= bb_lower[i] * float(params["bb_touch_buffer"])
                or c <= ema_fast[i] * float(params["ema_pullback_buffer"])
            )
            rsi_ok = (
                rsi_fast[i] <= float(params["rsi_fast_buy"])
                and rsi_main[i] <= float(params["rsi_main_buy"])
            )
            volume_ok = volume_sma[i] > 0 and volumes[i] >= volume_sma[i] * float(params["min_volume_ratio"])
            not_breakdown = c >= ema_long[i] * (1.0 - float(params["max_breakdown_pct"]))
            stabilizing = closes[i] >= closes[i - 1] or rsi_fast[i] > rsi_fast[i - 1]

            long_ok = allow_long and regime_ok and pullback_ok and rsi_ok and volume_ok and not_breakdown and stabilizing

            regime_short = (
                ema_trend[i] < ema_long[i]
                and c < ema_long[i] * float(params["regime_price_ceiling"])
            )
            pullback_short = (
                c >= bb_upper[i] * float(params["bb_reject_buffer"])
                or c >= ema_fast[i] * float(params["ema_bounce_buffer"])
            )
            rsi_short = (
                rsi_fast[i] >= float(params["rsi_fast_sell"])
                and rsi_main[i] >= float(params["rsi_main_sell"])
            )
            not_breakout = c <= ema_long[i] * (1.0 + float(params["max_breakout_pct"]))
            stabilizing_short = closes[i] <= closes[i - 1] or rsi_fast[i] < rsi_fast[i - 1]
            short_ok = (
                allow_short
                and bool(params.get("enable_short", True))
                and regime_short
                and pullback_short
                and rsi_short
                and volume_ok
                and not_breakout
                and stabilizing_short
            )

            side = None
            if long_ok and short_ok:
                long_score = (
                    max(0.0, float(params["rsi_fast_buy"]) - rsi_fast[i])
                    + max(0.0, float(params["rsi_main_buy"]) - rsi_main[i])
                    + max(0.0, (bb_lower[i] - c) / c * 100)
                )
                short_score = (
                    max(0.0, rsi_fast[i] - float(params["rsi_fast_sell"]))
                    + max(0.0, rsi_main[i] - float(params["rsi_main_sell"]))
                    + max(0.0, (c - bb_upper[i]) / c * 100)
                )
                side = "SHORT" if short_score > long_score else "LONG"
            elif long_ok:
                side = "LONG"
            elif short_ok:
                side = "SHORT"

            if side is not None:
                if side == "LONG":
                    confidence = calc_confidence_long(
                        c,
                        bb_lower[i],
                        ema_trend[i],
                        ema_long[i],
                        rsi_fast[i],
                        rsi_main[i],
                        volumes[i],
                        volume_sma[i],
                    )
                else:
                    confidence = calc_confidence_short(
                        c,
                        bb_upper[i],
                        ema_trend[i],
                        ema_long[i],
                        rsi_fast[i],
                        rsi_main[i],
                        volumes[i],
                        volume_sma[i],
                    )
                raw_size = min(balance * DEFAULT_LEVERAGE, balance * MAX_LEVERAGE, MAX_POSITION_USD)
                position_usd = round(raw_size * confidence, 2)
                if position_usd >= MIN_ORDER_VALUE:
                    if side == "LONG":
                        stop_loss = c - atr_now * float(params["stop_loss_atr_mult"])
                        take_profit = c + atr_now * float(params["take_profit_atr_mult"])
                    else:
                        stop_loss = c + atr_now * float(params["stop_loss_atr_mult"])
                        take_profit = c - atr_now * float(params["take_profit_atr_mult"])
                    valid, _ = check_profit_after_fees(position_usd, c, take_profit)
                    if valid:
                        has_position = True
                        position_side = side
                        entry_price = c
                        entry_idx = i

        equity_curve.append(balance)

    if has_position:
        last_price = klines[-1]["close"]
        if position_side == "LONG":
            pnl_pct = (last_price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - last_price) / entry_price
        fee = position_usd * TAKER_FEE + position_usd * (1 + pnl_pct) * TAKER_FEE
        pnl = position_usd * pnl_pct - fee
        balance += pnl
        trades.append(
            {
                "side": position_side,
                "entry_price": entry_price,
                "exit_price": last_price,
                "pnl": pnl,
                "balance": balance,
                "entry_idx": entry_idx,
                "exit_idx": len(klines) - 1,
                "exit": "CLOSE_END",
                "timestamp": klines[-1]["timestamp"],
            }
        )
        equity_curve.append(balance)

    total_return_pct = (balance - initial_capital) / initial_capital * 100 if initial_capital > 0 else 0.0
    wins = sum(1 for t in trades if t["pnl"] > 0)
    losses = sum(1 for t in trades if t["pnl"] <= 0)

    return {
        "symbol": symbol,
        "params": params,
        "initial_capital": initial_capital,
        "final_balance": round(balance, 2),
        "total_return_pct": round(total_return_pct, 2),
        "total_trades": len(trades),
        "winning_trades": wins,
        "losing_trades": losses,
        "win_rate": round(wins / len(trades) * 100, 1) if trades else 0.0,
        "max_drawdown_pct": round(max_drawdown(equity_curve), 2),
        "trades": trades,
        "equity_curve": equity_curve,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC", help="回测币种，如 BTC / ETH")
    parser.add_argument("--start-date", default="2025-08-01", help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", default="2026-02-20", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--cooldown-candles", type=int, default=DEFAULT_COOLDOWN_CANDLES, help="亏损后冷却K线根数")
    parser.add_argument("--max-hold-candles", type=int, default=DEFAULT_MAX_HOLD_CANDLES, help="单笔最长持仓K线根数")
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL, help="初始资金 USDC")
    parser.add_argument("--long-only", action="store_true", help="仅做多（更接近原版 NFI spot 风格）")
    parser.add_argument("--trade-side", choices=["both", "long_only", "short_only"], default="both", help="交易方向模式")
    args = parser.parse_args()

    symbol = args.symbol.upper().strip()
    try:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        print("日期格式错误，请使用 YYYY-MM-DD")
        return

    params = resolve_nfi_params(symbol)
    if args.long_only and args.trade_side != "both":
        print("参数冲突: --long-only 与 --trade-side 不能同时指定不同方向")
        return
    trade_side = "long_only" if args.long_only else args.trade_side

    print("=" * 70)
    print(f"NFI 专用回测 | 标的: {symbol} | 周期: 1h")
    print(f"模式: {trade_side}")
    print(
        f"参数: EMA({int(params['ema_fast'])}/{int(params['ema_trend'])}/{int(params['ema_long'])}), "
        f"RSI阈值(多:{params['rsi_fast_buy']}/{params['rsi_main_buy']} "
        f"空:{params['rsi_fast_sell']}/{params['rsi_main_sell']}), "
        f"SL={params['stop_loss_atr_mult']}xATR TP={params['take_profit_atr_mult']}xATR"
    )
    print(
        f"风控: 冷却={args.cooldown_candles}根K, 最长持仓={args.max_hold_candles}根K, "
        f"初始资金={args.initial_capital} USDC"
    )
    print("=" * 70)

    print(f"获取数据 {start_date.date()} ~ {end_date.date()} ...")
    klines = fetch_historical_klines(symbol, start_date, end_date, "1h")
    if len(klines) < 210:
        print(f"错误: 仅获取到 {len(klines)} 根 K 线，至少需要 210 根")
        return
    print(f"获取到 {len(klines)} 根 K 线")

    result = run_backtest(
        klines,
        symbol=symbol,
        cooldown_candles=args.cooldown_candles,
        max_hold_candles=args.max_hold_candles,
        initial_capital=args.initial_capital,
        allow_long=trade_side != "short_only",
        allow_short=trade_side != "long_only",
    )
    if "error" in result:
        print(f"回测失败: {result['error']}")
        return

    print("\n" + "=" * 70)
    print("回测结果")
    print("=" * 70)
    print(f"初始资金:      ${result['initial_capital']:.2f}")
    print(f"最终余额:      ${result['final_balance']:.2f}")
    print(f"总收益率:      {result['total_return_pct']:+.2f}%")
    print(f"最大回撤:      {result['max_drawdown_pct']:.2f}%")
    print(f"总交易次数:    {result['total_trades']}")
    print(f"盈利次数:      {result['winning_trades']}")
    print(f"亏损次数:      {result['losing_trades']}")
    print(f"胜率:          {result['win_rate']:.1f}%")
    print("=" * 70)

    if result["trades"]:
        print("\n最近 5 笔交易:")
        for t in result["trades"][-5:]:
            dt = datetime.fromtimestamp(t["timestamp"] / 1000).strftime("%Y-%m-%d %H:%M")
            print(
                f"  {t.get('side', 'LONG')}-{t['exit']:<10} 入场${t['entry_price']:.2f} "
                f"出场${t['exit_price']:.2f} PnL=${t['pnl']:.2f} ({dt})"
            )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
策略回测验证程序
验证 auto_trader 交易策略在 BTC 历史数据上的表现

用法:
  python backtest.py                           # 默认: 胜率优先参数
  python backtest.py --profile baseline        # 原始参数
  python backtest.py --profile balanced        # 收益平衡参数 (旧 --optimized)
  python backtest.py --profile win_rate        # 胜率优先参数

注意: Hyperliquid API 仅保留约 5000 根 1h K 线（约 7 个月），
无法获取更早的数据。默认回测 2025-08-01 ~ 2026-02-20。
"""

import argparse
import requests
from datetime import datetime
from typing import List, Dict, Tuple

# ============== 配置 ==============
INITIAL_CAPITAL = 100.0  # USDC
TAKER_FEE = 0.00035
MIN_PROFIT_AFTER_FEE = 0.005
STOP_LOSS_ATR_MULT = 2   # 可改为 3 使用优化参数
TAKE_PROFIT_ATR_MULT = 3  # 可改为 4 使用优化参数
DEFAULT_LEVERAGE = 2
MAX_LEVERAGE = 3
MIN_ORDER_VALUE = 10
TRADE_COOLDOWN_CANDLES = 1  # 亏损后冷却 1 根 K 线（1 小时）

# 可切换策略档位
STRATEGY_PROFILES = {
    "baseline": {
        "description": "原始参数（历史基线）",
        "stop_loss_atr_mult": float(STOP_LOSS_ATR_MULT),
        "take_profit_atr_mult": float(TAKE_PROFIT_ATR_MULT),
        "loss_cooldown_candles": TRADE_COOLDOWN_CANDLES,
    },
    "balanced": {
        "description": "收益平衡参数（旧 --optimized）",
        "stop_loss_atr_mult": 3.0,
        "take_profit_atr_mult": 4.0,
        "loss_cooldown_candles": 1,
    },
    "win_rate": {
        "description": "胜率优先参数（更宽止损 + 更近止盈 + 亏损后冷却）",
        "stop_loss_atr_mult": 3.0,
        "take_profit_atr_mult": 2.5,
        "loss_cooldown_candles": 6,
    },
}
DEFAULT_PROFILE = "win_rate"
# 按币种微调（与 auto_trader 一致）
PROFILE_SYMBOL_OVERRIDES = {
    "win_rate": {
        "ETH": {
            "stop_loss_atr_mult": 3.5,
            "take_profit_atr_mult": 2.0,
        }
    }
}


def resolve_profile_params(profile: str, symbol: str) -> Dict:
    """基于 profile + symbol 解析最终参数"""
    params = dict(STRATEGY_PROFILES[profile])
    symbol_overrides = PROFILE_SYMBOL_OVERRIDES.get(profile, {})
    params.update(symbol_overrides.get(symbol.upper(), {}))
    return params


def ema(data: List[float], period: int) -> List[float]:
    """计算指数移动平均线"""
    multiplier = 2 / (period + 1)
    result = [data[0]]
    for price in data[1:]:
        result.append(price * multiplier + result[-1] * (1 - multiplier))
    return result


def atr_array(highs: List[float], lows: List[float], closes: List[float], period: int) -> List[float]:
    """计算每个时间点的 ATR"""
    result = [0.0] * len(closes)
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
        if i < period:
            result[i] = sum(
                max(highs[j] - lows[j], abs(highs[j] - closes[j - 1]), abs(lows[j] - closes[j - 1]))
                for j in range(1, i + 1)
            ) / i
        else:
            tr_list = []
            for j in range(i - period + 1, i + 1):
                tr_list.append(max(
                    highs[j] - lows[j],
                    abs(highs[j] - closes[j - 1]),
                    abs(lows[j] - closes[j - 1])
                ))
            result[i] = sum(tr_list) / period
    return result


def check_profit_after_fees(position_size: float, entry_price: float, take_profit: float) -> Tuple[bool, float]:
    """检查扣除手续费后净利润是否 >= 0.5%"""
    price_change_pct = abs(take_profit - entry_price) / entry_price
    gross_profit = position_size * price_change_pct
    open_fee = position_size * TAKER_FEE
    close_position_value = position_size * (1 + price_change_pct)
    close_fee = close_position_value * TAKER_FEE
    total_fees = open_fee + close_fee
    net_profit = gross_profit - total_fees
    net_profit_pct = net_profit / position_size if position_size > 0 else 0
    return net_profit_pct >= MIN_PROFIT_AFTER_FEE, net_profit_pct


def calc_confidence(closes: List[float], ema9: List[float], ema21: List[float], ema55: List[float], i: int) -> float:
    """计算信号信心度"""
    confidence = 0.5
    ma_spread = abs(ema9[i] - ema55[i]) / ema55[i] if ema55[i] else 0
    confidence += min(ma_spread * 10, 0.2)
    price_ma_distance = abs(closes[i] - ema21[i]) / ema21[i] if ema21[i] else 0
    confidence += min(price_ma_distance * 5, 0.1)
    if (ema9[i] > ema21[i] > ema55[i]) or (ema9[i] < ema21[i] < ema55[i]):
        confidence += 0.1
    return min(confidence, 1.0)


def fetch_klines_chunk(symbol: str, start_ms: int, end_ms: int, interval: str = "1h") -> List[Dict]:
    """获取一段 K 线数据（单次最多 5000 根）"""
    url = "https://api.hyperliquid.xyz/info"
    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": symbol,
            "interval": interval,
            "startTime": start_ms,
            "endTime": end_ms
        }
    }
    resp = requests.post(url, json=payload, timeout=30)
    if resp.status_code != 200:
        return []
    data = resp.json()
    return [
        {
            "timestamp": c["t"],
            "open": float(c["o"]),
            "high": float(c["h"]),
            "low": float(c["l"]),
            "close": float(c["c"]),
            "volume": float(c["v"])
        }
        for c in data
    ]


def fetch_historical_klines(symbol: str, start_date: datetime, end_date: datetime, interval: str = "1h") -> List[Dict]:
    """分块获取历史 K 线（Hyperliquid 单次最多 5000 根）"""
    start_ms = int(start_date.timestamp() * 1000)
    end_ms = int(end_date.timestamp() * 1000)
    chunk_hours = 4000  # 每次请求少于 5000
    chunk_ms = chunk_hours * 60 * 60 * 1000

    all_klines = []
    current_start = start_ms

    while current_start < end_ms:
        current_end = min(current_start + chunk_ms, end_ms)
        chunk = fetch_klines_chunk(symbol, current_start, current_end, interval)
        if not chunk:
            break
        all_klines.extend(chunk)
        if len(chunk) < 4000:
            break
        current_start = chunk[-1]["timestamp"] + 3600 * 1000  # 下一根 K 线

    # 去重并按时间排序
    seen = set()
    unique = []
    for k in sorted(all_klines, key=lambda x: x["timestamp"]):
        if k["timestamp"] not in seen:
            seen.add(k["timestamp"])
            unique.append(k)
    return unique


def run_backtest(
    klines: List[Dict],
    symbol: str = "BTC",
    profile: str = DEFAULT_PROFILE,
    use_optimized: bool = False
) -> Dict:
    """执行回测"""
    if len(klines) < 60:
        return {"error": "数据不足 60 根 K 线"}

    # 兼容旧参数：--optimized 等价于 balanced
    effective_profile = "balanced" if use_optimized else profile
    if effective_profile not in STRATEGY_PROFILES:
        valid = ", ".join(sorted(STRATEGY_PROFILES))
        return {"error": f"未知 profile: {effective_profile}，可选: {valid}"}
    params = resolve_profile_params(effective_profile, symbol)

    sl_mult = float(params["stop_loss_atr_mult"])
    tp_mult = float(params["take_profit_atr_mult"])
    loss_cooldown_candles = int(params["loss_cooldown_candles"])

    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]

    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    ema55 = ema(closes, 55)
    atr14 = atr_array(highs, lows, closes, 14)

    balance = INITIAL_CAPITAL
    position_side = None  # "LONG" | "SHORT" | None
    entry_price = 0.0
    position_usd = 0.0
    stop_loss = 0.0
    take_profit = 0.0
    cooldown_until = -1
    trades = []
    equity_curve = [INITIAL_CAPITAL]

    for i in range(60, len(klines)):
        k = klines[i]
        ts, o, h, l, c = k["timestamp"], k["open"], k["high"], k["low"], k["close"]
        current_atr = atr14[i]

        # 1. 检查持仓是否触发止损/止盈
        if position_side is not None:
            if position_side == "LONG":
                if l <= stop_loss:
                    # 止损
                    pnl_pct = (stop_loss - entry_price) / entry_price
                    fee = position_usd * TAKER_FEE * 2
                    pnl = position_usd * pnl_pct - fee
                    balance += pnl
                    trades.append({
                        "type": "LONG",
                        "exit": "STOP_LOSS",
                        "entry_price": entry_price,
                        "exit_price": stop_loss,
                        "pnl": pnl,
                        "balance": balance,
                        "timestamp": ts
                    })
                    position_side = None
                    cooldown_until = i + loss_cooldown_candles
                elif h >= take_profit:
                    # 止盈
                    pnl_pct = (take_profit - entry_price) / entry_price
                    fee = position_usd * TAKER_FEE + position_usd * (1 + pnl_pct) * TAKER_FEE
                    pnl = position_usd * pnl_pct - fee
                    balance += pnl
                    trades.append({
                        "type": "LONG",
                        "exit": "TAKE_PROFIT",
                        "entry_price": entry_price,
                        "exit_price": take_profit,
                        "pnl": pnl,
                        "balance": balance,
                        "timestamp": ts
                    })
                    position_side = None

            elif position_side == "SHORT":
                if h >= stop_loss:
                    # 止损（空头）
                    pnl_pct = (entry_price - stop_loss) / entry_price
                    fee = position_usd * TAKER_FEE * 2
                    pnl = position_usd * pnl_pct - fee
                    balance += pnl
                    trades.append({
                        "type": "SHORT",
                        "exit": "STOP_LOSS",
                        "entry_price": entry_price,
                        "exit_price": stop_loss,
                        "pnl": pnl,
                        "balance": balance,
                        "timestamp": ts
                    })
                    position_side = None
                    cooldown_until = i + loss_cooldown_candles
                elif l <= take_profit:
                    # 止盈（空头）
                    pnl_pct = (entry_price - take_profit) / entry_price
                    fee = position_usd * TAKER_FEE + position_usd * (1 + pnl_pct) * TAKER_FEE
                    pnl = position_usd * pnl_pct - fee
                    balance += pnl
                    trades.append({
                        "type": "SHORT",
                        "exit": "TAKE_PROFIT",
                        "entry_price": entry_price,
                        "exit_price": take_profit,
                        "pnl": pnl,
                        "balance": balance,
                        "timestamp": ts
                    })
                    position_side = None

        # 2. 若无持仓且不在冷却期，检查新信号
        if position_side is None and i >= cooldown_until:
            trend_up = ema9[i] > ema21[i] > ema55[i]
            trend_down = ema9[i] < ema21[i] < ema55[i]
            golden_cross = ema9[i - 1] <= ema21[i - 1] and ema9[i] > ema21[i]
            death_cross = ema9[i - 1] >= ema21[i - 1] and ema9[i] < ema21[i]

            if trend_up and golden_cross:
                position_usd = min(balance * DEFAULT_LEVERAGE, balance * MAX_LEVERAGE)
                position_usd = max(MIN_ORDER_VALUE, min(position_usd, balance * MAX_LEVERAGE))
                if position_usd >= MIN_ORDER_VALUE:
                    stop_loss = c - sl_mult * current_atr
                    take_profit = c + tp_mult * current_atr
                    valid, _ = check_profit_after_fees(position_usd, c, take_profit)
                    if valid:
                        position_side = "LONG"
                        entry_price = c

            elif trend_down and death_cross:
                position_usd = min(balance * DEFAULT_LEVERAGE, balance * MAX_LEVERAGE)
                position_usd = max(MIN_ORDER_VALUE, min(position_usd, balance * MAX_LEVERAGE))
                if position_usd >= MIN_ORDER_VALUE:
                    stop_loss = c + sl_mult * current_atr
                    take_profit = c - tp_mult * current_atr
                    valid, _ = check_profit_after_fees(position_usd, c, take_profit)
                    if valid:
                        position_side = "SHORT"
                        entry_price = c

        equity_curve.append(balance)

    # 若最后仍有持仓，按收盘价平仓
    if position_side is not None:
        last_c = klines[-1]["close"]
        if position_side == "LONG":
            pnl_pct = (last_c - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - last_c) / entry_price
        fee = position_usd * TAKER_FEE * 2
        pnl = position_usd * pnl_pct - fee
        balance += pnl
        trades.append({
            "type": position_side,
            "exit": "CLOSE_END",
            "entry_price": entry_price,
            "exit_price": last_c,
            "pnl": pnl,
            "balance": balance,
            "timestamp": klines[-1]["timestamp"]
        })

    total_return = (balance - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    wins = sum(1 for t in trades if t["pnl"] > 0)
    losses = sum(1 for t in trades if t["pnl"] <= 0)

    return {
        "symbol": symbol,
        "profile": effective_profile,
        "stop_loss_atr_mult": sl_mult,
        "take_profit_atr_mult": tp_mult,
        "loss_cooldown_candles": loss_cooldown_candles,
        "initial_capital": INITIAL_CAPITAL,
        "final_balance": round(balance, 2),
        "total_return_pct": round(total_return, 2),
        "total_trades": len(trades),
        "winning_trades": wins,
        "losing_trades": losses,
        "win_rate": round(wins / len(trades) * 100, 1) if trades else 0,
        "trades": trades,
        "equity_curve": equity_curve,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        choices=sorted(STRATEGY_PROFILES.keys()),
        default=DEFAULT_PROFILE,
        help="策略档位：baseline / balanced / win_rate",
    )
    parser.add_argument("--optimized", action="store_true", help="兼容旧参数，等价于 --profile balanced")
    parser.add_argument("--symbol", default="BTC", help="回测币种，如 BTC / ETH")
    parser.add_argument("--start-date", default="2025-08-01", help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", default="2026-02-20", help="结束日期 YYYY-MM-DD")
    args = parser.parse_args()

    symbol = args.symbol.upper().strip()
    selected_profile = "balanced" if args.optimized else args.profile
    if selected_profile not in STRATEGY_PROFILES:
        print(f"未知 profile: {selected_profile}")
        return
    profile_info = resolve_profile_params(selected_profile, symbol)

    try:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        print("日期格式错误，请使用 YYYY-MM-DD，例如 2025-08-01")
        return

    print("=" * 60)
    print(f"策略回测验证 - {symbol} 1小时K线")
    print(f"策略档位: {selected_profile} ({profile_info['description']})")
    print(
        f"参数: SL={profile_info['stop_loss_atr_mult']} ATR, "
        f"TP={profile_info['take_profit_atr_mult']} ATR, "
        f"亏损冷却={profile_info['loss_cooldown_candles']} 根K"
    )
    if args.optimized:
        print("(兼容模式: --optimized => --profile balanced)")
    print("=" * 60)

    print(f"\n正在获取 {start_date.date()} ~ {end_date.date()} 的历史数据...")
    klines = fetch_historical_klines(symbol, start_date, end_date, "1h")

    if len(klines) < 60:
        print(f"错误: 仅获取到 {len(klines)} 根 K 线，需要至少 60 根")
        return

    print(f"获取到 {len(klines)} 根 1 小时 K 线")

    result = run_backtest(klines, symbol=symbol, profile=selected_profile)

    if "error" in result:
        print(f"回测失败: {result['error']}")
        return

    print("\n" + "=" * 60)
    print("回测结果")
    print("=" * 60)
    print(f"初始资金:    ${result['initial_capital']:.2f} USDC")
    print(f"最终余额:    ${result['final_balance']:.2f} USDC")
    print(f"总收益率:    {result['total_return_pct']:+.2f}%")
    print(f"总交易次数: {result['total_trades']}")
    print(f"盈利次数:    {result['winning_trades']}")
    print(f"亏损次数:    {result['losing_trades']}")
    print(f"胜率:        {result['win_rate']}%")
    print("=" * 60)

    if result["total_return_pct"] > 0:
        print("\n结论: 策略在历史数据上盈利")
    else:
        print("\n结论: 策略在历史数据上亏损")

    if result["trades"]:
        print("\n最近 5 笔交易:")
        for t in result["trades"][-5:]:
            dt = datetime.fromtimestamp(t["timestamp"] / 1000).strftime("%Y-%m-%d %H:%M")
            print(f"  {t['type']} {t['exit']}: 入场${t['entry_price']:.0f} 出场${t['exit_price']:.0f} PnL=${t['pnl']:.2f} 余额=${t['balance']:.2f} ({dt})")


if __name__ == "__main__":
    main()

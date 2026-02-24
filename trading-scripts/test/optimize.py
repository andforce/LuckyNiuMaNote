#!/usr/bin/env python3
"""
策略参数优化 - 基于历史数据寻找提高胜率和收益的参数组合

用法: python optimize.py --symbol BTC --objective win_rate
"""

import argparse
from datetime import datetime
from typing import List, Dict, Tuple

# 复用 backtest 的核心逻辑
from backtest import (
    ema, atr_array, check_profit_after_fees,
    fetch_historical_klines, INITIAL_CAPITAL, TAKER_FEE, MIN_ORDER_VALUE
)


def run_backtest_with_params(
    klines: List[Dict],
    stop_loss_atr: float = 2.0,
    take_profit_atr: float = 3.0,
    use_price_filter: bool = False,      # 价格 > EMA21 (多) / 价格 < EMA21 (空)
    min_ema_spread_pct: float = 0.0,     # EMA9 与 EMA21 最小发散度 %
    long_only: bool = False,              # 只做多
    cooldown: int = 1,
) -> Dict:
    """带可调参数的回测"""
    if len(klines) < 60:
        return {"error": "数据不足"}

    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    ema55 = ema(closes, 55)
    atr14 = atr_array(highs, lows, closes, 14)

    balance = INITIAL_CAPITAL
    position_side = None
    entry_price = 0.0
    position_usd = 0.0
    stop_loss = 0.0
    take_profit = 0.0
    cooldown_until = -1
    trades = []

    for i in range(60, len(klines)):
        k = klines[i]
        h, l, c = k["high"], k["low"], k["close"]
        current_atr = atr14[i]

        # 检查持仓
        if position_side is not None:
            if position_side == "LONG":
                if l <= stop_loss:
                    pnl_pct = (stop_loss - entry_price) / entry_price
                    fee = position_usd * TAKER_FEE * 2
                    pnl = position_usd * pnl_pct - fee
                    balance += pnl
                    trades.append({"type": "LONG", "exit": "SL", "pnl": pnl})
                    position_side = None
                    cooldown_until = i + cooldown
                elif h >= take_profit:
                    pnl_pct = (take_profit - entry_price) / entry_price
                    fee = position_usd * TAKER_FEE + position_usd * (1 + pnl_pct) * TAKER_FEE
                    pnl = position_usd * pnl_pct - fee
                    balance += pnl
                    trades.append({"type": "LONG", "exit": "TP", "pnl": pnl})
                    position_side = None

            elif position_side == "SHORT":
                if h >= stop_loss:
                    pnl_pct = (entry_price - stop_loss) / entry_price
                    fee = position_usd * TAKER_FEE * 2
                    pnl = position_usd * pnl_pct - fee
                    balance += pnl
                    trades.append({"type": "SHORT", "exit": "SL", "pnl": pnl})
                    position_side = None
                    cooldown_until = i + cooldown
                elif l <= take_profit:
                    pnl_pct = (entry_price - take_profit) / entry_price
                    fee = position_usd * TAKER_FEE + position_usd * (1 + pnl_pct) * TAKER_FEE
                    pnl = position_usd * pnl_pct - fee
                    balance += pnl
                    trades.append({"type": "SHORT", "exit": "TP", "pnl": pnl})
                    position_side = None

        # 新信号
        if position_side is None and i >= cooldown_until:
            trend_up = ema9[i] > ema21[i] > ema55[i]
            trend_down = ema9[i] < ema21[i] < ema55[i]
            golden_cross = ema9[i - 1] <= ema21[i - 1] and ema9[i] > ema21[i]
            death_cross = ema9[i - 1] >= ema21[i - 1] and ema9[i] < ema21[i]

            # 均线发散过滤：EMA9 与 EMA21 需拉开一定距离
            ema_spread = abs(ema9[i] - ema21[i]) / ema21[i] if ema21[i] else 0
            spread_ok = ema_spread >= min_ema_spread_pct / 100

            if trend_up and golden_cross and spread_ok:
                price_ok = not use_price_filter or c > ema21[i]
                if price_ok:
                    position_usd = min(balance * 2, balance * 3)
                    position_usd = max(MIN_ORDER_VALUE, min(position_usd, balance * 3))
                    if position_usd >= MIN_ORDER_VALUE:
                        stop_loss = c - stop_loss_atr * current_atr
                        take_profit = c + take_profit_atr * current_atr
                        valid, _ = check_profit_after_fees(position_usd, c, take_profit)
                        if valid:
                            position_side = "LONG"
                            entry_price = c

            elif trend_down and death_cross and spread_ok and (not long_only):
                price_ok = not use_price_filter or c < ema21[i]
                if price_ok:
                    position_usd = min(balance * 2, balance * 3)
                    position_usd = max(MIN_ORDER_VALUE, min(position_usd, balance * 3))
                    if position_usd >= MIN_ORDER_VALUE:
                        stop_loss = c + stop_loss_atr * current_atr
                        take_profit = c - take_profit_atr * current_atr
                        valid, _ = check_profit_after_fees(position_usd, c, take_profit)
                        if valid:
                            position_side = "SHORT"
                            entry_price = c

    # 平仓
    if position_side is not None:
        last_c = klines[-1]["close"]
        pnl_pct = (last_c - entry_price) / entry_price if position_side == "LONG" else (entry_price - last_c) / entry_price
        pnl = position_usd * pnl_pct - position_usd * TAKER_FEE * 2
        balance += pnl
        trades.append({"type": position_side, "exit": "END", "pnl": pnl})

    wins = sum(1 for t in trades if t["pnl"] > 0)
    total_return = (balance - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    return {
        "final_balance": balance,
        "return_pct": total_return,
        "trades": len(trades),
        "wins": wins,
        "win_rate": wins / len(trades) * 100 if trades else 0,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="策略参数优化（胜率/收益）")
    parser.add_argument("--symbol", default="BTC", help="币种，例如 BTC / ETH")
    parser.add_argument("--start-date", default="2025-08-01", help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", default="2026-02-20", help="结束日期 YYYY-MM-DD")
    parser.add_argument(
        "--mode",
        choices=["single", "train_test", "walk_forward"],
        default="single",
        help="single=全样本扫描, train_test=训练/测试验证, walk_forward=滚动窗口验证",
    )
    parser.add_argument("--objective", choices=["win_rate", "return"], default="win_rate", help="推荐目标")
    parser.add_argument("--min-trades", type=int, default=20, help="最少交易数过滤，避免样本太小")
    parser.add_argument("--top", type=int, default=10, help="展示前 N 条配置")
    parser.add_argument("--train-ratio", type=float, default=0.7, help="train_test 模式下训练集占比 (0~1)")
    parser.add_argument("--train-end-date", default="", help="train_test 模式可选: 训练集结束日期 YYYY-MM-DD")
    parser.add_argument("--candidate-top", type=int, default=20, help="train_test 模式下从训练集保留前 N 组参数用于测试验证")
    parser.add_argument("--wf-train-days", type=int, default=90, help="walk_forward 模式训练窗口天数")
    parser.add_argument("--wf-test-days", type=int, default=21, help="walk_forward 模式测试窗口天数")
    parser.add_argument("--wf-step-days", type=int, default=21, help="walk_forward 模式滚动步长天数")
    parser.add_argument("--wf-min-windows", type=int, default=2, help="walk_forward 至少需要的窗口数量")
    return parser.parse_args()


def format_cfg(item: Dict) -> str:
    text = (
        f"SL={item['sl']} TP={item['tp']} "
        f"冷却={item['cooldown']}"
    )
    if item["price_filter"]:
        text += " +价格过滤"
    if item["ema_spread"] > 0:
        text += f" +发散{item['ema_spread']}%"
    if item["long_only"]:
        text += " 仅多"
    return text


def ranking_key(item: Dict, objective: str) -> Tuple[float, float]:
    if objective == "win_rate":
        return item["win_rate"], item["return_pct"]
    return item["return_pct"], item["win_rate"]


def generate_configs() -> List[Tuple[float, float, bool, float, bool, int]]:
    configs: List[Tuple[float, float, bool, float, bool, int]] = []
    for sl in [2.0, 2.5, 3.0, 3.5, 4.0]:
        for tp in [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]:
            for cd in [1, 2, 3, 4, 6, 8, 12]:
                configs.append((sl, tp, False, 0.0, False, cd))
    return configs


def scan_configs(
    klines: List[Dict],
    configs: List[Tuple[float, float, bool, float, bool, int]],
) -> List[Dict]:
    results: List[Dict] = []
    for sl, tp, pf, spread, lo, cd in configs:
        r = run_backtest_with_params(klines, sl, tp, pf, spread, lo, cd)
        if "error" in r:
            continue
        item = {
            "sl": sl,
            "tp": tp,
            "price_filter": pf,
            "ema_spread": spread,
            "long_only": lo,
            "cooldown": cd,
            "return_pct": r["return_pct"],
            "trades": r["trades"],
            "win_rate": r["win_rate"],
        }
        results.append(item)
    return results


def pick_stable_candidate(candidates: List[Dict], min_test_trades: int = 8) -> Dict:
    # 稳健优先：训练和测试都为正收益，其次最大化两者较小值
    valid = [c for c in candidates if c["test"]["trades"] >= min_test_trades]
    both_positive = [c for c in valid if c["train"]["return_pct"] > 0 and c["test"]["return_pct"] > 0]
    if both_positive:
        both_positive.sort(
            key=lambda c: (
                min(c["train"]["return_pct"], c["test"]["return_pct"]),
                c["test"]["win_rate"],
                -abs(c["train"]["win_rate"] - c["test"]["win_rate"]),
            ),
            reverse=True,
        )
        return both_positive[0]
    if valid:
        valid.sort(
            key=lambda c: (
                c["test"]["return_pct"],
                c["test"]["win_rate"],
                -abs(c["train"]["return_pct"] - c["test"]["return_pct"]),
            ),
            reverse=True,
        )
        return valid[0]
    return candidates[0]


def evaluate_on_test(top_candidates: List[Dict], test_klines: List[Dict]) -> List[Dict]:
    merged_candidates: List[Dict] = []
    for item in top_candidates:
        test_r = run_backtest_with_params(
            test_klines,
            stop_loss_atr=item["sl"],
            take_profit_atr=item["tp"],
            use_price_filter=item["price_filter"],
            min_ema_spread_pct=item["ema_spread"],
            long_only=item["long_only"],
            cooldown=item["cooldown"],
        )
        if "error" in test_r:
            continue
        merged_candidates.append({
            "config": item,
            "train": {
                "return_pct": item["return_pct"],
                "win_rate": item["win_rate"],
                "trades": item["trades"],
            },
            "test": test_r,
        })
    return merged_candidates


def split_walk_forward_windows(
    klines: List[Dict],
    train_bars: int,
    test_bars: int,
    step_bars: int,
) -> List[Dict]:
    windows: List[Dict] = []
    if train_bars <= 0 or test_bars <= 0 or step_bars <= 0:
        return windows

    start = 0
    window_id = 1
    total = len(klines)
    while start + train_bars + test_bars <= total:
        train_slice = klines[start:start + train_bars]
        test_slice = klines[start + train_bars:start + train_bars + test_bars]
        windows.append({
            "id": window_id,
            "train": train_slice,
            "test": test_slice,
        })
        window_id += 1
        start += step_bars
    return windows


def config_key(item: Dict) -> Tuple[float, float, bool, float, bool, int]:
    return (
        float(item["sl"]),
        float(item["tp"]),
        bool(item["price_filter"]),
        float(item["ema_spread"]),
        bool(item["long_only"]),
        int(item["cooldown"]),
    )


def main():
    args = parse_args()
    symbol = args.symbol.upper().strip()
    try:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        print("日期格式错误，请使用 YYYY-MM-DD，例如 2025-08-01")
        return

    print("=" * 70)
    print("策略参数优化 - 寻找提高胜率的参数组合")
    print(
        f"模式: {args.mode} | 目标: {args.objective} | "
        f"标的: {symbol} | 最少交易数: {args.min_trades}"
    )
    print("=" * 70)

    print(f"\n获取数据 {start_date.date()} ~ {end_date.date()}...")
    klines = fetch_historical_klines(symbol, start_date, end_date, "1h")
    if len(klines) < 60:
        print("数据不足")
        return
    print(f"获取到 {len(klines)} 根 K 线\n")

    configs = generate_configs()
    print(f"正在扫描 {len(configs)} 组参数...")

    if args.mode == "single":
        results = scan_configs(klines, configs)

        filtered = [r for r in results if r["trades"] >= args.min_trades]
        if not filtered:
            print(f"没有满足最少交易数 >= {args.min_trades} 的配置，请调小 --min-trades")
            return

        by_return = sorted(filtered, key=lambda x: (x["return_pct"], x["win_rate"]), reverse=True)
        by_win_rate = sorted(filtered, key=lambda x: (x["win_rate"], x["return_pct"]), reverse=True)

        print(f"满足交易数过滤的配置数: {len(filtered)}\n")
        print(f"{'Top配置（按收益）':<36} {'收益%':>8} {'交易':>6} {'胜率%':>8}")
        print("-" * 70)
        for item in by_return[:args.top]:
            print(f"{format_cfg(item):<36} {item['return_pct']:>+7.1f}% {item['trades']:>6} {item['win_rate']:>7.1f}%")

        print("\n" + f"{'Top配置（按胜率）':<36} {'收益%':>8} {'交易':>6} {'胜率%':>8}")
        print("-" * 70)
        for item in by_win_rate[:args.top]:
            print(f"{format_cfg(item):<36} {item['return_pct']:>+7.1f}% {item['trades']:>6} {item['win_rate']:>7.1f}%")

        best_return = by_return[0]
        best_wr = by_win_rate[0]
        best = best_wr if args.objective == "win_rate" else best_return

        print("\n" + "=" * 70)
        print(f"收益最佳: {format_cfg(best_return)}")
        print(f"  收益: {best_return['return_pct']:+.1f}% | 胜率: {best_return['win_rate']:.1f}% | 交易: {best_return['trades']}")
        print(f"胜率最佳: {format_cfg(best_wr)}")
        print(f"  收益: {best_wr['return_pct']:+.1f}% | 胜率: {best_wr['win_rate']:.1f}% | 交易: {best_wr['trades']}")

        print("\n推荐配置（按 objective）:")
        print(f"  {args.objective}: {format_cfg(best)}")
        print(
            f"  参数: stop_loss_atr={best['sl']}, "
            f"take_profit_atr={best['tp']}, cooldown={best['cooldown']}"
        )
    elif args.mode == "train_test":
        if not (0 < args.train_ratio < 1):
            print("--train-ratio 必须在 (0, 1) 之间")
            return

        train_end_ts = None
        if args.train_end_date:
            try:
                train_end = datetime.strptime(args.train_end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                train_end_ts = int(train_end.timestamp() * 1000)
            except ValueError:
                print("--train-end-date 日期格式错误，请使用 YYYY-MM-DD")
                return

        if train_end_ts is not None:
            train_klines = [k for k in klines if k["timestamp"] <= train_end_ts]
            test_klines = [k for k in klines if k["timestamp"] > train_end_ts]
        else:
            split_idx = int(len(klines) * args.train_ratio)
            train_klines = klines[:split_idx]
            test_klines = klines[split_idx:]

        if len(train_klines) < 60 or len(test_klines) < 60:
            print(
                "训练集或测试集数据不足。"
                f" train={len(train_klines)}, test={len(test_klines)}"
            )
            return

        train_start = datetime.fromtimestamp(train_klines[0]["timestamp"] / 1000)
        train_end = datetime.fromtimestamp(train_klines[-1]["timestamp"] / 1000)
        test_start = datetime.fromtimestamp(test_klines[0]["timestamp"] / 1000)
        test_end = datetime.fromtimestamp(test_klines[-1]["timestamp"] / 1000)

        print(
            f"训练集: {train_start.date()} ~ {train_end.date()} ({len(train_klines)} 根)\n"
            f"测试集: {test_start.date()} ~ {test_end.date()} ({len(test_klines)} 根)"
        )

        train_results = scan_configs(train_klines, configs)
        train_filtered = [r for r in train_results if r["trades"] >= args.min_trades]
        if not train_filtered:
            print(f"训练集没有满足最少交易数 >= {args.min_trades} 的配置，请调小 --min-trades")
            return

        train_sorted = sorted(train_filtered, key=lambda x: ranking_key(x, args.objective), reverse=True)
        top_candidates = train_sorted[:max(1, args.candidate_top)]

        merged_candidates = evaluate_on_test(top_candidates, test_klines)

        if not merged_candidates:
            print("候选参数在测试集上无有效结果")
            return

        train_best = merged_candidates[0]
        test_best = sorted(
            merged_candidates,
            key=lambda c: ranking_key(c["test"], args.objective),
            reverse=True,
        )[0]
        stable_best = pick_stable_candidate(merged_candidates, min_test_trades=max(8, args.min_trades // 2))

        print("\n" + "=" * 70)
        print(f"训练集最优（{args.objective}）: {format_cfg(train_best['config'])}")
        print(
            f"  训练集 -> 收益{train_best['train']['return_pct']:+.1f}% "
            f"胜率{train_best['train']['win_rate']:.1f}% 交易{train_best['train']['trades']}"
        )
        print(
            f"  测试集 -> 收益{train_best['test']['return_pct']:+.1f}% "
            f"胜率{train_best['test']['win_rate']:.1f}% 交易{train_best['test']['trades']}"
        )

        print("\n测试集最优（来自训练候选）:")
        print(f"  {format_cfg(test_best['config'])}")
        print(
            f"  训练集 -> 收益{test_best['train']['return_pct']:+.1f}% "
            f"胜率{test_best['train']['win_rate']:.1f}% 交易{test_best['train']['trades']}"
        )
        print(
            f"  测试集 -> 收益{test_best['test']['return_pct']:+.1f}% "
            f"胜率{test_best['test']['win_rate']:.1f}% 交易{test_best['test']['trades']}"
        )

        print("\n稳健推荐（训练/测试都尽量稳定）:")
        print(f"  {format_cfg(stable_best['config'])}")
        print(
            f"  训练集 -> 收益{stable_best['train']['return_pct']:+.1f}% "
            f"胜率{stable_best['train']['win_rate']:.1f}% 交易{stable_best['train']['trades']}"
        )
        print(
            f"  测试集 -> 收益{stable_best['test']['return_pct']:+.1f}% "
            f"胜率{stable_best['test']['win_rate']:.1f}% 交易{stable_best['test']['trades']}"
        )
        print(
            f"\n建议用于实盘参数: stop_loss_atr={stable_best['config']['sl']}, "
            f"take_profit_atr={stable_best['config']['tp']}, cooldown={stable_best['config']['cooldown']}"
        )
    else:
        train_bars = args.wf_train_days * 24
        test_bars = args.wf_test_days * 24
        step_bars = args.wf_step_days * 24
        if train_bars <= 0 or test_bars <= 0 or step_bars <= 0:
            print("walk_forward 窗口参数必须 > 0")
            return

        windows = split_walk_forward_windows(klines, train_bars, test_bars, step_bars)
        if len(windows) < args.wf_min_windows:
            print(
                f"可用窗口数不足: {len(windows)} < {args.wf_min_windows}。"
                "请缩短训练/测试窗口或缩短步长。"
            )
            return

        print(
            f"walk_forward 参数: 训练{args.wf_train_days}天, "
            f"测试{args.wf_test_days}天, 步长{args.wf_step_days}天, "
            f"窗口数{len(windows)}"
        )

        min_test_trades = max(4, args.min_trades // 3)
        window_results: List[Dict] = []
        candidate_pool: Dict[Tuple[float, float, bool, float, bool, int], Dict] = {}

        for window in windows:
            train_klines = window["train"]
            test_klines = window["test"]
            train_start = datetime.fromtimestamp(train_klines[0]["timestamp"] / 1000)
            train_end = datetime.fromtimestamp(train_klines[-1]["timestamp"] / 1000)
            test_start = datetime.fromtimestamp(test_klines[0]["timestamp"] / 1000)
            test_end = datetime.fromtimestamp(test_klines[-1]["timestamp"] / 1000)

            train_results = scan_configs(train_klines, configs)
            train_filtered = [r for r in train_results if r["trades"] >= args.min_trades]
            if not train_filtered:
                print(
                    f"窗口{window['id']} 跳过: 训练集交易不足 "
                    f"({train_start.date()}~{train_end.date()})"
                )
                continue

            train_sorted = sorted(train_filtered, key=lambda x: ranking_key(x, args.objective), reverse=True)
            top_candidates = train_sorted[:max(1, args.candidate_top)]
            for c in top_candidates:
                candidate_pool[config_key(c)] = c
            merged_candidates = evaluate_on_test(top_candidates, test_klines)
            if not merged_candidates:
                print(
                    f"窗口{window['id']} 跳过: 测试集无有效候选 "
                    f"({test_start.date()}~{test_end.date()})"
                )
                continue

            train_best = merged_candidates[0]
            test_best = sorted(
                merged_candidates,
                key=lambda c: ranking_key(c["test"], args.objective),
                reverse=True,
            )[0]
            stable_best = pick_stable_candidate(merged_candidates, min_test_trades=min_test_trades)
            window_results.append({
                "id": window["id"],
                "train_start": train_start,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
                "test_klines": test_klines,
                "train_best": train_best,
                "test_best": test_best,
                "stable_best": stable_best,
            })

        if len(window_results) < args.wf_min_windows:
            print(
                f"有效窗口数不足: {len(window_results)} < {args.wf_min_windows}。"
                "请放宽参数（如降低 min-trades/candidate-top）。"
            )
            return

        print("\n" + "=" * 70)
        print("Walk-Forward 每窗口结果（采用稳健推荐）")
        print(f"{'窗口':<6} {'训练区间':<24} {'测试区间':<24} {'配置':<22} {'测试收益':>8} {'测试胜率':>8}")
        print("-" * 70)
        for w in window_results:
            c = w["stable_best"]["config"]
            t = w["stable_best"]["test"]
            cfg = f"SL={c['sl']} TP={c['tp']} 冷却={c['cooldown']}"
            print(
                f"{w['id']:<6} "
                f"{str(w['train_start'].date())+'~'+str(w['train_end'].date()):<24} "
                f"{str(w['test_start'].date())+'~'+str(w['test_end'].date()):<24} "
                f"{cfg:<22} "
                f"{t['return_pct']:>+7.1f}% "
                f"{t['win_rate']:>7.1f}%"
            )

        aggregate: Dict[Tuple[float, float, bool, float, bool, int], Dict] = {}
        for w in window_results:
            item = w["stable_best"]["config"]
            key = config_key(item)
            test_r = w["stable_best"]["test"]
            train_r = w["stable_best"]["train"]
            if key not in aggregate:
                aggregate[key] = {
                    "config": item,
                    "count": 0,
                    "test_returns": [],
                    "test_win_rates": [],
                    "test_trades": [],
                    "positive_windows": 0,
                    "ret_gap_sum": 0.0,
                    "wr_gap_sum": 0.0,
                }
            s = aggregate[key]
            s["count"] += 1
            s["test_returns"].append(test_r["return_pct"])
            s["test_win_rates"].append(test_r["win_rate"])
            s["test_trades"].append(test_r["trades"])
            if test_r["return_pct"] > 0:
                s["positive_windows"] += 1
            s["ret_gap_sum"] += abs(train_r["return_pct"] - test_r["return_pct"])
            s["wr_gap_sum"] += abs(train_r["win_rate"] - test_r["win_rate"])

        summary_rows: List[Dict] = []
        for s in aggregate.values():
            count = s["count"]
            avg_ret = sum(s["test_returns"]) / count
            avg_wr = sum(s["test_win_rates"]) / count
            avg_trades = sum(s["test_trades"]) / count
            pos_rate = s["positive_windows"] / count if count else 0.0
            avg_ret_gap = s["ret_gap_sum"] / count
            avg_wr_gap = s["wr_gap_sum"] / count
            summary_rows.append({
                "config": s["config"],
                "count": count,
                "avg_test_return": avg_ret,
                "avg_test_win_rate": avg_wr,
                "avg_test_trades": avg_trades,
                "positive_rate": pos_rate,
                "avg_ret_gap": avg_ret_gap,
                "avg_wr_gap": avg_wr_gap,
            })

        if args.objective == "win_rate":
            summary_rows.sort(
                key=lambda r: (
                    r["count"],
                    r["positive_rate"],
                    r["avg_test_win_rate"],
                    r["avg_test_return"],
                    -r["avg_wr_gap"],
                ),
                reverse=True,
            )
        else:
            summary_rows.sort(
                key=lambda r: (
                    r["count"],
                    r["positive_rate"],
                    r["avg_test_return"],
                    r["avg_test_win_rate"],
                    -r["avg_ret_gap"],
                ),
                reverse=True,
            )

        final_best = summary_rows[0]
        final_source = "frequency"
        print("\n" + "=" * 70)
        print("Walk-Forward 汇总（按出现频率 + 稳定性）")
        print(f"{'配置':<26} {'命中窗数':>8} {'正收益窗%':>9} {'均测收益':>9} {'均测胜率':>9}")
        print("-" * 70)
        for row in summary_rows[:args.top]:
            print(
                f"{format_cfg(row['config']):<26} "
                f"{row['count']:>8} "
                f"{row['positive_rate']*100:>8.1f}% "
                f"{row['avg_test_return']:>+8.1f}% "
                f"{row['avg_test_win_rate']:>8.1f}%"
            )

        # 二次稳健校验：把候选参数放到全部窗口测试集上统一复核
        cross_rows: List[Dict] = []
        for c in candidate_pool.values():
            test_returns: List[float] = []
            test_wins: List[float] = []
            test_trades: List[float] = []
            for w in window_results:
                tr = run_backtest_with_params(
                    w["test_klines"],
                    stop_loss_atr=c["sl"],
                    take_profit_atr=c["tp"],
                    use_price_filter=c["price_filter"],
                    min_ema_spread_pct=c["ema_spread"],
                    long_only=c["long_only"],
                    cooldown=c["cooldown"],
                )
                if "error" in tr:
                    continue
                test_returns.append(tr["return_pct"])
                test_wins.append(tr["win_rate"])
                test_trades.append(tr["trades"])

            if len(test_returns) != len(window_results):
                continue
            pos_rate = sum(1 for r in test_returns if r > 0) / len(test_returns)
            cross_rows.append({
                "config": c,
                "count": len(window_results),
                "avg_test_return": sum(test_returns) / len(test_returns),
                "avg_test_win_rate": sum(test_wins) / len(test_wins),
                "avg_test_trades": sum(test_trades) / len(test_trades),
                "positive_rate": pos_rate,
                "worst_test_return": min(test_returns),
            })

        if not cross_rows:
            print("跨窗口复核失败，使用频次汇总结果作为最终推荐。")
        else:
            if args.objective == "win_rate":
                cross_rows.sort(
                    key=lambda r: (
                        r["positive_rate"],
                        r["avg_test_win_rate"],
                        r["avg_test_return"],
                        r["worst_test_return"],
                    ),
                    reverse=True,
                )
            else:
                cross_rows.sort(
                    key=lambda r: (
                        r["positive_rate"],
                        r["avg_test_return"],
                        r["avg_test_win_rate"],
                        r["worst_test_return"],
                    ),
                    reverse=True,
                )
            final_best = cross_rows[0]
            final_source = "cross_window"
            print("\n" + "=" * 70)
            print("跨窗口统一参数复核（同一参数跑完全部测试窗口）")
            print(f"{'配置':<26} {'正收益窗%':>9} {'均测收益':>9} {'均测胜率':>9} {'最差窗收益':>10}")
            print("-" * 70)
            for row in cross_rows[:args.top]:
                print(
                    f"{format_cfg(row['config']):<26} "
                    f"{row['positive_rate']*100:>8.1f}% "
                    f"{row['avg_test_return']:>+8.1f}% "
                    f"{row['avg_test_win_rate']:>8.1f}% "
                    f"{row['worst_test_return']:>+9.1f}%"
                )

        all_selected_test_returns = [w["stable_best"]["test"]["return_pct"] for w in window_results]
        all_selected_test_wr = [w["stable_best"]["test"]["win_rate"] for w in window_results]
        positive_windows = sum(1 for r in all_selected_test_returns if r > 0)
        print("\n最终稳健推荐:")
        print(f"  {format_cfg(final_best['config'])}")
        print(
            f"  推荐依据: 命中窗口{final_best['count']}个, "
            f"测试正收益窗口占比{final_best['positive_rate']*100:.1f}%"
        )
        if final_source == "cross_window":
            print("  结果来源: 跨窗口统一参数复核")
        else:
            print("  结果来源: 每窗口稳健参数频次汇总")
        print(
            f"  每窗口自适应参数均值 -> 测试收益{(sum(all_selected_test_returns)/len(all_selected_test_returns)):+.1f}%, "
            f"测试胜率{(sum(all_selected_test_wr)/len(all_selected_test_wr)):.1f}%, "
            f"正收益窗口{positive_windows}/{len(window_results)}"
        )
        print(
            f"  建议用于实盘参数: stop_loss_atr={final_best['config']['sl']}, "
            f"take_profit_atr={final_best['config']['tp']}, cooldown={final_best['config']['cooldown']}"
        )

    # 固定基准对比（全样本）
    baseline = run_backtest_with_params(klines, 2.0, 3.0, False, 0.0, False, 1)
    balanced = run_backtest_with_params(klines, 3.0, 4.0, False, 0.0, False, 1)
    win_rate = run_backtest_with_params(klines, 3.0, 2.5, False, 0.0, False, 6)
    print("\n基准对比:")
    print(f"  baseline  SL=2 TP=3 冷却1  -> 收益{baseline['return_pct']:+.1f}% 胜率{baseline['win_rate']:.1f}% 交易{baseline['trades']}")
    print(f"  balanced  SL=3 TP=4 冷却1  -> 收益{balanced['return_pct']:+.1f}% 胜率{balanced['win_rate']:.1f}% 交易{balanced['trades']}")
    print(f"  win_rate  SL=3 TP=2.5 冷却6 -> 收益{win_rate['return_pct']:+.1f}% 胜率{win_rate['win_rate']:.1f}% 交易{win_rate['trades']}")
    print("=" * 70)


if __name__ == "__main__":
    main()

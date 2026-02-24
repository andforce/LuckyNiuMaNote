#!/usr/bin/env python3
"""
NFI 专用参数优化（独立文件）

目标:
- 仅针对 short_only 模式做参数稳健优化
- 支持单次全样本扫描与 walk-forward 多窗口验证
- 优先输出“跨窗口统一参数复核”的稳健推荐

用法示例:
  python trading-scripts/test/optimize_nostalgia_for_infinity.py --symbol BTC
  python trading-scripts/test/optimize_nostalgia_for_infinity.py --symbol ETH --objective return
  python trading-scripts/test/optimize_nostalgia_for_infinity.py --mode single --symbol BTC
"""

import argparse
from datetime import datetime
from typing import Dict, List, Tuple

from backtest_nostalgia_for_infinity import (
    fetch_historical_klines,
    resolve_nfi_params,
    run_backtest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NFI short_only 参数优化")
    parser.add_argument("--symbol", default="BTC", help="币种，如 BTC / ETH")
    parser.add_argument("--start-date", default="2025-08-01", help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", default="2026-02-20", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--mode", choices=["single", "walk_forward"], default="walk_forward", help="优化模式")
    parser.add_argument("--objective", choices=["win_rate", "return"], default="win_rate", help="优化目标")
    parser.add_argument("--min-trades", type=int, default=3, help="最少交易数过滤（short_only 建议较小）")
    parser.add_argument("--top", type=int, default=10, help="展示前N条")
    parser.add_argument("--candidate-top", type=int, default=25, help="每窗口训练集保留前N个候选")
    parser.add_argument("--wf-train-days", type=int, default=90, help="walk-forward 训练窗口天数")
    parser.add_argument("--wf-test-days", type=int, default=21, help="walk-forward 测试窗口天数")
    parser.add_argument("--wf-step-days", type=int, default=21, help="walk-forward 步长天数")
    parser.add_argument("--wf-min-windows", type=int, default=3, help="walk-forward 最小有效窗口数")
    return parser.parse_args()


def generate_configs() -> List[Dict]:
    configs: List[Dict] = []
    for sl in [2.4, 2.8, 3.2, 3.6]:
        for tp in [2.8, 3.2, 3.6, 4.0, 4.4]:
            for rsi_fast_sell in [75.0, 79.0, 83.0]:
                for rsi_main_sell in [62.0, 66.0, 70.0]:
                    for cooldown in [4, 6, 8]:
                        for max_hold in [72, 96]:
                            if rsi_fast_sell <= rsi_main_sell:
                                continue
                            configs.append(
                                {
                                    "sl": sl,
                                    "tp": tp,
                                    "rsi_fast_sell": rsi_fast_sell,
                                    "rsi_main_sell": rsi_main_sell,
                                    "cooldown": cooldown,
                                    "max_hold": max_hold,
                                }
                            )
    return configs


def format_cfg(cfg: Dict) -> str:
    return (
        f"SL={cfg['sl']:.1f} TP={cfg['tp']:.1f} "
        f"RSI空={cfg['rsi_fast_sell']:.0f}/{cfg['rsi_main_sell']:.0f} "
        f"冷却={cfg['cooldown']} 持仓={cfg['max_hold']}"
    )


def cfg_key(cfg: Dict) -> Tuple[float, float, float, float, int, int]:
    return (
        float(cfg["sl"]),
        float(cfg["tp"]),
        float(cfg["rsi_fast_sell"]),
        float(cfg["rsi_main_sell"]),
        int(cfg["cooldown"]),
        int(cfg["max_hold"]),
    )


def ranking_key(item: Dict, objective: str) -> Tuple[float, float, float]:
    if objective == "win_rate":
        return item["win_rate"], item["return_pct"], -item["max_drawdown_pct"]
    return item["return_pct"], item["win_rate"], -item["max_drawdown_pct"]


def run_with_cfg(klines: List[Dict], symbol: str, cfg: Dict) -> Dict:
    overrides = {
        "enable_short": True,
        "stop_loss_atr_mult": float(cfg["sl"]),
        "take_profit_atr_mult": float(cfg["tp"]),
        "rsi_fast_sell": float(cfg["rsi_fast_sell"]),
        "rsi_main_sell": float(cfg["rsi_main_sell"]),
    }
    r = run_backtest(
        klines=klines,
        symbol=symbol,
        cooldown_candles=int(cfg["cooldown"]),
        max_hold_candles=int(cfg["max_hold"]),
        allow_long=False,
        allow_short=True,
        params_override=overrides,
    )
    if "error" in r:
        return r
    return {
        "return_pct": float(r["total_return_pct"]),
        "win_rate": float(r["win_rate"]),
        "trades": int(r["total_trades"]),
        "max_drawdown_pct": float(r["max_drawdown_pct"]),
        "final_balance": float(r["final_balance"]),
    }


def scan_configs(klines: List[Dict], symbol: str, configs: List[Dict]) -> List[Dict]:
    out: List[Dict] = []
    for cfg in configs:
        r = run_with_cfg(klines, symbol, cfg)
        if "error" in r:
            continue
        item = dict(cfg)
        item.update(r)
        out.append(item)
    return out


def evaluate_on_test(symbol: str, top_candidates: List[Dict], test_klines: List[Dict]) -> List[Dict]:
    merged: List[Dict] = []
    for c in top_candidates:
        test_r = run_with_cfg(test_klines, symbol, c)
        if "error" in test_r:
            continue
        merged.append(
            {
                "config": c,
                "train": {
                    "return_pct": c["return_pct"],
                    "win_rate": c["win_rate"],
                    "trades": c["trades"],
                    "max_drawdown_pct": c["max_drawdown_pct"],
                },
                "test": test_r,
            }
        )
    return merged


def pick_stable_candidate(candidates: List[Dict], objective: str, min_test_trades: int) -> Dict:
    valid = [c for c in candidates if c["test"]["trades"] >= min_test_trades]
    if not valid:
        valid = [c for c in candidates if c["test"]["trades"] >= 1]
    if not valid:
        valid = candidates

    both_positive = [c for c in valid if c["train"]["return_pct"] > 0 and c["test"]["return_pct"] > 0]
    scoped = both_positive if both_positive else valid

    if objective == "win_rate":
        scoped.sort(
            key=lambda c: (
                c["test"]["trades"],
                c["test"]["win_rate"],
                c["test"]["return_pct"],
                -abs(c["train"]["win_rate"] - c["test"]["win_rate"]),
                -c["test"]["max_drawdown_pct"],
            ),
            reverse=True,
        )
    else:
        scoped.sort(
            key=lambda c: (
                c["test"]["trades"],
                c["test"]["return_pct"],
                c["test"]["win_rate"],
                -abs(c["train"]["return_pct"] - c["test"]["return_pct"]),
                -c["test"]["max_drawdown_pct"],
            ),
            reverse=True,
        )
    return scoped[0]


def split_walk_forward_windows(
    klines: List[Dict],
    train_bars: int,
    test_bars: int,
    step_bars: int,
) -> List[Dict]:
    windows: List[Dict] = []
    if train_bars <= 0 or test_bars <= 0 or step_bars <= 0:
        return windows

    i = 0
    win_id = 1
    total = len(klines)
    while i + train_bars + test_bars <= total:
        windows.append(
            {
                "id": win_id,
                "train": klines[i : i + train_bars],
                "test": klines[i + train_bars : i + train_bars + test_bars],
            }
        )
        i += step_bars
        win_id += 1
    return windows


def print_single_mode(symbol: str, klines: List[Dict], configs: List[Dict], args: argparse.Namespace) -> None:
    results = scan_configs(klines, symbol, configs)
    filtered = [r for r in results if r["trades"] >= args.min_trades]
    if not filtered:
        print(f"没有满足最少交易数 >= {args.min_trades} 的配置")
        return

    by_obj = sorted(filtered, key=lambda r: ranking_key(r, args.objective), reverse=True)
    by_return = sorted(filtered, key=lambda r: (r["return_pct"], r["win_rate"]), reverse=True)
    by_win = sorted(filtered, key=lambda r: (r["win_rate"], r["return_pct"]), reverse=True)

    print(f"满足交易数过滤的配置数: {len(filtered)}")
    print("\nTop配置（按 objective）")
    print(f"{'配置':<52} {'收益%':>8} {'胜率%':>8} {'回撤%':>8} {'交易':>6}")
    print("-" * 92)
    for r in by_obj[: args.top]:
        print(
            f"{format_cfg(r):<52} {r['return_pct']:>+7.1f}% {r['win_rate']:>7.1f}% "
            f"{r['max_drawdown_pct']:>7.1f}% {r['trades']:>6}"
        )

    print("\n收益最佳:")
    print(
        f"  {format_cfg(by_return[0])}\n"
        f"  收益{by_return[0]['return_pct']:+.1f}% 胜率{by_return[0]['win_rate']:.1f}% "
        f"回撤{by_return[0]['max_drawdown_pct']:.1f}% 交易{by_return[0]['trades']}"
    )
    print("胜率最佳:")
    print(
        f"  {format_cfg(by_win[0])}\n"
        f"  收益{by_win[0]['return_pct']:+.1f}% 胜率{by_win[0]['win_rate']:.1f}% "
        f"回撤{by_win[0]['max_drawdown_pct']:.1f}% 交易{by_win[0]['trades']}"
    )


def print_walk_forward_mode(symbol: str, klines: List[Dict], configs: List[Dict], args: argparse.Namespace) -> None:
    train_bars = args.wf_train_days * 24
    test_bars = args.wf_test_days * 24
    step_bars = args.wf_step_days * 24
    windows = split_walk_forward_windows(klines, train_bars, test_bars, step_bars)
    if len(windows) < args.wf_min_windows:
        print(f"可用窗口数不足: {len(windows)} < {args.wf_min_windows}")
        return

    print(
        f"walk_forward 参数: 训练{args.wf_train_days}天, 测试{args.wf_test_days}天, "
        f"步长{args.wf_step_days}天, 窗口数{len(windows)}"
    )

    min_test_trades = max(1, args.min_trades // 2)
    window_results: List[Dict] = []
    candidate_pool: Dict[Tuple[float, float, float, float, int, int], Dict] = {}
    base = resolve_nfi_params(symbol)
    baseline_cfg = {
        "sl": float(base["stop_loss_atr_mult"]),
        "tp": float(base["take_profit_atr_mult"]),
        "rsi_fast_sell": float(base["rsi_fast_sell"]),
        "rsi_main_sell": float(base["rsi_main_sell"]),
        "cooldown": 6,
        "max_hold": 72,
    }
    candidate_pool[cfg_key(baseline_cfg)] = baseline_cfg

    for w in windows:
        train_klines = w["train"]
        test_klines = w["test"]
        train_results = scan_configs(train_klines, symbol, configs)
        train_filtered = [r for r in train_results if r["trades"] >= args.min_trades]
        if not train_filtered:
            continue

        train_sorted = sorted(train_filtered, key=lambda r: ranking_key(r, args.objective), reverse=True)
        top_candidates = train_sorted[: max(1, args.candidate_top)]
        for c in top_candidates:
            candidate_pool[cfg_key(c)] = c

        merged = evaluate_on_test(symbol, top_candidates, test_klines)
        if not merged:
            continue

        stable_best = pick_stable_candidate(merged, args.objective, min_test_trades=min_test_trades)
        train_start = datetime.fromtimestamp(train_klines[0]["timestamp"] / 1000)
        train_end = datetime.fromtimestamp(train_klines[-1]["timestamp"] / 1000)
        test_start = datetime.fromtimestamp(test_klines[0]["timestamp"] / 1000)
        test_end = datetime.fromtimestamp(test_klines[-1]["timestamp"] / 1000)
        window_results.append(
            {
                "id": w["id"],
                "train_start": train_start,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
                "test_klines": test_klines,
                "stable_best": stable_best,
            }
        )

    if len(window_results) < args.wf_min_windows:
        print(f"有效窗口数不足: {len(window_results)} < {args.wf_min_windows}")
        return

    print("\n" + "=" * 100)
    print("Walk-Forward 每窗口结果（short_only, 稳健候选）")
    print(f"{'窗口':<6} {'训练区间':<24} {'测试区间':<24} {'配置':<36} {'测试收益':>8} {'测试胜率':>8}")
    print("-" * 100)
    for w in window_results:
        c = w["stable_best"]["config"]
        t = w["stable_best"]["test"]
        short_cfg = f"SL={c['sl']:.1f} TP={c['tp']:.1f} RSI={c['rsi_fast_sell']:.0f}/{c['rsi_main_sell']:.0f} CD={c['cooldown']}"
        print(
            f"{w['id']:<6} "
            f"{str(w['train_start'].date())+'~'+str(w['train_end'].date()):<24} "
            f"{str(w['test_start'].date())+'~'+str(w['test_end'].date()):<24} "
            f"{short_cfg:<36} "
            f"{t['return_pct']:>+7.1f}% "
            f"{t['win_rate']:>7.1f}%"
        )

    aggregate: Dict[Tuple[float, float, float, float, int, int], Dict] = {}
    for w in window_results:
        c = w["stable_best"]["config"]
        t = w["stable_best"]["test"]
        k = cfg_key(c)
        if k not in aggregate:
            aggregate[k] = {
                "config": c,
                "count": 0,
                "test_returns": [],
                "test_win_rates": [],
                "test_dds": [],
                "test_trades": [],
                "positive_windows": 0,
            }
        s = aggregate[k]
        s["count"] += 1
        s["test_returns"].append(t["return_pct"])
        s["test_win_rates"].append(t["win_rate"])
        s["test_dds"].append(t["max_drawdown_pct"])
        s["test_trades"].append(t["trades"])
        if t["return_pct"] > 0:
            s["positive_windows"] += 1

    summary_rows: List[Dict] = []
    for s in aggregate.values():
        count = s["count"]
        summary_rows.append(
            {
                "config": s["config"],
                "count": count,
                "avg_test_return": sum(s["test_returns"]) / count,
                "avg_test_win_rate": sum(s["test_win_rates"]) / count,
                "avg_test_dd": sum(s["test_dds"]) / count,
                "avg_test_trades": sum(s["test_trades"]) / count,
                "positive_rate": s["positive_windows"] / count,
            }
        )

    if args.objective == "win_rate":
        summary_rows.sort(
            key=lambda r: (
                r["count"],
                r["avg_test_trades"],
                r["positive_rate"],
                r["avg_test_win_rate"],
                r["avg_test_return"],
                -r["avg_test_dd"],
            ),
            reverse=True,
        )
    else:
        summary_rows.sort(
            key=lambda r: (
                r["count"],
                r["avg_test_return"],
                r["positive_rate"],
                r["avg_test_trades"],
                r["avg_test_win_rate"],
                -r["avg_test_dd"],
            ),
            reverse=True,
        )

    print("\n" + "=" * 100)
    print("Walk-Forward 汇总（按命中频率 + 稳定性）")
    print(f"{'配置':<52} {'命中窗数':>8} {'正收益窗%':>10} {'均测收益':>9} {'均测胜率':>9} {'均测回撤':>9} {'均测交易':>9}")
    print("-" * 100)
    for row in summary_rows[: args.top]:
        print(
            f"{format_cfg(row['config']):<52} "
            f"{row['count']:>8} "
            f"{row['positive_rate']*100:>9.1f}% "
            f"{row['avg_test_return']:>+8.1f}% "
            f"{row['avg_test_win_rate']:>8.1f}% "
            f"{row['avg_test_dd']:>8.1f}% "
            f"{row['avg_test_trades']:>8.1f}"
        )

    baseline_test_returns: List[float] = []
    baseline_test_wins: List[float] = []
    baseline_test_dds: List[float] = []
    baseline_test_trades: List[float] = []
    for w in window_results:
        br = run_with_cfg(w["test_klines"], symbol, baseline_cfg)
        if "error" in br:
            continue
        baseline_test_returns.append(br["return_pct"])
        baseline_test_wins.append(br["win_rate"])
        baseline_test_dds.append(br["max_drawdown_pct"])
        baseline_test_trades.append(br["trades"])

    baseline_window_row = None
    if len(baseline_test_returns) == len(window_results):
        baseline_window_row = {
            "config": baseline_cfg,
            "count": len(window_results),
            "positive_rate": sum(1 for x in baseline_test_returns if x > 0) / len(baseline_test_returns),
            "avg_test_return": sum(baseline_test_returns) / len(baseline_test_returns),
            "avg_test_win_rate": sum(baseline_test_wins) / len(baseline_test_wins),
            "avg_test_dd": sum(baseline_test_dds) / len(baseline_test_dds),
            "avg_test_trades": sum(baseline_test_trades) / len(baseline_test_trades),
            "worst_test_return": min(baseline_test_returns),
        }

    cross_rows: List[Dict] = []
    for c in candidate_pool.values():
        test_returns: List[float] = []
        test_wins: List[float] = []
        test_dds: List[float] = []
        test_trades: List[float] = []
        for w in window_results:
            r = run_with_cfg(w["test_klines"], symbol, c)
            if "error" in r:
                break
            test_returns.append(r["return_pct"])
            test_wins.append(r["win_rate"])
            test_dds.append(r["max_drawdown_pct"])
            test_trades.append(r["trades"])
        if len(test_returns) != len(window_results):
            continue
        avg_test_trades = sum(test_trades) / len(test_trades)
        if avg_test_trades < 0.25:
            continue
        cross_rows.append(
            {
                "config": c,
                "count": len(window_results),
                "positive_rate": sum(1 for x in test_returns if x > 0) / len(test_returns),
                "avg_test_return": sum(test_returns) / len(test_returns),
                "avg_test_win_rate": sum(test_wins) / len(test_wins),
                "avg_test_dd": sum(test_dds) / len(test_dds),
                "avg_test_trades": avg_test_trades,
                "worst_test_return": min(test_returns),
            }
        )

    final_best = summary_rows[0]
    final_source = "frequency"
    baseline_key = cfg_key(baseline_cfg)
    baseline_row = None
    if cross_rows:
        if args.objective == "win_rate":
            cross_rows.sort(
                key=lambda r: (
                    r["avg_test_trades"],
                    r["positive_rate"],
                    r["avg_test_win_rate"],
                    r["avg_test_return"],
                    r["worst_test_return"],
                    -r["avg_test_dd"],
                ),
                reverse=True,
            )
        else:
            cross_rows.sort(
                key=lambda r: (
                    r["avg_test_return"],
                    r["positive_rate"],
                    r["avg_test_trades"],
                    r["avg_test_win_rate"],
                    r["worst_test_return"],
                    -r["avg_test_dd"],
                ),
                reverse=True,
            )
        final_best = cross_rows[0]
        final_source = "cross_window"
        for row in cross_rows:
            if cfg_key(row["config"]) == baseline_key:
                baseline_row = row
                break

        print("\n" + "=" * 100)
        print("跨窗口统一参数复核（同一参数跑完全部测试窗口）")
        print(f"{'配置':<52} {'正收益窗%':>10} {'均测收益':>9} {'均测胜率':>9} {'均测回撤':>9} {'均测交易':>9} {'最差窗收益':>10}")
        print("-" * 100)
        for row in cross_rows[: args.top]:
            print(
                f"{format_cfg(row['config']):<52} "
                f"{row['positive_rate']*100:>9.1f}% "
                f"{row['avg_test_return']:>+8.1f}% "
                f"{row['avg_test_win_rate']:>8.1f}% "
                f"{row['avg_test_dd']:>8.1f}% "
                f"{row['avg_test_trades']:>8.1f} "
                f"{row['worst_test_return']:>+9.1f}%"
            )

    if baseline_row is None and baseline_window_row is not None:
        baseline_row = baseline_window_row

    if baseline_row is not None:
        if args.objective == "win_rate":
            baseline_better = (
                baseline_row["positive_rate"] >= final_best["positive_rate"]
                and baseline_row["avg_test_win_rate"] >= final_best["avg_test_win_rate"]
                and baseline_row["avg_test_return"] >= final_best["avg_test_return"]
            )
        else:
            baseline_better = (
                baseline_row["positive_rate"] >= final_best["positive_rate"]
                and baseline_row["avg_test_return"] >= final_best["avg_test_return"]
                and baseline_row["avg_test_win_rate"] >= final_best["avg_test_win_rate"]
            )
        if baseline_better:
            final_best = baseline_row
            final_source = "baseline_guard"

    print("\n最终稳健推荐:")
    print(f"  {format_cfg(final_best['config'])}")
    if final_source == "cross_window":
        print("  结果来源: 跨窗口统一参数复核")
    elif final_source == "baseline_guard":
        print("  结果来源: baseline 保底（跨窗表现不劣于候选）")
    else:
        print("  结果来源: 每窗口稳健参数频次汇总")
    print(
        f"  命中窗口: {final_best['count']} | "
        f"正收益窗口占比: {final_best['positive_rate']*100:.1f}% | "
        f"均测收益: {final_best['avg_test_return']:+.1f}% | "
        f"均测胜率: {final_best['avg_test_win_rate']:.1f}% | "
        f"均测回撤: {final_best['avg_test_dd']:.1f}% | "
        f"均测交易: {final_best['avg_test_trades']:.1f}"
    )
    print(
        "  建议实盘覆盖参数: "
        f"stop_loss_atr_mult={final_best['config']['sl']}, "
        f"take_profit_atr_mult={final_best['config']['tp']}, "
        f"rsi_fast_sell={final_best['config']['rsi_fast_sell']}, "
        f"rsi_main_sell={final_best['config']['rsi_main_sell']}, "
        f"cooldown={final_best['config']['cooldown']}, "
        f"max_hold={final_best['config']['max_hold']}"
    )


def main() -> None:
    args = parse_args()
    symbol = args.symbol.upper().strip()
    try:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        print("日期格式错误，请使用 YYYY-MM-DD")
        return

    print("=" * 100)
    print("NFI 参数优化（short_only）")
    print(
        f"模式: {args.mode} | 目标: {args.objective} | "
        f"标的: {symbol} | 最少交易数: {args.min_trades}"
    )
    print("=" * 100)

    print(f"\n获取数据 {start_date.date()} ~ {end_date.date()} ...")
    klines = fetch_historical_klines(symbol, start_date, end_date, "1h")
    if len(klines) < 260:
        print(f"数据不足，仅 {len(klines)} 根 K 线")
        return
    print(f"获取到 {len(klines)} 根 K 线")

    base = resolve_nfi_params(symbol)
    print(
        f"当前NFI基线(空头): RSI={base['rsi_fast_sell']}/{base['rsi_main_sell']} "
        f"SL={base['stop_loss_atr_mult']} TP={base['take_profit_atr_mult']}"
    )

    configs = generate_configs()
    print(f"参数组合数量: {len(configs)}")

    if args.mode == "single":
        print_single_mode(symbol, klines, configs, args)
    else:
        print_walk_forward_mode(symbol, klines, configs, args)

    baseline_cfg = {
        "sl": float(base["stop_loss_atr_mult"]),
        "tp": float(base["take_profit_atr_mult"]),
        "rsi_fast_sell": float(base["rsi_fast_sell"]),
        "rsi_main_sell": float(base["rsi_main_sell"]),
        "cooldown": 6,
        "max_hold": 72,
    }
    baseline = run_with_cfg(klines, symbol, baseline_cfg)
    print("\n基准对比（short_only 默认参数）:")
    print(
        f"  {format_cfg(baseline_cfg)} -> 收益{baseline['return_pct']:+.1f}% "
        f"胜率{baseline['win_rate']:.1f}% 回撤{baseline['max_drawdown_pct']:.1f}% "
        f"交易{baseline['trades']}"
    )
    print("=" * 100)


if __name__ == "__main__":
    main()

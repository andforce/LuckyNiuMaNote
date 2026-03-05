#!/usr/bin/env python3
"""
调试脚本：查询 Hyperliquid 账户余额与持仓信息
"""

import json
import sys
from pathlib import Path

import requests
from hyperliquid.info import Info
from hyperliquid.utils import constants

HL_API = "https://api.hyperliquid.xyz/info"


def load_config():
    config_path = Path(__file__).resolve().parents[1] / "config" / ".hl_config"
    if not config_path.exists():
        print(f"配置文件不存在: {config_path}")
        sys.exit(1)
    cfg = {}
    with open(config_path, 'r') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                cfg[key] = value
    return cfg


def get_spot_balances(wallet):
    """从 spotClearinghouseState 获取现货余额"""
    resp = requests.post(HL_API, json={"type": "spotClearinghouseState", "user": wallet}, timeout=10)
    data = resp.json()
    balances = {}
    for b in data.get("balances", []):
        total = float(b.get("total", 0))
        if total != 0 or b["coin"] == "USDC":
            balances[b["coin"]] = {
                "total": total,
                "hold": float(b.get("hold", 0)),
            }
    return balances


def main():
    cfg = load_config()
    wallet = cfg["MAIN_WALLET"]

    info = Info(constants.MAINNET_API_URL, skip_ws=True)
    state = info.user_state(wallet)
    mids = info.all_mids()
    spot = get_spot_balances(wallet)

    usdc = spot.get("USDC", {"total": 0, "hold": 0})
    print("=" * 60)
    print("  账户余额")
    print("=" * 60)
    print(f"  {'币种':<8} {'总余额':>18} {'可用余额':>18}")
    print(f"  {'─' * 8} {'─' * 18} {'─' * 18}")
    print(f"  {'USDC':<8} {usdc['total']:>18,.8f} {usdc['total'] - usdc['hold']:>18,.8f}")
    print()

    positions = state.get("assetPositions", [])
    active = [p for p in positions if float(p["position"]["szi"]) != 0]

    if not active:
        print("  无持仓")
        return

    print("=" * 60)
    print("  持仓信息")
    print("=" * 60)

    for item in active:
        p = item["position"]
        coin = p["coin"]
        size = float(p["szi"])
        leverage = p.get("leverage", {})
        lev_val = leverage.get("value", "")
        entry_px = float(p["entryPx"])
        pos_value = float(p.get("positionValue", 0))
        mark_px = float(mids.get(coin, 0))
        roe = float(p.get("returnOnEquity", 0))
        pnl = float(p.get("unrealizedPnl", 0))
        margin_used = float(p.get("marginUsed", 0))
        margin_type = leverage.get("type", "cross").capitalize()
        cum_funding = float(p.get("cumFunding", {}).get("sinceOpen", 0))
        direction = "LONG" if size > 0 else "SHORT"

        print(f"  ── {coin} {lev_val}x ({direction}) ──")
        print(f"  {'数量':<12} {abs(size):>14} {coin}")
        print(f"  {'仓位价值':<10} {pos_value:>14,.2f} USDC")
        print(f"  {'开仓价格':<10} {entry_px:>14,.1f}")
        print(f"  {'标记价格':<10} {mark_px:>14,.1f}")
        print(f"  {'盈亏(ROE)':<8} {pnl:>+10,.2f}  ({roe * 100:+.1f}%)")
        print(f"  {'保证金':<10} {margin_used:>14,.2f} ({margin_type})")
        print(f"  {'资金费':<10} {cum_funding:>+14,.2f}")
        print()


if __name__ == "__main__":
    main()

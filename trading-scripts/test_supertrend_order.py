#!/usr/bin/env python3
"""
测试SuperTrend机器人的实际下单撤单能力
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

def load_config():
    config_path = Path(__file__).parent / "config" / ".hl_config"
    config = {}
    with open(config_path, 'r') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                config[key] = value
    return config

hl_config = load_config()
CONFIG = {
    "main_wallet": hl_config.get("MAIN_WALLET", ""),
    "api_private_key": hl_config.get("API_PRIVATE_KEY", ""),
}

def test_order_cancel():
    print("=" * 60)
    print("SuperTrend 机器人下单/撤单能力测试")
    print("=" * 60)
    
    info = Info(constants.MAINNET_API_URL, skip_ws=True)
    account = Account.from_key(CONFIG["api_private_key"])
    exchange = Exchange(
        account,
        constants.MAINNET_API_URL,
        account_address=CONFIG["main_wallet"],
    )
    
    symbol = "BTC"
    mids = info.all_mids()
    current_price = float(mids.get("BTC", 73000))
    # 高价卖单，保证不成交
    test_price = int(current_price * 2.1)
    test_price = round(test_price / 10) * 10
    size = 0.0002
    
    print(f"\n1. 准备下单:")
    print(f"   币种: {symbol}")
    print(f"   当前市价: ${current_price}")
    print(f"   测试价格: ${test_price}")
    print(f"   数量: {size}")
    
    try:
        print(f"\n2. 正在下单...")
        result = exchange.order(
            symbol, False, size, test_price,
            {"limit": {"tif": "Gtc"}},
            reduce_only=False
        )
        
        print(f"   下单结果: {result}")
        
        order_id = None
        if result.get("status") == "ok":
            statuses = result.get("response", {}).get("data", {}).get("statuses", [])
            if statuses and "resting" in statuses[0]:
                order_id = statuses[0]["resting"].get("oid")
                print(f"   ✅ 下单成功，订单ID: {order_id}")
            elif statuses and "error" in statuses[0]:
                print(f"   ❌ 下单被拒: {statuses[0]['error']}")
                return
        
        if order_id:
            print(f"\n3. 正在撤单...")
            cancel_result = exchange.cancel(symbol, order_id)
            print(f"   撤单结果: {cancel_result}")
            
            if cancel_result.get("status") == "ok":
                print(f"   ✅ 撤单成功")
            else:
                print(f"   ❌ 撤单失败")
        
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    test_order_cancel()

#!/usr/bin/env python3
"""
测试NFI机器人的实际下单撤单能力
用离谱的高价卖单测试（保证不成交）
"""

import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

# 读取配置文件
def load_config():
    config_path = Path(__file__).parent / "config" / ".hl_config"
    config = {}
    with open(config_path, 'r') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                config[key] = value
    return config

# 加载配置
hl_config = load_config()

# 配置
CONFIG = {
    "main_wallet": hl_config.get("MAIN_WALLET", ""),
    "api_private_key": hl_config.get("API_PRIVATE_KEY", ""),
}

def test_order_cancel():
    """测试下单和撤单"""
    print("=" * 60)
    print("NFI 机器人下单/撤单能力测试")
    print("=" * 60)
    
    # 初始化连接
    info = Info(constants.MAINNET_API_URL, skip_ws=True)
    account = Account.from_key(CONFIG["api_private_key"])
    exchange = Exchange(
        account,
        constants.MAINNET_API_URL,
        account_address=CONFIG["main_wallet"],
    )
    
    symbol = "BTC"
    # 获取当前价格
    mids = info.all_mids()
    current_price = float(mids.get("BTC", 73000))
    # 价格高110%（卖单，保证不成交）
    # BTC szDecimals is 5, but price tick is 0.1
    # Use integer price to avoid tick size issues
    ridiculous_price = int(current_price * 2.1)
    # 确保是0.1的倍数
    ridiculous_price = round(ridiculous_price / 10) * 10
    # 最小数量
    size = 0.0002
    
    print(f"\n1. 准备下单:")
    print(f"   币种: {symbol}")
    print(f"   当前市价: ${current_price}")
    print(f"   测试价格: ${ridiculous_price} (高于市价110%，卖单保证不成交)")
    print(f"   数量: {size}")
    print(f"   订单价值: ${round(size * ridiculous_price, 2)}")
    
    try:
        # 下卖单（高价卖，保证不成交）
        print(f"\n2. 正在下限价卖单...")
        result = exchange.order(
            symbol,
            False,  # is_buy = False (卖单)
            size,
            ridiculous_price,
            {"limit": {"tif": "Gtc"}},  # Good till cancel
            reduce_only=False
        )
        
        print(f"   下单结果: {result}")
        
        # 解析订单ID
        order_id = None
        if result.get("status") == "ok":
            statuses = result.get("response", {}).get("data", {}).get("statuses", [])
            if statuses:
                if "resting" in statuses[0]:
                    order_id = statuses[0]["resting"].get("oid")
                    print(f"   ✅ 下单成功，订单ID: {order_id}")
                elif "error" in statuses[0]:
                    print(f"   ❌ 下单被拒: {statuses[0]['error']}")
                    return
        
        if order_id:
            # 查询当前订单
            print(f"\n3. 查询当前订单...")
            open_orders = info.open_orders(CONFIG["main_wallet"])
            print(f"   当前挂单数量: {len(open_orders)}")
            for order in open_orders:
                print(f"   - {order.get('coin')} {order.get('side')} @ {order.get('limitPx')} (ID: {order.get('oid')})")
            
            # 撤单
            print(f"\n4. 正在撤单...")
            cancel_result = exchange.cancel(symbol, order_id)
            print(f"   撤单结果: {cancel_result}")
            
            if cancel_result.get("status") == "ok":
                print(f"   ✅ 撤单成功")
            else:
                print(f"   ❌ 撤单失败: {cancel_result}")
            
            # 再次查询确认
            print(f"\n5. 确认订单已撤销...")
            open_orders_after = info.open_orders(CONFIG["main_wallet"])
            print(f"   剩余挂单数量: {len(open_orders_after)}")
            
        else:
            print(f"   ⚠️ 无法获取订单ID")
            
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    test_order_cancel()

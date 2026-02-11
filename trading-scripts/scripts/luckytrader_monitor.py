#!/home/xqianliu/.openclaw/workspace/scripts/.venv/bin/python3
"""
$LuckyTrader Token Monitor (v2)
Tracks price, volume, holders for the LuckyTrader meme coin on Base.

Token: 0xaF3b1aFeFfe9dF30705c2a759D0BB3ff48FC7b07
Deployer: 0xa65c04a0144ce9154a7daa0b6ca5d376c1ca047c
Fee Recipient: 0xa24E75A6F48C99Ec9ABda7b9dBa5c7c9663F918B (= Hyperliquid 交易账户)
"""

import requests
import json
import sys
from datetime import datetime
from pathlib import Path

# Constants (v2 - 2026-02-04 重新部署)
TOKEN_ADDRESS = "0xaF3b1aFeFfe9dF30705c2a759D0BB3ff48FC7b07"
FEE_RECIPIENT = "0xa24E75A6F48C99Ec9ABda7b9dBa5c7c9663F918B"  # LP 费用直接进交易账户
SNAPSHOT_FILE = Path(__file__).parent.parent / "memory" / "luckytrader-snapshots.json"

def get_dexscreener_data():
    """Fetch token data from DexScreener API"""
    url = f"https://api.dexscreener.com/latest/dex/tokens/{TOKEN_ADDRESS}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("pairs") and len(data["pairs"]) > 0:
            return data["pairs"][0]  # Return the main pair
        return None
    except Exception as e:
        print(f"Error fetching DexScreener data: {e}")
        return None

def get_basescan_balance(address):
    """Get ETH balance from Basescan (no API key needed for basic queries)"""
    url = f"https://api.basescan.org/api?module=account&action=balance&address={address}&tag=latest"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get("status") == "1":
            balance_wei = int(data["result"])
            return balance_wei / 1e18  # Convert to ETH
        return None
    except Exception as e:
        print(f"Error fetching balance: {e}")
        return None

def load_snapshots():
    """Load historical snapshots"""
    if SNAPSHOT_FILE.exists():
        with open(SNAPSHOT_FILE, 'r') as f:
            return json.load(f)
    return {"snapshots": []}

def save_snapshot(snapshot):
    """Save new snapshot"""
    data = load_snapshots()
    data["snapshots"].append(snapshot)
    # Keep last 100 snapshots
    data["snapshots"] = data["snapshots"][-100:]
    SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SNAPSHOT_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def format_number(num):
    """Format large numbers"""
    if num is None:
        return "N/A"
    if num >= 1_000_000:
        return f"${num/1_000_000:.2f}M"
    if num >= 1_000:
        return f"${num/1_000:.2f}K"
    return f"${num:.2f}"

def main():
    print("=" * 50)
    print("🍀 $LuckyTrader Token Monitor")
    print("=" * 50)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Get DexScreener data
    pair_data = get_dexscreener_data()
    
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "price_usd": None,
        "market_cap": None,
        "volume_24h": None,
        "liquidity": None,
        "price_change_24h": None,
        "txns_24h": None,
        "creator_balance_eth": None
    }
    
    if pair_data:
        price = float(pair_data.get("priceUsd", 0) or 0)
        mc = float(pair_data.get("marketCap", 0) or 0)
        vol = float(pair_data.get("volume", {}).get("h24", 0) or 0)
        liq = float(pair_data.get("liquidity", {}).get("usd", 0) or 0)
        change = float(pair_data.get("priceChange", {}).get("h24", 0) or 0)
        txns = pair_data.get("txns", {}).get("h24", {})
        buys = txns.get("buys", 0)
        sells = txns.get("sells", 0)
        
        snapshot["price_usd"] = price
        snapshot["market_cap"] = mc
        snapshot["volume_24h"] = vol
        snapshot["liquidity"] = liq
        snapshot["price_change_24h"] = change
        snapshot["txns_24h"] = {"buys": buys, "sells": sells}
        
        print("📊 Token Stats:")
        print(f"   Price:        ${price:.10f}")
        print(f"   Market Cap:   {format_number(mc)}")
        print(f"   24h Volume:   {format_number(vol)}")
        print(f"   Liquidity:    {format_number(liq)}")
        print(f"   24h Change:   {change:+.2f}%")
        print(f"   24h Txns:     {buys} buys / {sells} sells")
        print()
        
        # DEX info
        dex = pair_data.get("dexId", "unknown")
        pair_addr = pair_data.get("pairAddress", "")
        print(f"   DEX:          {dex}")
        print(f"   Pair:         {pair_addr[:20]}...")
    else:
        print("⚠️  Could not fetch token data from DexScreener")
    
    print()
    
    # Get fee recipient wallet balance (v2: fees go directly to trading account)
    fee_balance = get_basescan_balance(FEE_RECIPIENT)
    if fee_balance is not None:
        snapshot["creator_balance_eth"] = fee_balance  # 保持 key 兼容
        print("🏦 Fee Recipient (Trading Account):")
        print(f"   Address:      {FEE_RECIPIENT[:20]}...")
        print(f"   ETH Balance:  {fee_balance:.6f} ETH")
    else:
        print("⚠️  Could not fetch fee recipient balance")
    
    print()
    
    # Compare with last snapshot
    history = load_snapshots()
    if history["snapshots"]:
        last = history["snapshots"][-1]
        print("📈 vs Last Check:")
        
        if last.get("price_usd") and snapshot["price_usd"]:
            price_diff = ((snapshot["price_usd"] / last["price_usd"]) - 1) * 100
            print(f"   Price:        {price_diff:+.2f}%")
        
        if last.get("creator_balance_eth") and snapshot["creator_balance_eth"]:
            balance_diff = snapshot["creator_balance_eth"] - last["creator_balance_eth"]
            if balance_diff != 0:
                print(f"   Fee ETH:      {balance_diff:+.6f} ETH")
    
    # Save snapshot
    save_snapshot(snapshot)
    print()
    print(f"💾 Snapshot saved to {SNAPSHOT_FILE}")
    print("=" * 50)
    
    # Return data for programmatic use
    return snapshot

if __name__ == "__main__":
    main()

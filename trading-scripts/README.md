# Lucky Trading Scripts 🍀

[![Trading Journal](https://img.shields.io/badge/📖_Trading_Journal-luckyclaw.win-brightgreen)](https://luckyclaw.win)
[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

**Lucky's Hyperliquid trading toolkit** — born from a [$100 AI trading experiment](https://luckyclaw.win).

An autonomous AI trader's open-source toolbox for crypto trading on [Hyperliquid](https://hyperliquid.xyz). Every script here is battle-tested with real money.

## Scripts

| Script | Purpose |
|--------|---------|
| `hl_trade.py` | Main trading CLI (buy/sell/stop-loss/take-profit) |
| `market_check.py` | Price monitoring + alerts (designed for cron) |
| `trailing_stop.py` | Trailing stop manager |
| `luckytrader_monitor.py` | $LuckyTrader token monitor |

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/xqliu/lucky-trading-scripts.git
cd lucky-trading-scripts/scripts

python -m venv .venv
source .venv/bin/activate
pip install hyperliquid-python-sdk eth-account requests
```

### 2. Create API Wallet on Hyperliquid

1. Go to [Hyperliquid](https://app.hyperliquid.xyz)
2. Connect your wallet and deposit funds
3. Navigate to **Portfolio → API Wallets → Create**
4. Save the generated:
   - API Wallet Address
   - API Private Key (shown only once!)

### 3. Configure

```bash
cd config
cp .hl_config.sample .hl_config
chmod 600 .hl_config  # Restrict permissions
```

Edit `.hl_config` with your credentials:

```ini
# Your main wallet (where funds are held)
MAIN_WALLET=0xYourMainWalletAddress

# API wallet (created in step 2)
API_WALLET=0xYourApiWalletAddress
API_PRIVATE_KEY=0xYourApiPrivateKey
```

### 4. Usage

```bash
# Check account status
python hl_trade.py status

# Check prices
python hl_trade.py price --coin BTC

# Place orders
python hl_trade.py buy --coin BTC --size 0.001 --price 70000
python hl_trade.py sell --coin ETH --size 0.01

# Manage orders
python hl_trade.py orders
python hl_trade.py cancel --coin BTC --oid 12345
```

## Lessons Learned (The Hard Way)

These scripts evolved through real trading mistakes:

1. **Always set immediate stop-losses** — Don't wait for gains before protecting downside
2. **Verify orders on-chain** — `open_orders()` ≠ `frontend_open_orders()`. The latter shows trigger order details
3. **Validate prices** — A long stop-loss above current price is a market sell, not protection

Read the full story: [Day 7: $1.32 Tuition Fee](https://luckyclaw.win/day-7-tuition)

## Related

- 📖 **[LuckyClaw Trading Journal](https://luckyclaw.win)** — The full AI trading diary
- 🏗️ **[LuckyClaw Website Source](https://github.com/xqliu/luckyclaw)** — The journal site code
- 🐦 **[Twitter](https://x.com/xqliu)** — Latest updates

## License

MIT — Use freely, trade responsibly.

---

*Built by an AI named Lucky, supervised by [@xqliu](https://x.com/xqliu). Part of the [LuckyClaw](https://luckyclaw.win) experiment.*

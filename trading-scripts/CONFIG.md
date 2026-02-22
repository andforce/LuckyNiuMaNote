# LuckyNiuMa Trading Scripts Configuration

## 🔐 API 配置状态

✅ **已配置**

| 项目 | 地址 |
|------|------|
| 主钱包 | `0xfFd91a584cf6419b92E58245898D2A9281c628eb` |
| API 钱包 | `0xD50affea03a6DdcA663611d5487Cb962b0BDA892` |

## 📊 当前账户状态

```
现货账户 (Spot):  97.975836 USDC
合约账户 (Perp):  0.000000 USDC
--------------------------------
总计:            97.975836 USDC
```

## 🚀 开始使用

### 1. 激活环境

```bash
cd /home/ubuntu/.openclaw/workspace/LuckyNiuMaNote/trading-scripts
source .venv/bin/activate
```

### 2. 查看余额

```bash
python scripts/transfer.py status
```

### 3. 划转资金到合约账户（开始交易前必须做）

```bash
# 划转 90 USDC 到合约账户
python scripts/transfer.py to-perp --amount 90
```

### 4. 查看价格和账户

```bash
# 查看 BTC 价格
python scripts/hl_trade.py price --coin BTC

# 查看账户状态
python scripts/hl_trade.py status
```

### 5. 下单交易

```bash
# 市价买入 0.001 BTC
python scripts/hl_trade.py market-buy --coin BTC --size 0.001

# 限价买入
python scripts/hl_trade.py buy --coin BTC --size 0.001 --price 67000

# 查看持仓和订单
python scripts/hl_trade.py orders

# 取消订单
python scripts/hl_trade.py cancel --coin BTC --oid 12345
```

## ⚠️ 重要提醒

1. **交易前必须先划转资金** - 现货账户的资金不能直接用于合约交易
2. **设置止损** - 每次开仓必须设置止损
3. **API 私钥安全** - `.hl_config` 文件已设置权限 600，永远不要提交到 git

## 🛠️ 可用脚本

| 脚本 | 功能 |
|------|------|
| `hl_trade.py` | 主交易 CLI（买入/卖出/查看）|
| `transfer.py` | 资金划转（现货↔合约）|
| `market_check.py` | 价格监控 |
| `trailing_stop.py` | 移动止损管理 |
| `luckytrader_monitor.py` | LuckyTrader 代币监控 |

## 📝 交易日志

所有交易会自动记录在网站的交易日志中。

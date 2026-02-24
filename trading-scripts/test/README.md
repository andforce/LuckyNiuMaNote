# 策略回测验证

验证 `auto_trader` 交易策略在历史数据上的表现。

## 运行方式

```bash
# 从项目根目录
python trading-scripts/test/backtest.py

# 或进入 test 目录
cd trading-scripts/test
python backtest.py
```

## 依赖

- Python 3.7+
- requests

```bash
pip install requests
```

## 回测参数

- **数据范围**: 2025-08-01 ~ 2025-12-31（Hyperliquid 仅保留约 5000 根 1h K 线）
- **标的**: BTC
- **周期**: 1 小时 K 线
- **初始资金**: 100 USDC
- **规则**: 与 auto_trader.py 完全一致（EMA 排列 + 金叉/死叉 + fee_check）

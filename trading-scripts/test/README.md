# 策略回测验证

验证 `auto_trader` 交易策略在历史数据上的表现。

## 运行方式

```bash
# 回测（默认: 胜率优先参数）
python trading-scripts/test/backtest.py

# 回测原始参数
python trading-scripts/test/backtest.py --profile baseline

# 回测收益平衡参数（旧 optimized）
python trading-scripts/test/backtest.py --profile balanced

# 参数优化（寻找提高胜率的组合）
python trading-scripts/test/optimize.py --symbol BTC --objective win_rate

# 训练期/测试期自动选参（避免过拟合）
python trading-scripts/test/optimize.py --symbol BTC --mode train_test --objective win_rate --train-end-date 2025-12-31

# 滚动窗口 walk-forward（多段训练/测试，更稳健）
python trading-scripts/test/optimize.py --symbol BTC --mode walk_forward --objective win_rate
```

## 依赖

- Python 3.7+
- requests

```bash
pip install requests
```

## 回测参数

- **数据范围**: 默认 2025-08-01 ~ 2026-02-20（可通过参数调整）
- **策略档位**:
  - `baseline`: 原始参数（SL=2, TP=3, 冷却=1）
  - `balanced`: 收益平衡（SL=3, TP=4, 冷却=1）
  - `win_rate`: 胜率优先（SL=3, TP=2.5, 冷却=6）

## 优化结论（BTC，2025-08-01 ~ 2026-02-20）

| 配置 | 收益 | 胜率 | 说明 |
|------|------|------|------|
| baseline (SL=2 TP=3 冷却1) | -24.7% | 40.0% | 原始参数，震荡期回撤明显 |
| balanced (SL=3 TP=4 冷却1) | +9.6% | 51.9% | 收益/胜率折中 |
| **win_rate (SL=3 TP=2.5 冷却6)** | **+14.3%** | **66.0%** | 胜率优先，减少亏损后连续开仓 |

**建议**:
- 如果你当前重点是“提高胜率”，使用 `--profile win_rate`
- 如果你更看重单笔盈亏比，使用 `--profile balanced`
- **标的**: BTC
- **周期**: 1 小时 K 线
- **初始资金**: 100 USDC
- **规则**: 与 auto_trader.py 完全一致（EMA 排列 + 金叉/死叉 + fee_check）

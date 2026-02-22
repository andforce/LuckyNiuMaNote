#!/bin/bash
# 启动自动交易机器人

cd /home/ubuntu/.openclaw/workspace/LuckyNiuMaNote/trading-scripts
source .venv/bin/activate

# 确保日志目录存在
mkdir -p ../logs

# 启动机器人
exec python scripts/auto_trader.py

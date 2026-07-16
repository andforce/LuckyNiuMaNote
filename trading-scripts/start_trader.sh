#!/bin/bash
# 启动自动交易机器人

cd -- "$(dirname -- "${BASH_SOURCE[0]}")" || exit 1
source .venv/bin/activate

# 确保日志目录存在
mkdir -p ../logs

# 启动机器人（NFI short_only）
exec python scripts/auto_trader_nostalgia_for_infinity.py

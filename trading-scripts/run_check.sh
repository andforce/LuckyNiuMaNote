#!/bin/bash
# 检查交易脚本是否可正常运行
# 用法: ./run_check.sh

set -e
cd "$(dirname "$0")"

echo "=== 1. 检查依赖 ==="
if [ -d .venv ]; then
    source .venv/bin/activate
    echo "使用 .venv"
else
    echo "未找到 .venv，使用系统 Python"
fi

python -c "
import sys
try:
    import hyperliquid
    import eth_account
    import requests
    print('  ✓ hyperliquid, eth_account, requests 已安装')
except ImportError as e:
    print('  ✗ 缺少依赖:', e)
    print('  运行: pip install -r requirements.txt')
    sys.exit(1)
"

echo ""
echo "=== 2. 检查配置 ==="
if [ -f config/.hl_config ]; then
    echo "  ✓ config/.hl_config 存在"
    grep -q "MAIN_WALLET=0x" config/.hl_config && echo "  ✓ MAIN_WALLET 已配置" || echo "  ✗ MAIN_WALLET 未配置"
    grep -qE "API_PRIVATE_KEY=0x[0-9a-fA-F]{64}" config/.hl_config && echo "  ✓ API_PRIVATE_KEY 已配置" || echo "  ? API_PRIVATE_KEY (需检查或使用 HL_API_KEY 环境变量)"
else
    echo "  ✗ config/.hl_config 不存在"
    echo "  运行: cp config/.hl_config.sample config/.hl_config"
    exit 1
fi

echo ""
echo "=== 3. 语法检查 ==="
python -m py_compile scripts/auto_trader_nostalgia_for_infinity.py 2>/dev/null && echo "  ✓ 语法正确" || echo "  ✗ 语法错误"

echo ""
echo "=== 4. 启动测试（5秒后退出）==="
timeout 5 python scripts/auto_trader_nostalgia_for_infinity.py 2>&1 | head -20 || true
echo ""
echo "  (若看到 'NFI cycle' 或 'start NFI cycle' 则启动成功)"
echo ""
echo "=== 检查完成 ==="

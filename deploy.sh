#!/bin/bash
set -euo pipefail

DEPLOY_DIR="/home/ubuntu/LuckyNiuMaNote"
TRADING_DIR="$DEPLOY_DIR/trading-scripts"
VENV_DIR="$TRADING_DIR/.venv"
LOG_DIR="$DEPLOY_DIR/logs"
BACKEND_PM2_NAME="lucky-backend"

# ── 颜色输出 ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── 前置检查 ──────────────────────────────────────────────────────────────────
check_deps() {
  command -v node  >/dev/null 2>&1 || error "未找到 node，请先安装 Node.js"
  command -v npm   >/dev/null 2>&1 || error "未找到 npm"
  command -v pm2   >/dev/null 2>&1 || error "未找到 pm2，请先执行: npm install -g pm2"
  command -v python3 >/dev/null 2>&1 || error "未找到 python3"
  [[ -d "$DEPLOY_DIR" ]] || error "部署目录不存在: $DEPLOY_DIR"
  info "前置检查通过"
}

# ── Python 虚拟环境 & 依赖 ────────────────────────────────────────────────────
setup_python() {
  if [[ ! -d "$VENV_DIR" ]]; then
    warn "虚拟环境不存在，正在创建..."
    python3 -m venv "$VENV_DIR"
  fi
  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"
  pip install -q --upgrade pip
  pip install -q -r "$TRADING_DIR/requirements.txt"
  deactivate
  info "Python 虚拟环境就绪"
}

# ── Node.js 依赖 ──────────────────────────────────────────────────────────────
install_node_deps() {
  cd "$DEPLOY_DIR"
  npm install --omit=dev --silent
  info "Node.js 依赖安装完成"
}

# ── 构建前端 ──────────────────────────────────────────────────────────────────
build_frontend() {
  cd "$DEPLOY_DIR"
  npm --prefix frontend install --silent
  npm run build
  info "前端构建完成"
}

# ── 创建日志目录 ──────────────────────────────────────────────────────────────
ensure_logs_dir() {
  mkdir -p "$LOG_DIR"
  info "日志目录就绪: $LOG_DIR"
}

# ── 启动后端 ──────────────────────────────────────────────────────────────────
start_backend() {
  cd "$DEPLOY_DIR"
  if pm2 describe "$BACKEND_PM2_NAME" >/dev/null 2>&1; then
    pm2 restart "$BACKEND_PM2_NAME"
    info "后端已重启 (pm2: $BACKEND_PM2_NAME)"
  else
    pm2 start server.js \
      --name "$BACKEND_PM2_NAME" \
      --log "$LOG_DIR/backend.log" \
      --error "$LOG_DIR/backend_error.log" \
      --time \
      --restart-delay=3000
    info "后端已启动 (pm2: $BACKEND_PM2_NAME)"
  fi
}

# ── 启动交易机器人 ─────────────────────────────────────────────────────────────
start_traders() {
  cd "$TRADING_DIR"

  # run_trader_XX.sh 必须有可执行权限
  chmod +x run_trader_*.sh run_auto_trader.sh start_trader.sh 2>/dev/null || true

  # 用 ecosystem.config.json 管理 6 个机器人
  if pm2 describe trader-boll-macd >/dev/null 2>&1; then
    pm2 restart ecosystem.config.json
    info "交易机器人已重启"
  else
    pm2 start ecosystem.config.json
    info "交易机器人已启动"
  fi
}

# ── 保存 pm2 进程列表（开机自启） ─────────────────────────────────────────────
save_pm2() {
  pm2 save
  info "pm2 进程列表已保存"
  warn "如需开机自启，请执行: pm2 startup 并按提示运行输出的命令"
}

# ── 状态汇总 ──────────────────────────────────────────────────────────────────
show_status() {
  echo ""
  pm2 list
  echo ""
  info "部署完成！后端默认监听端口请查看 server.js 中的 PORT 配置"
}

# ── 主流程 ────────────────────────────────────────────────────────────────────
main() {
  echo "========================================="
  echo "  LuckyNiuMaNote 部署脚本"
  echo "========================================="

  check_deps
  setup_python
  install_node_deps
  build_frontend
  ensure_logs_dir
  start_backend
  start_traders
  save_pm2
  show_status
}

main "$@"

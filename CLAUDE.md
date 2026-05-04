# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

本项目是一个 AI 加密货币交易公开实验系统，包含两个独立部分：

1. **Web 端**：展示交易日志、策略说明、实时账户与机器人状态的站点
2. **Trading 端**：基于 Hyperliquid 的 Python 交易脚本与自动策略执行

## 常用命令

### Web 端

```bash
# 安装依赖（根 + frontend）
npm install
(cd frontend && npm install)

# 构建（内容 + 前端）
npm run build

# 本地开发：后端
node server.js
# 本地开发：前端
npm --prefix frontend run dev

# Lint 前端
npm --prefix frontend run lint
```

### Trading 端

```bash
cd trading-scripts
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 手动交易 CLI
python scripts/hl_trade.py status
python scripts/hl_trade.py price --coin BTC
python scripts/hl_trade.py market-buy --coin BTC --size 0.001

# 资金划转（交易前必须：现货 → 合约）
python scripts/transfer.py to-perp --amount 90
```

### 进程管理（PM2）

```bash
# 启动交易机器人（推荐用 ecosystem.army.json）
pm2 start trading-scripts/ecosystem.army.json

# 查看状态 / 日志
pm2 list
pm2 logs auto-trader --lines 50
pm2 logs trader-boll-macd --lines 50
```

### 生产部署

- **网站后端**：由 `systemd` 服务 `luckyniuma-backend` 管理（见 `infra/luckyniuma-backend.service`），不要同时用 PM2 起同名进程
- **交易脚本**：由 PM2 管理（`ecosystem.army.json`）
- **部署流程**：`npm run build` → `sudo systemctl restart luckyniuma-backend` → `pm2 restart all`
- 根目录 `deploy.sh` 假设用 PM2 跑后端，若生产已改用 systemd，**不要直接运行该脚本**

## 代码架构

### 数据流（Web）

```
content/*.json + content/**/*.md
        ↓ build.js
frontend/public/generated-data.json
src/generated-data.js
        ↓ server.js / React 前端
页面渲染 + /api/* 实时接口
```

- `build.js`：无外部依赖，解析 Markdown frontmatter，生成 JS/JSON 数据文件
- `server.js`：Express 5，提供静态资源（`frontend/dist`）和 API
- `frontend/`：Vite + React 19 + Chart.js，纯前端 SPA，路由由 React Router 处理

### 实时 API（server.js）

| 路由 | 数据来源 | 说明 |
|------|----------|------|
| `/api/position` | Hyperliquid API | 账户资产、持仓、价格 |
| `/api/traders-status` | `logs/*.log` + `pgrep` | 各策略进程存活与最新信号 |
| `/api/indicators` | Hyperliquid K 线 | NFI 策略指标实时计算（与 Python 脚本逻辑一致） |
| `/api/chart/:symbol` | Hyperliquid K 线 | K 线 + EMA + 信号数据 |

`server.js` 通过 `pgrep -f <scriptFile>` 和读取 `/proc/<pid>/cmdline` 检测 Python 策略进程是否运行。

### 交易脚本

- `scripts/auto_trader_nostalgia_for_infinity.py`：当前主力实盘，NFI 思路改造，默认做空
- `scripts/trader_01_boll_macd.py`、`trader_04_supertrend.py`、`trader_05_adx.py` 等：独立策略
- `scripts/hl_trade.py`：手动交易 CLI
- `scripts/transfer.py`：现货/合约资金划转（交易前必须划转）
- 策略日志写入 `logs/*.log`，由 Web API 读取展示

### 配置文件

- `trading-scripts/config/.hl_config`：API 钱包私钥（`KEY=value` 格式），**已加入 .gitignore，绝不要提交**
- `content/config.json`：站点配置与账户统计
- `content/strategy.json`：当前策略描述
- `trading-scripts/ecosystem.army.json`：PM2 配置，内含绝对路径，换机需替换

## 注意事项

- **端口**：后端默认 `3000`，前端 dev server 默认 `5173`
- **环境变量**：`PORT`、`LISTEN_HOST`（生产建议 `127.0.0.1`）、`TRUST_PROXY`、`SITE_PUBLIC_URL`
- **Nginx + Certbot**：HTTPS 由 `scripts/setup-https.sh` 配置，`infra/nginx-luckyniuma.conf` 为模板
- **日志目录**：`logs/` 在仓库根下，策略和 PM2 均会写入

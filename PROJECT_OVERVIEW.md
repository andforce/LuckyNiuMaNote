# LuckyNiuMaNote 项目概要

## 1. 项目定位

本项目是一个「AI 加密货币交易公开实验」系统，包含两个核心部分：

- Web 端：展示交易日志、策略说明、学习资料、实时账户与机器人状态。
- Trading 端：基于 Hyperliquid 的 Python 交易脚本与自动策略执行。

当前仓库主要承载数据展示与交易自动化脚本，不是单一前后端应用，而是内容站点 + 交易执行工具的组合。

## 2. 技术栈与依赖

### Web 层

- Node.js + Express
- 前端为原生 HTML/CSS/JS（无前端框架）
- 构建脚本：`build.js`（将 `content/` 下数据编译到 `src/generated-data.js`）

`package.json` 关键依赖：

- `express@^5.2.1`

### Trading 层

- Python（交易脚本）
- Hyperliquid SDK + eth-account + requests

`trading-scripts/requirements.txt`：

- `hyperliquid-python-sdk>=0.18.0`
- `eth-account>=0.10.0`
- `requests>=2.28.0`

## 3. 目录结构（核心）

- `content/`：站点内容源（交易日志、学习资料、配置、策略）
- `src/`：Web/Worker 代码与生成数据
- `public/`：静态资源
- `server.js`：本地/服务端页面与 API 聚合入口
- `build.js`：内容构建器（Frontmatter 解析 + 数据导出）
- `trading-scripts/scripts/`：交易 CLI、自动交易、监控与止损脚本
- `trading-scripts/config/.hl_config.sample`：交易账户配置模板
- `logs/`：运行日志目录（Web API 会读取机器人日志）

## 4. 核心模块说明

### 4.1 内容构建（`build.js`）

- 读取 `content/config.json`、`content/strategy.json`、`content/entries/*.md`、`content/learn/*.md`
- 解析 frontmatter + markdown 正文
- 生成 `src/generated-data.js`，作为站点渲染的数据源

### 4.2 Web 服务（`server.js`）

- 提供页面路由：主页、策略页、学习页、文章页、图表页
- 提供实时 API：
  - `/api/position`：账户资产、持仓、价格
  - `/api/trader-status`、`/api/traders-status`：交易机器人运行与信号状态
  - `/api/indicators`：NFI 指标计算结果
  - `/api/chart/:symbol`：K 线 + EMA + 信号数据
- 读取 `logs/*.log` 解析机器人状态
- 对接 Hyperliquid `info` 接口获取市场与账户数据

### 4.3 交易脚本（`trading-scripts/scripts`）

- `hl_trade.py`：手动交易 CLI（下单、撤单、止损、止盈、查状态）
- `auto_trader_nostalgia_for_infinity.py`：自动交易主脚本（NFI 思路改造）
  - 多指标：EMA/RSI/Bollinger/ATR/Volume
  - 风控：冷却期、回撤限制、最小交易额、手续费后利润过滤
  - 交易方向支持按币种覆盖（如 BTC `short_only`）
- `trailing_stop.py`：移动止损管理（含止损单校验）
- `market_check.py`：价格巡检与告警触发

## 5. 数据与执行链路

1. 内容作者维护 `content/*.json` 与 `content/**/*.md`
2. `build.js` 编译生成 `src/generated-data.js`
3. `server.js` 读取生成数据并提供页面/API
4. Python 交易脚本与 Hyperliquid 交互，日志写入 `logs/`
5. Web API 再读取日志与链上/交易所数据，展示实时状态

## 6. 当前策略画像（来自仓库配置）

- 策略名：`NFI Short-Only 反转策略`
- 主要市场：BTC、ETH
- 主要周期：1h
- 风控特征：ATR 止损/止盈、冷却期、最大回撤保护
- 站点定位：公开记录交易过程，强调透明与可验证

## 7. 初始化结论（本次）

本次“初始化”已按「认知初始化」完成：

- 已完成代码结构、依赖、核心模块与数据流梳理
- 已确认项目是运行中系统（PM2 管理），未进行重装依赖和重启操作
- 已将项目概要落盘为本文件

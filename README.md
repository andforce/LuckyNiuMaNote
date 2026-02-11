# 🐴 小牛马的炒币实验 LuckyNiuMa

一个 AI 自主学习加密货币交易的公开实验项目

## 项目介绍

参考 [LuckyClaw](https://luckyclaw.win) 项目，让 AI 助手通过真实交易学习加密货币市场。

- **交易平台**: [Hyperliquid](https://hyperliquid.xyz) - 去中心化衍生品交易所
- **启动资金**: $100 USDT
- **交易规则**: 
  - 最大杠杆: 3x
  - 单笔最大亏损: $10
  - 止损线: $70 (30% 回撤)
  - 完整记录所有交易

## 项目结构

```
LuckyNiuMaNote/
├── public/              # 静态资源（logo、图片等）
├── src/                 # 网站源代码
├── content/             # 交易日志 Markdown 文件
├── trading-scripts/     # 交易脚本（Python）
│   ├── scripts/
│   │   ├── hl_trade.py          # 主交易 CLI
│   │   ├── market_check.py      # 市场监控
│   │   └── trailing_stop.py     # 追踪止损
│   └── config/
│       └── .hl_config.sample    # 配置模板
├── server.js            # Express 本地服务器
├── build.js             # 静态网站生成器
└── README.md
```

## 快速开始

### 1. 网站部署

```bash
# 安装依赖
npm install

# 构建网站
npm run build

# 启动本地服务器
node server.js
```

访问 http://localhost:3000

### 2. 交易脚本配置

```bash
cd trading-scripts

# 创建 Python 虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install hyperliquid-python-sdk eth-account requests

# 配置钱包
cd config
cp .hl_config.sample .hl_config
chmod 600 .hl_config
# 编辑 .hl_config 填入你的钱包信息
```

### 3. 使用交易脚本

```bash
source .venv/bin/activate

# 查看账户状态
python scripts/hl_trade.py status

# 查看价格
python scripts/hl_trade.py price --coin BTC

# 下单（示例）
python scripts/hl_trade.py buy --coin BTC --size 0.001 --price 70000
```

## 技术栈

### 网站
- **前端**: Vanilla JS (零依赖)
- **后端**: Express.js + Node.js
- **部署**: Cloudflare Workers / 自托管
- **风格**: 暗色主题，响应式设计

### 交易脚本
- **语言**: Python 3.12
- **SDK**: hyperliquid-python-sdk
- **钱包**: eth-account (以太坊兼容)

## 安全提示 ⚠️

1. **永远不要提交 `.hl_config` 到 git**（已加入 .gitignore）
2. **API 私钥不要分享给任何人**
3. **建议先用小额测试**
4. **务必设置止损保护**

## 参考项目

- 🍀 [LuckyClaw](https://luckyclaw.win) - 原始灵感来源
- 📖 [Trading Scripts](https://github.com/xqliu/lucky-trading-scripts) - 开源交易脚本
- 🦞 [OpenClaw](https://openclaw.ai) - AI 助手框架

## 当前状态

| 指标 | 数值 |
|------|------|
| 启动资金 | $100 |
| 当前余额 | TBD |
| 总收益 | TBD |
| 完成交易 | 0 |

## License

MIT License - 参考原项目 [xqliu/luckyclaw](https://github.com/xqliu/luckyclaw)

---

**免责声明**: 本项目仅供学习研究使用。加密货币交易有风险，请谨慎参与。

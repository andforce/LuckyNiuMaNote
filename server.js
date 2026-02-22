const express = require('express');
const path = require('path');
const fs = require('fs');
const https = require('https');

const app = express();
const PORT = 3000;

// 主钱包地址
const WALLET_ADDRESS = '0xfFd91a584cf6419b92E58245898D2A9281c628eb';
const HL_API = 'https://api.hyperliquid.xyz/info';

// 调用 Hyperliquid API
function hlRequest(body) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body);
    const req = https.request(HL_API, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': data.length
      },
      timeout: 8000
    }, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(body));
        } catch (e) {
          reject(e);
        }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
    req.write(data);
    req.end();
  });
}

// 读取生成的数据（直接读文件内容并解析）
const generatedDataPath = path.join(__dirname, 'src', 'generated-data.js');
const dataContent = fs.readFileSync(generatedDataPath, 'utf-8');

// 提取数据（简单粗暴的方式）
function extractData(content, varName) {
  const regex = new RegExp(`export const ${varName} = ([\\s\\S]*?);\\s*(?=export const|$)`, 'm');
  const match = content.match(regex);
  if (match) {
    return JSON.parse(match[1]);
  }
  return null;
}

const SITE_CONFIG = extractData(dataContent, 'SITE_CONFIG');
const STATS = extractData(dataContent, 'STATS');
const ENTRIES = extractData(dataContent, 'ENTRIES');
const VERIFICATION = extractData(dataContent, 'VERIFICATION');
const STRATEGY = extractData(dataContent, 'STRATEGY');
const LEARN_ENTRIES = extractData(dataContent, 'LEARN_ENTRIES');

// 静态文件服务
app.use('/public', express.static(path.join(__dirname, 'public')));
app.use(express.static(path.join(__dirname, 'public')));

// ==================== API 路由 ====================

// 实时持仓和账户数据
app.get('/api/position', async (req, res) => {
  try {
    // 并行请求
    const [perpState, spotState, mids] = await Promise.all([
      hlRequest({ type: 'clearinghouseState', user: WALLET_ADDRESS }),
      hlRequest({ type: 'spotClearinghouseState', user: WALLET_ADDRESS }),
      hlRequest({ type: 'allMids' })
    ]);

    // 解析 Perp 账户
    const marginSummary = perpState.marginSummary || {};
    const perpValue = parseFloat(marginSummary.accountValue || 0);
    
    // 解析持仓
    const positions = (perpState.assetPositions || [])
      .filter(p => parseFloat(p.position.szi) !== 0)
      .map(p => {
        const pos = p.position;
        const size = parseFloat(pos.szi);
        const entryPx = parseFloat(pos.entryPx);
        const currentPx = parseFloat(mids[pos.coin] || 0);
        const pnl = parseFloat(pos.unrealizedPnl);
        const pnlPct = entryPx > 0 ? ((currentPx - entryPx) / entryPx * 100) : 0;
        
        return {
          coin: pos.coin,
          size: size,
          side: size > 0 ? 'LONG' : 'SHORT',
          entryPx: entryPx,
          currentPx: currentPx,
          pnl: pnl,
          pnlPct: size > 0 ? pnlPct : -pnlPct,
          liquidationPx: pos.liquidationPx ? parseFloat(pos.liquidationPx) : null
        };
      });

    // 解析 Spot 余额
    const spotBalances = (spotState.balances || [])
      .filter(b => parseFloat(b.total) > 0)
      .map(b => ({
        coin: b.coin,
        total: parseFloat(b.total)
      }));
    
    const spotValue = spotBalances.reduce((sum, b) => {
      if (b.coin === 'USDC') return sum + b.total;
      const price = parseFloat(mids[b.coin] || 0);
      return sum + b.total * price;
    }, 0);

    // 总资产
    const totalValue = perpValue + spotValue;
    const initialCapital = 98;
    const totalPnl = totalValue - initialCapital;
    const totalPnlPct = (totalPnl / initialCapital) * 100;

    res.json({
      success: true,
      timestamp: Date.now(),
      account: {
        perpValue: perpValue,
        spotValue: spotValue,
        totalValue: totalValue,
        initialCapital: initialCapital,
        totalPnl: totalPnl,
        totalPnlPct: totalPnlPct
      },
      positions: positions,
      spotBalances: spotBalances,
      prices: {
        BTC: parseFloat(mids.BTC || 0),
        ETH: parseFloat(mids.ETH || 0)
      }
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// ==================== 页面路由 ====================

// 简单的 markdown 渲染
function renderMarkdown(text) {
  return text
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
    .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>');
}

function formatDate(dateStr) {
  const d = new Date(dateStr);
  return d.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', year: 'numeric' });
}

function getHTML(content) {
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>小牛马的炒币日记 🐴</title>
  <link rel="icon" href="/favicon-32.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Noto+Sans+SC:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-primary: #0a0a0f;
      --bg-secondary: #0d1117;
      --bg-card: #161b22;
      --text-primary: #e6edf3;
      --text-secondary: #8b949e;
      --text-muted: #6e7681;
      --accent: #00ff9f;
      --accent-dim: #00cc7f;
      --accent-glow: rgba(0, 255, 159, 0.3);
      --cyber-pink: #ff0080;
      --cyber-blue: #00d4ff;
      --cyber-purple: #bf00ff;
      --border: #30363d;
      --grid-color: rgba(0, 255, 159, 0.03);
    }
    
    * { margin: 0; padding: 0; box-sizing: border-box; }
    
    body {
      font-family: 'Noto Sans SC', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg-primary);
      color: var(--text-primary);
      line-height: 1.8;
      min-height: 100vh;
      background-image: 
        linear-gradient(var(--grid-color) 1px, transparent 1px),
        linear-gradient(90deg, var(--grid-color) 1px, transparent 1px);
      background-size: 50px 50px;
    }
    
    body::before {
      content: '';
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: radial-gradient(ellipse at top, rgba(0, 255, 159, 0.08) 0%, transparent 50%),
                  radial-gradient(ellipse at bottom right, rgba(255, 0, 128, 0.05) 0%, transparent 50%);
      pointer-events: none;
      z-index: -1;
    }
    
    .container {
      max-width: 900px;
      margin: 0 auto;
      padding: 20px;
    }
    
    /* Header - Cyber Style */
    header {
      text-align: center;
      padding: 50px 0;
      position: relative;
    }
    
    header::after {
      content: '';
      position: absolute;
      bottom: 0;
      left: 50%;
      transform: translateX(-50%);
      width: 80%;
      height: 1px;
      background: linear-gradient(90deg, transparent, var(--accent), var(--cyber-pink), transparent);
    }
    
    .logo {
      width: 140px;
      height: 140px;
      margin: 0 auto 25px;
      border-radius: 50%;
      border: 3px solid var(--accent);
      box-shadow: 0 0 30px var(--accent-glow), 0 0 60px var(--accent-glow), inset 0 0 30px rgba(0, 255, 159, 0.1);
      animation: glow 3s ease-in-out infinite;
      display: block;
    }
    
    @keyframes glow {
      0%, 100% { box-shadow: 0 0 30px var(--accent-glow), 0 0 60px var(--accent-glow); }
      50% { box-shadow: 0 0 40px var(--accent-glow), 0 0 80px var(--accent-glow); }
    }
    
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }
    
    h1 {
      font-size: 2.8em;
      background: linear-gradient(135deg, var(--accent) 0%, var(--cyber-blue) 50%, var(--cyber-pink) 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      margin-bottom: 15px;
      font-weight: 700;
    }
    
    .subtitle {
      color: var(--text-secondary);
      font-size: 1.1em;
      font-family: 'JetBrains Mono', monospace;
    }
    
    /* Stats - Cyber Dashboard */
    .stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 20px;
      margin: 40px 0;
    }
    
    .stat-card {
      background: var(--bg-card);
      padding: 25px;
      border-radius: 8px;
      border: 1px solid var(--border);
      transition: all 0.3s;
      position: relative;
      overflow: hidden;
    }
    
    .stat-card::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 2px;
      background: linear-gradient(90deg, var(--accent), var(--cyber-blue));
      opacity: 0;
      transition: opacity 0.3s;
    }
    
    .stat-card:hover {
      transform: translateY(-5px);
      border-color: var(--accent);
      box-shadow: 0 10px 40px rgba(0, 255, 159, 0.15);
    }
    
    .stat-card:hover::before {
      opacity: 1;
    }
    
    .stat-label {
      color: var(--text-muted);
      font-size: 0.85em;
      margin-bottom: 10px;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      font-family: 'JetBrains Mono', monospace;
    }
    
    .stat-value {
      font-size: 2.2em;
      font-weight: 700;
      font-family: 'JetBrains Mono', monospace;
    }
    
    .stat-value.green {
      color: var(--accent);
      text-shadow: 0 0 20px var(--accent-glow);
    }
    
    .stat-value.blue {
      color: var(--cyber-blue);
      text-shadow: 0 0 20px rgba(0, 212, 255, 0.5);
    }
    
    .stat-value.pink {
      color: var(--cyber-pink);
      text-shadow: 0 0 20px rgba(255, 0, 128, 0.5);
    }
    
    /* Wallet Card - Cyber Panel */
    .wallet-card {
      background: var(--bg-card);
      padding: 30px;
      border-radius: 8px;
      border: 1px solid var(--accent);
      margin: 30px 0;
      position: relative;
      overflow: hidden;
      box-shadow: 0 0 30px rgba(0, 255, 159, 0.1);
    }
    
    .wallet-card::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 3px;
      background: linear-gradient(90deg, var(--accent), var(--cyber-pink), var(--cyber-blue));
    }
    
    .wallet-card h3 {
      color: var(--accent);
      margin-bottom: 20px;
      font-size: 1.3em;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    
    .wallet-card code {
      background: var(--bg-primary);
      padding: 12px 16px;
      border-radius: 4px;
      color: var(--accent);
      font-size: 0.9em;
      display: block;
      margin: 10px 0;
      word-break: break-all;
      font-family: 'JetBrains Mono', monospace;
      border: 1px solid var(--border);
    }
    
    .wallet-info {
      color: var(--text-secondary);
      font-size: 0.9em;
      margin-top: 20px;
      padding: 15px;
      background: var(--bg-secondary);
      border-radius: 4px;
      border-left: 3px solid var(--cyber-blue);
    }
    
    .wallet-info strong {
      color: var(--cyber-blue);
    }
    
    /* Entries Section */
    .entries {
      margin-top: 50px;
    }
    
    .entries > h2 {
      color: var(--accent);
      margin-bottom: 30px;
      font-size: 1.8em;
      display: flex;
      align-items: center;
      gap: 15px;
    }
    
    .entries > h2::after {
      content: '';
      flex: 1;
      height: 1px;
      background: linear-gradient(90deg, var(--accent), transparent);
    }
    
    .entry {
      background: var(--bg-card);
      padding: 30px;
      margin-bottom: 25px;
      border-radius: 8px;
      border: 1px solid var(--border);
      transition: all 0.3s;
      position: relative;
      overflow: hidden;
    }
    
    .entry::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      width: 3px;
      height: 100%;
      background: linear-gradient(180deg, var(--accent), var(--cyber-pink));
      opacity: 0;
      transition: opacity 0.3s;
    }
    
    .entry:hover {
      border-color: var(--accent);
      transform: translateX(8px);
      box-shadow: -8px 0 30px rgba(0, 255, 159, 0.1);
    }
    
    .entry:hover::before {
      opacity: 1;
    }
    
    .entry h2 {
      margin-bottom: 12px;
      font-size: 1.5em;
    }
    
    .entry h2 a {
      color: var(--text-primary);
      text-decoration: none;
      transition: all 0.3s;
    }
    
    .entry h2 a:hover {
      color: var(--accent);
      text-shadow: 0 0 15px var(--accent-glow);
    }
    
    .entry-meta {
      color: var(--text-muted);
      font-size: 0.9em;
      margin-bottom: 15px;
      font-family: 'JetBrains Mono', monospace;
    }
    
    .entry-content {
      color: var(--text-secondary);
      line-height: 1.9;
    }
    
    .entry-content p {
      margin: 15px 0;
    }
    
    .entry-content h2 {
      color: var(--accent);
      margin: 30px 0 15px;
      font-size: 1.4em;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--border);
    }
    
    .entry-content h3 {
      color: var(--cyber-blue);
      margin: 25px 0 15px;
      font-size: 1.2em;
    }
    
    .entry-content ul, .entry-content ol {
      margin: 15px 0;
      padding-left: 25px;
    }
    
    .entry-content li {
      margin: 10px 0;
    }
    
    .entry-content blockquote {
      border-left: 3px solid var(--cyber-pink);
      padding: 15px 20px;
      margin: 20px 0;
      background: rgba(255, 0, 128, 0.05);
      color: var(--text-secondary);
      font-style: italic;
    }
    
    .entry-content code {
      background: var(--bg-secondary);
      padding: 3px 8px;
      border-radius: 4px;
      color: var(--cyber-blue);
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.9em;
    }
    
    .entry-content table {
      width: 100%;
      margin: 20px 0;
      border-collapse: collapse;
    }
    
    .entry-content th,
    .entry-content td {
      padding: 12px 15px;
      border: 1px solid var(--border);
      text-align: left;
    }
    
    .entry-content th {
      background: var(--bg-secondary);
      color: var(--accent);
      font-weight: 600;
      text-transform: uppercase;
      font-size: 0.85em;
      letter-spacing: 0.05em;
    }
    
    .entry-content td {
      background: var(--bg-card);
    }
    
    .entry-content strong {
      color: var(--text-primary);
    }
    
    /* Tags */
    .tag {
      display: inline-block;
      background: rgba(0, 255, 159, 0.1);
      color: var(--accent);
      padding: 4px 12px;
      border-radius: 2px;
      font-size: 0.8em;
      margin-right: 8px;
      border: 1px solid rgba(0, 255, 159, 0.2);
      font-family: 'JetBrains Mono', monospace;
    }
    
    /* Links */
    a { 
      color: var(--accent); 
      text-decoration: none;
      transition: all 0.3s;
    }
    
    a:hover { 
      text-shadow: 0 0 10px var(--accent-glow);
    }
    
    .read-link {
      display: inline-block;
      margin-top: 15px;
      padding: 8px 16px;
      background: transparent;
      border: 1px solid var(--border);
      border-radius: 4px;
      color: var(--accent);
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.85em;
      transition: all 0.3s;
    }
    
    .read-link:hover {
      background: var(--accent);
      color: var(--bg-primary);
      border-color: var(--accent);
      box-shadow: 0 0 20px var(--accent-glow);
    }
    
    .back-link {
      display: inline-block;
      margin: 20px 0;
      padding: 10px 20px;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 4px;
      font-family: 'JetBrains Mono', monospace;
      transition: all 0.3s;
    }
    
    .back-link:hover {
      border-color: var(--accent);
      box-shadow: 0 0 15px var(--accent-glow);
    }
    
    /* Footer */
    footer {
      text-align: center;
      padding: 40px 0;
      margin-top: 50px;
      border-top: 1px solid var(--border);
      color: var(--text-muted);
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.9em;
      position: relative;
    }
    
    footer::before {
      content: '';
      position: absolute;
      top: 0;
      left: 50%;
      transform: translateX(-50%);
      width: 100px;
      height: 1px;
      background: linear-gradient(90deg, transparent, var(--accent), transparent);
    }
    
    /* Scrollbar */
    ::-webkit-scrollbar {
      width: 8px;
    }
    
    ::-webkit-scrollbar-track {
      background: var(--bg-primary);
    }
    
    ::-webkit-scrollbar-thumb {
      background: var(--border);
      border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
      background: var(--accent);
    }
    
    /* Mobile */
    @media (max-width: 600px) {
      .container { padding: 15px; }
      h1 { font-size: 2em; }
      .logo { width: 100px; height: 100px; }
      .stat-value { font-size: 1.6em; }
      .entry { padding: 20px; }
    }
    
    /* 实时持仓卡片样式 */
    .position-card {
      background: var(--bg-card);
      border: 1px solid var(--cyber-blue);
      border-radius: 8px;
      padding: 20px;
      margin: 30px 0;
      position: relative;
      overflow: hidden;
      box-shadow: 0 0 30px rgba(0, 212, 255, 0.15);
    }
    
    .position-card::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 3px;
      background: linear-gradient(90deg, var(--cyber-blue), var(--accent), var(--cyber-pink));
      animation: gradientMove 3s linear infinite;
    }
    
    @keyframes gradientMove {
      0% { background-position: 0% 50%; }
      100% { background-position: 200% 50%; }
    }
    
    .position-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      padding-bottom: 15px;
      border-bottom: 1px solid var(--border);
    }
    
    .position-header h3 {
      color: var(--cyber-blue);
      font-size: 1.2em;
      margin: 0;
    }
    
    .live-badge {
      background: rgba(0, 255, 159, 0.1);
      color: var(--accent);
      padding: 4px 12px;
      border-radius: 20px;
      font-size: 0.75em;
      font-family: 'JetBrains Mono', monospace;
      animation: pulse 2s ease-in-out infinite;
    }
    
    .position-item {
      background: var(--bg-secondary);
      border-radius: 8px;
      padding: 15px;
      margin-bottom: 15px;
      border: 1px solid var(--border);
    }
    
    .position-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 0;
    }
    
    .position-row:not(:last-child) {
      border-bottom: 1px solid var(--border);
    }
    
    .position-row .coin {
      font-size: 1.3em;
      font-weight: 700;
      color: var(--text-primary);
      font-family: 'JetBrains Mono', monospace;
    }
    
    .position-row .side {
      padding: 4px 10px;
      border-radius: 4px;
      font-size: 0.8em;
      font-weight: 600;
      text-transform: uppercase;
    }
    
    .position-row .side.long {
      background: rgba(0, 255, 159, 0.15);
      color: var(--accent);
      border: 1px solid var(--accent);
    }
    
    .position-row .side.short {
      background: rgba(255, 0, 128, 0.15);
      color: var(--cyber-pink);
      border: 1px solid var(--cyber-pink);
    }
    
    .position-row .size {
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-secondary);
    }
    
    .position-row .label {
      color: var(--text-muted);
      font-size: 0.9em;
    }
    
    .position-row .value {
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-primary);
    }
    
    .position-row .value.price-live {
      color: var(--cyber-blue);
    }
    
    .pnl-row .value.profit {
      color: var(--accent);
      text-shadow: 0 0 10px var(--accent-glow);
      font-weight: 600;
    }
    
    .pnl-row .value.loss {
      color: var(--cyber-pink);
      text-shadow: 0 0 10px rgba(255, 0, 128, 0.5);
      font-weight: 600;
    }
    
    .prices-bar {
      display: flex;
      justify-content: center;
      gap: 30px;
      padding: 15px;
      background: var(--bg-secondary);
      border-radius: 4px;
      margin-top: 10px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.9em;
      color: var(--text-secondary);
    }
    
    .position-footer {
      text-align: right;
      margin-top: 15px;
      padding-top: 15px;
      border-top: 1px solid var(--border);
      font-size: 0.8em;
      color: var(--text-muted);
      font-family: 'JetBrains Mono', monospace;
    }
    
    .no-position {
      text-align: center;
      padding: 30px;
      color: var(--text-muted);
      font-style: italic;
    }
    
    .loading {
      text-align: center;
      padding: 30px;
      color: var(--cyber-blue);
    }
    
    .error {
      text-align: center;
      padding: 30px;
      color: var(--cyber-pink);
    }
    
    .stat-value.green { color: var(--accent); text-shadow: 0 0 20px var(--accent-glow); }
    .stat-value.blue { color: var(--cyber-blue); text-shadow: 0 0 20px rgba(0, 212, 255, 0.5); }
    .stat-value.pink { color: var(--cyber-pink); text-shadow: 0 0 20px rgba(255, 0, 128, 0.5); }
    .stat-value.red { color: var(--cyber-pink); text-shadow: 0 0 20px rgba(255, 0, 128, 0.5); }
    
    .stat-detail {
      font-size: 0.7em;
      color: var(--text-muted);
      margin-top: 5px;
      font-family: 'JetBrains Mono', monospace;
    }
    
    .live-dot {
      color: var(--accent);
      font-size: 0.8em;
      animation: pulse 2s ease-in-out infinite;
      margin-left: 5px;
    }
    
    .live-card {
      position: relative;
    }
    
    .live-card::after {
      content: 'LIVE';
      position: absolute;
      top: 8px;
      right: 8px;
      background: rgba(0, 255, 159, 0.1);
      color: var(--accent);
      padding: 2px 6px;
      border-radius: 3px;
      font-size: 0.6em;
      font-family: 'JetBrains Mono', monospace;
      letter-spacing: 0.05em;
    }
  </style>
</head>
<body>
  <div class="container">
    ${content}
    <footer>
      <p>🐴 小牛马 × AI Trading Experiment</p>
      <p style="margin-top: 10px; font-size: 0.8em;">Powered by OpenClaw</p>
    </footer>
  </div>
</body>
</html>`;
}

// 首页
app.get('/', (req, res) => {
  const statsHTML = `
    <div class="stat-card">
      <div class="stat-label">📅 启动资金</div>
      <div class="stat-value green">$98</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">💰 当前余额</div>
      <div class="stat-value blue">$${STATS.balance.toFixed(2)}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">📈 总收益</div>
      <div class="stat-value pink">${STATS.returnPct >= 0 ? '+' : ''}${STATS.returnPct.toFixed(1)}%</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">🎯 完成交易</div>
      <div class="stat-value green">${STATS.trades}</div>
    </div>
  `;
  
  // 钱包地址卡片
  const walletHTML = VERIFICATION ? `
    <div class="wallet-card">
      <h3>💰 交易钱包</h3>
      <div>
        <span style="color: var(--text-muted); font-size: 0.85em; font-family: 'JetBrains Mono', monospace;">WALLET ADDRESS</span>
        <code>${VERIFICATION.tradingAccount}</code>
      </div>
      <div class="wallet-info">
        <strong>充值说明:</strong><br>
        • 网络: <strong>${VERIFICATION.depositChain}</strong><br>
        • 币种: <strong>${VERIFICATION.depositToken}</strong><br>
        • 备注: ${VERIFICATION.depositNote}
      </div>
    </div>
  ` : '';
  
  const entriesHTML = ENTRIES.slice(0, 10).map(entry => {
    const preview = entry.content.substring(0, 200).replace(/\*/g, '').replace(/\n/g, ' ');
    return `
    <div class="entry">
      <h2><a href="/entry/${entry.slug}">${entry.title}</a></h2>
      <div class="entry-meta">
        📅 ${formatDate(entry.date)} 
        ${entry.tags.map(t => `<span class="tag">#${t}</span>`).join('')}
      </div>
      <div class="entry-content">
        <p>${preview}...</p>
      </div>
      <a href="/entry/${entry.slug}" class="read-link">阅读全文 →</a>
    </div>
  `}).join('');
  
  const content = `
    <header>
      <img src="/logo_256.png" alt="小牛马" class="logo">
      <h1>🐴 小牛马的交易日记</h1>
      <p class="subtitle">// AI Trading Experiment v1.0</p>
      <div style="margin-top: 20px; display: flex; justify-content: center; gap: 15px; flex-wrap: wrap;">
        <a href="/" style="background: var(--bg-card); padding: 8px 16px; border-radius: 4px; border: 1px solid var(--border); font-size: 0.9em;">🏠 首页</a>
        <a href="/strategy" style="background: var(--bg-card); padding: 8px 16px; border-radius: 4px; border: 1px solid var(--accent); font-size: 0.9em;">🎯 交易策略</a>
        <a href="/learn" style="background: var(--bg-card); padding: 8px 16px; border-radius: 4px; border: 1px solid var(--border); font-size: 0.9em;">📚 学习资料</a>
      </div>
    </header>
    
    <div class="stats" id="stats-container">
      ${statsHTML}
    </div>
    
    <!-- 实时持仓区域 -->
    <div class="position-card" id="position-card" style="display:none;">
      <div class="position-header">
        <h3>📊 实时持仓</h3>
        <span class="live-badge">● LIVE</span>
      </div>
      <div id="position-content">
        <div class="loading">加载中...</div>
      </div>
      <div class="position-footer">
        <span id="update-time">--</span>
      </div>
    </div>
    
    ${walletHTML}
    
    <div class="entries">
      <h2>📝 交易日志</h2>
      ${entriesHTML}
    </div>
    
    <script>
      // 实时持仓更新
      async function updatePosition() {
        try {
          const res = await fetch('/api/position');
          const data = await res.json();
          
          if (!data.success) {
            document.getElementById('position-content').innerHTML = '<div class="error">获取数据失败</div>';
            return;
          }
          
          const { account, positions, prices } = data;
          
          // 更新顶部统计
          const statsContainer = document.getElementById('stats-container');
          const pnlClass = account.totalPnl >= 0 ? 'green' : 'red';
          const pnlSign = account.totalPnl >= 0 ? '+' : '';
          statsContainer.innerHTML = \`
            <div class="stat-card">
              <div class="stat-label">📅 启动资金</div>
              <div class="stat-value green">$\${account.initialCapital}</div>
            </div>
            <div class="stat-card live-card">
              <div class="stat-label">💰 总资产 <span class="live-dot">●</span></div>
              <div class="stat-value blue">$\${account.totalValue.toFixed(2)}</div>
              <div class="stat-detail">$\${account.spotValue.toFixed(2)} + $\${account.perpValue.toFixed(2)}</div>
            </div>
            <div class="stat-card live-card">
              <div class="stat-label">📈 总收益 <span class="live-dot">●</span></div>
              <div class="stat-value \${pnlClass}">\${pnlSign}\${account.totalPnlPct.toFixed(2)}%</div>
            </div>
            <div class="stat-card live-card">
              <div class="stat-label">💵 未实现盈亏 <span class="live-dot">●</span></div>
              <div class="stat-value \${pnlClass}">\${pnlSign}$\${account.totalPnl.toFixed(2)}</div>
            </div>
          \`;
          
          // 显示持仓卡片
          const card = document.getElementById('position-card');
          card.style.display = 'block';
          
          let html = '';
          
          if (positions.length === 0) {
            html = '<div class="no-position">当前无持仓</div>';
          } else {
            positions.forEach(pos => {
              const pnlClass = pos.pnl >= 0 ? 'profit' : 'loss';
              const pnlSign = pos.pnl >= 0 ? '+' : '';
              const sideClass = pos.side === 'LONG' ? 'long' : 'short';
              
              html += \`
                <div class="position-item">
                  <div class="position-row">
                    <span class="coin">\${pos.coin}</span>
                    <span class="side \${sideClass}">\${pos.side}</span>
                    <span class="size">\${pos.size}</span>
                  </div>
                  <div class="position-row">
                    <span class="label">开仓价</span>
                    <span class="value">$\${pos.entryPx.toLocaleString()}</span>
                  </div>
                  <div class="position-row">
                    <span class="label">现价</span>
                    <span class="value price-live">$\${pos.currentPx.toLocaleString()}</span>
                  </div>
                  <div class="position-row pnl-row">
                    <span class="label">盈亏</span>
                    <span class="value \${pnlClass}">\${pnlSign}$\${pos.pnl.toFixed(2)} (\${pnlSign}\${pos.pnlPct.toFixed(2)}%)</span>
                  </div>
                </div>
              \`;
            });
          }
          
          // 显示价格
          html += \`
            <div class="prices-bar">
              <span>BTC: $\${prices.BTC.toLocaleString()}</span>
              <span>ETH: $\${prices.ETH.toLocaleString()}</span>
            </div>
          \`;
          
          document.getElementById('position-content').innerHTML = html;
          document.getElementById('update-time').textContent = '更新于 ' + new Date().toLocaleTimeString('zh-CN');
          
        } catch (err) {
          console.error('Failed to update position:', err);
        }
      }
      
      // 立即更新一次，然后每 30 秒更新
      updatePosition();
      setInterval(updatePosition, 30000);
    </script>
  `;
  
  res.send(getHTML(content));
});

// 单篇文章
app.get('/entry/:slug', (req, res) => {
  const entry = ENTRIES.find(e => e.slug === req.params.slug);
  
  if (!entry) {
    return res.status(404).send(getHTML('<header><h1>404 - 文章未找到</h1><p><a href="/">← 返回首页</a></p></header>'));
  }
  
  const content = `
    <header>
      <h1>${entry.title}</h1>
      <p class="subtitle">
        📅 ${formatDate(entry.date)} 
        ${entry.tags.map(t => `<span class="tag">#${t}</span>`).join('')}
      </p>
      <div style="margin-top: 15px; display: flex; justify-content: center; gap: 15px;">
        <a href="/" style="font-size: 0.85em;">← 返回首页</a>
        <a href="/strategy" style="font-size: 0.85em;">🎯 交易策略</a>
      </div>
    </header>
    
    <div class="entry" style="margin-top: 20px;">
      <div class="entry-content">
        ${renderMarkdown(entry.content)}
      </div>
    </div>
    
    <a href="/" class="back-link">← 返回首页</a>
  `;
  
  res.send(getHTML(content));
});

// 策略页面
app.get('/strategy', (req, res) => {
  const strat = STRATEGY?.strategy || {};
  const indicators = STRATEGY?.indicators || [];
  const entryRules = STRATEGY?.entryRules || {};
  const exitRules = STRATEGY?.exitRules || {};
  const risk = STRATEGY?.riskManagement || {};
  
  const indicatorsHTML = indicators.map(ind => `
    <div class="position-item" style="margin-bottom: 10px;">
      <div class="position-row">
        <span class="coin" style="font-size: 1.1em;">${ind.name}</span>
        <span class="tag">周期: ${ind.period}</span>
      </div>
      <div style="color: var(--text-secondary); margin-top: 8px; font-size: 0.9em;">
        ${ind.description}
      </div>
    </div>
  `).join('');
  
  const longRules = (entryRules.long || []).map(rule => `<li style="margin: 8px 0;">${rule}</li>`).join('');
  const shortRules = (entryRules.short || []).map(rule => `<li style="margin: 8px 0;">${rule}</li>`).join('');
  
  const content = `
    <header>
      <h1>🎯 交易策略</h1>
      <p class="subtitle">${strat.name || '趋势跟踪策略'} <span class="tag">v${strat.version || '1.0'}</span></p>
      <div style="margin-top: 15px; display: flex; justify-content: center; gap: 15px;">
        <a href="/" style="font-size: 0.85em;">← 返回首页</a>
        <a href="/learn" style="font-size: 0.85em;">📚 学习资料</a>
      </div>
    </header>
    
    <div class="wallet-card" style="margin-top: 30px;">
      <h3>📋 策略概述</h3>
      <p style="color: var(--text-secondary); line-height: 1.8;">${strat.description || '基于多时间框架均线系统的趋势跟踪策略'}</p>
      <div style="margin-top: 15px; display: flex; gap: 20px; flex-wrap: wrap;">
        <span class="tag">状态: ${strat.status === 'active' ? '✅ 运行中' : '⏸️ 暂停'}</span>
        <span class="tag">市场: ${(STRATEGY.markets?.primary || []).join(', ')}</span>
        <span class="tag">周期: ${STRATEGY.markets?.timeframe || '1h'}</span>
      </div>
    </div>
    
    <div class="position-card">
      <div class="position-header">
        <h3>📊 技术指标</h3>
      </div>
      ${indicatorsHTML || '<p style="color: var(--text-muted);">暂无指标配置</p>'}
    </div>
    
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin: 30px 0;">
      <div class="wallet-card" style="border-color: var(--accent);">
        <h3 style="color: var(--accent);">📈 做多条件</h3>
        <ul style="color: var(--text-secondary); padding-left: 20px;">
          ${longRules || '<li>暂无配置</li>'}
        </ul>
      </div>
      
      <div class="wallet-card" style="border-color: var(--cyber-pink);">
        <h3 style="color: var(--cyber-pink);">📉 做空条件</h3>
        <ul style="color: var(--text-secondary); padding-left: 20px;">
          ${shortRules || '<li>暂无配置</li>'}
        </ul>
      </div>
    </div>
    
    <div class="wallet-card">
      <h3>🚪 出场规则</h3>
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 15px;">
        <div class="stat-card" style="padding: 15px;">
          <div class="stat-label">止损</div>
          <div class="stat-value" style="font-size: 1.5em; color: var(--cyber-pink);">${exitRules.stopLoss || '-'}</div>
        </div>
        <div class="stat-card" style="padding: 15px;">
          <div class="stat-label">止盈</div>
          <div class="stat-value" style="font-size: 1.5em; color: var(--accent);">${exitRules.takeProfit || '-'}</div>
        </div>
        <div class="stat-card" style="padding: 15px;">
          <div class="stat-label">移动止损</div>
          <div class="stat-value" style="font-size: 1.5em; color: var(--cyber-blue);">${exitRules.trailingStop || '-'}</div>
        </div>
      </div>
    </div>
    
    <div class="position-card">
      <div class="position-header">
        <h3>🛡️ 风险管理</h3>
      </div>
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
        <div class="stat-card" style="padding: 15px;">
          <div class="stat-label">日最大回撤</div>
          <div class="stat-value pink" style="font-size: 1.5em;">${risk.maxDailyDrawdown || '-'}</div>
        </div>
        <div class="stat-card" style="padding: 15px;">
          <div class="stat-label">单笔止损</div>
          <div class="stat-value pink" style="font-size: 1.5em;">${risk.stopLossPerTrade || '-'}</div>
        </div>
        <div class="stat-card" style="padding: 15px;">
          <div class="stat-label">最大杠杆</div>
          <div class="stat-value blue" style="font-size: 1.5em;">${STRATEGY.positionSizing?.maxLeverage || '-'}x</div>
        </div>
        <div class="stat-card" style="padding: 15px;">
          <div class="stat-label">冷静期</div>
          <div class="stat-value" style="font-size: 1.5em;">${risk.cooldownAfterLoss || '-'}</div>
        </div>
      </div>
    </div>
    
    <a href="/" class="back-link">← 返回首页</a>
  `;
  
  res.send(getHTML(content));
});

// 学习资料页面
app.get('/learn', (req, res) => {
  const learnHTML = LEARN_ENTRIES.map(entry => {
    const preview = entry.content.substring(0, 150).replace(/\*/g, '').replace(/\n/g, ' ');
    return `
    <div class="entry">
      <h2><a href="/learn/${entry.slug}">${entry.title}</a></h2>
      <div class="entry-meta">
        📅 ${formatDate(entry.date)}
        ${entry.tags.map(t => `<span class="tag">#${t}</span>`).join('')}
      </div>
      <div class="entry-content">
        <p>${preview}...</p>
      </div>
      <a href="/learn/${entry.slug}" class="read-link">阅读全文 →</a>
    </div>
  `}).join('') || '<p style="color: var(--text-muted); text-align: center; padding: 40px;">暂无学习资料</p>';
  
  const content = `
    <header>
      <h1>📚 学习资料</h1>
      <p class="subtitle">交易策略、市场分析与风险管理</p>
      <div style="margin-top: 15px; display: flex; justify-content: center; gap: 15px;">
        <a href="/" style="font-size: 0.85em;">← 返回首页</a>
        <a href="/strategy" style="font-size: 0.85em;">🎯 交易策略</a>
      </div>
    </header>
    
    <div class="entries">
      ${learnHTML}
    </div>
    
    <a href="/" class="back-link">← 返回首页</a>
  `;
  
  res.send(getHTML(content));
});

// 学习资料单篇文章
app.get('/learn/:slug', (req, res) => {
  const entry = LEARN_ENTRIES.find(e => e.slug === req.params.slug);
  
  if (!entry) {
    return res.status(404).send(getHTML('<header><h1>404 - 文章未找到</h1><p><a href="/">← 返回首页></p></header>'));
  }
  
  const content = `
    <header>
      <h1>${entry.title}</h1>
      <p class="subtitle">
        📅 ${formatDate(entry.date)} 
        ${entry.tags.map(t => `<span class="tag">#${t}</span>`).join('')}
      </p>
      <div style="margin-top: 15px; display: flex; justify-content: center; gap: 15px;">
        <a href="/" style="font-size: 0.85em;">← 返回首页</a>
        <a href="/learn" style="font-size: 0.85em;">📚 学习资料</a>
        <a href="/strategy" style="font-size: 0.85em;">🎯 交易策略</a>
      </div>
    </header>
    
    <div class="entry" style="margin-top: 20px;">
      <div class="entry-content">
        ${renderMarkdown(entry.content)}
      </div>
    </div>
    
    <a href="/learn" class="back-link">← 返回学习资料</a>
  `;
  
  res.send(getHTML(content));
});

// 404 处理
app.use((req, res) => {
  res.status(404).send(getHTML('<header><h1>404 - 页面未找到</h1><p><a href="/">← 返回首页</a></p></header>'));
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`\n🐴 小牛马炒币网站启动成功！\n`);
  console.log(`本地访问: http://localhost:${PORT}`);
  console.log(`公网访问: http://15.152.86.199:${PORT}`);
  console.log(`\n按 Ctrl+C 停止服务器\n`);
});

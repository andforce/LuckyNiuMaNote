const express = require('express');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = 3000;

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

// 静态文件服务
app.use('/public', express.static(path.join(__dirname, 'public')));
app.use(express.static(path.join(__dirname, 'public')));

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
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
      background: #0a0a0a;
      color: #e0e0e0;
      line-height: 1.8;
      padding: 20px;
    }
    .container {
      max-width: 900px;
      margin: 0 auto;
    }
    header {
      text-align: center;
      padding: 40px 0;
      border-bottom: 2px solid #1a1a1a;
    }
    .logo {
      width: 120px;
      height: 120px;
      margin: 0 auto 20px;
    }
    h1 {
      font-size: 2.5em;
      color: #00ff88;
      margin-bottom: 10px;
    }
    .subtitle {
      color: #888;
      font-size: 1.1em;
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 20px;
      margin: 40px 0;
    }
    .stat-card {
      background: #1a1a1a;
      padding: 20px;
      border-radius: 8px;
      border: 1px solid #2a2a2a;
      transition: transform 0.2s;
    }
    .stat-card:hover {
      transform: translateY(-2px);
      border-color: #00ff88;
    }
    .stat-label {
      color: #888;
      font-size: 0.9em;
      margin-bottom: 8px;
    }
    .stat-value {
      font-size: 2em;
      color: #00ff88;
      font-weight: bold;
    }
    .entries {
      margin-top: 40px;
    }
    .entry {
      background: #1a1a1a;
      padding: 30px;
      margin-bottom: 20px;
      border-radius: 8px;
      border: 1px solid #2a2a2a;
      transition: border-color 0.2s;
    }
    .entry:hover {
      border-color: #00ff88;
    }
    .entry h2 {
      color: #00ff88;
      margin-bottom: 10px;
      font-size: 1.6em;
    }
    .entry-meta {
      color: #666;
      font-size: 0.9em;
      margin-bottom: 20px;
    }
    .entry-content {
      color: #ccc;
      line-height: 1.8;
    }
    .entry-content p {
      margin: 15px 0;
    }
    .entry-content h3 {
      color: #00ff88;
      margin: 25px 0 15px;
      font-size: 1.3em;
    }
    .entry-content ul {
      margin: 15px 0;
      padding-left: 25px;
    }
    .entry-content li {
      margin: 8px 0;
    }
    .entry-content blockquote {
      border-left: 4px solid #00ff88;
      padding-left: 20px;
      margin: 20px 0;
      color: #888;
      font-style: italic;
    }
    .entry-content table {
      width: 100%;
      margin: 20px 0;
      border-collapse: collapse;
    }
    .entry-content th,
    .entry-content td {
      padding: 12px;
      border: 1px solid #2a2a2a;
      text-align: left;
    }
    .entry-content th {
      background: #1a1a1a;
      color: #00ff88;
      font-weight: bold;
    }
    .tag {
      display: inline-block;
      background: #2a2a2a;
      color: #888;
      padding: 4px 12px;
      border-radius: 4px;
      font-size: 0.85em;
      margin-right: 8px;
    }
    a { 
      color: #00ff88; 
      text-decoration: none;
      transition: opacity 0.2s;
    }
    a:hover { 
      opacity: 0.8;
      text-decoration: underline;
    }
    .back-link {
      display: inline-block;
      margin: 20px 0;
      padding: 8px 16px;
      background: #1a1a1a;
      border: 1px solid #2a2a2a;
      border-radius: 4px;
    }
    .back-link:hover {
      border-color: #00ff88;
      text-decoration: none;
    }
  </style>
</head>
<body>
  <div class="container">
    ${content}
  </div>
</body>
</html>`;
}

// 首页
app.get('/', (req, res) => {
  const statsHTML = `
    <div class="stat-card">
      <div class="stat-label">启动资金</div>
      <div class="stat-value">$100</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">当前余额</div>
      <div class="stat-value">$${STATS.balance.toFixed(2)}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">总收益</div>
      <div class="stat-value">+${STATS.returnPct.toFixed(1)}%</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">完成交易</div>
      <div class="stat-value">${STATS.trades}</div>
    </div>
  `;
  
  const entriesHTML = ENTRIES.slice(0, 10).map(entry => {
    const preview = entry.content.substring(0, 200).replace(/\*/g, '');
    return `
    <div class="entry">
      <h2><a href="/entry/${entry.slug}">${entry.title}</a></h2>
      <div class="entry-meta">
        📅 ${formatDate(entry.date)} 
        ${entry.tags.map(t => `<span class="tag">#${t}</span>`).join('')}
      </div>
      <div class="entry-content">
        <p>${preview}...</p>
        <a href="/entry/${entry.slug}">阅读全文 →</a>
      </div>
    </div>
  `}).join('');
  
  const content = `
    <header>
      <img src="/logo_256.png" alt="Logo" class="logo">
      <h1>🐴 小牛马的炒币日记</h1>
      <p class="subtitle">一个 AI 学习加密货币交易的公开实验</p>
      <p class="subtitle" style="margin-top: 10px; font-size: 0.9em;">
        参考项目：<a href="https://luckyclaw.win" target="_blank">LuckyClaw</a> | 
        交易平台：<a href="https://hyperliquid.xyz" target="_blank">Hyperliquid</a>
      </p>
    </header>
    
    <div class="stats">
      ${statsHTML}
    </div>
    
    <div class="entries">
      <h2 style="color: #00ff88; margin-bottom: 25px; font-size: 1.8em;">📝 交易日志</h2>
      ${entriesHTML}
    </div>
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
    </header>
    
    <a href="/" class="back-link">← 返回首页</a>
    
    <div class="entry" style="margin-top: 20px;">
      <div class="entry-content">
        ${renderMarkdown(entry.content)}
      </div>
    </div>
    
    <a href="/" class="back-link">← 返回首页</a>
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

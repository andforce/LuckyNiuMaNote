#!/usr/bin/env python3
"""
Island Trader - 岛主的自动交易机器人
24/7 运行，趋势跟踪策略，最大3倍杠杆
"""

import os
import sys
import json
import time
import logging
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# 添加 trading-scripts 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / 'trading-scripts'))

from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants
from eth_account import Account

# ============== 配置 ==============
CONFIG = {
    'main_wallet': '0xfFd91a584cf6419b92E58245898D2A9281c628eb',
    'api_wallet': '0xD50affea03a6DdcA663611d5487Cb962b0BDA892',
    'api_private_key': os.getenv('HL_API_KEY', ''),
    'symbols': ['BTC', 'ETH'],
    'timeframe': '1h',
    'max_leverage': 3,
    'default_leverage': 2,
    'max_position_usd': 294,  # $98 * 3
    'min_order_value': 10,    # Hyperliquid 最小订单金额
    'stop_loss_atr_mult': 2,
    'take_profit_atr_mult': 3,
    'check_interval': 60,     # 每秒检查一次
    'trade_cooldown': 3600,   # 亏损后冷却1小时
}

# ============== 日志配置 ==============
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/ubuntu/.openclaw/workspace/LuckyNiuMaNote/logs/trader.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('IslandTrader')

# ============== 技术指标计算 ==============
def ema(data: List[float], period: int) -> List[float]:
    """计算指数移动平均线"""
    multiplier = 2 / (period + 1)
    ema = [data[0]]
    for price in data[1:]:
        ema.append(price * multiplier + ema[-1] * (1 - multiplier))
    return ema

def atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> float:
    """计算平均真实波幅"""
    tr_list = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        tr_list.append(tr)
    
    if len(tr_list) >= period:
        return sum(tr_list[-period:]) / period
    return sum(tr_list) / len(tr_list) if tr_list else 0

# ============== 核心交易类 ==============
class IslandTrader:
    def __init__(self):
        self.info = Info(constants.MAINNET_API_URL, skip_ws=True)
        self.account = Account.from_key(CONFIG['api_private_key'])
        self.exchange = Exchange(
            self.account, 
            constants.MAINNET_API_URL, 
            account_address=CONFIG['main_wallet']
        )
        self.last_trade_time = None
        self.last_loss_time = None
        self.daily_pnl = 0.0
        self.peak_balance = 0.0
        
    def get_klines(self, symbol: str, interval: str = '1h', limit: int = 100) -> List[Dict]:
        """获取K线数据"""
        try:
            url = "https://api.hyperliquid.xyz/info"
            end_time = int(time.time() * 1000)
            start_time = end_time - (limit * 60 * 60 * 1000)  # 根据limit计算开始时间
            
            payload = {
                "type": "candleSnapshot",
                "req": {
                    "coin": symbol,
                    "interval": interval,
                    "startTime": start_time,
                    "endTime": end_time
                }
            }
            
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                candles = []
                for candle in data:
                    # API返回格式: {'t': timestamp, 'o': open, 'h': high, 'l': low, 'c': close, 'v': volume}
                    candles.append({
                        'timestamp': candle['t'],
                        'open': float(candle['o']),
                        'high': float(candle['h']),
                        'low': float(candle['l']),
                        'close': float(candle['c']),
                        'volume': float(candle['v'])
                    })
                return candles
        except Exception as e:
            logger.error(f"获取K线失败 {symbol}: {e}")
        return []
    
    def analyze_trend(self, symbol: str) -> Dict:
        """分析趋势并生成信号"""
        klines = self.get_klines(symbol)
        if len(klines) < 60:
            return {'action': 'HOLD', 'reason': '数据不足'}
        
        closes = [k['close'] for k in klines]
        highs = [k['high'] for k in klines]
        lows = [k['low'] for k in klines]
        
        # 计算EMA
        ema9 = ema(closes, 9)
        ema21 = ema(closes, 21)
        ema55 = ema(closes, 55)
        
        # 计算ATR
        current_atr = atr(highs, lows, closes, 14)
        current_price = closes[-1]
        
        # 趋势判断
        trend_up = ema9[-1] > ema21[-1] > ema55[-1]
        trend_down = ema9[-1] < ema21[-1] < ema55[-1]
        
        # 金叉/死叉判断
        golden_cross = ema9[-2] <= ema21[-2] and ema9[-1] > ema21[-1]
        death_cross = ema9[-2] >= ema21[-2] and ema9[-1] < ema21[-1]
        
        # 生成信号
        if trend_up and golden_cross:
            confidence = self._calc_confidence(closes, ema9, ema21, ema55)
            position_size = self._calc_position_size(confidence)
            stop_loss = current_price - 2 * current_atr
            take_profit = current_price + 3 * current_atr
            
            return {
                'action': 'BUY',
                'symbol': symbol,
                'confidence': confidence,
                'size': position_size,
                'entry_price': current_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'atr': current_atr,
                'reason': f'{symbol} 多头趋势确立，9/21金叉，ATR={current_atr:.2f}'
            }
        
        elif trend_down and death_cross:
            confidence = self._calc_confidence(closes, ema9, ema21, ema55)
            position_size = self._calc_position_size(confidence)
            stop_loss = current_price + 2 * current_atr
            take_profit = current_price - 3 * current_atr
            
            return {
                'action': 'SELL',
                'symbol': symbol,
                'confidence': confidence,
                'size': position_size,
                'entry_price': current_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'atr': current_atr,
                'reason': f'{symbol} 空头趋势确立，9/21死叉，ATR={current_atr:.2f}'
            }
        
        return {'action': 'HOLD', 'reason': f'{symbol} 无明确信号'}
    
    def _calc_confidence(self, closes, ema9, ema21, ema55) -> float:
        """计算信号信心度"""
        confidence = 0.5
        
        # 均线发散程度
        ma_spread = abs(ema9[-1] - ema55[-1]) / ema55[-1]
        confidence += min(ma_spread * 10, 0.2)
        
        # 价格与均线距离
        price_ma_distance = abs(closes[-1] - ema21[-1]) / ema21[-1]
        confidence += min(price_ma_distance * 5, 0.1)
        
        # 趋势一致性
        if (ema9[-1] > ema21[-1] > ema55[-1]) or (ema9[-1] < ema21[-1] < ema55[-1]):
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _calc_position_size(self, confidence: float) -> float:
        """计算仓位大小"""
        max_size = CONFIG['max_position_usd']
        size = max_size * confidence
        # 确保最小订单金额
        if size < CONFIG['min_order_value']:
            return 0
        return round(size, 2)
    
    def get_account_state(self) -> Dict:
        """获取账户状态"""
        try:
            state = self.info.user_state(CONFIG['main_wallet'])
            margin = state.get('marginSummary', {})
            return {
                'account_value': float(margin.get('accountValue', 0)),
                'withdrawable': float(state.get('withdrawable', 0)),
                'positions': state.get('assetPositions', [])
            }
        except Exception as e:
            logger.error(f"获取账户状态失败: {e}")
            return {'account_value': 0, 'withdrawable': 0, 'positions': []}
    
    def get_open_orders(self) -> List[Dict]:
        """获取当前挂单"""
        try:
            orders = self.info.open_orders(CONFIG['main_wallet'])
            return orders
        except Exception as e:
            logger.error(f"获取挂单失败: {e}")
            return []
    
    def place_order(self, symbol: str, is_buy: bool, size: float, price: float, reduce_only: bool = False) -> Dict:
        """下单"""
        try:
            result = self.exchange.order(
                symbol,
                is_buy,
                size,
                price,
                {"limit": {"tif": "Gtc"}},  # Good till cancel
                reduce_only=reduce_only
            )
            logger.info(f"下单结果: {result}")
            return result
        except Exception as e:
            logger.error(f"下单失败: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def cancel_all_orders(self, symbol: str):
        """取消所有挂单"""
        try:
            orders = self.get_open_orders()
            for order in orders:
                if order.get('coin') == symbol:
                    self.exchange.cancel(symbol, order.get('oid'))
                    logger.info(f"取消订单 {order.get('oid')}")
        except Exception as e:
            logger.error(f"取消订单失败: {e}")
    
    def can_trade(self) -> bool:
        """检查是否可以交易（风控）"""
        # 检查冷却期
        if self.last_loss_time:
            if datetime.now() - self.last_loss_time < timedelta(seconds=CONFIG['trade_cooldown']):
                logger.info("冷却期中，跳过交易")
                return False
        
        # 检查日回撤
        account = self.get_account_state()
        current_value = account['account_value']
        
        if self.peak_balance == 0:
            self.peak_balance = current_value
        
        if current_value > self.peak_balance:
            self.peak_balance = current_value
        
        if self.peak_balance > 0:
            drawdown = (self.peak_balance - current_value) / self.peak_balance
            if drawdown >= 0.20:  # 20% 回撤
                logger.warning(f"日回撤 {drawdown*100:.1f}% 超过限制，停止交易")
                return False
        
        return True
    
    def has_position(self, symbol: str) -> bool:
        """检查是否已有持仓"""
        account = self.get_account_state()
        for pos in account.get('positions', []):
            if pos.get('position', {}).get('coin') == symbol:
                return True
        return False
    
    def log_trade(self, signal: Dict, result: Dict):
        """记录交易日志到文件"""
        log_entry = {
            'time': datetime.now().isoformat(),
            'signal': signal,
            'result': result
        }
        
        log_file = Path('/home/ubuntu/.openclaw/workspace/LuckyNiuMaNote/logs/trades.jsonl')
        log_file.parent.mkdir(exist_ok=True)
        
        with open(log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    
    def run_cycle(self):
        """执行一次交易循环"""
        logger.info("=" * 50)
        logger.info("开始交易循环")
        
        # 检查风控
        if not self.can_trade():
            logger.info("风控阻止，跳过本次循环")
            return
        
        # 分析每个交易对
        for symbol in CONFIG['symbols']:
            # 检查是否已有持仓
            if self.has_position(symbol):
                logger.info(f"{symbol} 已有持仓，跳过")
                continue
            
            # 获取交易信号
            signal = self.analyze_trend(symbol)
            
            if signal['action'] == 'HOLD':
                logger.info(f"{symbol}: {signal['reason']}")
                continue
            
            # 检查仓位大小
            if signal['size'] < CONFIG['min_order_value']:
                logger.info(f"{symbol} 仓位太小 ({signal['size']})，跳过")
                continue
            
            # 执行交易
            logger.info(f"🎯 {symbol} 信号: {signal['action']}")
            logger.info(f"   信心度: {signal['confidence']*100:.1f}%")
            logger.info(f"   仓位: ${signal['size']}")
            logger.info(f"   入场价: ${signal['entry_price']:.2f}")
            logger.info(f"   止损: ${signal['stop_loss']:.2f}")
            logger.info(f"   止盈: ${signal['take_profit']:.2f}")
            
            is_buy = signal['action'] == 'BUY'
            
            # 取消现有挂单
            self.cancel_all_orders(symbol)
            
            # 下开仓单
            result = self.place_order(
                symbol, 
                is_buy, 
                signal['size'] / signal['entry_price'],  # size in coins
                signal['entry_price']
            )
            
            # 记录交易
            self.log_trade(signal, result)
            
            if result.get('status') == 'ok':
                logger.info(f"✅ {symbol} 下单成功")
                self.last_trade_time = datetime.now()
            else:
                logger.error(f"❌ {symbol} 下单失败: {result}")
    
    def run(self):
        """主循环"""
        logger.info("🚀 Island Trader 启动")
        logger.info(f"交易对: {CONFIG['symbols']}")
        logger.info(f"最大杠杆: {CONFIG['max_leverage']}x")
        logger.info(f"最大仓位: ${CONFIG['max_position_usd']}")
        
        while True:
            try:
                self.run_cycle()
            except Exception as e:
                logger.error(f"交易循环异常: {e}", exc_info=True)
            
            logger.info(f"等待 {CONFIG['check_interval']} 秒...")
            time.sleep(CONFIG['check_interval'])

if __name__ == '__main__':
    # 从配置文件读取私钥
    config_path = Path('/home/ubuntu/.openclaw/workspace/LuckyNiuMaNote/trading-scripts/.hl_config')
    if config_path.exists():
        with open(config_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith('API_PRIVATE_KEY='):
                    CONFIG['api_private_key'] = line.split('=', 1)[1]
                    break
    
    if not CONFIG['api_private_key']:
        logger.error("未找到 API_PRIVATE_KEY，请检查 .hl_config 文件")
        sys.exit(1)
    
    trader = IslandTrader()
    trader.run()

#!/usr/bin/env python3
"""
历史K线数据服务
提供带EMA和金叉死叉标记的K线数据
"""

import json
import requests
from datetime import datetime, timedelta
from typing import List, Dict

def ema(data: List[float], period: int) -> List[float]:
    """计算指数移动平均线"""
    multiplier = 2 / (period + 1)
    ema = [data[0]]
    for price in data[1:]:
        ema.append(price * multiplier + ema[-1] * (1 - multiplier))
    return ema

def get_klines_with_ema(symbol: str, days: int = 30) -> Dict:
    """获取K线数据并计算EMA和金叉死叉"""
    url = 'https://api.hyperliquid.xyz/info'
    end_time = int(datetime.now().timestamp() * 1000)
    start_time = end_time - (days * 24 * 60 * 60 * 1000)
    
    payload = {
        'type': 'candleSnapshot',
        'req': {
            'coin': symbol,
            'interval': '1h',
            'startTime': start_time,
            'endTime': end_time
        }
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=10)
        candles = resp.json()
        
        if not candles or len(candles) < 60:
            return {'success': False, 'error': '数据不足'}
        
        # 解析K线数据
        klines = []
        for c in candles:
            klines.append({
                'timestamp': c['t'],
                'open': float(c['o']),
                'high': float(c['h']),
                'low': float(c['l']),
                'close': float(c['c']),
                'volume': float(c['v'])
            })
        
        # 计算EMA
        closes = [k['close'] for k in klines]
        ema9 = ema(closes, 9)
        ema21 = ema(closes, 21)
        ema55 = ema(closes, 55)
        
        # 添加EMA到K线数据
        for i, k in enumerate(klines):
            k['ema9'] = ema9[i] if i < len(ema9) else None
            k['ema21'] = ema21[i] if i < len(ema21) else None
            k['ema55'] = ema55[i] if i < len(ema55) else None
        
        # 检测金叉死叉
        signals = []
        for i in range(1, len(klines)):
            prev = klines[i-1]
            curr = klines[i]
            
            if prev['ema9'] and prev['ema21'] and curr['ema9'] and curr['ema21']:
                # 金叉：EMA9上穿EMA21
                if prev['ema9'] <= prev['ema21'] and curr['ema9'] > curr['ema21']:
                    signals.append({
                        'type': 'golden_cross',
                        'timestamp': curr['timestamp'],
                        'price': curr['close'],
                        'index': i,
                        'label': '金叉买入'
                    })
                # 死叉：EMA9下穿EMA21
                elif prev['ema9'] >= prev['ema21'] and curr['ema9'] < curr['ema21']:
                    signals.append({
                        'type': 'death_cross',
                        'timestamp': curr['timestamp'],
                        'price': curr['close'],
                        'index': i,
                        'label': '死叉卖出'
                    })
        
        return {
            'success': True,
            'symbol': symbol,
            'klines': klines,
            'signals': signals
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

if __name__ == '__main__':
    # 测试
    result = get_klines_with_ema('BTC', 30)
    print(json.dumps(result, indent=2)[:1000])

# modules/data_fetcher.py

import requests
import pandas as pd
from datetime import datetime
from typing import Dict, Optional

class NSEDataFetcher:
    """Fetch data from NSE India"""
    
    BASE_URL = "https://www.nseindia.com"
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    @staticmethod
    def get_option_chain(symbol: str) -> Optional[Dict]:
        """Fetch option chain data for given symbol"""
        try:
            url = f"{NSEDataFetcher.BASE_URL}/api/option-chain-indices?symbol={symbol}"
            response = requests.get(url, headers=NSEDataFetcher.HEADERS, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching {symbol} data: {e}")
            return None
    
    @staticmethod
    def parse_option_chain(data: Dict, symbol: str) -> pd.DataFrame:
        """Parse NSE option chain data into structured DataFrame"""
        records = []
        
        if not data or 'records' not in data:
            return pd.DataFrame()
        
        spot_price = data['records']['underlyingValue']
        timestamp = data['records']['timestamp']
        
        for record in data['records']['data']:
            # Process Call options
            if 'CE' in record:
                ce = record['CE']
                records.append({
                    'symbol': symbol,
                    'strike': record['strikePrice'],
                    'option_type': 'CE',
                    'open_interest': ce['openInterest'],
                    'change_in_oi': ce['changeinOpenInterest'],
                    'volume': ce['totalTradedVolume'],
                    'iv': ce['impliedVolatility'] / 100 if ce['impliedVolatility'] else 0,
                    'last_price': ce['lastPrice'],
                    'bid_price': ce['bidprice'],
                    'ask_price': ce['askPrice'],
                    'spot_price': spot_price,
                    'timestamp': timestamp
                })
            
            # Process Put options
            if 'PE' in record:
                pe = record['PE']
                records.append({
                    'symbol': symbol,
                    'strike': record['strikePrice'],
                    'option_type': 'PE',
                    'open_interest': pe['openInterest'],
                    'change_in_oi': pe['changeinOpenInterest'],
                    'volume': pe['totalTradedVolume'],
                    'iv': pe['impliedVolatility'] / 100 if pe['impliedVolatility'] else 0,
                    'last_price': pe['lastPrice'],
                    'bid_price': pe['bidprice'],
                    'ask_price': pe['askPrice'],
                    'spot_price': spot_price,
                    'timestamp': timestamp
                })
        
        return pd.DataFrame(records)

class MarketData:
    """Market data utilities"""
    
    @staticmethod
    def get_spot_price(symbol: str) -> float:
        """Get current spot price - for demo, we'll use static. In production, use API."""
        if symbol == "NIFTY":
            return 22150.75
        elif symbol == "BANKNIFTY":
            return 48025.40
        return 0.0
    
    @staticmethod
    def get_vix() -> float:
        """Get India VIX"""
        return 14.25
    
    @staticmethod
    def get_market_status() -> str:
        """Get current market status"""
        current_time = datetime.now().time()
        market_open = datetime.strptime("09:15", "%H:%M").time()
        market_close = datetime.strptime("15:30", "%H:%M").time()
        
        if market_open <= current_time <= market_close:
            return "Open"
        else:
            return "Closed"

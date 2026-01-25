"""
Data fetching module for NSE options data
"""

import requests
import pandas as pd
from datetime import datetime
import time
import json


class NSEDataFetcher:
    """Fetch option chain data from NSE"""
    
    def __init__(self):
        self.base_url = "https://www.nseindia.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
    def _get_cookies(self):
        """Get cookies by visiting NSE homepage"""
        try:
            self.session.get(self.base_url, timeout=10)
            time.sleep(1)
        except Exception as e:
            print(f"Error getting cookies: {e}")
    
    def fetch_option_chain(self, symbol='NIFTY', expiry_date=None):
        """
        Fetch option chain data from NSE
        
        Args:
            symbol (str): Index symbol (NIFTY or BANKNIFTY)
            expiry_date (str): Expiry date in DD-MMM-YYYY format
        
        Returns:
            tuple: (DataFrame with options data, spot price)
        """
        # Get cookies first
        self._get_cookies()
        
        # Construct URL
        url = f"{self.base_url}/api/option-chain-indices?symbol={symbol}"
        
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if 'records' not in data:
                return None, None
            
            # Extract spot price
            spot_price = data['records']['underlyingValue']
            
            # Parse option chain data
            options_data = []
            
            for item in data['records']['data']:
                strike = item['strikePrice']
                expiry = item['expiryDate']
                
                # Filter by expiry if specified
                if expiry_date and expiry != expiry_date:
                    continue
                
                # Call data
                if 'CE' in item:
                    ce = item['CE']
                    options_data.append({
                        'strike': strike,
                        'expiry': expiry,
                        'type': 'CE',
                        'oi': ce.get('openInterest', 0),
                        'oi_change': ce.get('changeinOpenInterest', 0),
                        'volume': ce.get('totalTradedVolume', 0),
                        'iv': ce.get('impliedVolatility', 0),
                        'ltp': ce.get('lastPrice', 0),
                        'change': ce.get('change', 0),
                        'bid_qty': ce.get('bidQty', 0),
                        'ask_qty': ce.get('askQty', 0),
                    })
                
                # Put data
                if 'PE' in item:
                    pe = item['PE']
                    options_data.append({
                        'strike': strike,
                        'expiry': expiry,
                        'type': 'PE',
                        'oi': pe.get('openInterest', 0),
                        'oi_change': pe.get('changeinOpenInterest', 0),
                        'volume': pe.get('totalTradedVolume', 0),
                        'iv': pe.get('impliedVolatility', 0),
                        'ltp': pe.get('lastPrice', 0),
                        'change': pe.get('change', 0),
                        'bid_qty': pe.get('bidQty', 0),
                        'ask_qty': pe.get('askQty', 0),
                    })
            
            df = pd.DataFrame(options_data)
            return df, spot_price
            
        except Exception as e:
            print(f"Error fetching option chain: {e}")
            return None, None


def fetch_option_chain(symbol='NIFTY', expiry_date=None):
    """
    Wrapper function to fetch option chain
    
    Args:
        symbol (str): Index symbol
        expiry_date (str): Expiry date
    
    Returns:
        tuple: (DataFrame, spot_price)
    """
    fetcher = NSEDataFetcher()
    return fetcher.fetch_option_chain(symbol, expiry_date)


def generate_sample_data(symbol='NIFTY', spot_price=21500):
    """
    Generate sample option chain data for testing
    
    Args:
        symbol (str): Index symbol
        spot_price (float): Current spot price
    
    Returns:
        tuple: (DataFrame, spot_price)
    """
    import numpy as np
    
    # Generate strikes around spot
    strikes = np.arange(spot_price - 1000, spot_price + 1000, 50)
    
    options_data = []
    
    for strike in strikes:
        # Generate realistic OI based on distance from ATM
        distance = abs(strike - spot_price)
        base_oi = max(100000 - distance * 50, 10000)
        
        # Calls
        options_data.append({
            'strike': strike,
            'expiry': '25-JAN-2024',
            'type': 'CE',
            'oi': int(base_oi * np.random.uniform(0.8, 1.2)),
            'oi_change': int(np.random.uniform(-5000, 5000)),
            'volume': int(np.random.uniform(1000, 50000)),
            'iv': np.random.uniform(12, 18),
            'ltp': max(spot_price - strike + np.random.uniform(-20, 20), 0.05),
            'change': np.random.uniform(-10, 10),
            'bid_qty': int(np.random.uniform(50, 500)),
            'ask_qty': int(np.random.uniform(50, 500)),
        })
        
        # Puts
        options_data.append({
            'strike': strike,
            'expiry': '25-JAN-2024',
            'type': 'PE',
            'oi': int(base_oi * np.random.uniform(0.8, 1.2)),
            'oi_change': int(np.random.uniform(-5000, 5000)),
            'volume': int(np.random.uniform(1000, 50000)),
            'iv': np.random.uniform(12, 18),
            'ltp': max(strike - spot_price + np.random.uniform(-20, 20), 0.05),
            'change': np.random.uniform(-10, 10),
            'bid_qty': int(np.random.uniform(50, 500)),
            'ask_qty': int(np.random.uniform(50, 500)),
        })
    
    df = pd.DataFrame(options_data)
    return df, spot_price

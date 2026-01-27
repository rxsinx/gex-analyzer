"""
Data fetching module for NSE options data using nselib
"""

import pandas as pd
from datetime import datetime
import time
from nselib import capital_market


def get_live_spot_price(symbol='NIFTY'):
    """
    Get live spot price using nselib
    
    Args:
        symbol (str): Index symbol (NIFTY or BANKNIFTY)
    
    Returns:
        float: Current spot price
    """
    try:
        if symbol == 'NIFTY':
            # Get NIFTY 50 data
            data = capital_market.market_watch_all_indices()
            for item in data['data']:
                if item['index'] == 'NIFTY 50':
                    return float(item['last'])
        
        elif symbol == 'BANKNIFTY':
            # Get BANK NIFTY data
            data = capital_market.market_watch_all_indices()
            for item in data['data']:
                if item['index'] == 'NIFTY BANK':
                    return float(item['last'])
        
        return None
    
    except Exception as e:
        print(f"Error fetching spot price: {e}")
        return None


def fetch_option_chain(symbol='NIFTY', expiry_date=None):
    """
    Fetch option chain data using nselib
    
    Args:
        symbol (str): Index symbol (NIFTY or BANKNIFTY)
        expiry_date (str): Expiry date in DD-MMM-YYYY format
    
    Returns:
        tuple: (DataFrame with options data, spot price)
    """
    try:
        # Fetch option chain
        if symbol == 'NIFTY':
            oc_data = capital_market.nifty_option_chain()
        elif symbol == 'BANKNIFTY':
            oc_data = capital_market.bank_nifty_option_chain()
        else:
            return None, None
        
        # Extract spot price
        spot_price = oc_data['records']['underlyingValue']
        
        # Parse option chain data
        options_data = []
        
        for item in oc_data['records']['data']:
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


def get_market_status():
    """
    Get current market status
    
    Returns:
        dict: Market status information
    """
    try:
        data = capital_market.market_status()
        return {
            'market_state': data.get('marketState', 'Unknown'),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    except:
        return {
            'market_state': 'Unknown',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }


def get_index_quote(symbol='NIFTY'):
    """
    Get detailed index quote
    
    Args:
        symbol (str): Index symbol
    
    Returns:
        dict: Index quote data
    """
    try:
        data = capital_market.market_watch_all_indices()
        
        for item in data['data']:
            if symbol == 'NIFTY' and item['index'] == 'NIFTY 50':
                return {
                    'last': float(item['last']),
                    'change': float(item.get('percentChange', 0)),
                    'open': float(item.get('open', 0)),
                    'high': float(item.get('high', 0)),
                    'low': float(item.get('low', 0)),
                    'previous_close': float(item.get('previousClose', 0)),
                }
            elif symbol == 'BANKNIFTY' and item['index'] == 'NIFTY BANK':
                return {
                    'last': float(item['last']),
                    'change': float(item.get('percentChange', 0)),
                    'open': float(item.get('open', 0)),
                    'high': float(item.get('high', 0)),
                    'low': float(item.get('low', 0)),
                    'previous_close': float(item.get('previousClose', 0)),
                }
        
        return None
    
    except Exception as e:
        print(f"Error fetching index quote: {e}")
        return None


def generate_sample_data(symbol='NIFTY', spot_price=None):
    """
    Generate sample option chain data with live spot price
    
    Args:
        symbol (str): Index symbol
        spot_price (float): Current spot price (if None, fetches live)
    
    Returns:
        tuple: (DataFrame, spot_price)
    """
    import numpy as np
    
    # Try to get live spot price first
    if spot_price is None:
        spot_price = get_live_spot_price(symbol)
        
        # If that fails, use realistic fallback
        if spot_price is None:
            spot_price = 23500 if symbol == 'NIFTY' else 48000
    
    # Generate strikes around spot
    strike_interval = 50 if symbol == 'NIFTY' else 100
    num_strikes = 40
    
    # Center strikes around current spot
    start_strike = int((spot_price - (num_strikes/2 * strike_interval)) / strike_interval) * strike_interval
    strikes = np.arange(start_strike, start_strike + (num_strikes * strike_interval), strike_interval)
    
    options_data = []
    
    for strike in strikes:
        # Generate realistic OI based on distance from ATM
        distance = abs(strike - spot_price)
        base_oi = max(100000 - distance * 30, 5000)
        
        # Calls
        call_oi = int(base_oi * np.random.uniform(0.8, 1.2))
        call_ltp = max(spot_price - strike, 0) + np.random.uniform(5, 50) if spot_price > strike else np.random.uniform(0.5, 10)
        
        options_data.append({
            'strike': strike,
            'expiry': '30-JAN-2026',
            'type': 'CE',
            'oi': call_oi,
            'oi_change': int(np.random.uniform(-5000, 5000)),
            'volume': int(np.random.uniform(1000, 50000)),
            'iv': np.random.uniform(12, 18),
            'ltp': call_ltp,
            'change': np.random.uniform(-10, 10),
            'bid_qty': int(np.random.uniform(50, 500)),
            'ask_qty': int(np.random.uniform(50, 500)),
        })
        
        # Puts
        put_oi = int(base_oi * np.random.uniform(0.8, 1.2))
        put_ltp = max(strike - spot_price, 0) + np.random.uniform(5, 50) if strike > spot_price else np.random.uniform(0.5, 10)
        
        options_data.append({
            'strike': strike,
            'expiry': '30-JAN-2026',
            'type': 'PE',
            'oi': put_oi,
            'oi_change': int(np.random.uniform(-5000, 5000)),
            'volume': int(np.random.uniform(1000, 50000)),
            'iv': np.random.uniform(12, 18),
            'ltp': put_ltp,
            'change': np.random.uniform(-10, 10),
            'bid_qty': int(np.random.uniform(50, 500)),
            'ask_qty': int(np.random.uniform(50, 500)),
        })
    
    df = pd.DataFrame(options_data)
    return df, spot_price

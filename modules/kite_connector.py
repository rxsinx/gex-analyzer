"""
Kite Connect integration for live market data
"""

from kiteconnect import KiteConnect
import pandas as pd
from datetime import datetime
import streamlit as st


class KiteManager:
    """Manage Kite Connect API operations"""
    
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.kite = KiteConnect(api_key=api_key)
        self.access_token = None
    
    def get_login_url(self):
        """Get Kite login URL"""
        return self.kite.login_url()
    
    def set_access_token(self, request_token):
        """Generate and set access token"""
        try:
            data = self.kite.generate_session(request_token, api_secret=self.api_secret)
            self.access_token = data["access_token"]
            self.kite.set_access_token(self.access_token)
            return True
        except Exception as e:
            st.error(f"Authentication failed: {e}")
            return False
    
    def get_instruments(self, exchange='NFO'):
        """Get all instruments from exchange"""
        try:
            return self.kite.instruments(exchange)
        except Exception as e:
            st.error(f"Error fetching instruments: {e}")
            return []
    
    def get_option_chain(self, symbol, expiry):
        """
        Fetch option chain from Kite
        
        Args:
            symbol (str): Index symbol (NIFTY, BANKNIFTY, etc.)
            expiry (str): Expiry date
        
        Returns:
            tuple: (DataFrame, spot_price)
        """
        try:
            # Get instruments
            instruments = self.get_instruments('NFO')
            
            # Filter options for the symbol and expiry
            options = [i for i in instruments 
                      if i['name'] == symbol 
                      and i['expiry'].strftime('%d-%b-%Y').upper() == expiry
                      and i['instrument_type'] in ['CE', 'PE']]
            
            if not options:
                return None, None
            
            # Get quotes for all options
            instrument_tokens = [i['instrument_token'] for i in options]
            quotes = self.kite.quote([f'NFO:{i["tradingsymbol"]}' for i in options])
            
            # Parse option chain
            option_data = []
            
            for opt in options:
                key = f'NFO:{opt["tradingsymbol"]}'
                if key in quotes:
                    quote = quotes[key]
                    option_data.append({
                        'strike': opt['strike'],
                        'expiry': opt['expiry'].strftime('%d-%b-%Y').upper(),
                        'type': opt['instrument_type'],
                        'oi': quote.get('oi', 0),
                        'oi_change': quote.get('oi_day_high', 0) - quote.get('oi_day_low', 0),
                        'volume': quote.get('volume', 0),
                        'iv': 0,  # Kite doesn't provide IV directly
                        'ltp': quote.get('last_price', 0),
                        'change': quote.get('net_change', 0),
                        'bid_qty': quote.get('depth', {}).get('buy', [{}])[0].get('quantity', 0),
                        'ask_qty': quote.get('depth', {}).get('sell', [{}])[0].get('quantity', 0),
                    })
            
            # Get underlying spot price
            underlying_key = f'NSE:{symbol}'
            underlying_quote = self.kite.quote(underlying_key)
            spot_price = underlying_quote[underlying_key]['last_price']
            
            df = pd.DataFrame(option_data)
            return df, spot_price
            
        except Exception as e:
            st.error(f"Error fetching Kite option chain: {e}")
            return None, None
    
    def get_spot_price(self, symbol):
        """Get current spot price"""
        try:
            key = f'NSE:{symbol}'
            quote = self.kite.quote(key)
            return quote[key]['last_price']
        except Exception as e:
            st.error(f"Error fetching spot price: {e}")
            return None


def init_kite_session():
    """Initialize Kite session in Streamlit"""
    if 'kite_manager' not in st.session_state:
        st.session_state.kite_manager = None
        st.session_state.kite_authenticated = False
    
    return st.session_state.kite_manager

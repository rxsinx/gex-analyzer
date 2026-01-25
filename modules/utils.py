"""
Utility functions for GEX Analyzer
"""

import pandas as pd
from datetime import datetime, timedelta
import calendar


def get_next_expiry(expiry_type='weekly'):
    """
    Get the next expiry date for options
    
    Args:
        expiry_type (str): 'weekly' or 'monthly'
    
    Returns:
        str: Expiry date in DD-MMM-YYYY format
    """
    today = datetime.now()
    
    if expiry_type == 'weekly':
        # Next Thursday
        days_ahead = 3 - today.weekday()  # Thursday is 3
        if days_ahead <= 0:
            days_ahead += 7
        expiry = today + timedelta(days=days_ahead)
    else:
        # Last Thursday of current month
        last_day = calendar.monthrange(today.year, today.month)[1]
        last_date = datetime(today.year, today.month, last_day)
        
        # Find last Thursday
        offset = (last_date.weekday() - 3) % 7
        expiry = last_date - timedelta(days=offset)
        
        # If we've passed it, get next month's
        if expiry < today:
            if today.month == 12:
                next_month = datetime(today.year + 1, 1, 1)
            else:
                next_month = datetime(today.year, today.month + 1, 1)
            
            last_day = calendar.monthrange(next_month.year, next_month.month)[1]
            last_date = datetime(next_month.year, next_month.month, last_day)
            offset = (last_date.weekday() - 3) % 7
            expiry = last_date - timedelta(days=offset)
    
    return expiry.strftime('%d-%b-%Y').upper()


def get_atm_strike(spot_price, strike_interval=50):
    """
    Get the At-The-Money strike price
    
    Args:
        spot_price (float): Current spot price
        strike_interval (int): Strike price interval
    
    Returns:
        int: ATM strike price
    """
    return round(spot_price / strike_interval) * strike_interval


def format_number(num):
    """
    Format large numbers for display
    
    Args:
        num (float): Number to format
    
    Returns:
        str: Formatted number
    """
    if abs(num) >= 10000000:  # 1 crore
        return f"₹{num/10000000:.2f}Cr"
    elif abs(num) >= 100000:  # 1 lakh
        return f"₹{num/100000:.2f}L"
    else:
        return f"₹{num:,.0f}"


def calculate_time_to_expiry(expiry_date_str):
    """
    Calculate time to expiry in years
    
    Args:
        expiry_date_str (str): Expiry date in DD-MMM-YYYY format
    
    Returns:
        float: Time to expiry in years
    """
    try:
        expiry_date = datetime.strptime(expiry_date_str, '%d-%b-%Y')
        today = datetime.now()
        days_to_expiry = (expiry_date - today).days
        return max(days_to_expiry / 365.0, 0.0027)  # Minimum 1 day
    except:
        return 0.0027  # Default to 1 day


def filter_strikes(df, spot_price, range_pct=10):
    """
    Filter strikes within a percentage range of spot price
    
    Args:
        df (pd.DataFrame): Options data
        spot_price (float): Current spot price
        range_pct (int): Percentage range around spot
    
    Returns:
        pd.DataFrame: Filtered dataframe
    """
    lower_bound = spot_price * (1 - range_pct/100)
    upper_bound = spot_price * (1 + range_pct/100)
    
    return df[(df['strike'] >= lower_bound) & (df['strike'] <= upper_bound)]


def get_available_expiries():
    """
    Get list of available expiry dates (next 3 months)
    
    Returns:
        list: List of expiry dates
    """
    expiries = []
    today = datetime.now()
    
    # Get next 12 weekly expiries
    current = today
    for _ in range(12):
        days_ahead = 3 - current.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        expiry = current + timedelta(days=days_ahead)
        expiries.append(expiry.strftime('%d-%b-%Y').upper())
        current = expiry + timedelta(days=1)
    
    return expiries

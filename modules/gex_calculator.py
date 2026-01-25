"""
GEX (Gamma Exposure) calculation module
"""

import pandas as pd
import numpy as np
from scipy.stats import norm


def calculate_gamma(S, K, T, r, sigma, option_type='call'):
    """
    Calculate option gamma using Black-Scholes formula
    
    Args:
        S (float): Spot price
        K (float): Strike price
        T (float): Time to expiry in years
        r (float): Risk-free rate
        sigma (float): Implied volatility
        option_type (str): 'call' or 'put'
    
    Returns:
        float: Gamma value
    """
    if T <= 0 or sigma <= 0:
        return 0
    
    try:
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
        return gamma
    except:
        return 0


def calculate_gex(df, spot_price, expiry_date_str, risk_free_rate=0.07):
    """
    Calculate Gamma Exposure (GEX) for each strike
    
    Args:
        df (pd.DataFrame): Options data
        spot_price (float): Current spot price
        expiry_date_str (str): Expiry date
        risk_free_rate (float): Risk-free rate
    
    Returns:
        pd.DataFrame: DataFrame with GEX calculations
    """
    from modules.utils import calculate_time_to_expiry
    
    T = calculate_time_to_expiry(expiry_date_str)
    
    gex_data = []
    
    # Group by strike
    for strike in df['strike'].unique():
        strike_data = df[df['strike'] == strike]
        
        call_data = strike_data[strike_data['type'] == 'CE']
        put_data = strike_data[strike_data['type'] == 'PE']
        
        call_oi = call_data['oi'].sum() if not call_data.empty else 0
        put_oi = put_data['oi'].sum() if not put_data.empty else 0
        
        call_iv = call_data['iv'].mean() / 100 if not call_data.empty and call_data['iv'].mean() > 0 else 0.15
        put_iv = put_data['iv'].mean() / 100 if not put_data.empty and put_data['iv'].mean() > 0 else 0.15
        
        # Calculate gamma
        call_gamma = calculate_gamma(spot_price, strike, T, risk_free_rate, call_iv, 'call')
        put_gamma = calculate_gamma(spot_price, strike, T, risk_free_rate, put_iv, 'put')
        
        # GEX = Gamma * OI * Spot^2 * 0.01
        # Calls are negative GEX (dealers are short), Puts are positive GEX (dealers are long)
        call_gex = -call_gamma * call_oi * spot_price * spot_price * 0.01
        put_gex = put_gamma * put_oi * spot_price * spot_price * 0.01
        
        total_gex = call_gex + put_gex
        
        gex_data.append({
            'strike': strike,
            'call_oi': call_oi,
            'put_oi': put_oi,
            'call_gamma': call_gamma,
            'put_gamma': put_gamma,
            'call_gex': call_gex,
            'put_gex': put_gex,
            'total_gex': total_gex,
            'net_gex': total_gex
        })
    
    gex_df = pd.DataFrame(gex_data)
    gex_df = gex_df.sort_values('strike')
    
    return gex_df


def calculate_dex(df, spot_price, expiry_date_str, risk_free_rate=0.07):
    """
    Calculate Delta Exposure (DEX) for each strike
    
    Args:
        df (pd.DataFrame): Options data
        spot_price (float): Current spot price
        expiry_date_str (str): Expiry date
        risk_free_rate (float): Risk-free rate
    
    Returns:
        pd.DataFrame: DataFrame with DEX calculations
    """
    from modules.utils import calculate_time_to_expiry
    
    T = calculate_time_to_expiry(expiry_date_str)
    
    dex_data = []
    
    for strike in df['strike'].unique():
        strike_data = df[df['strike'] == strike]
        
        call_data = strike_data[strike_data['type'] == 'CE']
        put_data = strike_data[strike_data['type'] == 'PE']
        
        call_oi = call_data['oi'].sum() if not call_data.empty else 0
        put_oi = put_data['oi'].sum() if not put_data.empty else 0
        
        call_iv = call_data['iv'].mean() / 100 if not call_data.empty and call_data['iv'].mean() > 0 else 0.15
        put_iv = put_data['iv'].mean() / 100 if not put_data.empty and put_data['iv'].mean() > 0 else 0.15
        
        # Calculate delta
        if T > 0 and call_iv > 0:
            d1_call = (np.log(spot_price / strike) + (risk_free_rate + 0.5 * call_iv ** 2) * T) / (call_iv * np.sqrt(T))
            call_delta = norm.cdf(d1_call)
        else:
            call_delta = 1 if spot_price > strike else 0
        
        if T > 0 and put_iv > 0:
            d1_put = (np.log(spot_price / strike) + (risk_free_rate + 0.5 * put_iv ** 2) * T) / (put_iv * np.sqrt(T))
            put_delta = -norm.cdf(-d1_put)
        else:
            put_delta = -1 if spot_price < strike else 0
        
        # DEX = Delta * OI * Spot * multiplier
        call_dex = -call_delta * call_oi * spot_price
        put_dex = -put_delta * put_oi * spot_price
        
        total_dex = call_dex + put_dex
        
        dex_data.append({
            'strike': strike,
            'call_delta': call_delta,
            'put_delta': put_delta,
            'call_dex': call_dex,
            'put_dex': put_dex,
            'total_dex': total_dex
        })
    
    dex_df = pd.DataFrame(dex_data)
    dex_df = dex_df.sort_values('strike')
    
    return dex_df


def find_gamma_levels(gex_df, spot_price):
    """
    Find key gamma levels (flip points, resistance, support)
    
    Args:
        gex_df (pd.DataFrame): GEX data
        spot_price (float): Current spot price
    
    Returns:
        dict: Key gamma levels
    """
    # Find zero gamma (gamma flip point)
    gex_df['cumulative_gex'] = gex_df['total_gex'].cumsum()
    
    # Find where cumulative GEX crosses zero
    zero_cross = gex_df[gex_df['cumulative_gex'].abs() == gex_df['cumulative_gex'].abs().min()]
    gamma_flip = zero_cross['strike'].values[0] if not zero_cross.empty else spot_price
    
    # Find max positive GEX (support)
    max_positive = gex_df[gex_df['total_gex'] == gex_df['total_gex'].max()]
    support_level = max_positive['strike'].values[0] if not max_positive.empty else None
    
    # Find max negative GEX (resistance)
    max_negative = gex_df[gex_df['total_gex'] == gex_df['total_gex'].min()]
    resistance_level = max_negative['strike'].values[0] if not max_negative.empty else None
    
    return {
        'gamma_flip': gamma_flip,
        'support': support_level,
        'resistance': resistance_level,
        'total_gex': gex_df['total_gex'].sum(),
        'net_gex_above_spot': gex_df[gex_df['strike'] > spot_price]['total_gex'].sum(),
        'net_gex_below_spot': gex_df[gex_df['strike'] <= spot_price]['total_gex'].sum()
    }

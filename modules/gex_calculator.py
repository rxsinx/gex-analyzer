"""
Advanced GEX and Greeks calculation module
Includes: Delta, Gamma, Vega, Theta, Rho, and all exposure metrics
"""

import pandas as pd
import numpy as np
from scipy.stats import norm
import mibian


def calculate_all_greeks(S, K, T, r, sigma, option_type='call'):
    """
    Calculate all Greeks using both Black-Scholes and Mibian
    
    Args:
        S (float): Spot price
        K (float): Strike price
        T (float): Time to expiry in years
        r (float): Risk-free rate
        sigma (float): Implied volatility (as decimal)
        option_type (str): 'call' or 'put'
    
    Returns:
        dict: All Greeks and theoretical price
    """
    if T <= 0 or sigma <= 0:
        return {
            'delta': 0, 'gamma': 0, 'vega': 0, 'theta': 0, 'rho': 0,
            'theo_price': 0, 'iv': sigma * 100
        }
    
    try:
        # Convert to days for mibian
        days_to_expiry = max(int(T * 365), 1)
        
        # Use Mibian for more accurate Greeks
        if option_type == 'call':
            bs = mibian.BS([S, K, r * 100, days_to_expiry], volatility=sigma * 100)
            delta = bs.callDelta
            theta = bs.callTheta
            price = bs.callPrice
        else:
            bs = mibian.BS([S, K, r * 100, days_to_expiry], volatility=sigma * 100)
            delta = bs.putDelta
            theta = bs.putTheta
            price = bs.putPrice
        
        # Common Greeks
        gamma = bs.gamma
        vega = bs.vega
        
        # Calculate Rho manually (Mibian doesn't provide it directly)
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        
        if option_type == 'call':
            rho = K * T * np.exp(-r * T) * norm.cdf(d2) / 100
        else:
            rho = -K * T * np.exp(-r * T) * norm.cdf(-d2) / 100
        
        return {
            'delta': round(delta, 4),
            'gamma': round(gamma / 100, 6),  # Normalize gamma
            'vega': round(vega / 100, 4),    # Vega per 1% IV change
            'theta': round(theta, 4),
            'rho': round(rho, 4),
            'theo_price': round(price, 2),
            'iv': round(sigma * 100, 2)
        }
        
    except Exception as e:
        # Fallback to manual calculation
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        
        if option_type == 'call':
            delta = norm.cdf(d1)
            price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
            theta = ((-S * norm.pdf(d1) * sigma / (2 * np.sqrt(T)) 
                     - r * K * np.exp(-r * T) * norm.cdf(d2)) / 365)
            rho = K * T * np.exp(-r * T) * norm.cdf(d2) / 100
        else:
            delta = norm.cdf(d1) - 1
            price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
            theta = ((-S * norm.pdf(d1) * sigma / (2 * np.sqrt(T)) 
                     + r * K * np.exp(-r * T) * norm.cdf(-d2)) / 365)
            rho = -K * T * np.exp(-r * T) * norm.cdf(-d2) / 100
        
        gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
        vega = S * norm.pdf(d1) * np.sqrt(T) / 100
        
        return {
            'delta': round(delta, 4),
            'gamma': round(gamma, 6),
            'vega': round(vega, 4),
            'theta': round(

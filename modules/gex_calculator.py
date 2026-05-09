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
            bs = mibian.BS([S, K, r * 100, days_to_expiry], volatility=s

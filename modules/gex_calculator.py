# modules/gex_calculator.py

import numpy as np
from scipy.stats import norm
import pandas as pd

class GEXCalculator:
    """Gamma Exposure Calculator"""
    
    # Market parameters
    MARKET_PARAMS = {
        'NIFTY': {
            'lot_size': 65,
            'value_per_point': 65,
            'risk_free_rate': 0.05
        },
        'BANKNIFTY': {
            'lot_size': 30,
            'value_per_point': 30,
            'risk_free_rate': 0.05
        }
    }
    
    @staticmethod
    def calculate_greeks(option_type: str, S: float, K: float, T: float, 
                        iv: float, r: float = 0.05) -> dict:
        """
        Calculate option Greeks using Black-Scholes
        For European options (NIFTY/BANKNIFTY)
        """
        T = T / 365.0  # Convert to years
        
        d1 = (np.log(S/K) + (r + 0.5*iv**2)*T) / (iv*np.sqrt(T))
        d2 = d1 - iv*np.sqrt(T)
        
        if option_type == 'CE':
            # Call options
            delta = norm.cdf(d1)
            gamma = norm.pdf(d1) / (S * iv * np.sqrt(T))
            vega = S * norm.pdf(d1) * np.sqrt(T) / 100
            theta = (-S * norm.pdf(d1) * iv / (2*np.sqrt(T)) 
                    - r * K * np.exp(-r*T) * norm.cdf(d2)) / 365
            charm = -norm.pdf(d1) * (d2/(2*T) - r/(iv*np.sqrt(T)))
        else:
            # Put options
            delta = norm.cdf(d1) - 1
            gamma = norm.pdf(d1) / (S * iv * np.sqrt(T))
            vega = S * norm.pdf(d1) * np.sqrt(T) / 100
            theta = (-S * norm.pdf(d1) * iv / (2*np.sqrt(T)) 
                    + r * K * np.exp(-r*T) * norm.cdf(-d2)) / 365
            charm = -norm.pdf(d1) * (d2/(2*T) - r/(iv*np.sqrt(T)))
        
        return {
            'delta': delta,
            'gamma': gamma,
            'vega': vega,
            'theta': theta,
            'charm': charm,
            'd1': d1,
            'd2': d2
        }
    
    @staticmethod
    def calculate_gex_for_row(row: pd.Series, symbol: str) -> dict:
        """
        Calculate GEX for a single option row
        """
        params = GEXCalculator.MARKET_PARAMS[symbol]
        lot_size = params['lot_size']
        
        # Calculate Greeks
        greeks = GEXCalculator.calculate_greeks(
            option_type=row['option_type'],
            S=row['spot_price'],
            K=row['strike'],
            T=row['days_to_expiry'],
            iv=row['iv'],
            r=params['risk_free_rate']
        )
        
        # Calculate GEX
        gamma = greeks['gamma']
        oi = row['open_interest']
        spot = row['spot_price']
        
        # GEX formula: Gamma × Open Interest × Lot Size × Spot² × 0.01
        gex_rupees = gamma * oi * lot_size * (spot ** 2) * 0.01
        
        # Dealer exposure (negative for dealers as they're typically short options)
        dealer_gex = -gex_rupees
        
        return {
            'strike': row['strike'],
            'option_type': row['option_type'],
            'open_interest': oi,
            'gamma': gamma,
            'gex_rupees': gex_rupees,
            'dealer_gex': dealer_gex,
            'gex_crores': gex_rupees / 10000000,
            'dealer_gex_crores': dealer_gex / 10000000,
            'delta': greeks['delta'],
            'vega': greeks['vega'],
            'theta': greeks['theta'],
            'charm': greeks['charm'],
            'notional': oi * lot_size * spot / 10000000  # in crores
        }
    
    @staticmethod
    def calculate_total_gex(option_chain: pd.DataFrame, symbol: str) -> dict:
        """
        Calculate total GEX for entire option chain
        """
        if option_chain.empty:
            return {}
        
        results = []
        total_call_gex = 0
        total_put_gex = 0
        total_call_oi = 0
        total_put_oi = 0
        
        for _, row in option_chain.iterrows():
            gex_data = GEXCalculator.calculate_gex_for_row(row, symbol)
            results.append(gex_data)
            
            if row['option_type'] == 'CE':
                total_call_gex += gex_data['dealer_gex']
                total_call_oi += row['open_interest']
            else:
                total_put_gex += gex_data['dealer_gex']
                total_put_oi += row['open_interest']
        
        # Convert to DataFrame
        results_df = pd.DataFrame(results)
        
        # Calculate net GEX
        net_gex = total_call_gex + total_put_gex
        
        # Find gamma flip level
        gamma_flip = GEXCalculator.find_gamma_flip_level(results_df)
        
        # Calculate PCR
        pcr_oi = total_put_oi / total_call_oi if total_call_oi > 0 else 0
        
        # Find strikes with maximum GEX
        max_call_gex_strike = results_df[results_df['option_type'] == 'CE'].nlargest(1, 'dealer_gex_crores')
        max_put_gex_strike = results_df[results_df['option_type'] == 'PE'].nlargest(1, 'dealer_gex_crores')
        
        return {
            'total_gex_crores': abs(net_gex) / 10000000,
            'call_gex_crores': total_call_gex / 10000000,
            'put_gex_crores': total_put_gex / 10000000,
            'net_gex': net_gex,
            'net_gex_crores': net_gex / 10000000,
            'gamma_flip': gamma_flip,
            'pcr_oi': pcr_oi,
            'call_oi': total_call_oi,
            'put_oi': total_put_oi,
            'results_df': results_df,
            'max_call_gex': max_call_gex_strike.iloc[0] if not max_call_gex_strike.empty else None,
            'max_put_gex': max_put_gex_strike.iloc[0] if not max_put_gex_strike.empty else None,
            'dealer_position': 'SHORT GAMMA' if net_gex < 0 else 'LONG GAMMA'
        }
    
    @staticmethod
    def find_gamma_flip_level(gex_df: pd.DataFrame) -> float:
        """
        Find the price level where gamma flips sign
        """
        if gex_df.empty:
            return 0
        
        # Group by strike and calculate net gamma
        strike_groups = gex_df.groupby('strike').agg({
            'dealer_gex': 'sum'
        }).reset_index()
        
        # Find where gamma crosses zero
        strike_groups = strike_groups.sort_values('strike')
        strike_groups['sign'] = np.sign(strike_groups['dealer_gex'])
        strike_groups['sign_change'] = strike_groups['sign'].diff().fillna(0)
        
        flip_points = strike_groups[abs(strike_groups['sign_change']) > 0]
        
        if not flip_points.empty:
            return flip_points.iloc[0]['strike']
        
        return strike_groups.iloc[0]['strike']

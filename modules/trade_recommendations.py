"""
Intelligent trade recommendations engine
Based on GEX, Greeks, PCR, Max Pain, and OI analysis
"""

import pandas as pd
import numpy as np


def generate_trade_recommendations(gex_df, spot_price, gamma_levels):
    """
    Generate intelligent trade recommendations
    
    Args:
        gex_df (pd.DataFrame): GEX data with all Greeks
        spot_price (float): Current spot price
        gamma_levels (dict): Key gamma levels
    
    Returns:
        list: List of trade recommendations with signals
    """
    recommendations = []
    
    pcr = gamma_levels.get('pcr', 1.0)
    max_pain = gamma_levels.get('max_pain', spot_price)
    gamma_flip = gamma_levels.get('gamma_flip', spot_price)
    net_gex = gamma_levels.get('total_gex', 0)
    max_call_oi_strike = gamma_levels.get('max_call_oi_strike', spot_price)
    max_put_oi_strike = gamma_levels.get('max_put_oi_strike', spot_price)
    
    # 1. PCR-based sentiment
    if pcr > 1.3:
        recommendations.append({
            'signal': '🐻 STRONG BEARISH',
            'confidence': 'HIGH',
            'strategy': 'Put Buy / Call Write',
            'reasoning': f'Extremely high PCR ({pcr:.2f}) indicates excessive put buying and bearish sentiment.',
            'action': f'Consider buying ATM/OTM Puts or writing OTM Calls above ₹{int(spot_price * 1.02):,}'
        })
    elif pcr > 1.2:
        recommendations.append({
            'signal': '🔴 BEARISH',
            'confidence': 'MEDIUM',
            'strategy': 'Bearish Spread',
            'reasoning': f'High PCR ({pcr:.2f}) suggests bearish positioning.',
            'action': 'Consider Bear Put Spread or Calendar Spread with Puts'
        })
    elif pcr < 0.7:
        recommendations.append({
            'signal': '🐂 STRONG BULLISH',
            'confidence': 'HIGH',
            'strategy': 'Call Buy / Put Write',
            'reasoning': f'Extremely low PCR ({pcr:.2f}) indicates excessive call buying and bullish sentiment.',
            'action': f'Consider buying ATM/OTM Calls or writing OTM Puts below ₹{int(spot_price * 0.98):,}'
        })
    elif pcr < 0.8:
        recommendations.append({
            'signal': '🟢 BULLISH',
            'confidence': 'MEDIUM',
            'strategy': 'Bullish Spread',
            'reasoning': f'Low PCR ({pcr:.2f}) suggests bullish positioning.',
            'action': 'Consider Bull Call Spread or Calendar Spread with Calls'
        })
    
    # 2. Gamma regime analysis
    if net_gex > 0:
        recommendations.append({
            'signal': '📊 POSITIVE GAMMA REGIME',
            'confidence': 'INFO',
            'strategy': 'Range-bound Trading',
            'reasoning': f'Market in positive gamma (₹{net_gex/10000000:.2f}Cr). Dealers will dampen volatility.',
            'action': 'Favor Iron Condors, Butterflies, and premium selling strategies'
        })
    else:
        recommendations.append({
            'signal': '⚡ NEGATIVE GAMMA REGIME',
            'confidence': 'INFO',
            'strategy': 'Momentum/Breakout Trading',
            'reasoning': f'Market in negative gamma (₹{abs(net_gex)/10000000:.2f}Cr). Dealers will amplify moves.',
            'action': 'Favor Straddles, Strangles, and directional strategies'
        })
    
    # 3. Max Pain magnetic effect
    pain_distance = abs(max_pain - spot_price) / spot_price
    if pain_distance > 0.02:  # > 2%
        direction = "down" if spot_price > max_pain else "up"
        recommendations.append({
            'signal': '🎯 MAX PAIN DRIFT',
            'confidence': 'MEDIUM',
            'strategy': f'Directional {direction.title()}',
            'reasoning': f'Spot (₹{spot_price:,.0f}) is {pain_distance*100:.1f}% away from Max Pain (₹{max_pain:,.0f}). Market may drift towards Max Pain.',
            'action': f'Consider positioning for move {direction} to ₹{max_pain:,.0f}'
        })
    
    # 4. Support/Resistance from Max OI
    if max_call_oi_strike and max_call_oi_strike > spot_price:
        distance = ((max_call_oi_strike - spot_price) / spot_price) * 100
        recommendations.append({
            'signal': '🚧 STRONG CALL WALL',
            'confidence': 'HIGH',
            'strategy': 'Resistance Play',
            'reasoning': f'Maximum Call OI at ₹{max_call_oi_strike:,.0f} ({distance:.1f}% above spot) - Strong resistance level.',
            'action': f'Sell rallies near ₹{max_call_oi_strike:,.0f} or use Bear Call Spread'
        })
    
    if max_put_oi_strike and max_put_oi_strike < spot_price:
        distance = ((spot_price - max_put_oi_strike) / spot_price) * 100
        recommendations.append({
            'signal': '🛡️ STRONG PUT WALL',
            'confidence': 'HIGH',
            'strategy': 'Support Play',
            'reasoning': f'Maximum Put OI at ₹{max_put_oi_strike:,.0f} ({distance:.1f}% below spot) - Strong support level.',
            'action': f'Buy dips near ₹{max_put_oi_strike:,.0f} or use Bull Put Spread'
        })
    
    # 5. Gamma flip zone analysis
    if abs(gamma_flip - spot_price) / spot_price < 0.01:  # Within 1%
        recommendations.append({
            'signal': '⚠️ GAMMA FLIP ZONE',
            'confidence': 'HIGH',
            'strategy': 'Caution - High Volatility Risk',
            'reasoning': f'Spot near Gamma Flip (₹{gamma_flip:,.0f}). Crossing this level can trigger regime change.',
            'action': 'Reduce position size, use tight stops, or employ neutral strategies'
        })
    
    # 6. Theta decay opportunity
    atm_row = gex_df.iloc[(gex_df['strike'] - spot_price).abs().argsort()[:1]]
    if not atm_row.empty:
        total_theta = atm_row['total_tex'].values[0]
        if abs(total_theta) > 100000:  # Significant theta
            recommendations.append({
                'signal': '⏰ HIGH THETA ENVIRONMENT',
                'confidence': 'MEDIUM',
                'strategy': 'Premium Selling',
                'reasoning': f'High time decay (₹{abs(total_theta)/1000:.0f}K/day at ATM). Favorable for option sellers.',
                'action': 'Consider Credit Spreads, Iron Condors, or Covered Calls'
            })
    
    # 7. IV skew analysis
    atm_call_iv = atm_row['call_iv'].values[0] if not atm_row.empty else 15
    atm_put_iv = atm_row['put_iv'].values[0] if not atm_row.empty else 15
    iv_skew = atm_put_iv - atm_call_iv
    
    if abs(iv_skew) > 3:  # > 3% skew
        skew_direction = "Put" if iv_skew > 0 else "Call"
        recommendations.append({
            'signal': f'📐 {skew_direction.upper()} IV PREMIUM',
            'confidence': 'MEDIUM',
            'strategy': f'Sell {skew_direction}s / Buy {("Calls" if skew_direction == "Put" else "Puts")}',
            'reasoning': f'{skew_direction} IV ({(atm_put_iv if iv_skew > 0 else atm_call_iv):.1f}%) is {abs(iv_skew):.1f}% higher. IV overpriced.',
            'action': f'Consider {skew_direction} selling strategies or volatility arbitrage'
        })
    
    return recommendations


def format_recommendations_for_display(recommendations):
    """Format recommendations for Streamlit display"""
    if not recommendations:
        return "No strong signals detected. Market appears balanced."
    
    formatted = []
    
    for i, rec in enumerate(recommendations, 1):
        confidence_color = {
            'HIGH': '🔴',
            'MEDIUM': '🟡',
            'LOW': '🟢',
            'INFO': '🔵'
        }.get(rec['confidence'], '⚪')
        
        formatted.append(f"""
**{i}. {rec['signal']}** {confidence_color} `{rec['confidence']}`

**Strategy:** {rec['strategy']}

**Analysis:** {rec['reasoning']}

**Action:** {rec['action']}

---
""")
    
    return "\n".join(formatted)

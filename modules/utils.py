# modules/utils.py

from datetime import datetime, timedelta
import calendar

class IndianExpiryCalculator:
    """
    Calculate expiry dates for Indian indices
    """
    
    # Expiry schedule
    EXPIRY_SCHEDULE = {
        'NIFTY': {
            'weekly_expiry': 'Thursday',
            'monthly_expiry': 'Last Thursday',
        },
        'BANKNIFTY': {
            'weekly_expiry': 'Wednesday',
            'monthly_expiry': 'Last Wednesday',
        }
    }
    
    @staticmethod
    def get_next_expiry_date(symbol='NIFTY', expiry_type='weekly', reference_date=None):
        """
        Get next expiry date for Indian indices
        """
        if reference_date is None:
            reference_date = datetime.now()
        
        schedule = IndianExpiryCalculator.EXPIRY_SCHEDULE[symbol]
        
        if expiry_type == 'weekly':
            return IndianExpiryCalculator._get_next_weekly_expiry(
                reference_date, schedule['weekly_expiry']
            )
        else:  # monthly
            return IndianExpiryCalculator._get_next_monthly_expiry(
                reference_date, schedule['weekly_expiry']
            )
    
    @staticmethod
    def _get_next_weekly_expiry(reference_date, expiry_day_name):
        """
        Get next weekly expiry date
        """
        day_map = {
            'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 
            'Thursday': 3, 'Friday': 4, 'Saturday': 5, 'Sunday': 6
        }
        
        target_day = day_map[expiry_day_name]
        current_day = reference_date.weekday()
        
        days_ahead = target_day - current_day
        if days_ahead < 0:  # If already past this week's expiry
            days_ahead += 7
        
        expiry_date = reference_date + timedelta(days=days_ahead)
        
        # If the market is closed on expiry day, adjust? (Not handling holidays here)
        return expiry_date
    
    @staticmethod
    def _get_next_monthly_expiry(reference_date, weekly_expiry_day):
        """
        Get next monthly expiry (last weekly expiry of the month)
        """
        year = reference_date.year
        month = reference_date.month
        
        last_expiry = IndianExpiryCalculator._get_last_weekday_of_month(
            year, month, weekly_expiry_day
        )
        
        if reference_date > last_expiry:
            month += 1
            if month > 12:
                month = 1
                year += 1
            last_expiry = IndianExpiryCalculator._get_last_weekday_of_month(
                year, month, weekly_expiry_day
            )
        
        return last_expiry
    
    @staticmethod
    def _get_last_weekday_of_month(year, month, weekday_name):
        """
        Get last specific weekday of the month
        """
        day_map = {
            'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 
            'Thursday': 3, 'Friday': 4, 'Saturday': 5, 'Sunday': 6
        }
        target_weekday = day_map[weekday_name]
        
        last_day = calendar.monthrange(year, month)[1]
        
        for day in range(last_day, 0, -1):
            date_obj = datetime(year, month, day)
            if date_obj.weekday() == target_weekday:
                return date_obj
        
        return None

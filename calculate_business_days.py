import pandas as pd

def calculate_business_days(start_date, end_date):
    if pd.isna(start_date) or pd.isna(end_date):
        return pd.NA
    # Ensure start_date is always earlier than or equal to end_date for bdate_range
    if start_date > end_date:
        start_date, end_date = end_date, start_date
        sign = -1 # Indicate that the original end date was earlier than the start date
    else:
        sign = 1
    
    # Generate a business day range and count the number of days
    # The bdate_range includes both start and end dates if they are business days
    # So, if start_date == end_date and it's a business day, count is 1
    # If start_date == end_date and it's a weekend, count is 0
    business_days = len(pd.bdate_range(start=start_date, end=end_date))
    
    # Adjust for the direction of the original date difference
    return business_days * sign



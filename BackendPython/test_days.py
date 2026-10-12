from datetime import datetime

def noOfDaysCalculation(start_date_str: str, end_date_str: str) -> int:
    try:
        # Handles 2024-02-11T... or 2024-02-11
        d1 = datetime.fromisoformat(start_date_str.replace('Z', '+00:00')).replace(tzinfo=None)
    except:
        d1 = datetime.strptime(start_date_str.split('T')[0], "%Y-%m-%d")
    try:
        d2 = datetime.fromisoformat(end_date_str.replace('Z', '+00:00')).replace(tzinfo=None)
    except:
        d2 = datetime.strptime(end_date_str.split('T')[0], "%Y-%m-%d")
    
    d1 = d1.replace(hour=0, minute=0, second=0, microsecond=0)
    d2 = d2.replace(hour=0, minute=0, second=0, microsecond=0)
    
    diff = abs((d1 - d2).days)
    return diff

# Test cases
print(f"Same day: {noOfDaysCalculation('2026-03-16', '2026-03-16')}")
print(f"ISO same day: {noOfDaysCalculation('2026-03-16', '2026-03-16T22:53:43')}")
print(f"One day apart: {noOfDaysCalculation('2026-03-15', '2026-03-16')}")

# Interest calculation simulation
interest_rate = 36.0
prev_principal_bal = 100000.0
days_diff = noOfDaysCalculation('2026-03-16', '2026-03-16')
interest_calc = (prev_principal_bal * interest_rate * days_diff) / (365 * 100)
print(f"Interest calc for same day: {interest_calc}")

# What if days_diff is 0, but it should be 0? Yes, it's 0.
# So why did Row 3 have interest?
# Maybe get_loan_summary is using a hardcoded +1 or something?

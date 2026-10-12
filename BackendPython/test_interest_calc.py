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

def test_dates():
    # Same day
    assert noOfDaysCalculation("2026-03-16", "2026-03-16") == 0
    assert noOfDaysCalculation("2026-03-16T12:00:00", "2026-03-16T15:00:00") == 0
    
    # Next day
    assert noOfDaysCalculation("2026-03-16", "2026-03-17") == 1
    
    # Gap
    assert noOfDaysCalculation("2026-03-10", "2026-03-16") == 6
    
    print("All tests passed!")

if __name__ == "__main__":
    test_dates()

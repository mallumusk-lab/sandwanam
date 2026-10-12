import pytest
from decimal import Decimal
from datetime import date, timedelta
from services import calculate_loan_status

def test_new_loan_calculation():
    """Test generating a statement on the first day of the loan"""
    loan_data = {
        'principle_amount': Decimal("100000.00"),
        'interest': Decimal("12.0")  # 12% annual
    }
    
    # As of date = 1 day after stmt_date
    stmt_date = date(2025, 1, 1)
    target_date = date(2025, 1, 2)
    
    latest_stmt = {
        'date': stmt_date,
        'principlebalance': Decimal("100000.00"),
        'interestbalance': Decimal("0.00")
    }

    status = calculate_loan_status(loan_data, latest_stmt, is_closing=False, as_of_date=target_date)
    
    assert status['current_principal'] == Decimal("100000.00")
    
    # Days diff = (Jan 2 - Jan 1) + 1 = 2 days EOD
    # Accrued = 100,000 * 12 * 2 / 36500 = 65.7534... -> 65.75
    assert status['days_since_last_payment'] == 2
    assert status['current_interest'] == Decimal("65.75")

def test_same_day_transaction():
    """Test EOD Logic: Same day transaction must accrue 1 day of interest"""
    loan_data = {
        'principle_amount': Decimal("50000.00"),
        'interest': Decimal("24.0") 
    }
    stmt_date = date(2025, 5, 5)
    
    latest_stmt = {
        'date': stmt_date,
        'principlebalance': Decimal("50000.00"),
        'interestbalance': Decimal("0.00")
    }

    status = calculate_loan_status(loan_data, latest_stmt, is_closing=False, as_of_date=stmt_date)
    
    # EOD Rule: (same day) -> diff is 0 + 1 = 1 day
    # Accrued = 50,000 * 24 * 1 / 36500 = 32.876... -> 32.88
    assert status['days_since_last_payment'] == 1
    assert status['current_interest'] == Decimal("32.88")

def test_early_closing_seven_day_rule():
    """Test standard business rule: closing within 7 days incurs 7 day interest penalty"""
    loan_data = {
        'principle_amount': Decimal("100000.00"),
        'interest': Decimal("12.0") 
    }
    stmt_date = date(2025, 1, 1)
    target_date = date(2025, 1, 3) # Only 3 days later
    
    latest_stmt = {
        'date': stmt_date,
        'principlebalance': Decimal("100000.00"),
        'interestbalance': Decimal("0.00")
    }

    # is_closing=True activates the 7-day floor
    status = calculate_loan_status(loan_data, latest_stmt, is_closing=True, as_of_date=target_date)
    
    assert status['days_since_last_payment'] == 7
    # Accrued = 100,000 * 12 * 7 / 36500 = 230.136... -> 230.14
    assert status['current_interest'] == Decimal("230.14")

def test_unpaid_interest_rollover():
    """Test that existing unpaid interest balance rolls over correctly"""
    loan_data = {
        'principle_amount': Decimal("10000.00"),
        'interest': Decimal("10.0") 
    }
    stmt_date = date(2025, 2, 1)
    target_date = date(2025, 2, 11)
    
    latest_stmt = {
        'date': stmt_date,
        'principlebalance': Decimal("10000.00"),
        'interestbalance': Decimal("150.00") # Already owed 150
    }

    status = calculate_loan_status(loan_data, latest_stmt, is_closing=False, as_of_date=target_date)
    
    # Days diff = 10 + 1 = 11 days
    # Accrued = 10,000 * 10 * 11 / 36500 = 30.136... -> 30.14
    # Total = 150 + 30.14 = 180.14
    assert status['current_interest'] == Decimal("180.14")

def test_missing_interest_fallback():
    """Test safety fallback for interest"""
    loan_data = {
        'principle_amount': Decimal("10000.00"),
        'interest': None # Missing!
    }
    stmt_date = date(2025, 1, 1)
    
    latest_stmt = {
        'date': stmt_date,
        'principlebalance': Decimal("10000.00"),
        'interestbalance': Decimal("0.00")
    }

    status = calculate_loan_status(loan_data, latest_stmt, is_closing=False, as_of_date=stmt_date)
    
    # Should default to 18.0 percent
    # Expected: 10,000 * 18 * 1 / 36500 = 4.93
    assert status['current_interest'] == Decimal("4.93")

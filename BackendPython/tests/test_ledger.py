import unittest
from datetime import date
from decimal import Decimal as D

from app.domain import ledger
from app.domain.interest import PeriodEnd, accrual_days, closing_days
from app.domain.ledger import (
    HistoryRow,
    ImportEvent,
    LedgerError,
    LoanTerms,
    Position,
    advance,
    close,
    collect,
    days_already_charged,
    quote,
    simulate,
    top_up,
)
from app.domain.money import AmountError

START = date(2025, 1, 1)
TERMS = LoanTerms.of(START, D("12"))


def fresh(principal="100000.00"):
    return Position(START, D(principal), D("0.00"))


class DayCounting(unittest.TestCase):
    def test_customer_periods_are_inclusive(self):
        self.assertEqual(accrual_days(date(2025, 1, 1), date(2025, 1, 1), PeriodEnd.CUSTOMER), 1)
        self.assertEqual(accrual_days(date(2025, 1, 1), date(2025, 1, 10), PeriodEnd.CUSTOMER), 10)

    def test_compounding_periods_are_exact(self):
        self.assertEqual(accrual_days(date(2025, 1, 1), date(2026, 1, 1), PeriodEnd.COMPOUNDING), 365)

    def test_backwards_period_is_rejected(self):
        with self.assertRaises(ValueError):
            accrual_days(date(2025, 1, 2), date(2025, 1, 1), PeriodEnd.CUSTOMER)

    def test_consecutive_periods_double_count_the_boundary_day(self):
        """Agreed rule: Jan 1→10 is 10 days and Jan 10→20 is 11 days."""
        first = quote(TERMS, fresh(), date(2025, 1, 10))
        paid = collect(first, first.interest)
        second = quote(TERMS, advance(first.position, paid), date(2025, 1, 20))
        self.assertEqual((first.period_days, second.period_days), (10, 11))

    def test_closing_minimum(self):
        self.assertEqual(closing_days(3, 0, 3), 7)
        self.assertEqual(closing_days(2, 3, 5), 4)
        self.assertEqual(closing_days(8, 0, 8), 8)


class Collections(unittest.TestCase):
    def test_interest_is_settled_before_principal(self):
        q = quote(TERMS, fresh(), date(2025, 1, 10))  # 10 days → 328.77
        self.assertEqual(q.interest, D("328.77"))
        entry = collect(q, "1000")
        self.assertEqual(entry.current_interest, D("328.77"))
        self.assertEqual(entry.current_principal, D("-671.23"))
        self.assertEqual(entry.principal_balance, D("99328.77"))
        self.assertEqual(entry.interest_balance, D("0.00"))
        self.assertEqual(entry.accrued_days, 10)

    def test_partial_interest_payment_leaves_interest_owed(self):
        q = quote(TERMS, fresh(), date(2025, 1, 10))
        entry = collect(q, "100")
        self.assertEqual(entry.current_principal, D("0.00"))
        self.assertEqual(entry.interest_balance, D("228.77"))
        self.assertEqual(entry.principal_balance, D("100000.00"))

    def test_settling_in_full_must_use_close(self):
        """Otherwise the 7-day minimum is skipped and the loan is left open at ₹0."""
        q = quote(TERMS, fresh(), date(2025, 1, 10))
        for amount in (q.total, q.total + D("0.01")):
            with self.subTest(amount), self.assertRaises(LedgerError) as ctx:
                collect(q, amount)
            self.assertEqual(ctx.exception.code, "settle_with_close")
        entry = collect(q, q.total - D("0.01"))
        self.assertEqual(entry.principal_balance + entry.interest_balance, D("0.01"))

    def test_first_week_payments_cover_interest_only(self):
        """Otherwise repaying principal before closing would avoid the 7-day minimum."""
        q = quote(TERMS, fresh(), date(2025, 1, 3))
        self.assertEqual(collect(q, q.interest).current_principal, D("0.00"))
        with self.assertRaises(LedgerError) as ctx:
            collect(q, q.interest + D("1"))
        self.assertEqual(ctx.exception.code, "early_principal")
        closing = quote(TERMS, fresh(), date(2025, 1, 3), closing=True)
        self.assertEqual(closing.interest, D("230.14"), "closing still charges the 7-day minimum")

    def test_legacy_interest_credit_never_makes_interest_paid_negative(self):
        credit = Position(date(2025, 2, 1), D("10000.00"), D("-50.00"))
        q = quote(TERMS, credit, date(2025, 2, 2))
        self.assertEqual(q.principal, D("9950.00"), "the credit reduces what is owed")
        entry = collect(q, "100")
        self.assertGreaterEqual(entry.current_interest, D("0.00"))
        self.assertEqual(entry.principal_balance + entry.interest_balance, q.total - D("100"))
        settled = close(quote(TERMS, credit, date(2025, 2, 2), closing=True), q.total, write_off_remaining=False)
        self.assertEqual((settled[-1].principal_balance, settled[-1].interest_balance), (D("0.00"), D("0.00")))

    def test_zero_negative_and_fractional_paise_are_rejected(self):
        q = quote(TERMS, fresh(), date(2025, 1, 10))
        for bad in ("0", "-500", "10.005", "abc"):
            with self.subTest(bad), self.assertRaises(AmountError):
                collect(q, bad)

    def test_backdated_entry_is_rejected(self):
        position = Position(date(2025, 3, 1), D("1000.00"), D("0.00"))
        with self.assertRaises(LedgerError) as ctx:
            quote(TERMS, position, date(2025, 2, 28))
        self.assertEqual(ctx.exception.code, "backdated")


class TopUps(unittest.TestCase):
    def test_top_up_keeps_accrued_interest_owed(self):
        q = quote(TERMS, fresh(), date(2025, 1, 10))
        entry = top_up(q, "5000")
        self.assertEqual(entry.kind, ledger.TOP_UP)
        self.assertEqual(entry.current_principal, D("5000.00"))
        self.assertEqual(entry.principal_balance, D("105000.00"))
        self.assertEqual(entry.interest_balance, D("328.77"))
        self.assertEqual(entry.amount_paid, D("0.00"))


class Closing(unittest.TestCase):
    def test_full_settlement_records_the_cash_received(self):
        q = quote(TERMS, fresh(), date(2025, 1, 3), closing=True)
        entries = close(q, q.total, write_off_remaining=False)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].kind, ledger.COLLECTION)
        self.assertEqual(entries[0].amount_paid, q.total)
        self.assertEqual(entries[0].accrued_days, 7)

    def test_short_payment_requires_confirmation(self):
        q = quote(TERMS, fresh(), date(2025, 2, 1), closing=True)
        with self.assertRaises(LedgerError) as ctx:
            close(q, "5000", write_off_remaining=False)
        self.assertEqual(ctx.exception.code, "writeoff_not_confirmed")

    def test_short_payment_writes_off_the_rest_once(self):
        q = quote(TERMS, fresh(), date(2025, 2, 1), closing=True)  # 32 days → 1052.05
        payment, writeoff = close(q, "5000", write_off_remaining=True)
        self.assertEqual(payment.amount_paid, D("5000.00"))
        self.assertEqual(payment.accrued_days, 32)
        self.assertEqual(writeoff.kind, ledger.WRITE_OFF)
        self.assertEqual(writeoff.accrued_days, 0, "interest must not accrue twice for one closing")
        self.assertEqual(writeoff.writeoff_principal + writeoff.writeoff_interest, q.total - D("5000.00"))
        self.assertEqual((writeoff.principal_balance, writeoff.interest_balance), (D("0.00"), D("0.00")))

    def test_full_write_off_carries_the_accrual(self):
        q = quote(TERMS, fresh(), date(2025, 2, 1), closing=True)
        (writeoff,) = close(q, "0", write_off_remaining=True)
        self.assertEqual(writeoff.accrued_days, 32)
        self.assertEqual(writeoff.writeoff_interest, q.interest)

    def test_nothing_owed_closes_without_entries(self):
        q = quote(TERMS, Position(date(2025, 1, 20), D("0.00"), D("0.00")), date(2025, 2, 1), closing=True)
        self.assertEqual(close(q, "0", write_off_remaining=False), [])

    def test_receiving_more_than_owed_is_rejected(self):
        q = quote(TERMS, fresh(), date(2025, 2, 1), closing=True)
        with self.assertRaises(LedgerError):
            close(q, q.total + 1, write_off_remaining=True)

    def test_days_already_charged_counts_legacy_rows_exactly(self):
        rows = [
            HistoryRow(date(2025, 1, 1), ledger.NEW_LOAN, None),
            HistoryRow(date(2025, 1, 3), ledger.COLLECTION, None),
            HistoryRow(date(2025, 1, 4), ledger.COLLECTION, 2),
        ]
        self.assertEqual(days_already_charged(rows), 4)


class Compounding(unittest.TestCase):
    def test_anniversaries_are_anchored_to_the_loan_date(self):
        position = Position(START, D("100000.00"), D("0.00"), compoundings=1)
        entries, after = ledger.due_compoundings(TERMS, position, date(2026, 6, 1))
        self.assertEqual(entries, [])
        entries, after = ledger.due_compoundings(TERMS, position, date(2027, 1, 1))
        self.assertEqual([e.on for e in entries], [date(2027, 1, 1)])
        self.assertEqual(after.compoundings, 2)

    def test_missed_anniversary_is_dated_on_the_latest_entry(self):
        late = Position(date(2026, 3, 1), D("100000.00"), D("50.00"))
        entries, _ = ledger.due_compoundings(TERMS, late, date(2026, 3, 5))
        self.assertEqual(entries[0].on, date(2026, 3, 1))
        self.assertEqual(entries[0].accrued_days, 0)
        self.assertEqual(entries[0].current_principal, D("50.00"))


class HistorySimulation(unittest.TestCase):
    def test_replay_compounds_between_events_and_up_to_today(self):
        events = [
            ImportEvent(date(2025, 6, 1), ledger.COLLECTION, D("2000")),
            ImportEvent(date(2026, 2, 1), ledger.TOP_UP, D("10000")),
        ]
        entries = simulate(TERMS, D("100000"), events, today=date(2027, 1, 2))
        kinds = [e.kind for e in entries]
        self.assertEqual(kinds, ["newLoan", "addColl", "compounding", "disbursement", "compounding"])
        dates = [e.on for e in entries]
        self.assertEqual(dates, sorted(dates))

    def test_events_out_of_range_are_rejected(self):
        with self.assertRaises(LedgerError):
            simulate(TERMS, D("1000"), [ImportEvent(date(2024, 12, 31), ledger.COLLECTION, D("1"))], date(2025, 2, 1))
        with self.assertRaises(LedgerError):
            simulate(TERMS, D("1000"), [ImportEvent(date(2025, 3, 1), ledger.COLLECTION, D("1"))], date(2025, 2, 1))


if __name__ == "__main__":
    unittest.main()

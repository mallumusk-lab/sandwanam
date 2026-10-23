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

    def test_first_week_payment_reduces_principal_by_its_full_amount(self):
        """Replaces the earlier interest-only rule: in days 1-7 a payment goes wholly to principal."""
        q = quote(TERMS, fresh(), date(2025, 1, 3))
        self.assertTrue(q.first_week)
        entry = collect(q, "30000")
        self.assertEqual((entry.current_principal, entry.current_interest), (D("-30000.00"), D("0.00")))
        self.assertEqual((entry.principal_balance, entry.interest_balance), (D("70000.00"), D("0.00")))
        self.assertEqual(entry.accrued_days, 0, "no daily interest is recorded in the first 7 days")
        closing = quote(TERMS, advance(q.position, entry), date(2025, 1, 3), closing=True)
        self.assertEqual(closing.interest, D("230.14"), "7 days on the peak (100000), not on 70000")

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


TERMS18 = LoanTerms.of(START, D("18"))


def day(n):
    """Inclusive loan day n (day 1 is the loan date)."""
    return date(2025, 1, n)


class FirstWeek(unittest.TestCase):
    """The first-7-days rule: 7 days' interest on the highest principal reached in days 1-7."""

    def scenario(self, terms=TERMS18):
        """The user's example: 100000, pays 30000 on day 2, adds 50000 on day 4."""
        q = quote(terms, fresh(), day(2))
        paid = collect(q, "30000")
        position = advance(q.position, paid)
        q = quote(terms, position, day(4))
        added = top_up(q, "50000")
        return paid, added, advance(q.position, added)

    def test_users_scenario_closes_on_day_five_with_seven_days_on_the_peak(self):
        paid, added, position = self.scenario()
        self.assertEqual((paid.principal_balance, paid.accrued_days, paid.current_interest), (D("70000.00"), 0, D("0.00")))
        self.assertEqual((added.principal_balance, added.accrued_days, added.interest_balance), (D("120000.00"), 0, D("0.00")))
        self.assertEqual(position.window_peak, D("120000.00"))
        q = quote(TERMS18, position, day(5), closing=True)
        self.assertEqual((q.interest, q.total, q.period_days), (D("414.25"), D("120414.25"), 7))
        self.assertTrue(q.first_week)
        self.assertEqual((q.window_peak, q.first_week_interest), (D("120000.00"), D("414.25")))
        (payment,) = close(q, q.total, write_off_remaining=False)
        self.assertEqual((payment.current_interest, payment.current_principal), (D("414.25"), D("-120000.00")))
        self.assertEqual((payment.principal_balance, payment.interest_balance, payment.accrued_days),
                         (D("0.00"), D("0.00"), 7))

    def test_users_scenario_closed_on_day_ten_adds_the_days_after_day_seven(self):
        _, _, position = self.scenario()
        q = quote(TERMS18, position, day(10), closing=True)
        # 7 days on the peak 120000 + 3 days on 120000, rounded once = 10 days on 120000
        self.assertEqual((q.interest, q.period_days), (D("591.78"), 10))
        self.assertFalse(q.first_week)
        self.assertEqual((q.window_peak, q.first_week_interest), (D("120000.00"), None))
        self.assertEqual(quote(TERMS18, position, day(10)).interest, D("591.78"), "display quote matches")

    def test_day_two_payment_then_close_on_day_five(self):
        q = quote(TERMS, fresh(), day(2))
        position = advance(q.position, collect(q, "30000"))
        closing = quote(TERMS, position, day(5), closing=True)
        self.assertEqual((closing.principal, closing.interest, closing.total), (D("70000.00"), D("230.14"), D("70230.14")))

    def test_closing_on_day_three_without_events(self):
        q = quote(TERMS, fresh(), day(3), closing=True)
        self.assertEqual((q.interest, q.period_days, q.first_week), (D("230.14"), 7, True))

    def test_payment_that_clears_the_principal_is_refused(self):
        q = quote(TERMS, fresh(), day(2))
        for amount in ("100000", "100000.01", "250000"):
            with self.subTest(amount), self.assertRaises(LedgerError) as ctx:
                collect(q, amount)
            self.assertEqual(ctx.exception.code, "first_week_clears_principal")
            self.assertIn("use Close loan", ctx.exception.message)
        self.assertEqual(collect(q, "99999.99").principal_balance, D("0.01"))

    def test_peak_ignores_payments_and_display_shows_peak_interest_so_far(self):
        q = quote(TERMS, fresh(), day(2))
        position = advance(q.position, collect(q, "60000"))
        self.assertEqual(position.window_peak, D("100000.00"))
        shown = quote(TERMS, position, day(3))
        self.assertEqual((shown.principal, shown.interest, shown.period_days), (D("40000.00"), D("98.63"), 3))
        self.assertEqual(shown.window_peak, D("100000.00"))

    def test_top_up_in_the_window_accrues_nothing_and_raises_the_peak(self):
        q = quote(TERMS, fresh(), day(3))
        entry = top_up(q, "20000")
        self.assertEqual((entry.principal_balance, entry.interest_balance, entry.accrued_days),
                         (D("120000.00"), D("0.00"), 0))
        closing = quote(TERMS, advance(q.position, entry), day(7), closing=True)
        self.assertEqual(closing.interest, D("276.16"), "120000 × 12% × 7 ÷ 365")

    def test_day_eight_rounds_the_two_parts_once(self):
        q = quote(TERMS, fresh(), day(8), closing=True)
        # 230.1369… + 32.8767… = 263.0137 → 263.01 (rounding each part would give 263.02)
        self.assertEqual((q.interest, q.period_days), (D("263.01"), 8))

    def test_first_event_after_day_seven_settles_and_inclusive_counting_resumes(self):
        q = quote(TERMS, fresh(), day(2))
        position = advance(q.position, collect(q, "30000"))
        settle = quote(TERMS, position, day(10))
        # 7 days on 100000 (230.1369…) + 3 days on 70000 (69.0410…) = 299.18
        self.assertEqual((settle.interest, settle.period_days), (D("299.18"), 10))
        paid = collect(settle, "1000")
        self.assertEqual((paid.accrued_days, paid.current_interest), (10, D("299.18")))
        later = quote(TERMS, advance(settle.position, paid), day(20))
        self.assertEqual(later.period_days, 11, "10 → 20 counted inclusively")
        self.assertIsNone(later.window_peak)

    def test_compounding_settles_an_unsettled_first_week(self):
        q = quote(TERMS, fresh(), day(3))
        position = advance(q.position, top_up(q, "50000"))
        q = quote(TERMS, position, day(5))
        position = advance(q.position, collect(q, "50000"))
        entries, after = ledger.due_compoundings(TERMS, position, date(2026, 1, 1))
        (compounding,) = entries
        # 7 days on 150000 (345.2054…) + 358 exact days on 100000 (11769.8630…) = 12115.07
        self.assertEqual((compounding.accrued_days, compounding.current_principal), (365, D("12115.07")))
        self.assertEqual(after.principal, D("112115.07"))

    def test_loans_begun_under_the_earlier_rule_are_not_charged_twice(self):
        # Day 3 under the earlier rule: 3 days (98.63) charged and paid, nothing owed.
        paid_before = Position(day(3), D("100000.00"), D("0.00"), window_interest_paid=D("98.63"))
        q = quote(TERMS, paid_before, day(5), closing=True)
        self.assertEqual(q.interest, D("131.51"), "230.1369… less the 98.63 already charged")
        owed_before = Position(day(3), D("100000.00"), D("50.00"), window_interest_paid=D("48.63"))
        self.assertEqual(quote(TERMS, owed_before, day(5), closing=True).interest, D("181.51"))
        over = Position(day(3), D("100000.00"), D("10.00"), window_interest_paid=D("300.00"))
        self.assertEqual(quote(TERMS, over, day(5), closing=True).interest, D("10.00"), "never below what is owed")
        after = quote(TERMS, paid_before, day(10))
        self.assertEqual(after.interest, D("230.14"), "7 days less 98.63, plus 3 days on 100000")

    def test_history_import_follows_the_same_rule(self):
        events = [ImportEvent(day(2), ledger.COLLECTION, D("30000")), ImportEvent(day(4), ledger.TOP_UP, D("50000")),
                  ImportEvent(day(10), ledger.COLLECTION, D("1000"))]
        entries = simulate(TERMS18, D("100000"), events, today=day(12))
        self.assertEqual([e.kind for e in entries], ["newLoan", "addColl", "disbursement", "addColl"])
        self.assertEqual([e.accrued_days for e in entries], [0, 0, 0, 10])
        self.assertEqual(entries[1].principal_balance, D("70000.00"))
        self.assertEqual(entries[3].current_interest, D("591.78"))
        self.assertEqual(entries[3].principal_balance, D("119591.78"))
        with self.assertRaises(LedgerError) as ctx:
            simulate(TERMS18, D("100000"), [ImportEvent(day(3), ledger.COLLECTION, D("100000"))], today=day(12))
        self.assertEqual(ctx.exception.code, "first_week_clears_principal")


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

    def test_replayed_close_uses_the_live_closing_rules_and_stops_compounding(self):
        events = [ImportEvent(day(2), ledger.COLLECTION, D("30000")), ImportEvent(day(4), ledger.TOP_UP, D("50000")),
                  ImportEvent(day(5), ledger.CLOSING, D("120414.25"))]
        entries = simulate(TERMS18, D("100000"), events, today=date(2027, 6, 1))
        self.assertEqual([e.kind for e in entries], ["newLoan", "addColl", "disbursement", "addColl"],
                         "no compounding after the close, years later")
        closing = entries[-1]
        self.assertEqual((closing.current_interest, closing.current_principal, closing.accrued_days),
                         (D("414.25"), D("-120000.00"), 7), "7 days on the window peak, as a live close")
        self.assertEqual((closing.principal_balance, closing.interest_balance), (D("0.00"), D("0.00")))
        with self.assertRaises(LedgerError) as ctx:
            simulate(TERMS18, D("100000"), [ImportEvent(day(5), ledger.CLOSING, D("1000"))], today=day(20))
        self.assertEqual(ctx.exception.code, "writeoff_not_confirmed")
        written = simulate(TERMS18, D("100000"), [ImportEvent(day(5), ledger.CLOSING, D("1000"), True)], today=day(20))
        self.assertEqual([e.kind for e in written[1:]], ["addColl", "writeoff"])
        self.assertEqual((written[-1].writeoff_principal, written[-1].writeoff_interest), (D("99345.21"), D("0.00")))

    def test_replayed_close_must_be_last_and_only_once(self):
        close_ = ImportEvent(day(5), ledger.CLOSING, D("100345.21"))
        for events, code in (([close_, ImportEvent(day(6), ledger.COLLECTION, D("10"))], "close_not_last"),
                             ([close_, ImportEvent(day(6), ledger.CLOSING, D("0"), True)], "close_twice")):
            with self.subTest(code), self.assertRaises(LedgerError) as ctx:
                simulate(TERMS18, D("100000"), events, today=day(20))
            self.assertEqual(ctx.exception.code, code)

    def test_events_out_of_range_are_rejected(self):
        with self.assertRaises(LedgerError):
            simulate(TERMS, D("1000"), [ImportEvent(date(2024, 12, 31), ledger.COLLECTION, D("1"))], date(2025, 2, 1))
        with self.assertRaises(LedgerError):
            simulate(TERMS, D("1000"), [ImportEvent(date(2025, 3, 1), ledger.COLLECTION, D("1"))], date(2025, 2, 1))


if __name__ == "__main__":
    unittest.main()

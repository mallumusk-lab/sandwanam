"""The statement's "Show calculation" breakdown (app/domain/statement_calc.py)."""
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal as D

from app.domain import ledger
from app.domain.ledger import ImportEvent, LoanTerms, Position, advance, close, collect, quote, simulate, top_up
from app.domain.statement_calc import AS_RECORDED_NOTE, LEGACY_NOTE, explain

START = date(2025, 1, 1)
TERMS = LoanTerms.of(START, D("12"))
TERMS18 = LoanTerms.of(START, D("18"))
STAMP = datetime(2026, 10, 1, tzinfo=timezone.utc)


def rows_of(entries, *, legacy=False):
    return [
        dict(statementid=i + 1, transactiontype=e.kind, date=e.on, amountpaid=e.amount_paid,
             currentprincipal=e.current_principal, currentinterest=e.current_interest,
             principlebalance=e.principal_balance, interestbalance=e.interest_balance, accrued_days=e.accrued_days,
             writeoff_principal=e.writeoff_principal, writeoff_interest=e.writeoff_interest,
             created_at=None if legacy else STAMP)
        for i, e in enumerate(entries)
    ]


def replay(terms, principal, steps):
    """Run (day, action, amount) steps through the ledger like the live services do."""
    entries = [ledger.opening_entry(terms, D(principal))]
    position = Position(terms.start_date, D(principal), D("0.00"))
    for on, action, amount in steps:
        q = quote(terms, position, on, closing=action == "close")
        made = list(q.compoundings)
        if action == "pay":
            made.append(collect(q, amount))
        elif action == "top_up":
            made.append(top_up(q, amount))
        else:
            made.extend(close(q, amount, write_off_remaining=True))
        entries.extend(made)
        for entry in made:
            position = advance(position, entry)
    return entries


class Explain(unittest.TestCase):
    def test_users_first_week_scenario(self):
        entries = replay(TERMS18, "100000", [(date(2025, 1, 2), "pay", "30000"), (date(2025, 1, 4), "top_up", "50000"),
                                             (date(2025, 1, 5), "close", "120414.25")])
        calcs = explain(TERMS18, rows_of(entries), opening=D("100000"))
        self.assertEqual([c.method for c in calcs], ["opening", "first_week", "first_week", "first_week_settlement"])
        self.assertIn("payment reduces principal by ₹30000.00", calcs[1].note)
        self.assertEqual((calcs[1].days, calcs[1].interest_accrued, calcs[1].principal_paid),
                         (0, D("0.00"), D("30000.00")))
        settle = calcs[3]
        self.assertEqual((settle.peak_principal, settle.days, settle.first_week_days, settle.extra_days),
                         (D("120000.00"), 7, 7, 0))
        self.assertEqual((settle.interest_accrued, settle.interest_paid, settle.principal_paid),
                         (D("414.25"), D("414.25"), D("120000.00")))
        self.assertEqual((settle.period_from, settle.period_to), (START, date(2025, 1, 7)))
        self.assertIsNone(settle.extra_principal)
        self.assertIn("₹120000.00 × 18% × 7 ÷ 365 = ₹414.25", settle.note)

    def test_settlement_after_day_seven_then_inclusive_days(self):
        entries = replay(TERMS, "100000", [(date(2025, 1, 2), "pay", "30000"), (date(2025, 1, 10), "pay", "1000"),
                                           (date(2025, 1, 20), "pay", "1000")])
        calcs = explain(TERMS, rows_of(entries), opening=D("100000"))
        self.assertEqual([c.method for c in calcs], ["opening", "first_week", "first_week_settlement", "inclusive"])
        settle = calcs[2]
        self.assertEqual((settle.days, settle.extra_days, settle.extra_principal, settle.peak_principal),
                         (10, 3, D("70000.00"), D("100000.00")))
        self.assertEqual(settle.interest_accrued, D("299.18"))
        self.assertIn("plus 3 days after day 7: ₹70000.00 × 12% × 3 ÷ 365", settle.note)
        normal = calcs[3]
        self.assertEqual((normal.period_from, normal.period_to, normal.days), (date(2025, 1, 10), date(2025, 1, 20), 11))
        self.assertEqual(normal.principal_charged, entries[2].principal_balance)
        self.assertEqual(normal.rate, D("12"))
        self.assertIn("× 12% × 11 ÷ 365", normal.note)

    def test_compounding_rows(self):
        entries = simulate(TERMS, D("100000"), [], today=date(2027, 1, 1))
        calcs = explain(TERMS, rows_of(entries), opening=D("100000"))
        self.assertEqual([c.method for c in calcs], ["opening", "compounding", "compounding"])
        first, second = calcs[1:]
        self.assertEqual((first.days, first.interest_accrued), (365, D("12000.00")))
        self.assertIn("Yearly compounding", first.note)
        self.assertEqual((second.days, second.principal_charged, second.interest_accrued),
                         (365, D("112000.00"), D("13440.00")))
        self.assertIn("exact days", second.note)

    def test_write_offs(self):
        partial = replay(TERMS, "100000", [(date(2025, 2, 1), "close", "5000")])
        calcs = explain(TERMS, rows_of(partial), opening=D("100000"))
        self.assertEqual([c.method for c in calcs], ["opening", "inclusive", "writeoff"])
        self.assertEqual(calcs[2].days, 0)
        self.assertIn("Written off: principal ₹96052.05, interest ₹0.00.", calcs[2].note)
        full = replay(TERMS, "100000", [(date(2025, 2, 1), "close", "0")])
        (writeoff,) = explain(TERMS, rows_of(full), opening=D("100000"))[1:]
        self.assertEqual((writeoff.method, writeoff.days, writeoff.interest_accrued), ("writeoff", 32, D("1052.05")))

    def test_payment_after_day_seven_without_first_week_activity_uses_inclusive_period(self):
        start = date(2026, 5, 12)
        terms = LoanTerms.of(start, D("18"))
        entries = replay(terms, "10000", [(date(2026, 9, 2), "pay", "1000")])
        calcs = explain(terms, rows_of(entries), opening=D("10000"))
        self.assertEqual([c.method for c in calcs], ["opening", "inclusive"])
        payment = calcs[1]
        self.assertEqual((payment.period_from, payment.period_to, payment.days), (start, date(2026, 9, 2), 114))
        self.assertEqual(payment.principal_charged, D("10000.00"))
        self.assertEqual(payment.interest_accrued, D("562.19"))
        self.assertEqual(payment.interest_paid, D("562.19"))
        self.assertEqual(payment.principal_paid, D("437.81"))
        self.assertIsNone(payment.peak_principal)
        self.assertIsNone(payment.first_week_days)
        self.assertIn("114 days (12 May 2026 to 2 Sep 2026, both days counted): ₹10000.00 × 18% × 114 ÷ 365 = ₹562.19.", payment.note)

    def test_legacy_rows_are_not_recalculated(self):
        legacy = rows_of(replay(TERMS, "100000", [(date(2025, 2, 1), "pay", "1000")]), legacy=True)
        later = rows_of(replay(TERMS, "100000", [(date(2025, 2, 1), "pay", "1000"), (date(2025, 3, 1), "pay", "500")]))
        rows = legacy + later[2:]
        calcs = explain(TERMS, rows, opening=D("100000"))
        self.assertEqual([c.method for c in calcs], ["legacy", "legacy", "inclusive"])
        self.assertEqual(calcs[0].note, LEGACY_NOTE)
        self.assertEqual(calcs[1].principal_balance, legacy[1]["principlebalance"], "stored balances are shown")

    def test_loan_begun_under_the_earlier_rule(self):
        # Day 3 under the earlier rule: 3 days' interest (98.63) paid inside the first week.
        rows = rows_of([
            ledger.opening_entry(TERMS, D("100000")),
            ledger.Entry(ledger.COLLECTION, date(2025, 1, 3), D("98.63"), D("0.00"), D("98.63"), D("100000.00"),
                         D("0.00"), 3),
            # 230.1369 less 98.63 charged, plus 3 days on 100000 (98.6301), rounded once
            ledger.Entry(ledger.COLLECTION, date(2025, 1, 10), D("1000.00"), D("-769.86"), D("230.14"),
                         D("99230.14"), D("0.00"), 10),
        ])
        calcs = explain(TERMS, rows, opening=D("100000"))
        self.assertEqual([c.method for c in calcs], ["opening", "inclusive", "first_week_settlement"])
        self.assertIn("less ₹98.63 already charged", calcs[2].note)

    def test_mismatch_is_shown_as_recorded_and_nothing_raises(self):
        rows = rows_of(replay(TERMS, "100000", [(date(2025, 1, 10), "pay", "1000"), (date(2025, 1, 20), "pay", "1000")]))
        rows[2]["currentinterest"] += D("0.01")  # no longer follows from the balances
        rows.append(dict(statementid=99, transactiontype="addColl", date=None, created_at=STAMP))
        rows.append(dict(statementid=100, transactiontype="mystery", date=date(2025, 2, 1), created_at=STAMP,
                         principlebalance="x", accrued_days=1))
        calcs = explain(TERMS, rows, opening=D("100000"))
        self.assertEqual([c.method for c in calcs],
                         ["opening", "inclusive", "as_recorded", "as_recorded", "as_recorded"])
        self.assertEqual(calcs[3].note, AS_RECORDED_NOTE)
        self.assertEqual(explain(TERMS, []), [])


if __name__ == "__main__":
    unittest.main()

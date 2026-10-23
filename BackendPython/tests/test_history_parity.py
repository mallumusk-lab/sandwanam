"""History import must leave a loan exactly as if every entry had been recorded live on its own date.

Each scenario runs twice on separate in-memory databases:
  live:   the loan is created and every entry posted through loans_service with `now` = that day
          (12:00 IST), the daily compounding job runs on each anniversary, and once more today;
  import: import_service.commit enters the same loan and entries in one go, today.
Every ledger row, the loan's final status and the live quotes must then be identical.
"""
import asyncio
import importlib.util
import unittest
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D

from app.domain import dates, ledger
from app.domain.interest import interest_for
from app.domain.money import money
from app.errors import AppError, Invalid
from app.services import customers_service, import_service, loans_service, receipts_service
from app.services.auth_service import actor_from
from app.services.customers_service import NewCustomer
from app.services.loans_service import NewLoan
from tests.fakes import standard_repos

ITEMS = [{"name": "Chain", "qty": 1}]
CUSTOMER = NewCustomer("Lakshmi Nair", "9876543210", "Uchakkada, Kerala")
ROW_FIELDS = ("transactiontype", "amountpaid", "currentprincipal", "currentinterest", "principlebalance",
              "interestbalance", "accrued_days", "writeoff_principal", "writeoff_interest")
IDENTITY = ("loan_number", "customer_id", "customer_number", "customer_name")
FULL = "full"  # a close amount meaning "the closing amount shown that day"


def run(coro):
    return asyncio.run(coro)


def noon(day: date) -> datetime:
    """12:00 IST on `day` (06:30 UTC)."""
    return datetime(day.year, day.month, day.day, 6, 30, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Event:
    on: date
    kind: str  # "addColl", "disbursement" or "close"
    amount: str = FULL
    write_off: bool = False


def pay(on, amount):
    return Event(on, ledger.COLLECTION, amount)


def add(on, amount):
    return Event(on, ledger.TOP_UP, amount)


def close(on, amount=FULL, write_off=False):
    return Event(on, ledger.CLOSING, amount, write_off)


@dataclass
class Outcome:
    rows: list
    loan: dict | None
    statements: list | None
    quote_today: dict | None
    closing_today: dict | None
    customer_status: str | None
    error: tuple | None = None


class Harness:
    def __init__(self):
        self.repos = standard_repos()
        self.actor = actor_from(self.repos.state.users["User1"])

    def rows(self, loan_number):
        entries = sorted((s for s in self.repos.state.statements if s["loan_number"] == loan_number),
                         key=lambda s: (s["date"], s["statementid"]))
        return [(dates.business_date(s["date"]),) + tuple(s[f] for f in ROW_FIELDS) for s in entries]

    def outcome(self, loan_number, customer_id, today, error=None):
        if loan_number is None:
            return Outcome([], None, None, None, None, None, error)
        now = noon(today)
        detail = run(loans_service.detail(self.repos, self.actor, loan_number, now))
        loan = {k: v for k, v in detail["loan"].items() if k not in IDENTITY}
        statements = [{k: v for k, v in s.items() if k not in ("id", "loan_number", "at", "recorded_by")}
                      for s in detail["statements"]]
        stored = self.repos.state.loans[loan_number]
        loan["stored"] = (stored["loantype"], dates.business_date(stored["closed_at"]) if stored["closed_at"] else None,
                          stored["refreshprincipleamount"], stored["refreshinterest"])
        closing = None
        if stored["loantype"] == "open":
            closing = run(loans_service.closing_quote(self.repos, self.actor, loan_number, now))
        status = self.repos.state.customers[customer_id]["loanstatus"]
        return Outcome(self.rows(loan_number), loan, statements, detail["loan"]["outstanding"], closing, status, error)


def _error(exc: AppError) -> tuple:
    return type(exc).__name__, exc.code, exc.message


class LiveRun(Harness):
    """Every entry posted on its own day, as staff would have done, with the nightly compounding."""

    def __call__(self, loan_date, principal, rate, events, today):
        customer = run(customers_service.create(self.repos, self.actor, CUSTOMER))
        data = NewLoan(customer["id"], ITEMS, "20", "1", principal, rate, 12)
        number = run(loans_service.create(self.repos, self.actor, data, request_id="live-loan", now=noon(loan_date)))[
            "loan_number"]
        terms = ledger.LoanTerms.of(loan_date, D(rate))
        anniversaries = [ledger.anniversary(terms, k) for k in range(1, 20)]
        closed, error, amounts = False, None, []
        for index, event in enumerate(events):
            for due in [a for a in anniversaries if a <= event.on]:
                run(loans_service.apply_due_compounding(self.repos, number, noon(due)))  # the night job, that day
            anniversaries = [a for a in anniversaries if a > event.on]
            now = noon(event.on)
            request_id = f"live-{index:04d}"
            try:
                if event.kind == ledger.COLLECTION:
                    run(loans_service.collect(self.repos, self.actor, number, amount=event.amount, expected_total=None,
                                              request_id=request_id, now=now))
                elif event.kind == ledger.TOP_UP:
                    run(loans_service.top_up(self.repos, self.actor, number, amount=event.amount, expected_total=None,
                                             request_id=request_id, now=now))
                else:
                    shown = run(loans_service.closing_quote(self.repos, self.actor, number, now))
                    amount = shown["total"] if event.amount == FULL else event.amount
                    run(loans_service.close(self.repos, self.actor, number, amount_received=amount,
                                            write_off_remaining=event.write_off, expected_total=shown["total"],
                                            request_id=request_id, now=now))
                    closed = True
            except AppError as exc:
                error = _error(exc)
                break
            amounts.append(amount if event.kind == ledger.CLOSING else event.amount)
        if not closed and error is None:
            for due in [a for a in anniversaries if a <= today]:
                run(loans_service.apply_due_compounding(self.repos, number, noon(due)))
            run(loans_service.apply_due_compounding(self.repos, number, noon(today)))
        self.amounts = amounts
        return self.outcome(number, customer["id"], today, error)


class ImportRun(Harness):
    """The same loan and entries entered today through history import (preview, then commit)."""

    def __call__(self, loan_date, principal, rate, events, amounts, today):
        loan = import_service.HistoryLoan(ITEMS, "20", "1", principal, rate, 12, loan_date)
        entries = [import_service.HistoryEntry(e.on, e.kind, amount, e.write_off) for e, amount in zip(events, amounts)]
        now = noon(today)
        try:
            self.preview = run(import_service.preview(self.actor, loan, entries, now))
            expected = {k: self.preview[k] for k in ("principal_balance", "interest_balance")}
            result = run(import_service.commit(self.repos, self.actor, customer_id=None, new_customer=CUSTOMER,
                                               loan=loan, entries=entries, request_id="import-loan", now=now,
                                               expected=expected))
        except AppError as exc:
            return self.outcome(None, None, today, _error(exc))
        return self.outcome(result["loan_number"], result["customer_id"], today)


class Parity(unittest.TestCase):
    def check(self, loan_date, events, today, *, principal="100000", rate="18"):
        live = LiveRun()
        expected = live(loan_date, principal, rate, events, today)
        self.assertIsNone(expected.error, "the live run posted every entry")
        imported = ImportRun()
        actual = imported(loan_date, principal, rate, events, live.amounts, today)
        self.assertIsNone(actual.error, "the import accepted the same entries")
        self.assertEqual(actual.rows, expected.rows, "every ledger row is identical")
        self.assertEqual(actual.statements, expected.statements, "the statement and its explanations are identical")
        self.assertEqual(actual.loan, expected.loan, "status, closed date, follow-up and outstanding are identical")
        self.assertEqual(actual.closing_today, expected.closing_today, "the closing quote today is identical")
        self.assertEqual(actual.customer_status, expected.customer_status)
        preview = [(date.fromisoformat(e["date"]), e["kind"], D(e["amount_paid"]), D(e["principal_balance"]),
                    D(e["interest_balance"]), e["accrued_days"]) for e in imported.preview["entries"]]
        self.assertEqual(preview, [(r[0], r[1], r[2], r[5], r[6], r[7]) for r in expected.rows], "preview = stored")
        closing = next((e for e in events if e.kind == ledger.CLOSING), None)
        self.assertEqual(imported.preview["closes_on"], closing.on.isoformat() if closing else None)
        if closing is None:
            self.assertEqual(expected.loan["status"], "open")
            self.assertTrue(all(r[0] <= today for r in expected.rows))
        else:
            self.assertEqual(expected.loan["stored"][:2], ("closed", closing.on))
            self.assertEqual(expected.customer_status, "0")
            self.assertTrue(all(r[0] <= closing.on for r in expected.rows), "nothing is posted after the close")
        return expected

    def kinds(self, outcome):
        return [r[1] for r in outcome.rows]

    # ── open loans ──────────────────────────────────────────────────────────────
    def test_interest_only_part_payments(self):
        start = date(2024, 4, 1)
        out = self.check(start, [pay(date(2024, 5, 1), "500"), pay(date(2024, 6, 15), "800"),
                                 pay(date(2024, 8, 1), "1000")], date(2025, 1, 15), rate="12")
        self.assertTrue(all(r[3] == 0 and r[4] == r[2] for r in out.rows[1:]), "every payment goes to interest only")
        self.assertEqual(out.loan["status"], "open")

    def test_part_principal_payments(self):
        start = date(2023, 7, 1)
        out = self.check(start, [pay(date(2023, 8, 10), "20000"), pay(date(2023, 11, 20), "15000"),
                                 pay(date(2024, 3, 5), "5000")], date(2024, 9, 1))
        self.assertEqual(self.kinds(out), ["newLoan", "addColl", "addColl", "addColl", "compounding"])
        self.assertTrue(all(r[3] < 0 for r in out.rows[1:4]), "each payment reduces principal")

    def test_top_ups(self):
        start = date(2024, 2, 1)
        out = self.check(start, [add(date(2024, 2, 21), "25000"), add(date(2024, 8, 18), "10000")],
                         date(2025, 6, 1), rate="15")
        self.assertEqual(self.kinds(out), ["newLoan", "disbursement", "disbursement", "compounding"])

    def test_window_payment_then_nothing_until_after_the_first_anniversary(self):
        start = date(2024, 5, 10)
        out = self.check(start, [pay(date(2024, 5, 11), "30000")], date(2025, 6, 20))
        compounding = out.rows[-1]
        self.assertEqual((compounding[1], compounding[0], compounding[7]), ("compounding", date(2025, 5, 10), 365),
                         "the compounding settles the first week: 7 days on the peak plus the exact days after")
        self.assertEqual(compounding[3], money(interest_for(D("100000"), D("18"), 7)
                                                      + interest_for(D("70000"), D("18"), 358)))

    def test_payment_the_day_before_an_anniversary(self):
        out = self.check(date(2022, 6, 1), [pay(date(2023, 5, 31), "5000")], date(2023, 7, 1), rate="12")
        self.assertEqual(self.kinds(out), ["newLoan", "addColl", "compounding"])

    def test_payment_on_an_anniversary(self):
        out = self.check(date(2022, 6, 1), [pay(date(2023, 6, 1), "5000")], date(2023, 7, 1), rate="12")
        self.assertEqual(self.kinds(out), ["newLoan", "compounding", "addColl"])
        self.assertEqual(out.rows[1][0], out.rows[2][0], "compounded first, then the payment, the same day")

    def test_payment_the_day_after_an_anniversary(self):
        out = self.check(date(2022, 6, 1), [pay(date(2023, 6, 2), "5000")], date(2023, 7, 1), rate="12")
        self.assertEqual(self.kinds(out), ["newLoan", "compounding", "addColl"])

    def test_two_years_of_compounding_with_part_payments_and_a_top_up(self):
        start = date(2022, 2, 10)
        out = self.check(start, [pay(date(2022, 9, 1), "8000"), add(date(2023, 3, 15), "20000"),
                                 pay(date(2023, 10, 1), "12000"), pay(date(2024, 1, 20), "3000")],
                         date(2024, 8, 1), rate="16")
        self.assertEqual(self.kinds(out).count("compounding"), 2)

    def test_leap_year_loan_dated_29_february(self):
        start = date(2024, 2, 29)
        out = self.check(start, [pay(date(2024, 3, 3), "10000"), pay(date(2024, 9, 1), "4000")],
                         date(2026, 3, 15), rate="12")
        self.assertEqual([r[0] for r in out.rows if r[1] == "compounding"], [date(2025, 2, 28), date(2026, 2, 28)],
                         "anniversaries are every 365 days from the loan date")

    def test_same_day_payment_and_top_up(self):
        start = date(2024, 9, 1)
        out = self.check(start, [pay(date(2024, 9, 3), "10000"), add(date(2024, 9, 3), "5000"),
                                 pay(date(2024, 11, 15), "6000"), add(date(2024, 11, 15), "20000")],
                         date(2025, 3, 1))
        self.assertEqual(self.kinds(out), ["newLoan", "addColl", "disbursement", "addColl", "disbursement"])

    def test_still_open_loan_with_trailing_compounding_to_today(self):
        start = date(2023, 5, 1)
        out = self.check(start, [pay(date(2023, 9, 1), "6000")], date(2025, 8, 1), rate="12")
        self.assertEqual(self.kinds(out), ["newLoan", "addColl", "compounding", "compounding"])
        self.assertFalse(out.quote_today["first_week"])

    # ── closed loans ────────────────────────────────────────────────────────────
    def test_users_window_case_pay_day_two_add_day_four_close_day_five(self):
        start = date(2025, 3, 10)
        out = self.check(start, [pay(start + timedelta(days=1), "30000"), add(start + timedelta(days=3), "50000"),
                                 close(start + timedelta(days=4))], date(2025, 6, 1))
        closing = out.rows[-1]
        self.assertEqual((closing[1], closing[2], closing[4], closing[3], closing[7]),
                         ("addColl", D("120414.25"), D("414.25"), D("-120000.00"), 7))
        self.assertEqual(out.loan["closed_on"], "2025-03-14")

    def test_close_on_day_three_with_no_entries(self):
        start = date(2025, 1, 1)
        out = self.check(start, [close(start + timedelta(days=2))], date(2025, 2, 1))
        self.assertEqual((out.rows[-1][2], out.rows[-1][4], out.rows[-1][7]), (D("100345.21"), D("345.21"), 7),
                         "7 days' minimum on the peak")

    def test_close_on_day_seven(self):
        start = date(2025, 1, 1)
        out = self.check(start, [pay(start + timedelta(days=1), "20000"), close(start + timedelta(days=6))],
                         date(2025, 2, 1))
        self.assertEqual((out.rows[-1][4], out.rows[-1][7]), (D("345.21"), 7))

    def test_close_on_day_eight(self):
        start = date(2025, 1, 1)
        out = self.check(start, [pay(start + timedelta(days=1), "20000"), close(start + timedelta(days=7))],
                         date(2025, 2, 1))
        expected = money(interest_for(D("100000"), D("18"), 7) + interest_for(D("80000"), D("18"), 1))
        self.assertEqual((out.rows[-1][4], out.rows[-1][7]), (expected, 8))

    def test_close_on_day_ten(self):
        start = date(2025, 3, 10)
        out = self.check(start, [pay(start + timedelta(days=1), "30000"), add(start + timedelta(days=3), "50000"),
                                 close(start + timedelta(days=9))], date(2025, 6, 1))
        self.assertEqual((out.rows[-1][2], out.rows[-1][4], out.rows[-1][7]), (D("120591.78"), D("591.78"), 10))

    def test_close_after_compounding(self):
        start = date(2023, 1, 10)
        out = self.check(start, [pay(date(2023, 6, 1), "4000"), close(date(2024, 3, 1))], date(2025, 1, 1), rate="12")
        self.assertEqual(self.kinds(out), ["newLoan", "addColl", "compounding", "addColl"])

    def test_close_with_a_confirmed_write_off(self):
        start = date(2024, 1, 5)
        out = self.check(start, [pay(date(2024, 4, 1), "3000"), close(date(2024, 10, 1), "60000", write_off=True)],
                         date(2025, 3, 1), rate="12")
        self.assertEqual(self.kinds(out), ["newLoan", "addColl", "addColl", "writeoff"])
        writeoff = out.rows[-1]
        self.assertGreater(writeoff[8], 0, "principal written off is stored")
        self.assertEqual((writeoff[5], writeoff[6]), (D("0.00"), D("0.00")))

    def test_close_with_nothing_received_writes_off_everything(self):
        start = date(2024, 1, 5)
        out = self.check(start, [close(date(2024, 3, 1), "0", write_off=True)], date(2024, 6, 1), rate="12")
        self.assertEqual(self.kinds(out), ["newLoan", "writeoff"])
        self.assertEqual(out.rows[-1][8], D("100000.00"))

    def test_settling_via_close_with_full_payment(self):
        start = date(2024, 7, 1)
        out = self.check(start, [pay(date(2024, 8, 15), "10000"), add(date(2024, 10, 1), "5000"),
                                 close(date(2025, 2, 1))], date(2026, 1, 1))
        self.assertEqual(self.kinds(out), ["newLoan", "addColl", "disbursement", "addColl"])
        self.assertEqual((out.rows[-1][5], out.rows[-1][6]), (D("0.00"), D("0.00")))
        self.assertIsNone(out.loan["follow_up_date"], "a closed loan has no follow-up")
        self.assertIsNone(out.quote_today)

    def test_close_with_shortfall_and_no_write_off_is_refused_identically(self):
        start = date(2024, 1, 5)
        events = [pay(date(2024, 4, 1), "3000"), close(date(2024, 10, 1), "60000")]
        live = LiveRun()
        expected = live(start, "100000", "12", events, date(2025, 3, 1))
        imported = ImportRun()
        actual = imported(start, "100000", "12", events, ["3000", "60000"], date(2025, 3, 1))
        self.assertEqual(expected.error[:2], ("Invalid", "writeoff_not_confirmed"))
        self.assertEqual(actual.error, expected.error, "same refusal, same message and amount")
        self.assertEqual(expected.loan["status"], "open", "the live loan stays open")
        self.assertEqual(imported.repos.state.loans, {})
        self.assertEqual(imported.repos.state.customers, {}, "nothing is left behind")
        preview = run(import_service.preview(
            imported.actor, import_service.HistoryLoan(ITEMS, "20", "1", "100000", "12", 12, start),
            [import_service.HistoryEntry(e.on, e.kind, e.amount) for e in events], noon(date(2025, 3, 1))))
        self.assertEqual(preview["closes_on"], "2024-10-01")
        self.assertIn(f"₹{preview['remaining_after_close']} would remain unpaid", expected.error[2],
                      "the preview offers exactly the amount the close would write off")
        self.assertEqual(preview["entries"][-1]["kind"], "writeoff")


class ImportCloseRules(unittest.TestCase):
    LOAN = import_service.HistoryLoan(ITEMS, "20", "1", "50000", "12", 12, date(2024, 1, 15))
    TODAY = noon(date(2025, 3, 10))

    def setUp(self):
        self.repos = standard_repos()
        self.san = actor_from(self.repos.state.users["User1"])

    def preview(self, entries):
        return run(import_service.preview(self.san, self.LOAN, entries, self.TODAY))

    def refused(self, entries):
        with self.assertRaises(Invalid) as ctx:
            self.preview(entries)
        with self.assertRaises(Invalid) as committed:
            run(import_service.commit(self.repos, self.san, customer_id=None, new_customer=CUSTOMER, loan=self.LOAN,
                                      entries=entries, request_id="imp-refused", now=self.TODAY))
        self.assertEqual(committed.exception.code, ctx.exception.code)
        self.assertEqual(self.repos.state.customers, {})
        return ctx.exception.code

    def test_close_must_be_the_last_entry(self):
        close_ = import_service.HistoryEntry(date(2024, 6, 1), "close", "52000")
        self.assertEqual(self.refused([close_, import_service.HistoryEntry(date(2024, 6, 1), "addColl", "100")]),
                         "close_not_last")
        self.assertEqual(self.refused([import_service.HistoryEntry(date(2024, 7, 1), "addColl", "100"), close_]),
                         "close_not_last", "no entry may be dated after the close")

    def test_a_loan_is_closed_only_once(self):
        entries = [import_service.HistoryEntry(date(2024, 6, 1), "close", "52000", True),
                   import_service.HistoryEntry(date(2024, 6, 2), "close", "0", True)]
        self.assertEqual(self.refused(entries), "close_twice")

    def test_only_a_close_may_have_a_zero_amount(self):
        self.assertEqual(self.refused([import_service.HistoryEntry(date(2024, 6, 1), "addColl", "0")]), "invalid_import")
        preview = self.preview([import_service.HistoryEntry(date(2024, 6, 1), "close", "0", True)])
        self.assertEqual(preview["remaining_after_close"], "52284.93")
        self.assertEqual((preview["entries"][-1]["writeoff_principal"], preview["entries"][-1]["writeoff_interest"]),
                         ("50000.00", "2284.93"))

    def test_overpayment_on_close_is_refused(self):
        self.assertEqual(self.refused([import_service.HistoryEntry(date(2024, 6, 1), "close", "999999")]), "overpayment")

    def test_settling_payment_still_needs_a_close_entry(self):
        self.assertEqual(self.refused([import_service.HistoryEntry(date(2024, 6, 1), "addColl", "52284.93")]),
                         "settle_with_close")

    def test_open_import_preview_has_no_closing_fields(self):
        preview = self.preview([import_service.HistoryEntry(date(2024, 6, 1), "addColl", "1000")])
        self.assertEqual((preview["closes_on"], preview["remaining_after_close"]), (None, None))
        self.assertTrue(all(e["writeoff_principal"] is None for e in preview["entries"]))

    def test_full_settlement_has_no_remainder_and_no_trailing_compounding(self):
        entries = [import_service.HistoryEntry(date(2024, 6, 1), "close", "52284.93")]
        preview = self.preview(entries)
        self.assertEqual((preview["closes_on"], preview["remaining_after_close"]), ("2024-06-01", None))
        result = run(import_service.commit(self.repos, self.san, customer_id=None, new_customer=CUSTOMER,
                                           loan=self.LOAN, entries=entries, request_id="imp-closed", now=self.TODAY))
        kinds = [s["transactiontype"] for s in self.repos.state.statements]
        self.assertEqual(kinds, ["newLoan", "addColl"], "no compounding on 2025-01-14 after the close")
        loan = self.repos.state.loans[result["loan_number"]]
        self.assertEqual((loan["loantype"], dates.business_date(loan["closed_at"])), ("closed", date(2024, 6, 1)))
        self.assertEqual(self.repos.state.customers[result["customer_id"]]["loanstatus"], "0")
        self.assertIn("closed on 2024-06-01", self.repos.state.audit[-1]["details"])

    def receipts(self, entries, request_id):
        """Receipt of each payment/write-off row of the imported loan, in ledger order."""
        result = run(import_service.commit(self.repos, self.san, customer_id=None, new_customer=CUSTOMER,
                                           loan=self.LOAN, entries=entries, request_id=request_id, now=self.TODAY))
        rows = sorted((s for s in self.repos.state.statements if s["loan_number"] == result["loan_number"]
                       and s["transactiontype"] in ("addColl", "writeoff")), key=lambda s: s["date"])
        return [run(receipts_service.for_statement(self.repos, self.san, s["statementid"], self.TODAY)) for s in rows]

    def test_same_day_payment_before_a_zero_close_keeps_its_own_receipt(self):
        payment, writeoff = self.receipts([import_service.HistoryEntry(date(2024, 6, 1), "addColl", "1000"),
                                           import_service.HistoryEntry(date(2024, 6, 1), "close", "0", True)],
                                          "imp-sameday")
        self.assertFalse(payment["is_closing"], "an earlier payment that day is an ordinary payment")
        self.assertIsNone(payment["closing_writeoff"])
        self.assertEqual((payment["entry"]["kind"], payment["entry"]["amount_paid"]), ("addColl", "1000.00"))
        self.assertTrue(writeoff["is_closing"])
        self.assertEqual((writeoff["entry"]["kind"], writeoff["entry"]["amount_paid"]), ("writeoff", "0.00"),
                         "nothing was received at closing")
        self.assertEqual(writeoff["closing_writeoff"]["id"], writeoff["entry"]["id"])

    def test_imported_close_with_a_payment_still_prints_one_closing_receipt(self):
        earlier, payment, writeoff = self.receipts(
            [import_service.HistoryEntry(date(2024, 6, 1), "addColl", "1000"),
             import_service.HistoryEntry(date(2024, 6, 1), "close", "5000", True)], "imp-paired")
        self.assertFalse(earlier["is_closing"])
        self.assertEqual(earlier["entry"]["amount_paid"], "1000.00")
        self.assertTrue(payment["is_closing"] and writeoff["is_closing"])
        self.assertEqual((payment["entry"]["kind"], payment["entry"]["amount_paid"]), ("addColl", "5000.00"))
        self.assertEqual(writeoff["entry"]["id"], payment["entry"]["id"], "the write-off's receipt is the payment's")
        self.assertEqual(payment["closing_writeoff"]["kind"], "writeoff")

    @unittest.skipIf(importlib.util.find_spec("pydantic") is None, "pydantic is not installed")
    def test_request_body_accepts_a_close_with_write_off(self):
        from pydantic import ValidationError

        from app.schemas import HistoryEntryIn
        entry = HistoryEntryIn(date="2024-06-01", kind="close", amount="0", write_off_remaining=True)
        self.assertTrue(entry.write_off_remaining)
        self.assertFalse(HistoryEntryIn(date="2024-06-01", kind="addColl", amount="10").write_off_remaining)
        with self.assertRaises(ValidationError):
            HistoryEntryIn(date="2024-06-01", kind="writeoff", amount="10")


if __name__ == "__main__":
    unittest.main()

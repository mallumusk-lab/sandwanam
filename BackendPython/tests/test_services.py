import asyncio
import importlib.util
import unittest
from datetime import date, timedelta
from decimal import Decimal as D

from app.errors import Conflict, Forbidden, Invalid, NotFound, TooManyRequests, Unauthorized
from app.services import (
    auth_service,
    backup_service,
    branches_service,
    customers_service,
    import_service,
    loans_service,
    receipts_service,
    reports_service,
)
from app.services.auth_service import actor_from
from app.services.customers_service import NewCustomer
from app.services.loans_service import NewLoan
from tests.fakes import standard_repos, utc

NOW = utc(2025, 3, 10, 6, 0)  # 11:30 IST on 10 March 2025


def run(coro):
    return asyncio.run(coro)


def actor(repos, username):
    return actor_from(repos.state.users[username])


class Fixture(unittest.TestCase):
    def setUp(self):
        self.repos = standard_repos()
        self.hq = actor(self.repos, "Admin")
        self.san = actor(self.repos, "User1")
        self.swa = actor(self.repos, "User2")
        self.root = actor(self.repos, "root")

    def customer(self, who=None, phone="9876543210", name="Lakshmi Nair"):
        return run(customers_service.create(self.repos, who or self.san, NewCustomer(name, phone, "Uchakkada, Kerala")))

    def loan(self, who=None, customer_id=None, principal="100000", rate="12", request_id="req-loan", now=NOW):
        """A new loan dated `now` (daily entries are always dated on the day they are made)."""
        customer_id = customer_id or self.customer(who)["id"]
        data = NewLoan(customer_id, [{"name": "Chain", "qty": 1}, {"name": "Ring", "qty": 2}], "50.00", "2.00",
                       principal, rate, 12)
        return run(loans_service.create(self.repos, who or self.san, data, request_id=request_id, now=now))


class AuthTests(Fixture):
    def test_login_and_session(self):
        signed = run(auth_service.login(self.repos, "user1", "Santhwanam-2026", ip="1.1.1.1", user_agent="t", now=NOW))
        self.assertEqual(signed.actor.branch_prefix, "SAN")
        resolved = run(auth_service.resolve_session(self.repos, signed.token, NOW + timedelta(minutes=10)))
        self.assertEqual(resolved.username, "User1")
        with self.assertRaises(Unauthorized):
            run(auth_service.resolve_session(self.repos, signed.token, NOW + timedelta(hours=9)))

    def test_legacy_hash_is_upgraded_on_login(self):
        before = self.repos.state.users["User1"]["password"]
        run(auth_service.login(self.repos, "User1", "Santhwanam-2026", ip="1.1.1.1", user_agent="t", now=NOW))
        after = self.repos.state.users["User1"]["password"]
        self.assertNotEqual(before, after)
        self.assertTrue(after.startswith("pbkdf2_sha256$600000$"))

    def test_failures_are_generic_and_throttled_per_ip(self):
        for _ in range(3):
            with self.assertRaises(Unauthorized) as ctx:
                run(auth_service.login(self.repos, "User1", "wrong", ip="6.6.6.6", user_agent="t", now=NOW))
            self.assertEqual(ctx.exception.message, auth_service.GENERIC_FAILURE)
        with self.assertRaises(TooManyRequests):
            run(auth_service.login(self.repos, "User1", "Santhwanam-2026", ip="6.6.6.6", user_agent="t", now=NOW))
        # The real cashier on another address is not locked out.
        run(auth_service.login(self.repos, "User1", "Santhwanam-2026", ip="10.0.0.5", user_agent="t", now=NOW))

    def test_guessing_from_many_addresses_hits_the_account_limit(self):
        for n in range(20):
            with self.assertRaises(Unauthorized):
                run(auth_service.login(self.repos, "User1", "wrong", ip=f"10.0.{n}.1", user_agent="t", now=NOW))
        with self.assertRaises(TooManyRequests) as ctx:
            run(auth_service.login(self.repos, "User1", "Santhwanam-2026", ip="10.9.9.9", user_agent="t", now=NOW))
        self.assertEqual(ctx.exception.details, {}, "no exact retry time for the account-wide limit")
        later = NOW + timedelta(minutes=6)
        run(auth_service.login(self.repos, "User1", "Santhwanam-2026", ip="10.9.9.9", user_agent="t", now=later))
        self.assertEqual(self.repos.state.throttle.get(("user1", "*")), None, "success clears the account counter")

    def test_usual_device_is_not_locked_out_by_strangers(self):
        run(auth_service.login(self.repos, "User1", "Santhwanam-2026", ip="192.168.1.10", user_agent="t", now=NOW))
        for n in range(25):
            with self.assertRaises((Unauthorized, TooManyRequests)):
                run(auth_service.login(self.repos, "User1", "wrong", ip=f"10.1.{n}.1", user_agent="t", now=NOW))
        with self.assertRaises(TooManyRequests):
            run(auth_service.login(self.repos, "User1", "Santhwanam-2026", ip="10.200.0.1", user_agent="t", now=NOW))
        run(auth_service.login(self.repos, "User1", "Santhwanam-2026", ip="192.168.1.10", user_agent="t", now=NOW))
        audit = [a for a in self.repos.state.audit if a["action"] == "SIGN_IN_LOCKED"]
        self.assertTrue(audit, "lockouts are audited")

    def test_lockout_audited_only_when_the_attempt_fails(self):
        for _ in range(2):
            with self.assertRaises(Unauthorized):
                run(auth_service.login(self.repos, "User1", "wrong", ip="7.7.7.7", user_agent="t", now=NOW))
        run(auth_service.login(self.repos, "User1", "Santhwanam-2026", ip="7.7.7.7", user_agent="t", now=NOW))
        self.assertFalse([a for a in self.repos.state.audit if a["action"] == "SIGN_IN_LOCKED"])

    def test_wrong_current_password_is_throttled(self):
        signed = run(auth_service.login(self.repos, "User1", "Santhwanam-2026", ip="1.1.1.1", user_agent="t", now=NOW))
        for _ in range(3):
            with self.assertRaises(Invalid):
                run(auth_service.change_password(self.repos, signed.actor, signed.token, "guess", "A-much-better-pass-9", NOW))
        with self.assertRaises(TooManyRequests):
            run(auth_service.change_password(self.repos, signed.actor, signed.token, "guess", "A-much-better-pass-9", NOW))

    def test_unknown_inactive_and_passwordless_accounts_fail_identically(self):
        self.repos.add_account("Old", "Some-password-1", "branch", "OLD", is_active=False)
        self.repos.add_account("Reset", None, "branch", "RST")
        for name in ("nobody", "Old", "Reset"):
            with self.subTest(name), self.assertRaises(Unauthorized) as ctx:
                run(auth_service.login(self.repos, name, "Some-password-1", ip="2.2.2.2", user_agent="t", now=NOW))
            self.assertEqual(ctx.exception.message, auth_service.GENERIC_FAILURE)

    def test_change_password_keeps_only_the_current_session(self):
        first = run(auth_service.login(self.repos, "User1", "Santhwanam-2026", ip="1.1.1.1", user_agent="t", now=NOW))
        second = run(auth_service.login(self.repos, "User1", "Santhwanam-2026", ip="1.1.1.2", user_agent="t", now=NOW))
        with self.assertRaises(Invalid):
            run(auth_service.change_password(self.repos, first.actor, first.token, "Santhwanam-2026", "short", NOW))
        run(auth_service.change_password(self.repos, first.actor, first.token, "Santhwanam-2026", "A-much-better-pass-9", NOW))
        run(auth_service.resolve_session(self.repos, first.token, NOW))
        with self.assertRaises(Unauthorized):
            run(auth_service.resolve_session(self.repos, second.token, NOW))


class CustomerTests(Fixture):
    def test_numbers_are_allocated_per_branch(self):
        self.assertEqual(self.customer()["customer_number"], "SAN1")
        self.assertEqual(self.customer(phone="9876500000")["customer_number"], "SAN2")
        self.assertEqual(self.customer(self.swa, phone="9876511111")["customer_number"], "SWA1")

    def test_branches_cannot_see_each_other(self):
        mine = self.customer()
        with self.assertRaises(NotFound):
            run(customers_service.detail(self.repos, self.swa, mine["id"], NOW))
        listing = run(customers_service.search(self.repos, self.swa, branch=None, term=None, page=1, page_size=20))
        self.assertEqual(listing["total"], 0)
        with self.assertRaises(Forbidden):
            run(customers_service.search(self.repos, self.swa, branch="SAN", term=None, page=1, page_size=20))
        everyone = run(customers_service.search(self.repos, self.hq, branch=None, term=None, page=1, page_size=20))
        self.assertEqual(everyone["total"], 1)

    def test_duplicate_phone_does_not_leak_other_branch_ids(self):
        self.customer()
        with self.assertRaises(Conflict) as ctx:
            self.customer(self.swa)
        self.assertEqual(ctx.exception.details, {})

    def test_head_office_must_choose_a_real_branch(self):
        with self.assertRaises(Invalid):
            run(customers_service.create(self.repos, self.hq, NewCustomer("Ravi Kumar", "9000000001", "Pozhiyoor", "XYZ")))
        created = run(customers_service.create(self.repos, self.hq, NewCustomer("Ravi Kumar", "9000000001", "Pozhiyoor", "SWA")))
        self.assertEqual(created["customer_number"], "SWA1")


class LoanTests(Fixture):
    def outstanding(self, loan_number, now=NOW):
        return run(loans_service.detail(self.repos, self.san, loan_number, now))["loan"]["outstanding"]

    def test_create_allocates_number_and_opening_entry(self):
        created = self.loan()
        self.assertEqual(created["loan_number"], "SAN1L1")
        loan = self.repos.state.loans["SAN1L1"]
        self.assertEqual(loan["net_weight"], D("48.00"))
        self.assertEqual(loan["particulars"], "Chain(1), Ring(2)")
        self.assertEqual(self.repos.state.customers[1]["loanstatus"], "1")
        self.assertEqual([s["transactiontype"] for s in self.repos.state.statements], ["newLoan"])

    def test_same_day_quote_charges_one_day(self):
        self.loan()
        self.assertEqual(self.outstanding("SAN1L1")["interest"], "32.88")

    def test_collection_is_idempotent_and_checks_the_shown_amount(self):
        self.loan()
        later = NOW + timedelta(days=9)  # 19 March: 10 inclusive days → 328.77
        with self.assertRaises(Conflict) as ctx:
            run(loans_service.collect(self.repos, self.san, "SAN1L1", amount="500", expected_total="100032.88",
                                      request_id="pay-1", now=later))
        self.assertEqual(ctx.exception.code, "outstanding_changed")
        first = run(loans_service.collect(self.repos, self.san, "SAN1L1", amount="500",
                                          expected_total="100328.77", request_id="pay-1", now=later))
        again = run(loans_service.collect(self.repos, self.san, "SAN1L1", amount="500",
                                          expected_total="100328.77", request_id="pay-1", now=later))
        self.assertTrue(again["replayed"])
        self.assertEqual(first["statement_id"], again["statement_id"])
        payments = [s for s in self.repos.state.statements if s["transactiontype"] == "addColl"]
        self.assertEqual(len(payments), 1)
        self.assertEqual(payments[0]["currentinterest"], D("328.77"))
        self.assertEqual(self.repos.state.loans["SAN1L1"]["refreshprincipleamount"], D("99828.77"))
        self.assertEqual(self.repos.state.audit[-1]["username"], "User1")

    def test_overpayment_and_backdating_are_rejected_without_side_effects(self):
        self.loan()
        before = len(self.repos.state.statements)
        with self.assertRaises(Invalid) as ctx:
            run(loans_service.collect(self.repos, self.san, "SAN1L1", amount="200000", expected_total=None,
                                      request_id="pay-x", now=NOW))
        self.assertEqual(ctx.exception.code, "first_week_clears_principal")
        with self.assertRaises(Invalid) as ctx:  # out of order: a clock behind the latest entry's day
            run(loans_service.collect(self.repos, self.san, "SAN1L1", amount="10", expected_total=None,
                                      request_id="pay-y", now=NOW - timedelta(days=2)))
        self.assertEqual(ctx.exception.code, "backdated")
        self.assertEqual(len(self.repos.state.statements), before)

    def test_other_branch_cannot_post(self):
        self.loan()
        with self.assertRaises(NotFound):
            run(loans_service.collect(self.repos, self.swa, "SAN1L1", amount="10", expected_total=None,
                                      request_id="pay-z", now=NOW))

    def test_close_records_cash_received_and_write_off(self):
        self.loan()
        closing_day = NOW + timedelta(days=2)  # day 3 of the loan → 7-day minimum → 230.14
        quote = run(loans_service.closing_quote(self.repos, self.san, "SAN1L1", closing_day))
        self.assertEqual((quote["interest"], quote["period_days"]), ("230.14", 7))
        with self.assertRaises(Invalid):
            run(loans_service.close(self.repos, self.san, "SAN1L1", amount_received="100000", write_off_remaining=False,
                                    expected_total=quote["total"], request_id="close-1", now=closing_day))
        result = run(loans_service.close(self.repos, self.san, "SAN1L1", amount_received="100000",
                                         write_off_remaining=True, expected_total=quote["total"],
                                         request_id="close-1", now=closing_day))
        kinds = [s["transactiontype"] for s in self.repos.state.statements]
        self.assertEqual(kinds, ["newLoan", "addColl", "writeoff"])
        payment, writeoff = self.repos.state.statements[1:]
        self.assertEqual(payment["amountpaid"], D("100000.00"))
        self.assertEqual(payment["client_request_id"], "close-1")
        self.assertEqual(result["statement_id"], payment["statementid"])
        self.assertEqual(writeoff["writeoff_interest"] + writeoff["writeoff_principal"], D("230.14"))
        loan = self.repos.state.loans["SAN1L1"]
        self.assertEqual(loan["loantype"], "closed")
        self.assertIsNotNone(loan["closed_at"])
        self.assertEqual(self.repos.state.customers[1]["loanstatus"], "0")
        with self.assertRaises(Conflict):
            run(loans_service.collect(self.repos, self.san, "SAN1L1", amount="1", expected_total=None,
                                      request_id="late", now=closing_day))

    def test_top_up_and_item_edit(self):
        self.loan()
        run(loans_service.top_up(self.repos, self.san, "SAN1L1", amount="5000", expected_total=None,
                                 request_id="top-1", now=NOW))
        self.assertEqual(self.repos.state.loans["SAN1L1"]["refreshprincipleamount"], D("105000.00"))
        entries_before = len(self.repos.state.statements)
        run(loans_service.edit_items(self.repos, self.san, "SAN1L1", [{"name": "Bangle", "qty": 3}]))
        self.assertEqual(len(self.repos.state.statements), entries_before, "editing items must not touch the ledger")
        self.assertEqual(self.repos.state.loans["SAN1L1"]["particulars"], "Bangle(3)")

    def test_daily_entries_are_dated_today_and_in_order(self):
        """Replaces head-office backdating: every daily entry is dated on the day it is made."""
        opened = utc(2025, 3, 1, 6, 0)
        number = self.loan(self.hq, customer_id=self.customer(self.hq)["id"], request_id="old",
                           now=opened)["loan_number"]
        self.assertEqual(number, "AD1L1")
        paid_at = utc(2025, 3, 5, 6, 0)
        run(loans_service.collect(self.repos, self.hq, number, amount="100", expected_total=None,
                                  request_id="p1", now=paid_at))
        with self.assertRaises(Invalid) as ctx:
            run(loans_service.collect(self.repos, self.hq, number, amount="100", expected_total=None,
                                      request_id="p2", now=utc(2025, 3, 4, 6, 0)))
        self.assertEqual(ctx.exception.code, "backdated")
        stored = [s["date"] for s in self.repos.state.statements]
        self.assertEqual(stored, sorted(stored))
        self.assertEqual(stored, [opened, paid_at], "stored at the real time of each entry")
        self.assertEqual(self.repos.state.loans[number]["date"], opened)

    def test_cron_compounding_runs_once(self):
        number = self.loan(self.hq, customer_id=self.customer(self.hq)["id"], request_id="year",
                           now=utc(2024, 3, 1, 6, 0))["loan_number"]
        self.assertEqual(run(loans_service.apply_due_compounding(self.repos, number, NOW)), 1)
        self.assertEqual(run(loans_service.apply_due_compounding(self.repos, number, NOW)), 0)
        compounding = [s for s in self.repos.state.statements if s["transactiontype"] == "compounding"]
        self.assertEqual(compounding[0]["accrued_days"], 365)
        self.assertEqual(compounding[0]["currentprincipal"], D("12000.00"))


class ReviewFixes(Fixture):
    def test_branch_without_customer_access_cannot_use_loans(self):
        self.loan()
        self.repos.add_account("Reports", "Reports-only-2026", "branch", "SAN2", permissions="report")
        limited = actor(self.repos, "Reports")
        for call in (
            lambda: customers_service.detail(self.repos, limited, 1, NOW),
            lambda: loans_service.detail(self.repos, limited, "SAN1L1", NOW),
            lambda: loans_service.collect(self.repos, limited, "SAN1L1", amount="10", expected_total=None,
                                          request_id="perm-1", now=NOW),
            lambda: receipts_service.for_loan(self.repos, limited, "SAN1L1", NOW),
        ):
            with self.assertRaises(Forbidden):
                run(call())

    def test_closing_a_loan_with_nothing_owed(self):
        self.loan()
        loan = self.repos.state.loans["SAN1L1"]
        # Settled after day 7, so the first-week charge on the peak no longer applies.
        later = NOW + timedelta(days=8)
        self.repos.state.statements.append(dict(self.repos.state.statements[0], statementid=99, transactiontype="addColl",
                                                principlebalance=D("0.00"), interestbalance=D("0.00"),
                                                date=later + timedelta(seconds=1), client_request_id=None))
        quote = run(loans_service.closing_quote(self.repos, self.san, "SAN1L1", later))
        self.assertEqual(quote["total"], "0.00")
        result = run(loans_service.close(self.repos, self.san, "SAN1L1", amount_received="0", write_off_remaining=False,
                                         expected_total="0.00", request_id="close-zero", now=later))
        self.assertIsNone(result["statement_id"])
        self.assertEqual(loan["loantype"], "closed")

    def test_earlier_same_day_payment_keeps_its_own_receipt(self):
        self.loan()
        morning = NOW + timedelta(days=9)
        paid = run(loans_service.collect(self.repos, self.san, "SAN1L1", amount="500", expected_total=None,
                                         request_id="am-pay", now=morning))
        afternoon = morning + timedelta(hours=5)
        quote = run(loans_service.closing_quote(self.repos, self.san, "SAN1L1", afternoon))
        run(loans_service.close(self.repos, self.san, "SAN1L1", amount_received="0", write_off_remaining=True,
                                expected_total=quote["total"], request_id="pm-close", now=afternoon))
        receipt = run(receipts_service.for_statement(self.repos, self.san, paid["statement_id"], afternoon))
        self.assertFalse(receipt["is_closing"])
        self.assertIsNone(receipt["closing_writeoff"])

    def test_request_id_cannot_be_replayed_for_another_customer(self):
        self.loan(request_id="shared-id")
        other = self.customer(phone="9000000003", name="Second Customer")
        with self.assertRaises(Conflict):
            self.loan(customer_id=other["id"], request_id="shared-id")

    def test_branch_directory_hides_usernames(self):
        directory = run(branches_service.directory(self.repos))
        self.assertTrue(directory)
        self.assertTrue(all("username" not in b for b in directory))
        accounts = run(branches_service.list_accounts(self.repos, self.root))
        self.assertTrue(all("username" in a for a in accounts))

    def test_new_branches_do_not_get_history_import_by_default(self):
        created = run(branches_service.create_branch(
            self.repos, self.root, username="User5", branch_prefix="KOV", temporary_password="Temporary-pass-42",
            fields=branches_service.BranchFields(display_name="Kovalam")))
        self.assertNotIn("history", created["permissions"])


class ImportTests(Fixture):
    LOAN = import_service.HistoryLoan([{"name": "Chain", "qty": 1}], "20", "1", "50000", "18", 12, date(2024, 1, 15))
    ENTRIES = [import_service.HistoryEntry(date(2024, 6, 1), "addColl", "3000"),
               import_service.HistoryEntry(date(2024, 9, 1), "disbursement", "5000")]

    def test_preview_writes_nothing_and_matches_commit(self):
        preview = run(import_service.preview(self.san, self.LOAN, self.ENTRIES, NOW))
        self.assertEqual(self.repos.state.statements, [])
        result = run(import_service.commit(self.repos, self.san, customer_id=None,
                                           new_customer=NewCustomer("Anil Das", "9123456789", "Vizhinjam"),
                                           loan=self.LOAN, entries=self.ENTRIES, request_id="imp-1", now=NOW))
        stored = [s["transactiontype"] for s in self.repos.state.statements]
        self.assertEqual(stored, [e["kind"] for e in preview["entries"]])
        self.assertEqual(stored, ["newLoan", "addColl", "disbursement", "compounding"])
        self.assertEqual(self.repos.state.loans[result["loan_number"]]["refreshprincipleamount"],
                         D(preview["principal_balance"]))

    def test_retry_returns_the_original_import(self):
        args = dict(customer_id=None, new_customer=NewCustomer("Anil Das", "9123456789", "Vizhinjam"),
                    loan=self.LOAN, entries=self.ENTRIES, request_id="imp-retry", now=NOW)
        first = run(import_service.commit(self.repos, self.san, **args))
        again = run(import_service.commit(self.repos, self.san, **args))
        self.assertTrue(again["replayed"])
        self.assertEqual((again["loan_number"], again["customer_id"]), (first["loan_number"], first["customer_id"]))
        with self.assertRaises(NotFound):
            run(import_service.commit(self.repos, self.swa, **args))

    def test_commit_refuses_an_outdated_preview(self):
        preview = run(import_service.preview(self.san, self.LOAN, self.ENTRIES, NOW))
        stale = {"principal_balance": preview["principal_balance"], "interest_balance": "1.00"}
        with self.assertRaises(Conflict):
            run(import_service.commit(self.repos, self.san, customer_id=None,
                                      new_customer=NewCustomer("Anil Das", "9123456789", "Vizhinjam"), loan=self.LOAN,
                                      entries=self.ENTRIES, request_id="imp-stale", now=NOW, expected=stale))
        fresh = {"principal_balance": preview["principal_balance"], "interest_balance": preview["interest_balance"]}
        run(import_service.commit(self.repos, self.san, customer_id=None,
                                  new_customer=NewCustomer("Anil Das", "9123456789", "Vizhinjam"), loan=self.LOAN,
                                  entries=self.ENTRIES, request_id="imp-fresh", now=NOW, expected=fresh))

    def test_commit_requires_exactly_one_customer_choice(self):
        with self.assertRaises(Invalid):
            run(import_service.commit(self.repos, self.san, customer_id=None, new_customer=None, loan=self.LOAN,
                                      entries=[], request_id="imp-2", now=NOW))

    def test_failed_import_leaves_no_partial_customer(self):
        bad = [import_service.HistoryEntry(date(2024, 6, 1), "addColl", "999999")]
        with self.assertRaises(Invalid):
            run(import_service.commit(self.repos, self.san, customer_id=None,
                                      new_customer=NewCustomer("Anil Das", "9123456789", "Vizhinjam"),
                                      loan=self.LOAN, entries=bad, request_id="imp-3", now=NOW))
        self.assertEqual(self.repos.state.customers, {})


class ReportTests(Fixture):
    def test_portfolio_is_live_and_branch_scoped(self):
        self.loan()
        self.loan(self.swa, customer_id=self.customer(self.swa, phone="9000000002")["id"], principal="50000",
                  request_id="r2")
        mine = run(reports_service.portfolio(self.repos, self.san, None, NOW))
        self.assertEqual((mine["open_loans"], mine["principal"]), (1, "100000.00"))
        everyone = run(reports_service.portfolio(self.repos, self.hq, None, NOW))
        self.assertEqual(everyone["open_loans"], 2)
        self.assertEqual(everyone["ltv"], None, "no gold rate set yet")
        run(reports_service.set_gold_rate(self.repos, self.hq, "6000"))
        priced = run(reports_service.portfolio(self.repos, self.hq, None, NOW))
        self.assertIsNotNone(priced["ltv"])

    def test_branch_users_cannot_set_the_gold_rate(self):
        with self.assertRaises(Forbidden):
            run(reports_service.set_gold_rate(self.repos, self.san, "6000"))


class AdminTests(Fixture):
    def test_only_superadmin_manages_branches(self):
        with self.assertRaises(Forbidden):
            run(branches_service.list_accounts(self.repos, self.hq))
        created = run(branches_service.create_branch(
            self.repos, self.root, username="User3", branch_prefix="vzm", temporary_password="Temporary-pass-42",
            fields=branches_service.BranchFields(display_name="Vizhinjam", permissions=["userlist", "report"])))
        self.assertEqual((created["code"], created["permissions"]), ("VZM", ["report", "userlist"]))
        self.assertTrue(created["must_change_password"])
        with self.assertRaises(Conflict):
            run(branches_service.create_branch(
                self.repos, self.root, username="User4", branch_prefix="VZM", temporary_password="Temporary-pass-42",
                fields=branches_service.BranchFields(display_name="Other")))

    def test_branch_with_customers_cannot_be_deleted(self):
        self.customer()
        with self.assertRaises(Conflict):
            run(branches_service.delete_branch(self.repos, self.root, "User1"))
        with self.assertRaises(Forbidden):
            run(branches_service.delete_branch(self.repos, self.root, "Admin"))

    def test_restore_requires_superadmin_and_confirmation(self):
        with self.assertRaises(Forbidden):
            run(backup_service.restore(self.repos, self.hq, document={}, confirmation="RESTORE", now=NOW))
        with self.assertRaises(Invalid):
            run(backup_service.restore(self.repos, self.root, document={}, confirmation="yes", now=NOW))
        with self.assertRaises(Forbidden):
            run(backup_service.check(self.repos, self.san, document={}))

    def test_receipts_come_from_the_ledger(self):
        self.loan()
        later = NOW + timedelta(days=9)
        paid = run(loans_service.collect(self.repos, self.san, "SAN1L1", amount="1000", expected_total=None,
                                         request_id="rc-1", now=later))
        receipt = run(receipts_service.for_statement(self.repos, self.san, paid["statement_id"], later))
        self.assertEqual(receipt["entry"]["amount_paid"], "1000.00")
        self.assertEqual(receipt["entry"]["interest_paid"], "328.77")
        self.assertEqual(receipt["entry"]["principal_change"], "-671.23")
        self.assertEqual(receipt["letterhead"]["code"], "SAN")
        self.assertFalse(receipt["is_closing"])
        with self.assertRaises(NotFound):
            run(receipts_service.for_statement(self.repos, self.swa, paid["statement_id"], later))
        quote = run(loans_service.closing_quote(self.repos, self.san, "SAN1L1", later))
        closed = run(loans_service.close(self.repos, self.san, "SAN1L1", amount_received="1000", write_off_remaining=True,
                                         expected_total=quote["total"], request_id="rc-close", now=later))
        closing = run(receipts_service.for_statement(self.repos, self.san, closed["statement_id"], later))
        self.assertTrue(closing["is_closing"])
        self.assertIsNotNone(closing["closing_writeoff"])
        earlier = run(receipts_service.for_statement(self.repos, self.san, paid["statement_id"], later))
        self.assertFalse(earlier["is_closing"], "older payments keep their own receipt title")

    def test_receipt_number_starts_from_one_for_each_branch(self):
        san_loan = self.loan(who=self.san, principal="50000")["loan_number"]
        swa_cust = self.customer(who=self.swa, phone="9876543299", name="Rajesh Kumar")
        swa_loan = self.loan(who=self.swa, customer_id=swa_cust["id"], principal="50000", request_id="swa-l1")["loan_number"]

        san_p1 = run(loans_service.collect(self.repos, self.san, san_loan, amount="1000", expected_total=None, request_id="san-p1", now=NOW))
        san_rec1 = run(receipts_service.for_statement(self.repos, self.san, san_p1["statement_id"], NOW))
        self.assertEqual(san_rec1["entry"]["receipt_no"], 1)

        swa_p1 = run(loans_service.collect(self.repos, self.swa, swa_loan, amount="1000", expected_total=None, request_id="swa-p1", now=NOW))
        swa_rec1 = run(receipts_service.for_statement(self.repos, self.swa, swa_p1["statement_id"], NOW))
        self.assertEqual(swa_rec1["entry"]["receipt_no"], 1)

        san_p2 = run(loans_service.collect(self.repos, self.san, san_loan, amount="1000", expected_total=None, request_id="san-p2", now=NOW + timedelta(days=1)))
        san_rec2 = run(receipts_service.for_statement(self.repos, self.san, san_p2["statement_id"], NOW + timedelta(days=1)))
        self.assertEqual(san_rec2["entry"]["receipt_no"], 2)

        swa_p2 = run(loans_service.collect(self.repos, self.swa, swa_loan, amount="1000", expected_total=None, request_id="swa-p2", now=NOW + timedelta(days=1)))
        swa_rec2 = run(receipts_service.for_statement(self.repos, self.swa, swa_p2["statement_id"], NOW + timedelta(days=1)))
        self.assertEqual(swa_rec2["entry"]["receipt_no"], 2)


class FirstWeekServiceTests(Fixture):
    """The first-7-days rule through the services: the user's example, 100000 at 18% from 10 March."""

    def outstanding(self, number, now):
        return run(loans_service.detail(self.repos, self.san, number, now))["loan"]["outstanding"]

    def scenario(self):
        """Pays 30000 on day 2 and adds 50000 on day 4, each against the amount shown that day."""
        number = self.loan(rate="18")["loan_number"]
        day2 = NOW + timedelta(days=1)
        shown = self.outstanding(number, day2)
        self.assertEqual((shown["first_week"], shown["window_peak"], shown["first_week_interest"]),
                         (True, "100000.00", "345.21"))
        self.assertEqual((shown["interest"], shown["period_days"]), ("98.63", 2), "interest so far on the peak")
        run(loans_service.collect(self.repos, self.san, number, amount="30000", expected_total=shown["total"],
                                  request_id="fw-pay", now=day2))
        day4 = NOW + timedelta(days=3)
        shown = self.outstanding(number, day4)
        run(loans_service.top_up(self.repos, self.san, number, amount="50000", expected_total=shown["total"],
                                 request_id="fw-top", now=day4))
        return number

    def test_users_scenario_closes_on_day_five(self):
        number = self.scenario()
        payment, top = self.repos.state.statements[1:]
        self.assertEqual((payment["currentprincipal"], payment["currentinterest"], payment["principlebalance"],
                          payment["accrued_days"]), (D("-30000.00"), D("0.00"), D("70000.00"), 0))
        self.assertEqual((top["principlebalance"], top["interestbalance"], top["accrued_days"]),
                         (D("120000.00"), D("0.00"), 0))
        day5 = NOW + timedelta(days=4)
        quote = run(loans_service.closing_quote(self.repos, self.san, number, day5))
        self.assertEqual((quote["interest"], quote["total"], quote["period_days"]), ("414.25", "120414.25", 7))
        self.assertEqual((quote["first_week"], quote["window_peak"], quote["first_week_interest"]),
                         (True, "120000.00", "414.25"))
        run(loans_service.close(self.repos, self.san, number, amount_received=quote["total"], write_off_remaining=False,
                                expected_total=quote["total"], request_id="fw-close", now=day5))
        closing = self.repos.state.statements[-1]
        self.assertEqual((closing["currentinterest"], closing["currentprincipal"], closing["accrued_days"]),
                         (D("414.25"), D("-120000.00"), 7))
        self.assertEqual(self.repos.state.loans[number]["loantype"], "closed")

    def test_day_ten_charges_the_peak_week_plus_three_days_and_matches_the_live_quote(self):
        number = self.scenario()
        day10 = NOW + timedelta(days=9)
        shown = self.outstanding(number, day10)
        self.assertEqual((shown["interest"], shown["period_days"], shown["first_week"]), ("591.78", 10, False))
        self.assertEqual(run(loans_service.closing_quote(self.repos, self.san, number, day10))["interest"], "591.78")
        run(loans_service.collect(self.repos, self.san, number, amount="1000", expected_total=shown["total"],
                                  request_id="fw-day10", now=day10))
        payment = self.repos.state.statements[-1]
        self.assertEqual((payment["currentinterest"], payment["accrued_days"], payment["principlebalance"]),
                         (D("591.78"), 10, D("119591.78")))
        self.assertEqual(self.outstanding(number, day10)["period_days"], 1, "inclusive counting resumes")

    def test_payment_that_clears_the_principal_is_refused(self):
        number = self.loan()["loan_number"]
        with self.assertRaises(Invalid) as ctx:
            run(loans_service.collect(self.repos, self.san, number, amount="100000", expected_total=None,
                                      request_id="fw-all", now=NOW + timedelta(days=2)))
        self.assertEqual(ctx.exception.code, "first_week_clears_principal")
        self.assertEqual(len(self.repos.state.statements), 1)

    def test_statement_explains_each_row_and_receipts_do_not(self):
        number = self.scenario()
        day10 = NOW + timedelta(days=9)
        run(loans_service.collect(self.repos, self.san, number, amount="1000", expected_total=None,
                                  request_id="fw-day10", now=day10))
        rows = list(reversed(run(loans_service.detail(self.repos, self.san, number, day10))["statements"]))
        self.assertEqual([r["calculation"]["method"] for r in rows],
                         ["opening", "first_week", "first_week", "first_week_settlement"])
        self.assertEqual([r["in_first_week"] for r in rows], [False, True, True, False])
        settle = rows[-1]["calculation"]
        self.assertEqual(
            {k: settle[k] for k in ("peak_principal", "first_week_days", "extra_days", "extra_principal", "days",
                                    "rate", "interest_accrued", "interest_paid", "principal_paid",
                                    "principal_balance", "interest_balance", "period_from", "period_to")},
            {"peak_principal": "120000.00", "first_week_days": 7, "extra_days": 3, "extra_principal": "120000.00",
             "days": 10, "rate": "18.00", "interest_accrued": "591.78", "interest_paid": "591.78",
             "principal_paid": "408.22", "principal_balance": "119591.78", "interest_balance": "0.00",
             "period_from": "2025-03-10", "period_to": "2025-03-19"},
        )
        self.assertIn("₹120000.00 × 18% × 7 ÷ 365", settle["note"])
        receipt = run(receipts_service.for_statement(self.repos, self.san, rows[1]["id"], day10))
        self.assertNotIn("calculation", receipt["entry"])
        self.assertTrue(receipt["entry"]["in_first_week"])

    def test_earlier_rule_first_week_payment_is_not_flagged_on_its_receipt(self):
        number = self.loan(rate="18")["loan_number"]
        day3 = NOW + timedelta(days=2)
        paid = run(loans_service.collect(self.repos, self.san, number, amount="500", expected_total=None,
                                         request_id="fw-old", now=day3))
        current = run(receipts_service.for_statement(self.repos, self.san, paid["statement_id"], day3))
        self.assertTrue(current["entry"]["in_first_week"], "a first-7-days payment charges nothing")
        row = self.repos.state.statements[-1]  # as posted before the rule shipped: 3 days of interest charged
        row.update(currentinterest=D("147.95"), currentprincipal=D("-352.05"), principlebalance=D("99647.95"),
                   accrued_days=3)
        receipt = run(receipts_service.for_statement(self.repos, self.san, paid["statement_id"], day3))
        self.assertEqual(receipt["entry"]["interest_paid"], "147.95")
        self.assertFalse(receipt["entry"]["in_first_week"], "it paid interest, so it did not go to principal only")

    def test_import_preview_applies_the_first_week_rule(self):
        loan = import_service.HistoryLoan([{"name": "Chain", "qty": 1}], "20", "1", "100000", "18", 12, date(2025, 1, 1))
        entries = [import_service.HistoryEntry(date(2025, 1, 2), "addColl", "30000"),
                   import_service.HistoryEntry(date(2025, 1, 4), "disbursement", "50000"),
                   import_service.HistoryEntry(date(2025, 1, 10), "addColl", "1000")]
        preview = run(import_service.preview(self.san, loan, entries, NOW))
        self.assertEqual([e["accrued_days"] for e in preview["entries"]], [0, 0, 0, 10])
        self.assertEqual(preview["entries"][1]["principal_change"], "-30000.00")
        self.assertEqual(preview["entries"][3]["interest_paid"], "591.78")
        self.assertEqual(preview["principal_balance"], "119591.78")


class DailyEntryDateTests(unittest.TestCase):
    def test_daily_entry_bodies_have_no_date_field(self):
        """Read from the source so it also runs where pydantic is not installed."""
        import ast
        from pathlib import Path
        tree = ast.parse((Path(__file__).resolve().parents[1] / "app" / "schemas.py").read_text(encoding="utf-8"))
        classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
        for name in ("LoanIn", "PostingIn"):
            fields = {s.target.id for s in classes[name].body if isinstance(s, ast.AnnAssign)}
            with self.subTest(name):
                self.assertTrue(fields, "the class still exists")
                self.assertFalse(fields & {"date", "loan_date"}, "daily entries are always dated today")
                self.assertEqual([b.id for b in classes[name].bases], ["Body"], "unknown fields are rejected")
        self.assertIn("extra='forbid'", ast.unparse(classes["Body"]))

    @unittest.skipIf(importlib.util.find_spec("pydantic") is None, "pydantic is not installed")
    def test_request_bodies_reject_a_date_on_daily_entries(self):
        from pydantic import ValidationError

        from app.schemas import LoanIn, PostingIn
        loan = {"customer_id": 1, "items": [{"name": "Chain", "qty": 1}], "gross_weight": "10", "deduction": "0",
                "principal": "1000", "rate": "18", "tenure_months": 12, "request_id": "req-12345"}
        LoanIn(**loan)
        PostingIn(amount="10", request_id="req-12345")
        with self.assertRaises(ValidationError):
            LoanIn(**loan, loan_date="2025-03-01")
        for field in ("date", "loan_date"):
            with self.subTest(field), self.assertRaises(ValidationError):
                PostingIn(amount="10", request_id="req-12345", **{field: "2025-03-01"})


class AccessTests(Fixture):
    SUPERADMIN_REFUSED = "A SuperAdmin account cannot use this feature."

    def test_superadmin_works_with_customers_and_loans_of_any_branch(self):
        root = self.root
        self.assertEqual(root.effective_permissions(), ["newcustomer", "userlist"])
        self.assertTrue(root.is_head_office, "sees every branch and keeps backups")
        customer = run(customers_service.create(self.repos, root, NewCustomer("Ravi Kumar", "9000000001", "Pozhiyoor", "SAN")))
        number = self.loan(root, customer_id=customer["id"], request_id="root-loan")["loan_number"]
        later = NOW + timedelta(days=9)
        for call in (
            lambda: customers_service.search(self.repos, root, branch="SAN", term=None, page=1, page_size=20),
            lambda: customers_service.detail(self.repos, root, customer["id"], later),
            lambda: loans_service.detail(self.repos, root, number, later),
            lambda: loans_service.collect(self.repos, root, number, amount="100", expected_total=None,
                                          request_id="root-pay", now=later),
            lambda: loans_service.top_up(self.repos, root, number, amount="100", expected_total=None,
                                         request_id="root-top", now=later),
            lambda: loans_service.edit_items(self.repos, root, number, [{"name": "Bangle", "qty": 1}]),
            lambda: loans_service.set_follow_up(self.repos, root, number, date(2025, 4, 1), later),
            lambda: receipts_service.for_loan(self.repos, root, number, later),
        ):
            run(call())
        quote = run(loans_service.closing_quote(self.repos, root, number, later))
        run(loans_service.close(self.repos, root, number, amount_received=quote["total"], write_off_remaining=False,
                                expected_total=quote["total"], request_id="root-close", now=later))
        self.assertEqual(self.repos.state.loans[number]["loantype"], "closed")

    def test_superadmin_is_refused_analytics_reports_history_gold_rate_and_audit(self):
        from app.services import maintenance_service
        root = self.root
        refused = {
            "dashboard": lambda: reports_service.dashboard(self.repos, root, None, NOW),
            "portfolio": lambda: reports_service.portfolio(self.repos, root, None, NOW),
            "performance": lambda: reports_service.performance(self.repos, root, None, None, None, NOW),
            "details": lambda: reports_service.details(self.repos, root, "disbursed", None, None, None, NOW),
            "trends": lambda: reports_service.trends(self.repos, root, None, NOW),
            "transactions": lambda: reports_service.transactions(self.repos, root, branch=None, start=None, end=None,
                                                                 term=None, kind=None, page=1, page_size=20, now=NOW),
            "csv": lambda: reports_service.transactions_csv(self.repos, root, branch=None, start=None, end=None,
                                                            term=None, kind=None, now=NOW),
            "import preview": lambda: import_service.preview(root, ImportTests.LOAN, [], NOW),
            "import": lambda: import_service.commit(self.repos, root, customer_id=1, new_customer=None,
                                                    loan=ImportTests.LOAN, entries=[], request_id="root-imp", now=NOW),
        }
        for name, call in refused.items():
            with self.subTest(name), self.assertRaises(Forbidden) as ctx:
                run(call())
            self.assertEqual(ctx.exception.message, self.SUPERADMIN_REFUSED)
        for name, call in {
            "gold rate": lambda: reports_service.set_gold_rate(self.repos, root, "6000"),
            "audit log": lambda: maintenance_service.audit_page(self.repos, root, None, 1, 20),
        }.items():
            with self.subTest(name), self.assertRaises(Forbidden) as ctx:
                run(call())
            self.assertEqual(ctx.exception.message, "Only head office can do this.")

    def test_head_office_keeps_every_feature_with_gold_rate_and_audit_log(self):
        from app.services import maintenance_service
        from app.services.context import PERMISSIONS
        self.assertEqual(self.hq.effective_permissions(), list(PERMISSIONS))
        self.assertIsNotNone(run(reports_service.set_gold_rate(self.repos, self.hq, "6000")))
        page = run(maintenance_service.audit_page(self.repos, self.hq, None, 1, 20))
        self.assertEqual(page["items"][0]["action"], "SET_GOLD_RATE")
        with self.assertRaises(Forbidden) as ctx:
            run(maintenance_service.audit_page(self.repos, self.san, None, 1, 20))
        self.assertEqual(ctx.exception.message, "Only head office can do this.")
        self.repos.add_account("Counter", "Counter-only-2026", "branch", "CTR", permissions="newcustomer,userlist")
        with self.assertRaises(Forbidden) as ctx:
            run(import_service.preview(actor(self.repos, "Counter"), ImportTests.LOAN, [], NOW))
        self.assertEqual(ctx.exception.message, "Your branch does not have access to this feature.")


if __name__ == "__main__":
    unittest.main()

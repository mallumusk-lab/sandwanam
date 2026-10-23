"""Branch cash ledger: the domain rules and cash_service against the in-memory repositories."""
import asyncio
import importlib.util
import itertools
import unittest
from datetime import date, timedelta
from decimal import Decimal as D

from app.domain import cash
from app.errors import Conflict, Forbidden, Invalid, NotFound
from app.services import cash_service
from app.services.auth_service import actor_from
from tests.fakes import standard_repos, utc

NOW = utc(2025, 3, 10, 6, 0)  # 11:30 IST on 10 March 2025
TODAY = date(2025, 3, 10)
SUPERADMIN_REFUSED = "A SuperAdmin account cannot use this feature."
NO_ACCESS = "Your branch does not have access to this feature."


def run(coro):
    return asyncio.run(coro)


def day(offset):
    """`offset` days after NOW, same time of day."""
    return NOW + timedelta(days=offset)


class DomainRules(unittest.TestCase):
    def test_totals_ignore_voided_entries_and_show_differences(self):
        entries = [
            {"direction": "in", "amount": D("500.00"), "voided_at": None},
            {"direction": "out", "amount": D("200.50"), "voided_at": None},
            {"direction": "in", "amount": D("999.00"), "voided_at": NOW},
        ]
        totals = cash.day_totals(D("1000.00"), D("990.00"), entries)
        self.assertEqual((totals.cash_in, totals.cash_out), (D("500.00"), D("200.50")))
        self.assertEqual(totals.expected, D("1289.50"))
        self.assertEqual(totals.opening_difference, D("-10.00"), "negative is a shortage")
        self.assertEqual(cash.closing_difference(D("1289.50"), D("1300")), D("10.50"))
        self.assertEqual(cash.day_totals("0", "0", []).expected, D("0.00"))

    def test_categories_and_other_needs_a_description(self):
        keys = [(c.key, c.direction) for c in cash.CATEGORIES]
        self.assertEqual(keys, [
            ("loan_collection", "in"), ("from_head_office", "in"), ("other_income", "in"),
            ("loan_disbursement", "out"), ("bill_payment", "out"), ("donation", "out"), ("expense", "out"),
            ("to_head_office", "out"), ("other", "any"),
        ])
        self.assertEqual(cash.label("to_head_office"), "Cash to head office / bank")
        entry = cash.validate_entry("out", "other", "  Tea   for staff ", " B-12 ", "45.5")
        self.assertEqual((entry.description, entry.reference, entry.amount), ("Tea for staff", "B-12", D("45.50")))
        self.assertEqual(cash.validate_entry("in", "other", "Scrap sale", None, "10").direction, "in")
        self.assertIsNone(cash.validate_entry("out", "donation", "  ", "", "1").description)
        cases = {
            "direction": (("sideways", "other", "x", None, "1"), "invalid_direction"),
            "unknown category": (("in", "salary", None, None, "1"), "invalid_category"),
            "category is cash out": (("in", "bill_payment", None, None, "1"), "category_direction"),
            "category is cash in": (("out", "loan_collection", None, None, "1"), "category_direction"),
            "other without description": (("out", "other", "   ", None, "1"), "description_required"),
            "long description": (("out", "expense", "x" * 256, None, "1"), "invalid_description"),
            "long reference": (("out", "expense", None, "r" * 41, "1"), "invalid_reference"),
            "zero": (("in", "loan_collection", None, None, "0"), "invalid_amount"),
            "negative": (("in", "loan_collection", None, None, "-5"), "invalid_amount"),
            "three decimals": (("in", "loan_collection", None, None, "1.005"), "invalid_amount"),
            "not a number": (("in", "loan_collection", None, None, "ten"), "invalid_amount"),
        }
        for name, (args, code) in cases.items():
            with self.subTest(name), self.assertRaises(cash.CashError) as caught:
                cash.validate_entry(*args)
            self.assertEqual(caught.exception.code, code)

    def test_counted_amounts_may_be_zero_but_not_negative(self):
        self.assertEqual(cash.counted("0", field="f", name="Cash in hand"), D("0.00"))
        self.assertEqual(cash.counted("1,250.5", field="f", name="Cash in hand"), D("1250.50"))
        for bad in ("-1", "1.234", "abc"):
            with self.subTest(bad), self.assertRaises(cash.CashError):
                cash.counted(bad, field="f", name="Cash in hand")
        with self.assertRaises(cash.CashError):
            cash.void_reason(" ab ")
        self.assertEqual(cash.void_reason("  typed   twice "), "typed twice")
        self.assertEqual(cash.shown_amount("-12.5", field="f"), D("-12.50"), "an expected figure may be below zero")
        for bad in ("1e999", "Infinity", "x"):
            with self.subTest(bad), self.assertRaises(cash.CashError):
                cash.shown_amount(bad, field="f")

    def test_retention_keeps_today_and_the_previous_thirteen_days(self):
        self.assertEqual(cash.RETENTION_DAYS, 14)
        self.assertEqual(cash.cutoff(TODAY), date(2025, 2, 25))


class CashFixture(unittest.TestCase):
    def setUp(self):
        self.repos = standard_repos()
        users = self.repos.state.users
        self.hq, self.san, self.swa, self.root = (actor_from(users[n]) for n in ("Admin", "User1", "User2", "root"))
        self.ids = itertools.count(1)

    def rid(self, prefix="req"):
        return f"{prefix}-{next(self.ids):04d}"

    def start(self, counted="1000", who=None, now=NOW, branch=None, request_id=None):
        return run(cash_service.start_day(self.repos, who or self.san, branch=branch, opening_counted=counted,
                                          request_id=request_id or self.rid("start"), now=now))

    def add(self, day_id, amount="500", direction="in", category="loan_collection", description=None,
            reference=None, who=None, now=NOW, request_id=None):
        return run(cash_service.add_entry(self.repos, who or self.san, day_id, direction=direction, category=category,
                                          description=description, reference=reference, amount=amount,
                                          request_id=request_id or self.rid("entry"), now=now))

    def void(self, entry_id, reason="Typed twice", who=None, now=NOW):
        return run(cash_service.void_entry(self.repos, who or self.san, entry_id, reason=reason, now=now))

    def close(self, day_id, counted, expected, who=None, now=NOW):
        return run(cash_service.close_day(self.repos, who or self.san, day_id, closing_counted=counted,
                                          expected_total=expected, now=now))

    def overview(self, who=None, branch=None, now=NOW):
        return run(cash_service.overview(self.repos, who or self.san, branch, now))

    def assertRefused(self, error, code, call):
        with self.assertRaises(error) as caught:
            run(call())
        if code:
            self.assertEqual(caught.exception.code, code)
        return caught.exception


class DayFlow(CashFixture):
    def test_overview_shape_before_and_after_the_day_starts(self):
        view = self.overview()
        self.assertEqual(set(view), {"branch", "branch_name", "today", "carry_forward", "today_day", "history",
                                     "categories", "suggestions", "can_reopen"})
        self.assertEqual((view["branch"], view["branch_name"], view["today"]), ("SAN", "User1", "2025-03-10"))
        self.assertEqual(view["carry_forward"], {"amount": "0.00", "from_day": None})
        self.assertEqual((view["today_day"], view["history"], view["suggestions"], view["can_reopen"]),
                         (None, [], [], False))
        self.assertEqual(view["categories"][-1], {"key": "other", "label": "Other (type a description)",
                                                  "direction": "any"})
        self.assertEqual(len(view["categories"]), 9)
        started = self.start("1000")
        today = started["today_day"]
        self.assertEqual(set(today), {
            "id", "day", "status", "carried_forward", "opening_counted", "opening_difference", "cash_in", "cash_out",
            "expected", "closing_counted", "closing_difference", "closed_automatically", "opened_by", "opened_at",
            "closed_by", "closed_at", "entries"})
        added = self.add(today["id"], "500", reference="SAN1L1")["today_day"]
        self.assertEqual(set(added["entries"][0]), {
            "id", "at", "direction", "category", "category_label", "description", "reference", "amount",
            "recorded_by", "voided", "voided_at", "voided_by", "void_reason"})
        self.assertEqual(added["entries"][0]["category_label"], "Loan collection")
        self.assertEqual(added["entries"][0]["amount"], "500.00")
        self.assertEqual(added["entries"][0]["recorded_by"], "User1")

    def test_first_day_carries_zero_and_records_the_opening_difference(self):
        today = self.start("250.5")["today_day"]
        self.assertEqual((today["day"], today["status"], today["carried_forward"], today["opening_counted"]),
                         ("2025-03-10", "open", "0.00", "250.50"))
        self.assertEqual((today["opening_difference"], today["expected"]), ("250.50", "250.50"))
        self.assertEqual((today["closing_counted"], today["closing_difference"], today["closed_at"]), (None, None, None))
        self.assertEqual((today["opened_by"], today["closed_automatically"]), ("User1", False))

    def test_carry_forward_chain_uses_the_last_counted_closing(self):
        first = self.start("1000")["today_day"]
        self.add(first["id"], "500")
        view = self.add(first["id"], "200", direction="out", category="bill_payment", description="Electricity")
        self.assertEqual((view["today_day"]["cash_in"], view["today_day"]["cash_out"], view["today_day"]["expected"]),
                         ("500.00", "200.00", "1300.00"))
        closed = self.close(first["id"], "1290", "1300.00")["today_day"]
        self.assertEqual((closed["status"], closed["closing_counted"], closed["closing_difference"]),
                         ("closed", "1290.00", "-10.00"))
        self.assertEqual(closed["closed_by"], "User1")
        tomorrow = self.overview(now=day(1))
        self.assertEqual(tomorrow["carry_forward"], {"amount": "1290.00", "from_day": "2025-03-10"})
        self.assertIsNone(tomorrow["today_day"])
        second = self.start("1300", now=day(1))
        self.assertEqual((second["today_day"]["carried_forward"], second["today_day"]["opening_difference"]),
                         ("1290.00", "10.00"))
        self.assertEqual([d["day"] for d in second["history"]], ["2025-03-10"])
        self.close(second["today_day"]["id"], "1300", "1300.00", now=day(1))
        third = self.start("0", now=day(3))  # a day with no ledger in between
        self.assertEqual((third["today_day"]["carried_forward"], third["today_day"]["opening_difference"]),
                         ("1300.00", "-1300.00"))
        self.assertEqual([d["day"] for d in third["history"]], ["2025-03-11", "2025-03-10"], "newest first")

    def test_second_start_is_refused_and_a_replayed_start_is_not(self):
        first = self.start("1000", request_id="start-once")
        self.assertRefused(Conflict, "day_already_started", lambda: cash_service.start_day(
            self.repos, self.san, branch=None, opening_counted="900", request_id="start-again", now=NOW))
        again = self.start("1000", request_id="start-once")
        self.assertEqual(again["today_day"]["id"], first["today_day"]["id"])
        self.assertEqual(len(self.repos.state.cash_days), 1)
        self.assertEqual([a["action"] for a in self.repos.state.audit], ["CASH_START_DAY"])

    def test_entries_are_idempotent_by_request_id(self):
        first = self.start()["today_day"]
        once = self.add(first["id"], "500", request_id="entry-once")
        twice = self.add(first["id"], "500", request_id="entry-once")
        self.assertEqual(once, twice)
        self.assertEqual(len(self.repos.state.cash_entries), 1)
        self.close(first["id"], "1500", "1500.00")
        second = self.start("1500", now=day(1))["today_day"]
        self.assertRefused(Conflict, "request_id_reused", lambda: cash_service.add_entry(
            self.repos, self.san, second["id"], direction="in", category="loan_collection", description=None,
            reference=None, amount="500", request_id="entry-once", now=day(1)))

    def test_voided_entries_stop_counting_and_need_a_reason(self):
        today = self.start("1000")["today_day"]
        self.add(today["id"], "500")
        wrong = self.add(today["id"], "700", direction="out", category="expense")["today_day"]["entries"][1]
        self.assertEqual(self.overview()["today_day"]["expected"], "800.00")
        self.assertRefused(Invalid, "invalid_reason", lambda: cash_service.void_entry(
            self.repos, self.san, wrong["id"], reason="no", now=NOW))
        view = self.void(wrong["id"], "Entered on the wrong side")["today_day"]
        self.assertEqual((view["cash_out"], view["expected"]), ("0.00", "1500.00"))
        line = view["entries"][1]
        self.assertEqual((line["voided"], line["voided_by"], line["void_reason"]),
                         (True, "User1", "Entered on the wrong side"))
        self.assertEqual(line["amount"], "700.00", "a voided line keeps its amount; it just stops counting")
        self.assertIsNotNone(line["voided_at"])
        self.assertRefused(Conflict, "entry_voided", lambda: cash_service.void_entry(
            self.repos, self.san, wrong["id"], reason="Again please", now=NOW))
        self.assertRefused(NotFound, None, lambda: cash_service.void_entry(
            self.repos, self.san, 999, reason="Missing entry", now=NOW))

    def test_closed_day_refuses_entries_voids_and_a_second_close(self):
        today = self.start("1000")["today_day"]
        entry = self.add(today["id"], "100")["today_day"]["entries"][0]
        self.close(today["id"], "1100", "1100.00")
        self.assertRefused(Invalid, "day_closed", lambda: cash_service.add_entry(
            self.repos, self.san, today["id"], direction="in", category="loan_collection", description=None,
            reference=None, amount="5", request_id="late-entry-1", now=NOW))
        self.assertRefused(Invalid, "day_closed", lambda: cash_service.void_entry(
            self.repos, self.san, entry["id"], reason="Too late now", now=NOW))
        self.assertRefused(Invalid, "day_closed", lambda: cash_service.close_day(
            self.repos, self.san, today["id"], closing_counted="1100", expected_total="1100.00", now=NOW))
        self.assertEqual(len(self.repos.state.cash_entries), 1)

    def test_only_todays_open_day_takes_entries(self):
        yesterday = self.start("1000")["today_day"]
        later = day(1)
        self.assertRefused(Invalid, "no_open_day", lambda: cash_service.add_entry(
            self.repos, self.san, yesterday["id"], direction="in", category="loan_collection", description=None,
            reference=None, amount="5", request_id="stale-entry-1", now=later))
        self.assertRefused(Invalid, "no_open_day", lambda: cash_service.close_day(
            self.repos, self.san, yesterday["id"], closing_counted="1000", expected_total="1000.00", now=later))
        self.assertRefused(NotFound, None, lambda: cash_service.close_day(
            self.repos, self.san, 999, closing_counted="1", expected_total="1.00", now=NOW))

    def test_close_checks_the_shown_expected_amount(self):
        today = self.start("1000")["today_day"]
        shown = self.add(today["id"], "500")["today_day"]["expected"]
        self.add(today["id"], "100", who=self.san)  # a colleague's entry after the figure was shown
        error = self.assertRefused(Conflict, "cash_changed", lambda: cash_service.close_day(
            self.repos, self.san, today["id"], closing_counted="1500", expected_total=shown, now=NOW))
        self.assertEqual(error.status, 409)
        self.assertEqual(error.details, {"expected": "1600.00"})
        self.assertEqual(self.overview()["today_day"]["status"], "open")
        self.assertRefused(Invalid, "invalid_amount", lambda: cash_service.close_day(
            self.repos, self.san, today["id"], closing_counted="-1", expected_total="1600.00", now=NOW))
        for shown_bad in ("lots", "1e999", "NaN"):
            with self.subTest(shown_bad):
                self.assertRefused(Invalid, "invalid_amount", lambda: cash_service.close_day(
                    self.repos, self.san, today["id"], closing_counted="1600", expected_total=shown_bad, now=NOW))
        closed = self.close(today["id"], "1600", "1600")["today_day"]
        self.assertEqual((closed["closing_counted"], closed["closing_difference"]), ("1600.00", "0.00"))
        stored = self.repos.state.cash_days[today["id"]]
        self.assertEqual((stored["closing_expected"], stored["closed_automatically"]), (D("1600.00"), False))

    def test_a_drawer_below_zero_can_still_be_counted_and_closed(self):
        today = self.start("0")["today_day"]
        shown = self.add(today["id"], "100", direction="out", category="loan_disbursement")["today_day"]["expected"]
        self.assertEqual(shown, "-100.00", "recorded out of order: shown as it is, never hidden")
        closed = self.close(today["id"], "0", shown)["today_day"]
        self.assertEqual((closed["closing_counted"], closed["closing_difference"]), ("0.00", "100.00"))

    def test_reopen_is_head_office_only_today_only_latest_only(self):
        today = self.start("1000")["today_day"]
        self.assertRefused(Invalid, "day_open", lambda: cash_service.reopen_day(
            self.repos, self.hq, today["id"], now=NOW))
        self.close(today["id"], "990", "1000.00")
        self.assertFalse(self.overview()["can_reopen"], "branch staff cannot reopen")
        self.assertTrue(self.overview(self.hq, "SAN")["can_reopen"])
        with self.assertRaises(Forbidden) as caught:
            run(cash_service.reopen_day(self.repos, self.san, today["id"], now=NOW))
        self.assertEqual(caught.exception.message, "Only head office can do this.")
        with self.assertRaises(Forbidden) as caught:
            run(cash_service.reopen_day(self.repos, self.root, today["id"], now=NOW))
        self.assertEqual(caught.exception.message, SUPERADMIN_REFUSED)
        reopened = run(cash_service.reopen_day(self.repos, self.hq, today["id"], now=NOW))
        self.assertEqual(reopened["branch"], "SAN")
        day_view = reopened["today_day"]
        self.assertEqual((day_view["status"], day_view["closing_counted"], day_view["closed_by"]), ("open", None, None))
        self.assertFalse(reopened["can_reopen"])
        self.add(today["id"], "10")  # open again for entries
        self.close(today["id"], "1010", "1010.00")
        self.assertRefused(Invalid, "reopen_not_allowed", lambda: cash_service.reopen_day(
            self.repos, self.hq, today["id"], now=day(1)))
        # A later day exists (only possible through data from elsewhere): today's is no longer the latest.
        self.repos.state.cash_days[99] = dict(self.repos.state.cash_days[today["id"]], id=99, day=date(2025, 3, 11))
        self.assertFalse(self.overview(self.hq, "SAN")["can_reopen"])
        self.assertRefused(Invalid, "reopen_not_allowed", lambda: cash_service.reopen_day(
            self.repos, self.hq, today["id"], now=NOW))

    def test_start_day_auto_closes_a_stale_open_day(self):
        stale = self.start("1000")["today_day"]
        self.add(stale["id"], "200")
        waiting = self.overview(now=day(2))
        self.assertEqual(waiting["carry_forward"], {"amount": "1200.00", "from_day": "2025-03-10"},
                         "an open earlier day carries what its automatic close will store")
        self.assertEqual(waiting["history"][0]["status"], "open")
        started = self.start("1200", now=day(2))
        old = started["history"][0]
        self.assertEqual((old["status"], old["closed_automatically"], old["closed_by"]), ("closed", True, "system"))
        self.assertEqual((old["closing_counted"], old["closing_difference"]), ("1200.00", "0.00"))
        self.assertEqual(started["today_day"]["carried_forward"], "1200.00")
        audit = [(a["username"], a["action"]) for a in self.repos.state.audit]
        self.assertIn(("system", "CASH_CLOSE_DAY"), audit)
        self.assertLess(audit.index(("system", "CASH_CLOSE_DAY")), audit.index(("User1", "CASH_START_DAY"), 1))

    def test_daily_job_auto_closes_and_purges_keeping_each_branchs_latest_day(self):
        for offset in range(20):
            opened = self.start("100", now=day(offset))["today_day"]
            if offset == 0:
                self.add(opened["id"], "50", now=day(offset))
                self.void(self.repos.state.cash_entries[0]["id"], now=day(offset))
            self.close(opened["id"], "100", "100.00", now=day(offset))
        swa = self.start("300", who=self.swa)["today_day"]  # SWA's only day, never closed
        self.add(swa["id"], "20", who=self.swa)
        result = run(cash_service.auto_close_and_purge(self.repos, day(20)))
        self.assertEqual(result, {"cash_days_closed": 1, "cash_days_purged": 7})
        san_days = sorted(d["day"] for d in self.repos.state.cash_days.values() if d["branch_prefix"] == "SAN")
        self.assertEqual((san_days[0], san_days[-1], len(san_days)), (date(2025, 3, 17), date(2025, 3, 29), 13))
        kept = next(d for d in self.repos.state.cash_days.values() if d["branch_prefix"] == "SWA")
        self.assertEqual((kept["closed_automatically"], kept["closing_counted"]), (True, D("320.00")),
                         "the latest day survives the purge so its closing can be carried forward")
        self.assertEqual([e["day_id"] for e in self.repos.state.cash_entries], [swa["id"]],
                         "a deleted day's entries go with it")
        view = self.overview(self.swa, now=day(20))
        self.assertEqual(view["carry_forward"], {"amount": "320.00", "from_day": "2025-03-10"})
        self.assertEqual(view["history"], [], "older than 14 days: not listed, only carried forward")
        self.assertEqual(run(cash_service.auto_close_and_purge(self.repos, day(20))),
                         {"cash_days_closed": 0, "cash_days_purged": 0})

    def test_suggestions_are_custom_descriptions_most_used_first(self):
        today = self.start("1000")["today_day"]
        for minutes, text in enumerate(("Tea", "Courier", "Tea")):
            self.add(today["id"], "10", direction="out", category="other", description=text,
                     now=NOW + timedelta(minutes=minutes))
        self.add(today["id"], "10", direction="in", category="other", description="Scrap sale",
                 now=NOW + timedelta(minutes=5))  # used as often as Courier, but more recently
        wrong = self.add(today["id"], "10", direction="out", category="other", description="Wrong",
                         now=NOW + timedelta(minutes=6))
        self.void(wrong["today_day"]["entries"][-1]["id"])
        self.add(today["id"], "10", direction="out", category="expense", description="Printer ink")
        self.assertEqual(self.overview()["suggestions"], ["Tea", "Scrap sale", "Courier"])
        self.assertEqual(self.overview(self.swa)["suggestions"], [], "each branch has its own")

    def test_invalid_entries_change_nothing(self):
        today = self.start("1000")["today_day"]
        before = len(self.repos.state.audit)
        for kwargs, code in (({"category": "other", "direction": "out"}, "description_required"),
                             ({"category": "donation", "direction": "in"}, "category_direction"),
                             ({"amount": "0"}, "invalid_amount")):
            with self.subTest(code):
                error = self.assertRefused(Invalid, code, lambda: cash_service.add_entry(
                    self.repos, self.san, today["id"], **{"direction": "in", "category": "loan_collection",
                                                          "description": None, "reference": None, "amount": "5",
                                                          "request_id": self.rid(), "now": NOW, **kwargs}))
                self.assertIn("field", error.details)
        self.assertEqual((self.repos.state.cash_entries, len(self.repos.state.audit)), ([], before))
        self.assertRefused(Invalid, "invalid_amount", lambda: cash_service.start_day(
            self.repos, self.swa, branch=None, opening_counted="-5", request_id="start-bad-1", now=NOW))

    def test_every_write_is_audited(self):
        today = self.start("1000")["today_day"]
        entry = self.add(today["id"], "100")["today_day"]["entries"][0]
        self.void(entry["id"], "Wrong amount")
        self.close(today["id"], "1000", "1000.00")
        run(cash_service.reopen_day(self.repos, self.hq, today["id"], now=NOW, context={"ip": "1.1.1.1"}))
        audit = self.repos.state.audit
        self.assertEqual([(a["username"], a["action"]) for a in audit], [
            ("User1", "CASH_START_DAY"), ("User1", "CASH_ENTRY"), ("User1", "CASH_VOID"), ("User1", "CASH_CLOSE_DAY"),
            ("Admin", "CASH_REOPEN_DAY")])
        self.assertTrue(all(a["entity_type"] == "CASH" for a in audit))
        self.assertEqual(audit[0]["entity_id"], "SAN 2025-03-10")
        self.assertIn("Wrong amount", audit[2]["details"])
        self.assertEqual(audit[-1]["ip"], "1.1.1.1")


class Access(CashFixture):
    def test_branch_staff_see_only_their_own_drawer(self):
        swa = self.start("300", who=self.swa)["today_day"]
        entry = self.add(swa["id"], "20", who=self.swa)["today_day"]["entries"][0]
        hidden = {
            "add": lambda: cash_service.add_entry(self.repos, self.san, swa["id"], direction="in",
                                                  category="loan_collection", description=None, reference=None,
                                                  amount="5", request_id="probe-0001", now=NOW),
            "void": lambda: cash_service.void_entry(self.repos, self.san, entry["id"], reason="Not mine", now=NOW),
            "close": lambda: cash_service.close_day(self.repos, self.san, swa["id"], closing_counted="320",
                                                    expected_total="320.00", now=NOW),
        }
        for name, call in hidden.items():
            with self.subTest(name), self.assertRaises(NotFound):
                run(call())
        for call in (lambda: cash_service.overview(self.repos, self.san, "SWA", NOW),
                     lambda: cash_service.start_day(self.repos, self.san, branch="SWA", opening_counted="1",
                                                    request_id="probe-0002", now=NOW)):
            with self.assertRaises(Forbidden):
                run(call())
        self.assertEqual(self.overview(branch="san")["branch"], "SAN", "a branch may name itself")
        self.assertIsNone(self.overview()["today_day"], "SWA's day is not SAN's")
        self.assertEqual(len(self.repos.state.cash_entries), 1)

    def test_head_office_works_on_one_branch_at_a_time(self):
        for requested in (None, "", "ALL"):
            with self.subTest(requested):
                error = self.assertRefused(Invalid, "branch_required", lambda: cash_service.overview(
                    self.repos, self.hq, requested, NOW))
                self.assertEqual(error.message, "Choose a branch to see its cash ledger.")
        self.assertRefused(Invalid, "branch_required", lambda: cash_service.start_day(
            self.repos, self.hq, branch=None, opening_counted="1", request_id="hq-start-1", now=NOW))
        self.assertRefused(NotFound, None, lambda: cash_service.overview(self.repos, self.hq, "XYZ", NOW))
        swa = self.start("300", who=self.swa)["today_day"]
        view = self.overview(self.hq, "swa")
        self.assertEqual((view["branch"], view["today_day"]["id"]), ("SWA", swa["id"]))
        self.add(swa["id"], "10", who=self.hq)
        own = self.start("50", who=self.hq, branch="AD")
        self.assertEqual((own["branch"], own["today_day"]["carried_forward"]), ("AD", "0.00"))
        self.assertEqual(self.overview(self.swa)["today_day"]["entries"][0]["recorded_by"], "Admin")

    def test_superadmin_is_refused(self):
        swa = self.start("300", who=self.swa)["today_day"]
        calls = {
            "overview": lambda: cash_service.overview(self.repos, self.root, "SWA", NOW),
            "start": lambda: cash_service.start_day(self.repos, self.root, branch="SAN", opening_counted="1",
                                                    request_id="root-start-1", now=NOW),
            "add": lambda: cash_service.add_entry(self.repos, self.root, swa["id"], direction="in",
                                                  category="loan_collection", description=None, reference=None,
                                                  amount="5", request_id="root-entry-1", now=NOW),
            "void": lambda: cash_service.void_entry(self.repos, self.root, 1, reason="No access", now=NOW),
            "close": lambda: cash_service.close_day(self.repos, self.root, swa["id"], closing_counted="1",
                                                    expected_total="300.00", now=NOW),
            "reopen": lambda: cash_service.reopen_day(self.repos, self.root, swa["id"], now=NOW),
        }
        for name, call in calls.items():
            with self.subTest(name), self.assertRaises(Forbidden) as caught:
                run(call())
            self.assertEqual(caught.exception.message, SUPERADMIN_REFUSED)
        self.assertNotIn("cashbook", self.root.effective_permissions())

    def test_a_branch_without_the_feature_is_refused(self):
        self.repos.add_account("Counter", "Counter-only-2026", "branch", "CTR", permissions="newcustomer,userlist")
        counter = actor_from(self.repos.state.users["Counter"])
        for call in (lambda: cash_service.overview(self.repos, counter, None, NOW),
                     lambda: cash_service.start_day(self.repos, counter, branch=None, opening_counted="1",
                                                    request_id="ctr-start-1", now=NOW),
                     lambda: cash_service.add_entry(self.repos, counter, 1, direction="in", category="loan_collection",
                                                    description=None, reference=None, amount="5",
                                                    request_id="ctr-entry-1", now=NOW)):
            with self.assertRaises(Forbidden) as caught:
                run(call())
            self.assertEqual(caught.exception.message, NO_ACCESS)
        self.assertEqual(self.repos.state.cash_days, {})
        self.assertIn("cashbook", self.san.effective_permissions())
        self.assertIn("cashbook", self.hq.effective_permissions())

    def test_new_branches_get_the_cash_ledger_by_default(self):
        from app.services.context import DEFAULT_PERMISSIONS, PERMISSIONS
        self.assertIn("cashbook", PERMISSIONS)
        self.assertEqual(DEFAULT_PERMISSIONS, "newcustomer,userlist,form1,analytics,report,cashbook")
        from pathlib import Path
        migration = (Path(__file__).resolve().parents[1] / "migrations" / "005_cash_ledger.sql").read_text("utf-8")
        self.assertIn(f"SET DEFAULT '{DEFAULT_PERMISSIONS}'", migration, "the column default matches the code")

    def test_a_branch_with_cash_days_cannot_be_deleted(self):
        from app.services import branches_service
        self.start(who=self.swa)
        with self.assertRaises(Conflict) as caught:
            run(branches_service.delete_branch(self.repos, self.root, "User2"))
        self.assertEqual(caught.exception.code, "branch_in_use")
        self.assertIn("User2", self.repos.state.users, "nothing is deleted")
        self.assertEqual(len(self.repos.state.cash_days), 1)


@unittest.skipIf(importlib.util.find_spec("pydantic") is None, "pydantic is not installed")
class RequestBodies(unittest.TestCase):
    def test_cash_bodies_reject_unknown_and_malformed_fields(self):
        from pydantic import ValidationError
        from app.schemas import CashCloseIn, CashDayIn, CashEntryIn, CashVoidIn
        entry = {"direction": "out", "category": "other", "description": "Tea", "amount": 12.5,
                 "request_id": "req-12345"}
        self.assertEqual(CashEntryIn(**entry).amount, "12.5", "numbers arrive as strings, never floats")
        self.assertEqual(CashDayIn(opening_counted="0", request_id="req-12345").branch, None)
        CashCloseIn(closing_counted="10", expected_total="10.00")
        bad = {
            "unknown field": lambda: CashEntryIn(**entry, date="2025-03-01"),
            "direction": lambda: CashEntryIn(**dict(entry, direction="sideways")),
            "reference too long": lambda: CashEntryIn(**dict(entry, reference="r" * 41)),
            "no request id": lambda: CashDayIn(opening_counted="10"),
            "short reason": lambda: CashVoidIn(reason="no"),
            "close without expected": lambda: CashCloseIn(closing_counted="10"),
        }
        for name, build in bad.items():
            with self.subTest(name), self.assertRaises(ValidationError):
                build()


if __name__ == "__main__":
    unittest.main()

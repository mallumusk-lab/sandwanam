"""Every repository method runs against a recording connection. `Db` asserts that each
statement's $n placeholders match its arguments, so a mismatch fails here instead of
in production. The tests also check that user input never ends up inside SQL text."""
import asyncio
import unittest
from datetime import date
from decimal import Decimal as D
from pathlib import Path

from app.domain import backup_codec
from app.repositories import QueryArgumentError, Repos, check_arguments, like_pattern
from tests.fakes import utc

NOW = utc(2025, 3, 10, 6)
EVIL = "x'); DROP TABLE customers; --"


class RecordingConnection:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    async def fetch(self, sql, *args):
        self.calls.append((sql, args))
        return []

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args))
        return None

    async def fetchval(self, sql, *args):
        self.calls.append((sql, args))
        return 1

    async def execute(self, sql, *args):
        self.calls.append((sql, args))
        return "OK"

    async def executemany(self, sql, rows):
        for row in rows:
            self.calls.append((sql, tuple(row)))

    def transaction(self):
        raise AssertionError("repositories must not open transactions themselves")


def run(coro):
    return asyncio.run(coro)


class PlaceholderChecks(unittest.TestCase):
    def test_check_arguments(self):
        check_arguments("SELECT $1, $2, $1", (1, 2))
        for sql, args in (("SELECT $1", ()), ("SELECT $1, $3", (1, 2, 3)), ("SELECT 1", (1,))):
            with self.subTest(sql), self.assertRaises(QueryArgumentError):
                check_arguments(sql, args)

    def test_like_pattern_escapes_wildcards(self):
        self.assertEqual(like_pattern("50%_off\\"), "%50\\%\\_off\\\\%")


class EveryRepositoryMethod(unittest.TestCase):
    def setUp(self):
        self.conn = RecordingConnection()
        self.repos = Repos(self.conn)

    def tearDown(self):
        for sql, args in self.conn.calls:
            self.assertNotIn(EVIL, sql, "user input must be passed as a parameter")

    def test_users_sessions_throttle(self):
        r = self.repos
        run(r.users.get(EVIL))
        run(r.users.list_accounts())
        run(r.users.branches())
        run(r.users.branch("SAN"))
        run(r.users.branch_prefixes())
        run(r.users.create(username="u", password_hash="h", account_type="branch", branch_prefix="SAN",
                           display_name=EVIL, legal_name=None, address=None, phone=None, email=None, logo=None,
                           permissions="report"))
        run(r.users.update_settings("u", {"display_name": EVIL, "logo": None, "password": "ignored"}))
        run(r.users.update_settings("u", {}))
        run(r.users.set_password("u", "h", must_change=True))
        run(r.users.upgrade_hash("u", "h"))
        run(r.users.set_active("u", False))
        run(r.users.delete("u"))
        run(r.users.customer_count("SAN"))
        run(r.users.ensure_counter("SAN"))
        run(r.sessions.create(b"h", "u", NOW, NOW, "1.1.1.1", "agent"))
        run(r.sessions.get(b"h"))
        run(r.sessions.touch(b"h", NOW))
        run(r.sessions.delete(b"h"))
        run(r.sessions.delete_for_user("u"))
        run(r.sessions.delete_for_user("u", b"keep"))
        run(r.sessions.purge_expired(NOW, NOW))
        run(r.throttle.lock_row(EVIL, "ip", NOW))
        run(r.throttle.get(EVIL, "trusted:ip"))
        run(r.throttle.purge(NOW, NOW, NOW))
        run(r.throttle.save("u", "ip", 1, None, NOW))
        run(r.throttle.clear("u", "ip"))
        run(r.throttle.clear_user("u"))
        update = next(sql for sql, _ in self.conn.calls if sql.startswith("UPDATE role SET display_name"))
        self.assertNotIn("password", update, "only whitelisted columns can be updated")

    def test_customers_loans_statements(self):
        r = self.repos
        run(r.customers.search("SAN", EVIL, 20, 0))
        run(r.customers.search(None, None, 20, 0))
        run(r.customers.get(1))
        run(r.customers.by_phone(EVIL))
        run(r.customers.lock(1))
        run(r.customers.next_customer_number("SAN"))
        run(r.customers.user_id_taken("SAN1"))
        run(r.customers.insert(name=EVIL, phone="9876543210", address="a", user_id="SAN1", branch="SAN"))
        run(r.customers.next_loan_number(1))
        run(r.customers.refresh_loan_status(1))
        run(r.loans.get(EVIL))
        run(r.loans.lock("SAN1L1"))
        run(r.loans.exists("SAN1L1"))
        run(r.loans.for_customer(1))
        run(r.loans.open_with_position(None))
        run(r.loans.insert(customer_id=1, loan_number="SAN1L1", items_json="[]", particulars=EVIL, number_of_items=1,
                           weight=D("1"), deduction=D("0"), net_weight=D("1"), principal=D("1"), rate=D("1"),
                           tenure=1, branch="SAN", loan_date=NOW, created_by="u"))
        run(r.loans.set_items("SAN1L1", "[]", "x", 1))
        run(r.loans.update_cache("SAN1L1", D("1"), D("0")))
        run(r.loans.mark_closed("SAN1L1", NOW))
        run(r.loans.set_follow_up("SAN1L1", date(2025, 4, 1)))
        run(r.statements.latest("SAN1L1"))
        run(r.statements.totals("SAN1L1"))
        run(r.statements.by_request_id(EVIL))
        run(r.statements.insert(loan_id=1, loan_number="SAN1L1", kind="addColl", at=NOW, amount_paid=D("1"),
                                current_principal=D("0"), current_interest=D("1"), principal_balance=D("1"),
                                interest_balance=D("0"), accrued_days=1, writeoff_principal=None,
                                writeoff_interest=None, created_by="u", request_id="r"))
        run(r.statements.for_loan("SAN1L1"))
        run(r.statements.get(1))
        lock_sql = next(sql for sql, _ in self.conn.calls if "FOR UPDATE OF l" in sql)
        self.assertIn("WHERE l.loan_number = $1", lock_sql)

    def test_first_week_totals_come_from_the_whole_ledger(self):
        """The window peak and interest already collected (first-7-days rule) are read by the
        position queries and, for the locked write path, by statements.totals."""
        r = self.repos
        run(r.loans.get("SAN1L1"))
        run(r.loans.for_customer(1))
        run(r.loans.open_with_position("SAN"))
        run(r.statements.totals("SAN1L1"))
        get_sql, customer_sql, open_sql, totals_sql = [sql for sql, _ in self.conn.calls]
        for sql in (get_sql, customer_sql, open_sql):
            self.assertIn("cc.peak_principal", sql)
            self.assertIn("cc.interest_collected", sql)
            self.assertIn("MAX(s.principlebalance) AS peak_principal", sql)
        for sql in (get_sql, totals_sql):
            self.assertIn("COUNT(*) FILTER (WHERE s.transactiontype = 'compounding') AS compoundings", sql)
            self.assertIn("SUM(s.currentinterest) FILTER (WHERE s.transactiontype = 'addColl')", sql)
        self.assertIn("WHERE s.loan_number = $1", totals_sql)

    def test_reports(self):
        r = self.repos
        lower, upper = utc(2025, 3, 1), utc(2025, 3, 2)
        run(r.reports.period_totals(None, lower, upper))
        for metric in ("disbursed", "new_loans", "interest_collected", "principal_collected", "total_collected",
                       "compounded", "written_off", "closures", "gold_pledged", "gold_released"):
            with self.subTest(metric):
                run(r.reports.details(metric, "SAN", lower, upper, 10))
        run(r.reports.monthly_flows(None, lower, upper))
        run(r.reports.recent(None, 8))
        run(r.reports.loan_counts("SAN"))
        run(r.reports.transactions(None, lower, upper, EVIL, "addColl", 50, 0))
        transactions = self.conn.calls[-1][0]
        self.assertIn("l.date AS loan_date", transactions, "statement rows need the loan date (in_first_week)")
        self.assertIn("s.created_at", transactions)

    def test_admin(self):
        r = self.repos
        run(r.audit.log(username="u", action="A", entity_type="E", entity_id="1", details=EVIL))
        run(r.audit.page(EVIL, 50, 0))
        run(r.settings.get("gold_rate"))
        run(r.settings.put("gold_rate", {"per_gram": EVIL}, "u"))
        run(r.backups.export_rows())
        run(r.backups.missing_branches({"SAN"}))
        payload = backup_codec.encode(
            {"customers": [{"customerid": 1, "customername": EVIL, "branch_prefix": "SAN"}],
             "loan_data": [{"loanid": 1, "loan_number": "SAN1L1", "items": []}],
             "statement": [{"statementid": 1, "loan_number": "SAN1L1"}],
             "branches": [{"username": "User1", "branch_prefix": "SAN"}],
             "branch_counters": [{"branch_prefix": "SAN", "next_customer_no": 2}],
             "app_settings": [{"key": "gold_rate", "value": {"per_gram": "1"}, "updated_at": NOW, "updated_by": "u"}]},
            NOW,
        )
        run(r.backups.replace_business_data(backup_codec.decode(payload)))
        sqls = [sql for sql, _ in self.conn.calls]
        drops = [i for i, sql in enumerate(sqls) if "DROP CONSTRAINT" in sql]
        adds = [i for i, sql in enumerate(sqls) if "ADD CONSTRAINT" in sql]
        self.assertEqual(len(drops), 4)
        self.assertTrue(all(sqls[i].endswith("NOT VALID") for i in adds), "re-added constraints stay NOT VALID")
        self.assertLess(max(drops), min(adds))
        branch_update = next(sql for sql in sqls if "UPDATE role SET display_name" in sql)
        self.assertNotIn("permissions", branch_update, "a restore never re-grants features")
        self.assertFalse(any("backup_snapshots" in sql for sql in sqls), "backups are never stored")
        repositories = Path(__file__).resolve().parents[1] / "app" / "repositories"
        for source in sorted(repositories.glob("*.py")):
            self.assertNotIn("backup_snapshots", source.read_text("utf-8"), source.name)
        self.assertEqual([name for name in dir(r.backups) if "snapshot" in name], [])
        migration = (repositories.parents[1] / "migrations" / "005_cash_ledger.sql").read_text("utf-8")
        self.assertIn("\nDROP TABLE IF EXISTS backup_snapshots;", migration, "005 removes the old snapshots table")
        truncate = next(sql for sql, _ in self.conn.calls if sql.startswith("TRUNCATE"))
        self.assertNotIn("role", truncate, "restores never touch accounts")
        self.assertNotIn("audit_logs", truncate)

    def test_cash_ledger(self):
        import inspect
        from app.repositories.cash import CashRepo
        r, day = self.repos, date(2025, 3, 10)
        calls = {
            "latest_day": [lambda: r.cash.latest_day(EVIL), lambda: r.cash.latest_day("SAN", day)],
            "day_for_update": [lambda: r.cash.day_for_update(1)],
            "days_since": [lambda: r.cash.days_since(EVIL, day)],
            "entries_for_days": [lambda: r.cash.entries_for_days([1, 2]), lambda: r.cash.entries_for_days([])],
            "entry": [lambda: r.cash.entry(1)],
            "entry_by_request_id": [lambda: r.cash.entry_by_request_id(EVIL)],
            "create_day": [lambda: r.cash.create_day(branch="SAN", day=day, carried_forward=D("0"),
                                                     opening_counted=D("1"), opened_by=EVIL, opened_at=NOW,
                                                     request_id="r")],
            "add_entry": [lambda: r.cash.add_entry(day_id=1, direction="out", category="other", description=EVIL,
                                                   reference=EVIL, amount=D("1"), request_id="r", created_by="u",
                                                   created_at=NOW)],
            "void_entry": [lambda: r.cash.void_entry(1, voided_by="u", reason=EVIL, at=NOW)],
            "close_day": [lambda: r.cash.close_day(1, expected=D("1"), counted=D("1"), closed_by="u", at=NOW,
                                                   automatically=False)],
            "reopen_day": [lambda: r.cash.reopen_day(1)],
            "open_days_before": [lambda: r.cash.open_days_before(day), lambda: r.cash.open_days_before(day, EVIL)],
            "purge": [lambda: r.cash.purge(day)],
            "recent_custom_descriptions": [lambda: r.cash.recent_custom_descriptions(EVIL, day, 20)],
        }
        public = {name for name, fn in inspect.getmembers(CashRepo, inspect.iscoroutinefunction)
                  if not name.startswith("_")}
        self.assertEqual(set(calls), public, "every CashRepo method is exercised here")
        for name, makers in calls.items():
            for make in makers:
                with self.subTest(name):
                    run(make())
        sqls = [sql for sql, _ in self.conn.calls]
        self.assertEqual(len(sqls), sum(len(m) for m in calls.values()) - 1, "no query for an empty id list")
        lock = next(sql for sql in sqls if "FOR UPDATE" in sql)
        self.assertIn("FROM cash_days d WHERE d.id = $1 FOR UPDATE", lock)
        purge = next(sql for sql in sqls if "DELETE FROM cash_days" in sql)
        self.assertIn("d.day < $1", purge)
        self.assertIn("d.day < (SELECT MAX(l.day) FROM cash_days l WHERE l.branch_prefix = d.branch_prefix)", purge,
                      "each branch's latest day is kept for the carry forward")
        self.assertIn("ON CONFLICT (branch_prefix, day) DO NOTHING", next(s for s in sqls if "INSERT INTO cash_days" in s))
        self.assertIn("ON CONFLICT (client_request_id) DO NOTHING",
                      next(s for s in sqls if "INSERT INTO cash_entries" in s))
        self.assertIn("voided_at IS NULL", next(s for s in sqls if s.lstrip().startswith("UPDATE cash_entries")))
        self.assertTrue(all("loan" not in s and "statement" not in s for s in sqls), "independent of loans")

    def test_cash_tables_are_backed_up_and_restored_children_last(self):
        r = self.repos
        payload = backup_codec.encode(
            {"customers": [], "loan_data": [], "statement": [],
             "cash_days": [{"id": 1, "branch_prefix": "SAN", "day": date(2025, 3, 10), "carried_forward": D("0"),
                            "opening_counted": D("1"), "opened_by": EVIL, "opened_at": NOW,
                            "closed_automatically": False}],
             "cash_entries": [{"id": 1, "day_id": 1, "direction": "out", "category": "other", "description": EVIL,
                               "amount": D("1"), "created_by": "u", "created_at": NOW}]},
            NOW,
        )
        run(r.backups.export_rows())
        run(r.backups.replace_business_data(backup_codec.decode(payload)))
        sqls = [sql for sql, _ in self.conn.calls]
        self.assertIn("SELECT id, branch_prefix, day,", next(s for s in sqls if "FROM cash_days ORDER BY id" in s))
        self.assertTrue(any("FROM cash_entries ORDER BY id" in s for s in sqls))
        truncate = next(s for s in sqls if s.startswith("TRUNCATE"))
        self.assertIn("cash_entries, cash_days", truncate)
        inserts = [s.split("(")[0].split()[-1] for s in sqls if s.startswith("INSERT INTO") and "VALUES ($1" in s]
        self.assertLess(inserts.index("cash_days"), inserts.index("cash_entries"), "parents first")
        for table in ("cash_days", "cash_entries"):
            self.assertTrue(any(f"pg_get_serial_sequence('{table}', 'id')" in s for s in sqls), table)


if __name__ == "__main__":
    unittest.main()

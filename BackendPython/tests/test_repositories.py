"""Every repository method runs against a recording connection. `Db` asserts that each
statement's $n placeholders match its arguments, so a mismatch fails here instead of
in production. The tests also check that user input never ends up inside SQL text."""
import asyncio
import unittest
from datetime import date
from decimal import Decimal as D

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
        run(r.statements.history("SAN1L1"))
        run(r.statements.compounding_count("SAN1L1"))
        run(r.statements.by_request_id(EVIL))
        run(r.statements.insert(loan_id=1, loan_number="SAN1L1", kind="addColl", at=NOW, amount_paid=D("1"),
                                current_principal=D("0"), current_interest=D("1"), principal_balance=D("1"),
                                interest_balance=D("0"), accrued_days=1, writeoff_principal=None,
                                writeoff_interest=None, created_by="u", request_id="r"))
        run(r.statements.for_loan("SAN1L1"))
        run(r.statements.get(1))
        lock_sql = next(sql for sql, _ in self.conn.calls if "FOR UPDATE OF l" in sql)
        self.assertIn("WHERE l.loan_number = $1", lock_sql)

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
        run(r.backups.create_snapshot(kind="manual", created_by="u", payload=b"x", sha256="0" * 64))
        run(r.backups.snapshots())
        run(r.backups.snapshot(1))
        run(r.backups.prune_snapshots("manual", 5))
        run(r.backups.latest_snapshot_at("manual"))
        sqls = [sql for sql, _ in self.conn.calls]
        drops = [i for i, sql in enumerate(sqls) if "DROP CONSTRAINT" in sql]
        adds = [i for i, sql in enumerate(sqls) if "ADD CONSTRAINT" in sql]
        self.assertEqual(len(drops), 4)
        self.assertTrue(all(sqls[i].endswith("NOT VALID") for i in adds), "re-added constraints stay NOT VALID")
        self.assertLess(max(drops), min(adds))
        branch_update = next(sql for sql in sqls if "UPDATE role SET display_name" in sql)
        self.assertNotIn("permissions", branch_update, "a restore never re-grants features")
        prune = next(sql for sql in sqls if "DELETE FROM backup_snapshots" in sql)
        self.assertIn("kind = $1", prune, "snapshots are pruned per kind")
        truncate = next(sql for sql, _ in self.conn.calls if sql.startswith("TRUNCATE"))
        self.assertNotIn("role", truncate, "restores never touch accounts")
        self.assertNotIn("audit_logs", truncate)


if __name__ == "__main__":
    unittest.main()

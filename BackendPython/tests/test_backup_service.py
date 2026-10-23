"""Backups built in memory, Import backup (the dry-run check and restores of a .json, .json.gz
or the emailed password ZIP) and the daily job, against the in-memory repositories. Nothing
is ever stored as a backup."""
import asyncio
import base64
import gzip
import hashlib
import json
import unittest
from datetime import datetime, timedelta
from decimal import Decimal as D

from app.domain import backup_codec
from app.errors import Forbidden, Invalid
from app.repositories.admin import BackupsRepo
from app.services import backup_email_service, backup_service, cash_service, maintenance_service
from app.services.auth_service import actor_from
from tests.backup_fakes import FakeMailer, MailFailure, with_backups
from tests.fakes import standard_repos, utc

try:
    import pyzipper
except ImportError:  # the app runs without it (ZIP import and email are then reported as not set up)
    pyzipper = None

NOW = utc(2025, 3, 10, 6, 0)  # 11:30 IST
ZIP_PASSWORD = "Correct-horse-battery-9"


def run(coro):
    return asyncio.run(coro)


def seed(repos):
    """One SAN customer with a loan and its opening entry, plus a business setting."""
    s = repos.state
    s.customers[1] = dict(customerid=1, customername="Lakshmi Nair", phone="9876543210", address="Uchakkada",
                          user_id="SAN1", branch_prefix="SAN", loanstatus="1", last_loan_no=1, role=None,
                          created_at=utc(2025, 1, 1))
    s.loans["SAN1L1"] = dict(loanid=1, customerid=1, loan_number="SAN1L1", items=[{"name": "Chain", "qty": 1}],
                             particulars="Chain", number_of_items="1", weight=D("50.00"), deduction=D("2.00"),
                             net_weight=D("48.00"), principle_amount=D("100000.00"), interest=D("12.00"), tenure=12,
                             date=utc(2025, 3, 1, 6), loantype="open", refreshprincipleamount=D("100000.00"),
                             refreshinterest=D("0.00"), follow_up_date=None, closed_at=None, created_by="User1")
    s.statements.append(dict(statementid=1, loanid=1, loan_number="SAN1L1", transactiontype="newLoan",
                             date=utc(2025, 3, 1, 6), amountpaid=D("0.00"), currentprincipal=D("100000.00"),
                             currentinterest=D("0.00"), principlebalance=D("100000.00"), interestbalance=D("0.00"),
                             accrued_days=0, writeoff_principal=None, writeoff_interest=None, created_by="User1",
                             client_request_id="req-loan", created_at=utc(2025, 3, 1, 6)))
    s.next_ids.update(customer=2, loan=2, statement=2)
    s.settings["gold_rate"] = {"value": {"per_gram": "7000.00"}, "updated_at": NOW, "updated_by": "Admin"}
    return repos


class BackupFixture(unittest.TestCase):
    def setUp(self):
        self.repos = seed(with_backups(standard_repos()))
        users = self.repos.state.users
        self.hq, self.san, self.root = (actor_from(users[name]) for name in ("Admin", "User1", "root"))

    def packed(self, document):
        return base64.b64encode(backup_codec.pack(backup_codec.canonical(document))).decode("ascii")

    def audit_actions(self):
        return [entry["action"] for entry in self.repos.state.audit]

    def state_dump(self):
        return json.dumps(self.repos.state.__dict__, default=str, sort_keys=True)


class Files(BackupFixture):
    def test_backup_bytes_are_canonical_v3_and_nothing_is_stored(self):
        before = self.state_dump()
        raw, digest = run(backup_service.backup_bytes(self.repos, NOW, created_by="Admin", kind="manual"))
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
        document = backup_codec.loads(raw)
        self.assertEqual(raw, backup_codec.canonical(document), "the emailed bytes are the canonical document")
        self.assertEqual((document["format_version"], document["kind"], document["created_by"]), (3, "manual", "Admin"))
        self.assertEqual(document["manifest"]["tables"]["loan_data"]["rows"], 1)
        self.assertEqual(backup_codec.inspect(document)["checksum"], "verified")
        self.assertEqual(self.state_dump(), before, "building a backup writes nothing, not even an audit line")
        for repo in (BackupsRepo, self.repos.backups):
            self.assertEqual([name for name in dir(repo) if "snapshot" in name], [], "backups are never stored")
        self.assertFalse(hasattr(self.repos.state, "snapshots"))
        for removed in ("export_file", "snapshot_with_raw", "create_snapshot", "manual_snapshot", "list_snapshots",
                        "snapshot_file", "KEEP_SNAPSHOTS"):
            self.assertFalse(hasattr(backup_service, removed), removed)

    def test_a_damaged_or_edited_file_is_refused(self):
        document = run(backup_service.export_document(self.repos, NOW, created_by="Admin", kind="manual"))
        packed = backup_codec.pack(backup_codec.canonical(document))
        edited = json.loads(json.dumps(document))
        edited["tables"]["loan_data"]["rows"][0][backup_codec.columns("loan_data").index("principle_amount")] = "1.00"
        sources = {
            "damaged gzip": {"packed": base64.b64encode(packed[:-12] + b"x" * 12).decode()},
            "cut short": {"packed": base64.b64encode(packed[: len(packed) // 2]).decode()},
            "edited amount": {"document": edited},
            "edited gzip": {"packed": self.packed(edited)},
        }
        before = self.state_dump()
        for name, source in sources.items():
            calls = {
                "check": lambda: backup_service.check(self.repos, self.hq, **source),
                "restore": lambda: backup_service.restore(self.repos, self.root, confirmation="RESTORE", now=NOW,
                                                          **source),
            }
            for step, call in calls.items():
                with self.subTest(name, step=step), self.assertRaises(Invalid) as caught:
                    run(call())
                self.assertEqual(caught.exception.code, "invalid_backup")
        self.assertEqual(self.state_dump(), before, "nothing changes when a file is refused")

    def test_old_v2_files_still_check_and_restore(self):
        document = run(backup_service.export_document(self.repos, NOW))
        legacy = json.dumps({"format_version": 2, "created_at": document["created_at"], "tables": document["tables"]},
                            separators=(",", ":")).encode()
        for source in ({"packed": base64.b64encode(gzip.compress(legacy, compresslevel=6)).decode()},
                       {"document": json.loads(legacy)}):
            with self.subTest(list(source)):
                report = run(backup_service.check(self.repos, self.hq, **source))
                self.assertEqual((report["format_version"], report["checksum"], report["restorable"]),
                                 (2, "absent", True))
                result = run(backup_service.restore(self.repos, self.root, confirmation="RESTORE", now=NOW, **source))
                self.assertEqual((result["customers"], result["loans"], result["entries"]), (1, 1, 1))
                self.assertEqual(run(backup_service.export_document(self.repos, NOW))["tables"], document["tables"])


class Check(BackupFixture):
    def test_check_reports_without_changing_anything(self):
        document = run(backup_service.export_document(self.repos, NOW, created_by="Admin", kind="manual"))
        before = json.dumps(self.repos.state.__dict__, default=str, sort_keys=True)
        for who in (self.hq, self.root):
            for source in ({"packed": self.packed(document)}, {"document": document}):
                with self.subTest(who=who.username, source=list(source)):
                    report = run(backup_service.check(self.repos, who, **source))
                    self.assertEqual(report["counts"], {"branches": 3, "customers": 1, "loans": 1, "entries": 1,
                                                        "settings": 1})
                    self.assertEqual(report["checksum"], "verified")
                    self.assertEqual((report["created_by"], report["kind"]), ("Admin", "manual"))
                    self.assertEqual(report["branch_prefixes"], ["SAN"],
                                     "only branches with business data; counters (AD is the head office) are not listed")
                    self.assertNotIn("required_branches", report)
                    self.assertEqual((report["missing_branches"], report["restorable"], report["warnings"]),
                                     ([], True, []))
        self.assertEqual(json.dumps(self.repos.state.__dict__, default=str, sort_keys=True), before)
        self.assertEqual(self.audit_actions(), [], "a check is not audited")
        with self.assertRaises(Forbidden):
            run(backup_service.check(self.repos, self.san, document=document))

    def test_missing_branches_make_a_file_not_restorable(self):
        rows = run(self.repos.backups.export_rows())
        rows["customers"][0] = dict(rows["customers"][0], branch_prefix="XYZ")
        report = run(backup_service.check(self.repos, self.hq, document=backup_codec.encode(rows, NOW)))
        self.assertEqual((report["missing_branches"], report["restorable"]), (["XYZ"], False))

    def test_a_cash_day_for_a_missing_branch_is_refused_before_anything_changes(self):
        run(cash_service.start_day(self.repos, self.san, branch=None, opening_counted="500", request_id="cash-x",
                                   now=NOW))
        rows = run(self.repos.backups.export_rows())
        rows["cash_days"][0] = dict(rows["cash_days"][0], branch_prefix="XYZ")
        document = backup_codec.encode(rows, NOW)
        report = run(backup_service.check(self.repos, self.hq, document=document))
        self.assertEqual(report["branch_prefixes"], ["SAN", "XYZ"])
        self.assertEqual((report["missing_branches"], report["restorable"]), (["XYZ"], False))
        before = json.dumps(self.repos.state.__dict__, default=str, sort_keys=True)
        with self.assertRaises(Invalid) as caught:
            run(backup_service.restore(self.repos, self.root, document=document, confirmation="RESTORE", now=NOW))
        self.assertEqual(caught.exception.code, "unknown_branches")
        self.assertEqual(json.dumps(self.repos.state.__dict__, default=str, sort_keys=True), before)

    def test_a_branch_counter_for_a_missing_branch_is_refused_before_anything_changes(self):
        rows = run(self.repos.backups.export_rows())
        rows["branch_counters"].append({"branch_prefix": "ZZZ", "next_customer_no": 1})  # a branch deleted since
        document = backup_codec.encode(rows, NOW)
        report = run(backup_service.check(self.repos, self.hq, document=document))
        self.assertEqual(report["branch_prefixes"], ["SAN"], "a counter alone does not list the branch")
        self.assertEqual((report["missing_branches"], report["restorable"]), (["ZZZ"], False))
        before = json.dumps(self.repos.state.__dict__, default=str, sort_keys=True)
        with self.assertRaises(Invalid) as caught:
            run(backup_service.restore(self.repos, self.root, document=document, confirmation="RESTORE", now=NOW))
        self.assertEqual(caught.exception.code, "unknown_branches")
        self.assertEqual(json.dumps(self.repos.state.__dict__, default=str, sort_keys=True), before)

    def test_bad_sources_are_plain_errors(self):
        document = run(backup_service.export_document(self.repos, NOW))
        opens = lambda *args, **kwargs: b"{}"  # noqa: E731 - a stand-in for app.infra.aeszip.read_backup_zip
        cases = {
            "none": ({}, "invalid_restore"),
            "two": ({"document": document, "packed": self.packed(document)}, "invalid_restore"),
            "gzip and zip": ({"packed": self.packed(document), "zipped": "UEsDBA==", "zip_password": "x" * 12},
                             "invalid_restore"),
            "password without a zip": ({"packed": self.packed(document), "zip_password": "x" * 12}, "invalid_restore"),
            "zip without a password": ({"zipped": "UEsDBA==", "unzip": opens}, "zip_password"),
            "zip without the unzip helper": ({"zipped": "UEsDBA==", "zip_password": "x" * 12}, "invalid_backup"),
            "zip not base64": ({"zipped": "%%%", "zip_password": "x" * 12, "unzip": opens}, "invalid_backup"),
            "not base64": ({"packed": "%%%"}, "invalid_backup"),
            "not a backup": ({"packed": base64.b64encode(gzip.compress(b"[1,2]")).decode()}, "invalid_backup"),
            "tampered": ({"document": dict(document, created_by="x")}, "invalid_backup"),
        }
        for name, (source, code) in cases.items():
            with self.subTest(name):
                with self.assertRaises(Invalid) as caught:
                    run(backup_service.check(self.repos, self.hq, **source))
                self.assertEqual(caught.exception.code, code)


class Restore(BackupFixture):
    def test_restore_from_a_gzip_upload_round_trips(self):
        document = run(backup_service.export_document(self.repos, NOW, created_by="Admin", kind="manual"))
        exported = document["tables"]
        s = self.repos.state
        s.customers[2] = dict(s.customers[1], customerid=2, phone="9000000001", user_id="SAN2")
        s.loans["SAN1L1"]["refreshprincipleamount"] = D("1.00")
        s.settings["backup_email"] = {"value": {"recipient": "keep@example.in", "enabled": True},
                                      "updated_at": NOW, "updated_by": "root"}
        with self.assertRaises(Forbidden):
            run(backup_service.restore(self.repos, self.hq, packed=self.packed(document), confirmation="RESTORE",
                                       now=NOW))
        result = run(backup_service.restore(self.repos, self.root, packed=self.packed(document), confirmation="RESTORE",
                                            now=NOW, context={"ip": "1.1.1.1", "request_id": "r1"}))
        self.assertEqual((result["customers"], result["loans"], result["entries"]), (1, 1, 1))
        restored = run(backup_service.export_document(self.repos, NOW))["tables"]
        self.assertEqual(restored, exported)
        self.assertEqual(s.settings["backup_email"]["value"]["recipient"], "keep@example.in",
                         "this server's email settings survive a restore")
        self.assertEqual(self.audit_actions(), ["RESTORE_BACKUP"])
        self.assertEqual((s.audit[0]["entity_id"], s.audit[0]["ip"], s.audit[0]["request_id"]), ("upload", "1.1.1.1", "r1"))

    def test_restore_keeps_no_copy_of_the_old_data(self):
        document = run(backup_service.export_document(self.repos, NOW, created_by="Admin", kind="manual"))
        s = self.repos.state
        s.customers[2] = dict(s.customers[1], customerid=2, customername="Later Customer", phone="9000000001",
                              user_id="SAN2")
        result = run(backup_service.restore(self.repos, self.root, packed=self.packed(document), confirmation="RESTORE",
                                            now=NOW))
        self.assertEqual(result, {"customers": 1, "loans": 1, "entries": 1, "taken_at": document["created_at"]})
        self.assertNotIn(2, s.customers)
        self.assertNotIn("Later Customer", self.state_dump(), "no copy of the replaced data is kept anywhere")
        self.assertEqual(self.audit_actions(), ["RESTORE_BACKUP"], "a restore writes only the data and its audit line")
        self.assertIn(f"from a backup taken {document['created_at']}", s.audit[0]["details"])
        self.assertFalse(hasattr(s, "snapshots"))

    def test_restore_still_checks_branches_logos_and_confirmation(self):
        rows = run(self.repos.backups.export_rows())
        rows["customers"][0] = dict(rows["customers"][0], branch_prefix="XYZ")
        before = self.state_dump()
        with self.assertRaises(Invalid) as caught:
            run(backup_service.restore(self.repos, self.root, document=backup_codec.encode(rows, NOW),
                                       confirmation="RESTORE", now=NOW))
        self.assertEqual(caught.exception.code, "unknown_branches")
        self.assertEqual(self.state_dump(), before, "nothing is written when a restore is refused")
        rows = run(self.repos.backups.export_rows())
        rows["branches"] = [dict(b, logo="data:image/png;base64,bm90IGEgcG5n") for b in rows["branches"]]
        run(backup_service.restore(self.repos, self.root, document=backup_codec.encode(rows, NOW),
                                   confirmation="RESTORE", now=NOW))
        self.assertIsNone(self.repos.state.users["User1"]["logo"], "a logo that is not an image is dropped")
        with self.assertRaises(Invalid) as caught:
            run(backup_service.restore(self.repos, self.root, packed=self.packed({}), confirmation="restore", now=NOW))
        self.assertEqual(caught.exception.code, "confirmation_required")

    def test_duplicate_keys_in_a_file_are_a_plain_error(self):
        rows = run(self.repos.backups.export_rows())
        rows["customers"].append(dict(rows["customers"][0], customerid=2, user_id="SAN2"))
        with self.assertRaises(Invalid) as caught:
            run(backup_service.restore(self.repos, self.root, document=backup_codec.encode(rows, NOW),
                                       confirmation="RESTORE", now=NOW))
        self.assertEqual(caught.exception.code, "invalid_backup")
        self.assertIn("9876543210", caught.exception.message)

    def test_restore_round_trips_the_cash_ledger(self):
        day = run(cash_service.start_day(self.repos, self.san, branch=None, opening_counted="1000",
                                         request_id="cash-start-1", now=NOW))["today_day"]
        run(cash_service.add_entry(self.repos, self.san, day["id"], direction="out", category="other",
                                   description="Tea", reference=None, amount="45.50", request_id="cash-entry-1",
                                   now=NOW))
        run(cash_service.close_day(self.repos, self.san, day["id"], closing_counted="954.50",
                                   expected_total="954.50", now=NOW))
        document = run(backup_service.export_document(self.repos, NOW, created_by="Admin", kind="manual"))
        self.assertEqual((document["manifest"]["tables"]["cash_days"]["rows"],
                          document["manifest"]["tables"]["cash_entries"]["rows"]), (1, 1))
        later = NOW + timedelta(days=1)
        run(cash_service.start_day(self.repos, self.san, branch=None, opening_counted="954.50",
                                   request_id="cash-start-2", now=later))
        run(backup_service.restore(self.repos, self.root, packed=self.packed(document), confirmation="RESTORE",
                                   now=later))
        self.assertEqual(run(backup_service.export_document(self.repos, NOW))["tables"], document["tables"])
        self.assertEqual(sorted(self.repos.state.cash_days), [day["id"]], "the later day is replaced by the backup")
        self.assertEqual(self.repos.state.next_ids["cash_day"], day["id"] + 1)
        view = run(cash_service.overview(self.repos, self.san, None, later))
        self.assertEqual(view["carry_forward"], {"amount": "954.50", "from_day": "2025-03-10"})


@unittest.skipIf(pyzipper is None, "pyzipper is not installed")
class ZipImport(BackupFixture):
    """Import backup with the emailed ZIP itself, opened by app.infra.aeszip in memory (no network)."""

    def emailed_zip(self):
        from app.infra import aeszip
        raw, _ = run(backup_service.backup_bytes(self.repos, NOW, created_by="system", kind="scheduled"))
        blob = aeszip.encrypt_zip([(f"backup_{backup_codec.file_stamp(NOW)}.json", raw),
                                   ("README.txt", backup_email_service.README.encode())],
                                  ZIP_PASSWORD, modified=datetime(2025, 3, 10, 11, 30))
        return base64.b64encode(blob).decode("ascii"), raw

    @staticmethod
    def source(zipped, password=ZIP_PASSWORD):
        from app.infra import aeszip
        return {"zipped": zipped, "zip_password": password, "unzip": aeszip.read_backup_zip}

    def test_the_emailed_zip_checks_and_restores_with_its_password(self):
        zipped, raw = self.emailed_zip()
        exported = backup_codec.loads(raw)["tables"]
        for who in (self.hq, self.root):
            with self.subTest(who.username):
                report = run(backup_service.check(self.repos, who, **self.source(zipped)))
                self.assertEqual(report["counts"], {"branches": 3, "customers": 1, "loans": 1, "entries": 1,
                                                    "settings": 1})
                self.assertEqual((report["checksum"], report["kind"], report["restorable"]),
                                 ("verified", "scheduled", True))
                self.assertEqual(report["created_at"], NOW.isoformat())
        self.repos.state.customers[2] = dict(self.repos.state.customers[1], customerid=2, phone="9000000001",
                                             user_id="SAN2")
        result = run(backup_service.restore(self.repos, self.root, confirmation="RESTORE", now=NOW,
                                            context={"ip": "1.1.1.1", "request_id": "r1"}, **self.source(zipped)))
        self.assertEqual((result["customers"], result["loans"], result["entries"]), (1, 1, 1))
        self.assertEqual(run(backup_service.export_document(self.repos, NOW))["tables"], exported)
        (audit,) = self.repos.state.audit
        self.assertEqual((audit["action"], audit["entity_id"]), ("RESTORE_BACKUP", "zip"))
        self.assertNotIn(ZIP_PASSWORD, self.state_dump(), "the ZIP password is never stored or audited")

    def test_zip_password_and_access_are_checked_before_anything_changes(self):
        zipped, _ = self.emailed_zip()
        before = self.state_dump()
        for password in ("Wrong-password-123", ZIP_PASSWORD + " "):
            with self.subTest(password), self.assertRaises(Invalid) as caught:
                run(backup_service.check(self.repos, self.hq, **self.source(zipped, password)))
            self.assertEqual((caught.exception.code, caught.exception.message, caught.exception.details),
                             ("zip_password", "The ZIP password is wrong.", {"field": "zip_password"}))
        with self.assertRaises(Invalid) as caught:
            run(backup_service.restore(self.repos, self.root, confirmation="RESTORE", now=NOW,
                                       **self.source(zipped, "Wrong-password-123")))
        self.assertEqual(caught.exception.code, "zip_password")

        opened = []

        def spy(*args, **kwargs):
            opened.append(args)
            return b"{}"

        source = {"zipped": zipped, "zip_password": ZIP_PASSWORD, "unzip": spy}
        refused = {
            "branch user checks": (lambda: backup_service.check(self.repos, self.san, **source), Forbidden),
            "head office restores": (lambda: backup_service.restore(self.repos, self.hq, confirmation="RESTORE",
                                                                    now=NOW, **source), Forbidden),
            "no RESTORE": (lambda: backup_service.restore(self.repos, self.root, confirmation="restore", now=NOW,
                                                          **source), Invalid),
        }
        for name, (call, error) in refused.items():
            with self.subTest(name), self.assertRaises(error):
                run(call())
        self.assertEqual(opened, [], "the ZIP is not opened before access and RESTORE are checked")
        self.assertEqual(self.state_dump(), before)


class Routes(unittest.TestCase):
    """Only Import backup and the email remain under /backup; the router hands ZIPs to app.infra."""

    def test_backup_routes_and_request_bodies(self):
        from pydantic import ValidationError

        from app.infra import aeszip
        from app.routers import admin as admin_router
        from app.schemas import BackupSourceIn

        routes = sorted((route.path, sorted(route.methods)) for route in admin_router.router.routes
                        if route.path.startswith("/backup"))
        self.assertEqual(routes, [("/backup/check", ["POST"]), ("/backup/email", ["GET"]), ("/backup/email", ["PUT"]),
                                  ("/backup/email/send", ["POST"]), ("/backup/restore", ["POST"])])
        body = BackupSourceIn(backup_zip="UEsDBA==", zip_password=ZIP_PASSWORD)
        self.assertEqual(admin_router._source(body), {"document": None, "packed": None, "zipped": "UEsDBA==",
                                                      "zip_password": ZIP_PASSWORD, "unzip": aeszip.read_backup_zip})
        for bad in ({"snapshot_id": 1}, {"backup_zip": "UEsDBA==", "zip_password": "x" * 11},
                    {"backup_zip": "UEsDBA==", "zip_password": "x" * 129}, {"backup_zip": "x" * 4_700_001}):
            with self.subTest(sorted(bad)), self.assertRaises(ValidationError):
                BackupSourceIn(**bad)
        self.assertEqual(BackupSourceIn(backup_zip="UEsDBA==", zip_password="x" * 128).zip_password, "x" * 128)


class DailyJob(unittest.TestCase):
    def setUp(self):
        self.repos = with_backups(standard_repos())
        self.repos.state.settings["backup_email"] = {"value": {"recipient": "backups@example.in", "enabled": True},
                                                     "updated_at": NOW, "updated_by": "root"}

    def test_daily_job_emails_a_v3_zip_and_stores_nothing(self):
        mailer = FakeMailer()
        result = run(maintenance_service.run_daily(self.repos, NOW, mailer))
        self.assertEqual(result["backup_email"], "sent")
        self.assertNotIn("snapshot_id", result)
        (entries,) = mailer.zipped
        self.assertEqual([name for name, _ in entries], ["backup_2025-03-10_1130IST.json", "README.txt"])
        raw = entries[0][1]
        document = backup_codec.loads(raw)
        self.assertEqual((document["format_version"], document["kind"], document["created_by"]),
                         (3, "scheduled", "system"))
        self.assertEqual(backup_codec.inspect(document)["checksum"], "verified")
        status = self.repos.state.settings[backup_email_service.STATUS_KEY]["value"]["nightly"]
        self.assertEqual(status["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(mailer.sent[0]["attachment"][0], "backup_2025-03-10_1130IST.zip")
        self.assertFalse(hasattr(self.repos.state, "snapshots"))
        self.assertEqual([name for name in dir(self.repos.backups) if "snapshot" in name], [])
        self.assertEqual(sorted(self.repos.state.settings), ["backup_email", "backup_email_status"],
                         "only the email status is written; no backup is kept")

    def test_daily_job_survives_mail_failure_and_missing_setup(self):
        with self.assertLogs("goldloan", "ERROR"):
            result = run(maintenance_service.run_daily(self.repos, NOW, FakeMailer(fail=MailFailure())))
        self.assertEqual(result["backup_email"], "failed")
        self.assertNotIn("snapshot_id", result)
        broken = FakeMailer()
        broken.encrypt_zip = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        with self.assertLogs("goldloan", "ERROR"):
            self.assertEqual(run(maintenance_service.run_daily(self.repos, NOW, broken))["backup_email"], "failed")
        result = run(maintenance_service.run_daily(self.repos, NOW, None, mail_missing=("SMTP_HOST",)))
        self.assertEqual(result["backup_email"], "skipped_not_configured")
        self.assertEqual(set(result), {"loans_checked", "compoundings", "failed", "cash_days_closed",
                                       "cash_days_purged", "backup_email"})

    def test_daily_job_closes_and_purges_the_cash_ledger_and_survives_its_failure(self):
        san = actor_from(self.repos.state.users["User1"])
        run(cash_service.start_day(self.repos, san, branch=None, opening_counted="500", request_id="cash-start-1",
                                   now=NOW - timedelta(days=20)))
        run(cash_service.start_day(self.repos, san, branch=None, opening_counted="500", request_id="cash-start-2",
                                   now=NOW - timedelta(days=1)))
        mailer = FakeMailer()
        result = run(maintenance_service.run_daily(self.repos, NOW, mailer))
        self.assertEqual((result["cash_days_closed"], result["cash_days_purged"]), (1, 1))
        kept = list(self.repos.state.cash_days.values())
        self.assertEqual([(d["closed_automatically"], d["closing_counted"]) for d in kept], [(True, D("500.00"))])
        emailed = backup_codec.loads(mailer.zipped[0][0][1])
        self.assertEqual(emailed["manifest"]["tables"]["cash_days"]["rows"], 1, "the backup is built after the cash step")

        async def broken(*args, **kwargs):
            raise RuntimeError("cash ledger unavailable")

        self.repos.cash.open_days_before = broken
        with self.assertLogs("goldloan", "ERROR"):
            result = run(maintenance_service.run_daily(self.repos, NOW, None))
        self.assertEqual((result["cash_days_closed"], result["cash_days_purged"]), (None, None))
        self.assertEqual(result["backup_email"], "skipped_not_configured", "the rest of the job still runs")


if __name__ == "__main__":
    unittest.main()

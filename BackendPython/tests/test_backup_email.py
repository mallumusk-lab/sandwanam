"""The backup email (nightly and "Email backup now") and its settings, with a recording mailer
(no network). Each email carries a backup built in memory; nothing is stored."""
import asyncio
import unittest
from datetime import timedelta

from app.domain import backup_codec
from app.errors import Forbidden, Invalid, ServiceUnavailable, TooManyRequests
from app.services import backup_email_service as email
from app.services.auth_service import actor_from
from tests.backup_fakes import FakeMailer, MailFailure, with_backups
from tests.fakes import standard_repos, utc

NIGHT = utc(2025, 10, 19, 18, 31)  # 00:01 IST on 20 October 2025
MISSING = ("SMTP_HOST", "BACKUP_ZIP_PASSWORD (12 to 128 characters)")


def run(coro):
    return asyncio.run(coro)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.repos = with_backups(standard_repos())
        users = self.repos.state.users
        self.hq, self.san, self.root = (actor_from(users[name]) for name in ("Admin", "User1", "root"))

    def configure(self, recipient="backups@example.in", enabled=True):
        return run(email.set_email_settings(self.repos, self.root, recipient=recipient, enabled=enabled, missing=()))

    def nightly(self, mailer, now=NIGHT, **kwargs):
        return run(email.send_nightly(self.repos, mailer, now=now, **kwargs))

    def send_now(self, who, mailer, now, missing=()):
        return run(email.send_now(self.repos, who, mailer, missing=missing, now=now))

    def status(self):
        return run(email.email_settings(self.repos, self.hq, missing=()))["status"]

    def audits(self, action):
        return [a for a in self.repos.state.audit if a["action"] == action]


class Settings(Fixture):
    def test_superadmin_sets_the_address_and_head_office_reads_it(self):
        view = self.configure("  backups@example.in ")
        self.assertEqual(view, {"configured": True, "missing": [], "recipient": "backups@example.in", "enabled": True,
                                "status": {"nightly": None, "manual": None}})
        self.assertEqual(self.audits("SET_BACKUP_EMAIL")[0]["username"], "root")
        read = run(email.email_settings(self.repos, self.hq, missing=MISSING))
        self.assertEqual((read["configured"], read["missing"], read["recipient"]), (False, list(MISSING),
                                                                                   "backups@example.in"))
        with self.assertRaises(Forbidden):
            run(email.email_settings(self.repos, self.san, missing=()))
        with self.assertRaises(Forbidden):
            run(email.set_email_settings(self.repos, self.hq, recipient="x@y.co", enabled=True, missing=()))
        off = self.configure(None, enabled=False)
        self.assertEqual((off["recipient"], off["enabled"]), (None, False))

    def test_invalid_addresses_are_refused(self):
        for bad in ("a,b@x.co", "a@x.co b@y.co", "Name <a@x.co>", '"a"@x.co', "a@x", "not an address"):
            with self.subTest(bad), self.assertRaises(Invalid) as caught:
                self.configure(bad)
            self.assertEqual(caught.exception.code, "invalid_email")
        with self.assertRaises(Invalid) as caught:
            self.configure("", enabled=True)
        self.assertEqual(caught.exception.code, "email_no_recipient")
        self.assertEqual(self.repos.state.settings, {})

    def test_settings_never_travel_in_backups(self):
        self.configure()
        mailer = FakeMailer()
        self.nightly(mailer)
        self.send_now(self.hq, mailer, NIGHT + timedelta(hours=9))
        for entries in mailer.zipped:
            keys = [row[0] for row in backup_codec.loads(entries[0][1])["tables"]["app_settings"]["rows"]]
            self.assertNotIn(email.SETTINGS_KEY, keys)
            self.assertNotIn(email.STATUS_KEY, keys)
        rows = run(self.repos.backups.export_rows())
        keys = [row[0] for row in backup_codec.encode(rows, NIGHT)["tables"]["app_settings"]["rows"]]
        self.assertNotIn(email.SETTINGS_KEY, keys)
        self.assertNotIn(email.STATUS_KEY, keys)

    def test_an_older_test_status_is_ignored_and_dropped(self):
        self.configure()
        recent = (NIGHT + timedelta(hours=9)).isoformat()
        self.repos.state.settings[email.STATUS_KEY] = {
            "value": {"nightly": None, "test": {"at": recent, "ok": True, "result": "sent", "message": "Test email sent."}},
            "updated_at": NIGHT, "updated_by": "system"}
        self.assertEqual(self.status(), {"nightly": None, "manual": None})
        view = self.send_now(self.hq, FakeMailer(), NIGHT + timedelta(hours=9, minutes=1))
        self.assertEqual(view["status"]["manual"]["result"], "sent", "an old test send does not rate-limit")
        self.assertEqual(sorted(self.repos.state.settings[email.STATUS_KEY]["value"]), ["manual", "nightly"])


class Nightly(Fixture):
    def test_sent(self):
        self.configure()
        mailer = FakeMailer()
        self.assertEqual(self.nightly(mailer), "sent")
        (sent,) = mailer.sent
        self.assertEqual(sent["to"], "backups@example.in")
        self.assertEqual(sent["subject"], "Gold Loan Desk nightly backup · taken 20 Oct 2025, 00:01 IST")
        name, archive = sent["attachment"]
        self.assertEqual(name, "backup_2025-10-20_0001IST.zip")
        (entries,) = mailer.zipped
        self.assertEqual(entries[0][0], "backup_2025-10-20_0001IST.json")
        document = backup_codec.loads(entries[0][1])
        self.assertEqual((document["format_version"], document["kind"], document["created_by"]),
                         (3, "scheduled", "system"))
        self.assertEqual(entries[0][1], backup_codec.canonical(document))
        self.assertEqual(entries[1][0], "README.txt")
        readme = entries[1][1].decode()
        for words in ("7-Zip", "RESTORE", "Import backup", "ZIP password", "keep your own copy"):
            self.assertIn(words, readme)
        self.assertNotIn("snapshot", readme)
        status = self.status()["nightly"]
        self.assertEqual((status["result"], status["ok"], status["size_bytes"]), ("sent", True, len(archive)))
        self.assertEqual(status["at"], NIGHT.isoformat())
        (audit,) = self.audits("EMAIL_BACKUP")
        self.assertEqual((audit["username"], audit["entity_id"]), ("system", "backup_2025-10-20_0001IST"))
        self.assertIn(status["sha256"], audit["details"])

    def test_password_is_never_in_the_email(self):
        self.configure()
        mailer = FakeMailer()
        self.nightly(mailer)
        text = mailer.sent[0]["text"] + mailer.zipped[0][1][1].decode()
        self.assertNotIn("zip-secret", text)
        self.assertIn("password", text.lower())

    def test_failed_send_is_recorded_and_never_raises(self):
        self.configure()
        with self.assertLogs("goldloan", "INFO") as logged:
            self.assertEqual(self.nightly(FakeMailer(fail=MailFailure("The mail server could not be reached."))),
                             "failed")
            self.assertEqual(self.nightly(FakeMailer(fail=RuntimeError("secret detail"))), "failed")
        fields = repr([getattr(record, "fields", {}) for record in logged.records])
        self.assertNotIn("backups@example.in", fields, "logs never carry the address")
        self.assertNotIn("secret detail", fields)
        status = self.status()["nightly"]
        self.assertEqual(status["ok"], False)
        self.assertEqual(self.status()["nightly"]["message"], "The email could not be sent.")
        self.assertEqual(len(self.audits("EMAIL_BACKUP")), 2)

    def test_too_large_sends_a_notice_without_the_file(self):
        self.configure()
        mailer = FakeMailer(zip_size=email.MAX_ATTACHMENT_BYTES + 1)
        self.assertEqual(self.nightly(mailer), "too_large")
        (sent,) = mailer.sent
        self.assertIsNone(sent["attachment"])
        self.assertIn("Nothing is stored in the app", sent["text"])
        self.assertNotIn("snapshot", sent["text"])
        self.assertEqual(self.status()["nightly"]["result"], "too_large")
        self.assertEqual(email.MAX_ATTACHMENT_BYTES, 15 * 1024 * 1024)

    def test_skipped_when_off_or_not_set_up(self):
        mailer = FakeMailer()
        self.assertEqual(self.nightly(mailer), "skipped_disabled")
        self.configure(enabled=False)
        self.assertEqual(self.nightly(mailer), "skipped_disabled")
        self.configure()
        self.assertEqual(self.nightly(None, missing=MISSING), "skipped_not_configured")
        self.assertIn("SMTP_HOST", self.status()["nightly"]["message"])
        self.assertEqual((mailer.sent, mailer.zipped), ([], []), "no backup is even built when it is not sent")

    def test_already_sent_today(self):
        self.configure()
        mailer = FakeMailer()
        self.assertEqual(self.nightly(mailer), "sent")
        self.assertEqual(self.nightly(mailer, now=NIGHT + timedelta(hours=5)), "already_sent_today")
        self.assertEqual(len(mailer.sent), 1)
        self.assertEqual(self.status()["nightly"]["at"], NIGHT.isoformat(), "the sent result is kept")
        self.assertEqual(self.nightly(mailer, now=NIGHT + timedelta(days=1)), "sent")

    def test_status_store_failure_still_returns_the_result(self):
        self.configure()

        async def broken(*args, **kwargs):
            raise RuntimeError("database gone")

        self.repos.settings.put = broken
        with self.assertLogs("goldloan", "ERROR"):
            self.assertEqual(self.nightly(FakeMailer()), "sent")


class SendNow(Fixture):
    def test_head_office_emails_a_backup_now_and_keeps_the_nightly_status(self):
        self.configure()
        self.nightly(FakeMailer())
        nightly = self.status()["nightly"]
        morning = NIGHT + timedelta(hours=9)  # 09:01 IST
        for who, at in ((self.hq, morning), (self.root, morning + timedelta(minutes=10))):
            with self.subTest(who.username):
                mailer = FakeMailer()
                view = self.send_now(who, mailer, at)
                self.assertEqual(view["status"]["nightly"], nightly, "a manual send never overwrites last night's result")
                manual = view["status"]["manual"]
                self.assertEqual((manual["result"], manual["ok"], manual["by"], manual["at"]),
                                 ("sent", True, who.username, at.isoformat()))
                (sent,) = mailer.sent
                stamp = backup_codec.file_stamp(at)
                self.assertEqual(sent["attachment"][0], f"backup_{stamp}.zip")
                self.assertEqual(sent["subject"], f"Gold Loan Desk backup · taken {email.taken_label(at)} IST")
                (entries,) = mailer.zipped
                self.assertEqual([name for name, _ in entries], [f"backup_{stamp}.json", "README.txt"])
                document = backup_codec.loads(entries[0][1])
                self.assertEqual((document["format_version"], document["kind"], document["created_by"]),
                                 (3, "manual", who.username))
        self.assertEqual([a["username"] for a in self.audits("EMAIL_BACKUP_NOW")], ["Admin", "root"])
        with self.assertRaises(Forbidden):
            self.send_now(self.san, FakeMailer(), morning + timedelta(hours=1))

    def test_rate_limit_and_failures(self):
        self.configure()
        first = NIGHT + timedelta(hours=9)
        with self.assertLogs("goldloan", "WARNING"):
            view = self.send_now(self.root, FakeMailer(fail=MailFailure("Refused.")), first)
        self.assertEqual((view["status"]["manual"]["ok"], view["status"]["manual"]["message"]), (False, "Refused."))
        self.assertIn("failed", self.audits("EMAIL_BACKUP_NOW")[0]["details"])
        for who in (self.root, self.hq):
            with self.subTest(who.username), self.assertRaises(TooManyRequests) as caught:
                self.send_now(who, FakeMailer(), first + timedelta(minutes=9))
            self.assertEqual(caught.exception.code, "email_backup_too_soon")
        self.assertEqual(email.SEND_NOW_INTERVAL, timedelta(minutes=10))
        view = self.send_now(self.hq, FakeMailer(), first + timedelta(minutes=10))
        self.assertEqual(view["status"]["manual"]["result"], "sent")

    def test_not_configured_or_no_address(self):
        for who in (self.root, self.hq):
            with self.subTest(who.username):
                with self.assertRaises(ServiceUnavailable) as caught:
                    self.send_now(who, None, NIGHT, missing=MISSING)
                self.assertEqual(caught.exception.code, "email_not_configured")
                self.assertIn("SMTP_HOST", caught.exception.message)
                with self.assertRaises(Invalid) as caught:
                    self.send_now(who, FakeMailer(), NIGHT)
                self.assertEqual(caught.exception.code, "email_no_recipient")
        self.assertEqual(self.audits("EMAIL_BACKUP_NOW"), [])


if __name__ == "__main__":
    unittest.main()

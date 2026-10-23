import asyncio
import unittest

from app.config import ConfigError, load_settings
from app.middleware import ApiPrefixMiddleware, OriginGuardMiddleware, RequestContextMiddleware


def http_scope(method="GET", path="/", headers=()):
    return {"type": "http", "method": method, "path": path, "raw_path": path.encode(),
            "headers": [(k.encode(), v.encode()) for k, v in headers]}


async def call(app, scope, body=b""):
    sent = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    return sent


class Echo:
    def __init__(self):
        self.scope = None

    async def __call__(self, scope, receive, send):
        self.scope = scope
        await receive()
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": b"{}"})


def headers_of(messages):
    return {k.decode(): v.decode() for k, v in messages[0]["headers"]}


class ApiPrefix(unittest.TestCase):
    def test_strips_only_the_api_segment(self):
        echo = Echo()
        for path, expected in (("/api/loans/X", "/loans/X"), ("/api", "/"), ("/apiary", "/apiary"), ("/health", "/health")):
            with self.subTest(path):
                asyncio.run(call(ApiPrefixMiddleware(echo), http_scope(path=path)))
                self.assertEqual(echo.scope["path"], expected)


class RequestContext(unittest.TestCase):
    def test_adds_request_id_and_security_headers(self):
        sent = asyncio.run(call(RequestContextMiddleware(Echo()), http_scope()))
        headers = headers_of(sent)
        self.assertEqual(headers["x-content-type-options"], "nosniff")
        self.assertEqual(headers["x-frame-options"], "DENY")
        self.assertEqual(headers["cache-control"], "no-store")
        self.assertEqual(len(headers["x-request-id"]), 32)

    def test_keeps_a_safe_incoming_request_id_only(self):
        sent = asyncio.run(call(RequestContextMiddleware(Echo()), http_scope(headers=[("x-request-id", "abc-123")])))
        self.assertEqual(headers_of(sent)["x-request-id"], "abc-123")
        sent = asyncio.run(call(RequestContextMiddleware(Echo()), http_scope(headers=[("x-request-id", "<script>")])))
        self.assertNotEqual(headers_of(sent)["x-request-id"], "<script>")

    def test_rejects_oversized_bodies(self):
        app = RequestContextMiddleware(Echo(), max_body=10)
        sent = asyncio.run(call(app, http_scope("POST", headers=[("content-length", "11")])))
        self.assertEqual(sent[0]["status"], 413)


class OriginGuard(unittest.TestCase):
    def status(self, method, headers, trusted=()):
        sent = asyncio.run(call(OriginGuardMiddleware(Echo(), trusted), http_scope(method, headers=headers)))
        return sent[0]["status"]

    def test_same_origin_and_trusted_origins_pass(self):
        self.assertEqual(self.status("POST", [("origin", "https://app.example.in"), ("host", "app.example.in")]), 200)
        self.assertEqual(self.status("POST", [("origin", "https://x.vercel.app"), ("host", "internal"),
                                              ("x-forwarded-host", "x.vercel.app")]), 200)
        self.assertEqual(self.status("POST", [("origin", "http://localhost:5173"), ("host", "localhost:8000")],
                                     ["http://localhost:5173"]), 200)

    def test_cross_site_writes_are_blocked_but_reads_are_not(self):
        hostile = [("origin", "https://evil.example"), ("host", "app.example.in")]
        self.assertEqual(self.status("POST", hostile), 403)
        self.assertEqual(self.status("DELETE", hostile), 403)
        self.assertEqual(self.status("GET", hostile), 200)


class Config(unittest.TestCase):
    SECRET = "s" * 40

    def test_development_defaults(self):
        settings = load_settings({})
        self.assertEqual(settings.environment, "development")
        self.assertEqual(settings.cookie_name, "__Host-sid")
        self.assertIn("http://localhost:5173", settings.trusted_origins)
        self.assertFalse(settings.docs_enabled)

    def test_production_requires_secrets(self):
        with self.assertRaises(ConfigError):
            load_settings({"VERCEL_ENV": "production"})
        with self.assertRaises(ConfigError):
            load_settings({"VERCEL_ENV": "production", "DATABASE_URL": "postgres://x", "CRON_SECRET": "short"})
        with self.assertRaises(ConfigError):
            load_settings({"VERCEL_ENV": "production", "DATABASE_URL": "postgres://x", "CRON_SECRET": self.SECRET,
                           "COOKIE_SECURE": "false"})
        settings = load_settings({"VERCEL_ENV": "production", "DATABASE_URL": "postgres://u@h/db",
                                  "CRON_SECRET": self.SECRET, "DOCS_ENABLED": "true"})
        self.assertTrue(settings.is_production)
        self.assertTrue(settings.database_url.startswith("postgresql://"))
        self.assertFalse(settings.docs_enabled, "API docs are never served in production")
        self.assertNotIn("http://localhost:5173", settings.trusted_origins)

    def test_plain_http_development_cookie(self):
        self.assertEqual(load_settings({"COOKIE_SECURE": "false"}).cookie_name, "sid")

    def test_mail_settings_are_optional_and_never_fatal(self):
        bare = load_settings({"VERCEL_ENV": "production", "DATABASE_URL": "postgres://u@h/db", "CRON_SECRET": self.SECRET})
        self.assertEqual(bare.mail_missing()[:2], ("SMTP_HOST", "SMTP_FROM (the sender address)"))
        self.assertIn("BACKUP_ZIP_PASSWORD (12 to 128 characters)", bare.mail_missing())
        bad = load_settings({"SMTP_HOST": "smtp.example.in", "SMTP_PORT": "abc", "SMTP_FROM": "a,b@x.co",
                             "SMTP_USERNAME": "u", "BACKUP_ZIP_PASSWORD": "short"})
        self.assertEqual(bad.mail_missing(), ("SMTP_PORT (a port number such as 587)", "SMTP_PASSWORD",
                                              "SMTP_FROM (the sender address)",
                                              "BACKUP_ZIP_PASSWORD (12 to 128 characters)"))
        ready = load_settings(MAIL_ENV)
        self.assertEqual(ready.mail_missing(), ())
        self.assertEqual((ready.smtp_port, ready.smtp_from), (587, "desk@example.in"))
        self.assertEqual(load_settings(dict(MAIL_ENV, SMTP_FROM="")).smtp_from, "desk@example.in",
                         "the login is used as sender when it is an address")
        text = repr(ready)
        self.assertNotIn(MAIL_ENV["SMTP_PASSWORD"], text)
        self.assertNotIn(MAIL_ENV["BACKUP_ZIP_PASSWORD"], text)


MAIL_ENV = {"SMTP_HOST": "smtp.example.in", "SMTP_USERNAME": "desk@example.in", "SMTP_PASSWORD": "smtp-secret-pw",
            "SMTP_FROM": "desk@example.in", "BACKUP_ZIP_PASSWORD": "zip-secret-password-1"}


class FakeSMTP:
    """Stands in for smtplib.SMTP / SMTP_SSL: records every call, never opens a socket."""

    instances: list = []

    def __init__(self, host, port, *, local_hostname=None, timeout=None, context=None, starttls=True,
                 fail_starttls=False):
        self.calls = [("connect", host, port, local_hostname, timeout, context is not None)]
        self.offers_starttls, self.fail_starttls = starttls, fail_starttls
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append(("quit",))
        return False

    def ehlo(self):
        self.calls.append(("ehlo",))

    def has_extn(self, name):
        return name == "starttls" and self.offers_starttls

    def starttls(self, *, context=None):
        if self.fail_starttls:
            import ssl
            raise ssl.SSLError("handshake failed")
        self.calls.append(("starttls", context is not None))

    def login(self, user, password):
        self.calls.append(("login", user))

    def send_message(self, message, from_addr=None, to_addrs=None):
        self.calls.append(("send", from_addr, tuple(to_addrs)))
        self.message = message
        return {}

    def names(self):
        return [call[0] for call in self.calls]


def fake_smtp(**options):
    return lambda *args, **kwargs: FakeSMTP(*args, **kwargs, **options)


class Mailer(unittest.TestCase):
    def mailer(self, port=587, **options):
        from app.infra import mailer

        FakeSMTP.instances = []
        settings = load_settings(dict(MAIL_ENV, SMTP_PORT=str(port)))
        built, missing = mailer.from_settings(settings, smtp_class=fake_smtp(**options),
                                              smtp_ssl_class=fake_smtp(**options))
        self.assertEqual(missing, ())
        return built

    def send(self, mailer, to="backups@example.in"):
        asyncio.run(mailer.send(to=to, subject="Gold Loan Desk nightly backup · taken 20 Oct 2025, 00:01 IST",
                                text="Attached.", attachment=("backup.zip", b"PK\x03\x04data")))
        return FakeSMTP.instances[-1]

    def test_starttls_comes_before_login_and_send(self):
        server = self.send(self.mailer())
        self.assertEqual(server.names(), ["connect", "ehlo", "starttls", "ehlo", "login", "send", "quit"])
        connect = server.calls[0]
        self.assertEqual(connect[1:5], ("smtp.example.in", 587, "example.in", 20.0), "explicit EHLO name, 20 s timeout")
        self.assertEqual(server.calls[2], ("starttls", True), "verified TLS context")
        self.assertEqual(server.calls[5], ("send", "desk@example.in", ("backups@example.in",)))
        message = server.message
        self.assertTrue(message["Message-ID"].endswith("@example.in>"))
        self.assertEqual(message["To"], "backups@example.in")
        attachment = next(message.iter_attachments())
        self.assertEqual((attachment.get_filename(), attachment.get_content_type()), ("backup.zip", "application/zip"))
        self.assertEqual(attachment.get_content(), b"PK\x03\x04data")

    def test_port_465_uses_tls_from_the_start(self):
        server = self.send(self.mailer(port=465))
        self.assertEqual(server.names(), ["connect", "login", "send", "quit"])
        self.assertTrue(server.calls[0][5], "SMTP_SSL gets a verified context")

    def test_no_encryption_means_nothing_is_sent(self):
        from app.infra.mailer import MailError

        for options in ({"starttls": False}, {"fail_starttls": True}):
            with self.subTest(options):
                mailer = self.mailer(**options)
                with self.assertRaises(MailError) as caught:
                    self.send(mailer)
                server = FakeSMTP.instances[-1]
                self.assertNotIn("login", server.names())
                self.assertNotIn("send", server.names())
                self.assertIn("nothing was sent", caught.exception.public_message)

    def test_recipients_are_exactly_one_checked_address(self):
        from app.infra.mailer import MailError

        mailer = self.mailer()
        for bad in ("a@x.co, b@y.co", "x@y.co\r\nBcc: z@evil.example", "Name <a@x.co>"):
            with self.subTest(bad), self.assertRaises(MailError):
                self.send(mailer, to=bad)
        self.assertEqual(FakeSMTP.instances, [], "an invalid address never opens a connection")

    def test_errors_and_repr_never_show_secrets(self):
        import smtplib

        from app.infra import mailer as mailer_module

        built = self.mailer()
        for text in (repr(built), repr(built.config)):
            self.assertNotIn(MAIL_ENV["SMTP_PASSWORD"], text)
            self.assertNotIn(MAIL_ENV["BACKUP_ZIP_PASSWORD"], text)

        def refusing(*args, **kwargs):
            server = FakeSMTP(*args, **kwargs)
            server.send_message = lambda *a, **k: (_ for _ in ()).throw(
                smtplib.SMTPRecipientsRefused({"backups@example.in": (550, b"no such user")}))
            return server

        built = mailer_module.BackupMailer(built.config, "zip-secret-password-1", smtp_class=refusing)
        with self.assertRaises(mailer_module.MailError) as caught:
            self.send(built)
        self.assertNotIn("backups@example.in", caught.exception.public_message)
        self.assertIsNone(caught.exception.__cause__)

    def test_not_configured_lists_what_is_missing(self):
        from app.infra import aeszip, mailer

        built, missing = mailer.from_settings(load_settings({}))
        self.assertIsNone(built)
        self.assertIn("SMTP_HOST", missing)
        original = aeszip.available
        aeszip.available = lambda: False
        try:
            built, missing = mailer.from_settings(load_settings(MAIL_ENV))
        finally:
            aeszip.available = original
        self.assertEqual((built, missing), (None, ("pyzipper is not installed",)))


if __name__ == "__main__":
    unittest.main()

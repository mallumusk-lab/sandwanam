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


if __name__ == "__main__":
    unittest.main()

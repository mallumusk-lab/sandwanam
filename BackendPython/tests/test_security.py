import hashlib
import unittest
from datetime import datetime, timedelta, timezone

from app.security import passwords, sessions, throttle

FAST = 1_000  # keep unit tests quick; production uses passwords.ITERATIONS


class Passwords(unittest.TestCase):
    def test_round_trip_and_unicode(self):
        stored = passwords.hash_password("ശക്തമായ-പാസ്‌വേഡ്-2026", iterations=FAST)
        self.assertTrue(stored.startswith("pbkdf2_sha256$1000$"))
        self.assertTrue(passwords.verify_password("ശക്തമായ-പാസ്‌വേഡ്-2026", stored))
        self.assertFalse(passwords.verify_password("wrong", stored))

    def test_salts_differ(self):
        self.assertNotEqual(passwords.hash_password("same", iterations=FAST), passwords.hash_password("same", iterations=FAST))

    def test_legacy_formats_verify_and_need_rehash(self):
        legacy_sha = "sha256:" + hashlib.sha256(b"1234salthere").hexdigest()
        self.assertTrue(passwords.verify_password("1234", legacy_sha))
        self.assertTrue(passwords.needs_rehash(legacy_sha))
        salt = bytes(range(32))
        legacy_pbkdf2 = "pbkdf2:%s:%s" % (salt.hex(), hashlib.pbkdf2_hmac("sha256", b"pw", salt, 260_000).hex())
        self.assertTrue(passwords.verify_password("pw", legacy_pbkdf2))
        self.assertTrue(passwords.needs_rehash(passwords.hash_password("pw", iterations=FAST)))

    def test_plaintext_and_garbage_are_never_accepted(self):
        for stored in ("1234", "", None, "pbkdf2_sha256$x$y", "pbkdf2:zz:zz"):
            with self.subTest(stored):
                self.assertFalse(passwords.verify_password("1234", stored))

    def test_known_defaults_are_detected(self):
        self.assertTrue(passwords.uses_known_default("sha256:" + hashlib.sha256(b"super1234salthere").hexdigest()))
        self.assertTrue(passwords.uses_known_default("1234"), "plaintext counts as unusable")
        self.assertFalse(passwords.uses_known_default(passwords.hash_password("Kerala-gold-2026", iterations=FAST)))


class Sessions(unittest.TestCase):
    def test_tokens_are_random_and_hashed(self):
        a, b = sessions.new_token(), sessions.new_token()
        self.assertNotEqual(a, b)
        self.assertEqual(len(sessions.token_hash(a)), 32)

    def test_csrf_is_bound_to_the_session(self):
        token = sessions.new_token()
        csrf = sessions.csrf_token(token)
        self.assertTrue(sessions.csrf_matches(token, csrf))
        self.assertFalse(sessions.csrf_matches(sessions.new_token(), csrf))
        self.assertFalse(sessions.csrf_matches(token, None))

    def test_expiry_rules(self):
        now = datetime(2025, 1, 1, 12, tzinfo=timezone.utc)
        expires = sessions.expires_at(now - timedelta(hours=1))
        self.assertTrue(sessions.is_active(expires, now - timedelta(minutes=10), now))
        self.assertFalse(sessions.is_active(expires, now - timedelta(minutes=61), now), "idle timeout")
        self.assertFalse(sessions.is_active(now, now, now), "absolute timeout")
        self.assertFalse(sessions.should_touch(now - timedelta(minutes=2), now))
        self.assertTrue(sessions.should_touch(now - timedelta(minutes=6), now))


class Throttle(unittest.TestCase):
    def test_backoff_grows_and_caps(self):
        self.assertEqual(throttle.lock_duration(2), timedelta(0))
        self.assertEqual(throttle.lock_duration(3), timedelta(seconds=30))
        self.assertEqual(throttle.lock_duration(4), timedelta(seconds=60))
        self.assertEqual(throttle.lock_duration(30), timedelta(minutes=15))

    def test_delays_never_overflow(self):
        self.assertEqual(throttle.lock_duration(10_000, throttle.PER_ACCOUNT), timedelta(minutes=5))
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        claim = throttle.claim({"failures": 10**9, "locked_until": None, "updated_at": now}, now, throttle.PER_ADDRESS)
        self.assertEqual(claim.failures, throttle.MAX_COUNTED_FAILURES)

    def test_trust_expires(self):
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        self.assertTrue(throttle.is_trusted({"updated_at": now - timedelta(days=29)}, now))
        self.assertFalse(throttle.is_trusted({"updated_at": now - timedelta(days=31)}, now))
        self.assertFalse(throttle.is_trusted(None, now))

    def test_old_failures_expire(self):
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(throttle.failures_after_window(5, now - timedelta(minutes=30), now), 5)
        self.assertEqual(throttle.failures_after_window(5, now - timedelta(hours=2), now), 0)

    def test_client_ip(self):
        self.assertEqual(throttle.client_ip({"x-real-ip": "1.2.3.4"}, None), "1.2.3.4")
        self.assertEqual(throttle.client_ip({"x-forwarded-for": "5.6.7.8, 10.0.0.1"}, None), "5.6.7.8")
        self.assertEqual(throttle.client_ip({}, "127.0.0.1"), "127.0.0.1")
        self.assertEqual(throttle.client_ip({"x-real-ip": "6.6.6.6"}, "10.0.0.9", trust_proxy_headers=False), "10.0.0.9")

    def test_ipv6_clients_are_grouped_by_64(self):
        self.assertEqual(throttle.address_key("2001:db8:1:2:aaaa::1"), throttle.address_key("2001:db8:1:2:ffff::9"))
        self.assertNotEqual(throttle.address_key("2001:db8:1:2::1"), throttle.address_key("2001:db8:1:3::1"))
        self.assertEqual(throttle.address_key("::ffff:1.2.3.4"), "1.2.3.4")
        self.assertEqual(throttle.address_key("not-an-ip"), "not-an-ip")

    def test_claims_count_before_verification(self):
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        record = None
        allowed = []
        for _ in range(5):  # what parallel requests see once each has taken the row lock in turn
            claim = throttle.claim(record, now)
            allowed.append(claim.allowed)
            if claim.allowed:
                record = {"failures": claim.failures, "locked_until": claim.locked_until, "updated_at": now}
        self.assertEqual(allowed, [True, True, True, False, False])
        account = throttle.claim({"failures": 19, "locked_until": None, "updated_at": now}, now, throttle.PER_ACCOUNT)
        self.assertTrue(account.allowed)
        self.assertEqual(account.locked_until, now + timedelta(seconds=30))


if __name__ == "__main__":
    unittest.main()

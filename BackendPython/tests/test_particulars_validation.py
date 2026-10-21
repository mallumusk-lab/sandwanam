import base64
import unittest
from decimal import Decimal as D

from app.domain import particulars, validation
from app.domain.particulars import Item, ItemsError
from app.domain.validation import ValidationError


class Particulars(unittest.TestCase):
    def test_both_legacy_delimiters_parse_the_same(self):
        expected = [Item("Chain", 1), Item("Ring", 2)]
        self.assertEqual(particulars.parse_legacy("Chain(1),Ring(2)"), expected)
        self.assertEqual(particulars.parse_legacy("Chain(1), Ring(2)"), expected)

    def test_oldest_quantity_first_format(self):
        self.assertEqual(particulars.parse_legacy("2 Ring, Chain(1)"), [Item("Ring", 2), Item("Chain", 1)])

    def test_items_without_quantity_default_to_one(self):
        self.assertEqual(particulars.parse_legacy("Bangle"), [Item("Bangle", 1)])
        self.assertEqual(particulars.parse_legacy(""), [])

    def test_round_trip(self):
        items = [Item("Gold chain", 1), Item("Ear ring", 2)]
        text = particulars.to_display(items)
        self.assertEqual(text, "Gold chain(1), Ear ring(2)")
        self.assertEqual(particulars.parse_legacy(text), items)
        self.assertEqual(particulars.total_quantity(items), 3)

    def test_validate(self):
        self.assertEqual(particulars.validate([{"name": "  Ring  ", "qty": 2}]), [Item("Ring", 2)])
        for bad in ([], [{"name": "", "qty": 1}], [{"name": "Ring", "qty": 0}], [{"name": "Ring", "qty": True}], "Ring"):
            with self.subTest(bad), self.assertRaises(ItemsError):
                particulars.validate(bad)


class Validation(unittest.TestCase):
    def test_phone(self):
        self.assertEqual(validation.phone("+91 98765-43210"), "9876543210")
        for bad in ("12345", "abcdefghij", "5876543210"):
            with self.subTest(bad), self.assertRaises(ValidationError):
                validation.phone(bad)

    def test_weights(self):
        self.assertEqual(validation.weights("10.1", "0.3"), (D("10.10"), D("0.30"), D("9.80")))
        for gross, deduction in (("0", "0"), ("10", "10"), ("10", "-1")):
            with self.subTest((gross, deduction)), self.assertRaises(ValidationError):
                validation.weights(gross, deduction)

    def test_rate_and_tenure(self):
        self.assertEqual(validation.rate("18"), D("18.00"))
        for bad in ("0", "12.125", "101"):
            with self.subTest(bad), self.assertRaises(ValidationError):
                validation.rate(bad)
        self.assertEqual(validation.tenure(12), 12)
        for bad in (0, 121, 1.5, True):
            with self.subTest(bad), self.assertRaises(ValidationError):
                validation.tenure(bad)

    def test_password_policy(self):
        validation.password("Kerala-gold-2026", "User1")
        for bad, user in (("short", ""), ("1234567890", ""), ("aaaaaaaaaaaa", ""), ("my-User1-password", "User1")):
            with self.subTest(bad), self.assertRaises(ValidationError):
                validation.password(bad, user)

    def test_branch_prefix_and_username(self):
        self.assertEqual(validation.branch_prefix(" san "), "SAN")
        with self.assertRaises(ValidationError):
            validation.branch_prefix("S4N")
        with self.assertRaises(ValidationError):
            validation.username("a b")

    def test_logo_checks_magic_bytes_and_size(self):
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        url = "data:image/png;base64," + base64.b64encode(png).decode()
        self.assertTrue(validation.logo_data_url(url).startswith("data:image/png;base64,"))
        self.assertIsNone(validation.logo_data_url(""))
        fake = "data:image/png;base64," + base64.b64encode(b"<svg onload=alert(1)>").decode()
        big = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 300_000).decode()
        for bad in (fake, big, "data:image/svg+xml;base64,PHN2Zz4=", "javascript:alert(1)"):
            with self.subTest(bad[:30]), self.assertRaises(ValidationError):
                validation.logo_data_url(bad)


if __name__ == "__main__":
    unittest.main()

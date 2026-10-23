"""The emailed backup ZIP: AES-256 (WinZip AES), deflated, opened only with the password, and
opened again in memory for Import backup."""
import io
import sys
import unittest
import zipfile
from datetime import datetime
from unittest import mock

from app.errors import Invalid, ServiceUnavailable
from app.infra import aeszip

try:
    import pyzipper
except ImportError:  # the app runs without it (email is then reported as not set up)
    pyzipper = None

PASSWORD = "Correct-horse-battery-9"
MODIFIED = datetime(2025, 10, 20, 0, 1)
ENTRIES = [("backup_2025-10-20_0001IST.json", b'{"format_version":3}' * 500), ("README.txt", "Open with 7-Zip ₹".encode())]


@unittest.skipIf(pyzipper is None, "pyzipper is not installed")
class AesZip(unittest.TestCase):
    def setUp(self):
        self.blob = aeszip.encrypt_zip(ENTRIES, PASSWORD, modified=MODIFIED)

    def test_round_trip_with_the_password(self):
        self.assertTrue(aeszip.available())
        with pyzipper.AESZipFile(io.BytesIO(self.blob)) as archive:
            archive.setpassword(PASSWORD.encode())
            self.assertEqual(archive.namelist(), [name for name, _ in ENTRIES])
            for name, data in ENTRIES:
                self.assertEqual(archive.read(name), data)
            self.assertEqual(archive.getinfo("README.txt").date_time, (2025, 10, 20, 0, 1, 0))

    def test_wrong_or_missing_password_fails(self):
        with pyzipper.AESZipFile(io.BytesIO(self.blob)) as archive:
            with self.assertRaises(RuntimeError):
                archive.read("README.txt")
            archive.setpassword(b"wrong-password-123")
            with self.assertRaises(RuntimeError):
                archive.read("README.txt")
        with zipfile.ZipFile(io.BytesIO(self.blob)) as plain, self.assertRaises(Exception):
            plain.read("README.txt")

    def test_method_is_aes_256_and_content_is_not_readable(self):
        with zipfile.ZipFile(io.BytesIO(self.blob)) as archive:
            for info in archive.infolist():
                self.assertTrue(info.flag_bits & 0x1, "encrypted flag")
                self.assertEqual(info.compress_type, 99, "WinZip AES marker")
                extra = info.extra
                at = extra.find(b"\x01\x99")
                self.assertGreaterEqual(at, 0, "AES extra field")
                vendor, strength, method = extra[at + 6:at + 8], extra[at + 8], int.from_bytes(extra[at + 9:at + 11], "little")
                self.assertEqual((vendor, strength, method), (b"AE", 3, zipfile.ZIP_DEFLATED), "AES-256, deflate")
        self.assertNotIn(b"format_version", self.blob)
        self.assertNotIn(b"7-Zip", self.blob)

    def test_bad_input_is_refused(self):
        for entries, password, modified in (
            (ENTRIES, "", MODIFIED),
            ([("../evil.txt", b"x")], PASSWORD, MODIFIED),
            ([("/abs.txt", b"x")], PASSWORD, MODIFIED),
            ([("C:x.txt", b"x")], PASSWORD, MODIFIED),
            (ENTRIES, PASSWORD, datetime(1970, 1, 1)),
        ):
            with self.subTest(entries[0][0]), self.assertRaises(ValueError):
                aeszip.encrypt_zip(entries, password, modified=modified)


BACKUP = b'{"format_version":3,"tables":{}}' * 200
LIMIT = 1024 * 1024


@unittest.skipIf(pyzipper is None, "pyzipper is not installed")
class ReadBackupZip(unittest.TestCase):
    def zipped(self, entries=None, password=PASSWORD):
        entries = entries if entries is not None else [("backup_2025-10-20_0001IST.json", BACKUP), ("README.txt", b"x")]
        return aeszip.encrypt_zip(entries, password, modified=MODIFIED)

    def refused(self, data, password=PASSWORD, limit=LIMIT):
        with self.assertRaises(Invalid) as caught:
            aeszip.read_backup_zip(data, password, limit=limit)
        return caught.exception

    def test_round_trip_with_encrypt_zip(self):
        self.assertEqual(aeszip.read_backup_zip(self.zipped(), PASSWORD, limit=LIMIT), BACKUP)
        unicode_password = "Pāsswörd-₹-2025"
        self.assertEqual(aeszip.read_backup_zip(self.zipped(password=unicode_password), unicode_password, limit=LIMIT),
                         BACKUP)

    def test_wrong_password_is_a_plain_error(self):
        for password in ("wrong-password-123", PASSWORD.lower(), PASSWORD + " "):
            with self.subTest(password):
                error = self.refused(self.zipped(), password)
                self.assertEqual((error.code, error.message, error.details),
                                 ("zip_password", "The ZIP password is wrong.", {"field": "zip_password"}))
                self.assertNotIn(password, error.message)

    def test_the_zip_must_hold_exactly_one_backup_json(self):
        cases = {
            "none": [("README.txt", b"x")],
            "two": [("backup_a.json", BACKUP), ("backup_b.json", BACKUP)],
            "in a folder": [("old/backup_a.json", BACKUP)],
            "other name": [("customers.json", BACKUP)],
        }
        for name, entries in cases.items():
            with self.subTest(name):
                error = self.refused(self.zipped(entries))
                self.assertEqual(error.code, "invalid_backup")
                self.assertIn("exactly one backup_", error.message)
        for name, data in (("not a zip", b"{}"), ("cut short", self.zipped()[:-40]), ("empty", b"")):
            with self.subTest(name):
                self.assertEqual(self.refused(data).code, "invalid_backup")
        damaged = bytearray(self.zipped())
        damaged[120] ^= 0xFF
        self.assertIn(self.refused(bytes(damaged)).code, ("invalid_backup", "zip_password"))

    def test_size_is_capped_before_and_after_unpacking(self):
        blob = self.zipped()
        error = self.refused(blob, limit=len(blob) - 1)
        self.assertEqual((error.code, error.message), ("invalid_backup", "The backup is larger than 0 MB."))
        bomb = self.zipped([("backup_big.json", b" " * (2 * LIMIT))])
        self.assertLess(len(bomb), LIMIT // 10, "deflate makes it small")
        self.assertEqual(self.refused(bomb).message, "The backup is larger than 1 MB.")
        # a header that understates the size never yields more than it declares (the JSON is then refused)
        with mock.patch.object(pyzipper.AESZipFile, "infolist", autospec=True,
                               side_effect=lambda archive: [_understated(i) for i in archive.filelist]):
            self.assertEqual(aeszip.read_backup_zip(bomb, PASSWORD, limit=LIMIT), b" " * 10)

    def test_without_pyzipper_the_server_says_so(self):
        with mock.patch.dict(sys.modules, {"pyzipper": None}):
            with self.assertRaises(ServiceUnavailable) as caught:
                aeszip.read_backup_zip(b"PK", PASSWORD, limit=LIMIT)
        self.assertEqual(caught.exception.code, "zip_unavailable")
        self.assertIn(".json", caught.exception.message)


def _understated(info):
    info.file_size = 10
    return info


if __name__ == "__main__":
    unittest.main()

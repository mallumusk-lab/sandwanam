import gzip
import hashlib
import json
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal as D

from app.domain import backup_codec, reports
from app.domain.backup_codec import BackupFormatError


class Periods(unittest.TestCase):
    TODAY = date(2025, 10, 20)

    def test_defaults_to_today(self):
        self.assertEqual(reports.resolve_period(None, None, self.TODAY), (self.TODAY, self.TODAY))

    def test_rejects_bad_ranges(self):
        for start, end in (("2025-10-21", "2025-10-21"), ("2025-10-10", "2025-10-01"), ("2010-01-01", "2025-10-01"), ("x", None)):
            with self.subTest((start, end)), self.assertRaises(reports.PeriodError):
                reports.resolve_period(start, end, self.TODAY)

    def test_aging_buckets(self):
        self.assertEqual(reports.aging_bucket(0), "0–30 days")
        self.assertEqual(reports.aging_bucket(45), "31–60 days")
        self.assertEqual(reports.aging_bucket(91), "Over 90 days")

    def test_month_starts(self):
        self.assertEqual(
            reports.month_starts(date(2025, 2, 14), 3),
            [date(2024, 12, 1), date(2025, 1, 1), date(2025, 2, 1)],
        )


class Csv(unittest.TestCase):
    def test_formula_injection_is_neutralised(self):
        self.assertEqual(reports.csv_cell("=HYPERLINK(\"x\")"), "\"'=HYPERLINK(\"\"x\"\")\"")
        self.assertEqual(reports.csv_cell("-5"), "'-5")
        self.assertEqual(reports.csv_cell("a,b"), '"a,b"')
        self.assertEqual(reports.to_csv(["A"], [[1], [None]]), "A\r\n1\r\n\r\n")


class BackupCodec(unittest.TestCase):
    def sample(self):
        now = datetime(2025, 10, 20, 6, tzinfo=timezone.utc)
        return {
            "customers": [{"customerid": 1, "customername": "Test", "phone": "9876543210", "address": "X", "loanstatus": "1",
                           "role": "Admin", "user_id": "SAN1", "branch_prefix": "SAN", "last_loan_no": 1, "created_at": now}],
            "loan_data": [{"loanid": 1, "customerid": 1, "loan_number": "SAN1L1", "weight": D("10.00"), "date": now,
                           "follow_up_date": date(2025, 11, 1), "items": [{"name": "Ring", "qty": 1}], "principle_amount": D("1000.00")}],
            "statement": [{"statementid": 1, "loanid": 1, "loan_number": "SAN1L1", "amountpaid": D("0.00"), "date": now,
                           "transactiontype": "newLoan"}],
        }

    def test_round_trip_including_follow_up_dates(self):
        payload = backup_codec.encode(self.sample(), datetime(2025, 10, 20, tzinfo=timezone.utc))
        decoded = backup_codec.decode(json.loads(json.dumps(payload)))
        loan = dict(zip(backup_codec.columns("loan_data"), decoded["loan_data"][0]))
        self.assertEqual(loan["follow_up_date"], date(2025, 11, 1))
        self.assertEqual(loan["weight"], D("10.00"))
        self.assertEqual(json.loads(loan["items"]), [{"name": "Ring", "qty": 1}])
        self.assertEqual(decoded["branches"], [])

    def test_legacy_and_tampered_files_are_rejected(self):
        payload = backup_codec.encode(self.sample(), datetime(2025, 10, 20, tzinfo=timezone.utc))
        legacy = {"customers": [], "loan_data": [], "statement": [], "role": []}
        injected = json.loads(json.dumps(payload))
        injected["tables"]["customers"]["columns"][1] = 'customername") VALUES (1); --'
        unknown = json.loads(json.dumps(payload))
        unknown["tables"]["role"] = {"columns": ["password"], "rows": []}
        wrong_type = json.loads(json.dumps(payload))
        wrong_type["tables"]["loan_data"]["rows"][0][0] = "1; DROP TABLE x"
        for bad in (legacy, injected, unknown, wrong_type, [], {"format_version": 2}):
            with self.subTest(str(bad)[:40]), self.assertRaises(BackupFormatError):
                backup_codec.decode(bad)


def tamper(document, change):
    copy = json.loads(json.dumps(document))
    change(copy)
    return copy


def v2_of(document):
    """The same data as a version 2 file (what older snapshots and downloads contain)."""
    return {"format_version": 2, "created_at": document["created_at"], "tables": document["tables"]}


class BackupFormatV3(unittest.TestCase):
    NOW = datetime(2025, 10, 20, 6, tzinfo=timezone.utc)

    def rows(self, **extra):
        rows = BackupCodec.sample(None)
        rows["app_settings"] = [
            {"key": "gold_rate", "value": {"per_gram": "7000.00"}, "updated_at": self.NOW, "updated_by": "Admin"},
            {"key": "backup_email", "value": {"recipient": "x@y.co", "enabled": True}, "updated_at": self.NOW,
             "updated_by": "root"},
            {"key": "backup_email_status", "value": {"nightly": None}, "updated_at": self.NOW, "updated_by": "system"},
        ]
        for table, more in extra.items():
            rows[table] = rows.get(table, []) + more
        return rows

    def document(self, **extra):
        return backup_codec.encode(self.rows(**extra), self.NOW, created_by="root", kind="manual")

    def test_v3_document_has_manifest_schema_and_checksum(self):
        doc = self.document()
        self.assertEqual(doc["format_version"], 3)
        self.assertEqual(doc["app"], "gold-loan-desk")
        self.assertRegex(doc["schema"], r"^[0-9a-f]{16}$")
        self.assertEqual((doc["created_by"], doc["kind"]), ("root", "manual"))
        self.assertEqual(set(doc["manifest"]["tables"]), set(backup_codec.TABLES))
        customers = doc["manifest"]["tables"]["customers"]
        self.assertEqual(customers["rows"], 1)
        self.assertEqual(customers["sha256"],
                         hashlib.sha256(backup_codec.canonical(doc["tables"]["customers"])).hexdigest())
        body = {k: v for k, v in doc.items() if k != "checksum"}
        self.assertEqual(doc["checksum"], hashlib.sha256(backup_codec.canonical(body)).hexdigest())
        raw = backup_codec.canonical(doc)
        self.assertEqual(raw, json.dumps(doc, separators=(",", ":"), sort_keys=True).encode("ascii"))
        self.assertEqual(backup_codec.loads(raw), doc)
        with self.assertRaises(ValueError):
            backup_codec.canonical({"x": float("nan")})
        with self.assertRaises(ValueError):
            backup_codec.encode(self.rows(), self.NOW, kind="nightly")

    def test_only_nightly_and_manual_kinds_are_written_but_older_files_still_read(self):
        self.assertEqual(backup_codec.KINDS, ("scheduled", "manual"))
        for old in ("pre_restore", "export"):
            with self.subTest(old), self.assertRaises(ValueError):
                backup_codec.encode(self.rows(), self.NOW, kind=old)

        def relabelled(kind):
            doc = {k: v for k, v in self.document().items() if k != "checksum"}
            doc["kind"] = kind
            return dict(doc, checksum=hashlib.sha256(backup_codec.canonical(doc)).hexdigest())

        for old in ("pre_restore", "export"):
            with self.subTest(read=old):
                report = backup_codec.inspect(relabelled(old))
                self.assertEqual((report["kind"], report["checksum"]), (old, "verified"))
                self.assertEqual(backup_codec.decode(relabelled(old)), backup_codec.decode(self.document()))
        with self.assertRaises(BackupFormatError):
            backup_codec.decode(relabelled("nightly"))

    def test_tampering_is_rejected(self):
        doc = self.document()
        amount_at = backup_codec.columns("loan_data").index("principle_amount")
        changes = {
            "amount": lambda d: d["tables"]["loan_data"]["rows"][0].__setitem__(amount_at, "1.00"),
            "manifest": lambda d: d["manifest"]["tables"]["customers"].__setitem__("rows", 2),
            "dropped table": lambda d: d["tables"].pop("app_settings"),
            "metadata": lambda d: d.__setitem__("created_by", "someone"),
            "checksum": lambda d: d.__setitem__("checksum", "0" * 64),
            "no checksum": lambda d: d.pop("checksum"),
            "other app": lambda d: d.__setitem__("app", "other"),
            "other schema": lambda d: d.__setitem__("schema", "0" * 16),
            "version as text": lambda d: d.__setitem__("format_version", "3"),
            "version 4": lambda d: d.__setitem__("format_version", 4),
        }
        for name, change in changes.items():
            with self.subTest(name), self.assertRaises(BackupFormatError):
                backup_codec.decode(tamper(doc, change))
        backup_codec.decode(doc)

    def test_v2_files_still_decode_identically(self):
        doc = self.document()
        self.assertEqual(backup_codec.decode(v2_of(doc)), backup_codec.decode(doc))
        report = backup_codec.inspect(v2_of(doc))
        self.assertEqual(report["checksum"], "absent")
        self.assertEqual(report["format_version"], 2)
        self.assertTrue(any("older backup" in w for w in report["warnings"]))
        self.assertEqual(backup_codec.inspect(doc)["checksum"], "verified")

    def test_gzip_plain_and_bom_inputs_are_equal(self):
        raw = backup_codec.canonical(self.document())
        packed = backup_codec.pack(raw)
        self.assertEqual(packed[:2], b"\x1f\x8b")
        self.assertEqual(packed, backup_codec.pack(raw), "same document, same bytes (mtime 0)")
        self.assertEqual(gzip.decompress(packed), raw)
        expected = backup_codec.loads(raw)
        inputs = (("gzip", packed), ("plain", raw), ("bom", b"\xef\xbb\xbf" + raw),
                  ("gzip of bom", gzip.compress(b"\xef\xbb\xbf" + raw)), ("spaced", b"  " + raw + b"\n"))
        for name, data in inputs:
            with self.subTest(name):
                self.assertEqual(backup_codec.loads(data), expected)

    def test_bad_bytes_are_refused(self):
        raw = backup_codec.canonical(self.document())
        packed = backup_codec.pack(raw)
        bad_crc = packed[:-8] + bytes([packed[-8] ^ 1]) + packed[-7:]
        cases = {
            "two BOMs": b"\xef\xbb\xbf\xef\xbb\xbf" + raw,
            "latin-1": '{"a":"é"}'.encode("latin-1"),
            "utf-16": raw.decode("ascii").encode("utf-16"),
            "NaN": b'{"a":NaN}',
            "Infinity": b'{"a":-Infinity}',
            "duplicate keys": b'{"format_version":3,"format_version":2}',
            "nested duplicate": b'{"a":{"b":1,"b":2}}',
            "trailing JSON": raw + b"{}",
            "trailing gzip data": packed + b"junk",
            "second gzip member": packed + packed,
            "truncated gzip": packed[:-10],
            "bad CRC": bad_crc,
            "not JSON": b"customers,loans",
        }
        for name, data in cases.items():
            with self.subTest(name), self.assertRaises(BackupFormatError):
                backup_codec.loads(data)

    def test_decompression_bomb_is_refused(self):
        bomb = gzip.compress(b" " * (3 * 1024 * 1024))
        self.assertLess(len(bomb), 20_000)
        with self.assertRaises(BackupFormatError) as caught:
            backup_codec.loads(bomb, limit=2 * 1024 * 1024)
        self.assertIn("larger than 2 MB", str(caught.exception))
        with self.assertRaises(BackupFormatError):
            backup_codec.loads(b" " * (2 * 1024 * 1024 + 1), limit=2 * 1024 * 1024)
        self.assertEqual(backup_codec.MAX_UPLOAD_BYTES, 48 * 1024 * 1024)
        self.assertFalse(hasattr(backup_codec, "MAX_STORED_BYTES"), "no snapshots are stored, so uploads have the only cap")
        self.assertEqual(backup_codec.unpack(gzip.compress(b"x" * 100), limit=100), b"x" * 100)

    def test_each_unique_key_is_checked(self):
        now = self.NOW
        customer = {"customerid": 2, "customername": "B", "phone": "9876500000", "user_id": "SAN2",
                    "branch_prefix": "SAN", "created_at": now}
        loan = {"loanid": 2, "customerid": 1, "loan_number": "SAN1L2", "date": now, "principle_amount": D("5")}
        entry = {"statementid": 2, "loanid": 2, "loan_number": "SAN1L2", "date": now, "transactiontype": "addColl",
                 "amountpaid": D("1")}
        cases = {
            "customerid": {"customers": [dict(customer, customerid=1)]},
            "phone": {"customers": [dict(customer, phone="9876543210")]},
            "user_id (any case)": {"customers": [dict(customer, user_id="san1")]},
            "loanid": {"loan_data": [dict(loan, loanid=1)]},
            "loan_number": {"loan_data": [dict(loan, loan_number="SAN1L1")]},
            "statementid": {"statement": [dict(entry, statementid=1)]},
            "client_request_id": {"statement": [dict(entry, client_request_id="req-1"),
                                                dict(entry, statementid=3, client_request_id="req-1")]},
            "two openings": {"statement": [dict(entry, loan_number="SAN1L1", transactiontype="newLoan")]},
        }
        for name, extra in cases.items():
            with self.subTest(name), self.assertRaises(BackupFormatError) as caught:
                backup_codec.decode(self.document(**extra))
            self.assertIn("more than", str(caught.exception))
        allowed = self.document(
            customers=[dict(customer, phone=None), dict(customer, customerid=3, phone=None, user_id="SAN3")],
            statement=[dict(entry, client_request_id=None), dict(entry, statementid=3, client_request_id=None)],
        )
        self.assertEqual(len(backup_codec.decode(allowed)["customers"]), 3, "missing phones are not duplicates")

    def test_floats_in_items_round_trip(self):
        rows = self.rows()
        rows["loan_data"][0]["items"] = json.dumps([{"name": "Chain", "qty": 1, "grams": 12.345},
                                                    {"name": "Ring", "qty": 2}])
        raw = backup_codec.canonical(backup_codec.encode(rows, self.NOW))
        decoded = backup_codec.decode(backup_codec.loads(backup_codec.pack(raw)))
        items = json.loads(decoded["loan_data"][0][backup_codec.columns("loan_data").index("items")])
        self.assertEqual(items[0]["grams"], 12.345)
        with self.assertRaises(BackupFormatError):
            backup_codec.decode(v2_of(tamper(backup_codec.encode(rows, self.NOW), lambda d: d["tables"]["loan_data"][
                "rows"][0].__setitem__(backup_codec.columns("loan_data").index("items"), [float("nan")]))))

    def test_local_settings_are_never_exported_or_restored(self):
        doc = self.document()
        self.assertEqual([row[0] for row in doc["tables"]["app_settings"]["rows"]], ["gold_rate"])
        smuggled = v2_of(doc)
        smuggled["tables"]["app_settings"]["rows"].append(
            ["backup_email", {"recipient": "attacker@evil.example", "enabled": True}, self.NOW.isoformat(), "x"])
        restored = backup_codec.decode(smuggled)
        self.assertEqual([row[0] for row in restored["app_settings"]], ["gold_rate"])
        self.assertEqual(backup_codec.LOCAL_SETTINGS, {"backup_email", "backup_email_status"})

    def test_inspect_reports_counts_and_loose_ends(self):
        now = self.NOW
        doc = self.document(
            customers=[{"customerid": 2, "customername": "No branch", "phone": "9000000000", "user_id": "X2",
                        "branch_prefix": None, "created_at": now}],
            loan_data=[{"loanid": 2, "customerid": 99, "loan_number": "SWA9L1", "date": now,
                        "principle_amount": D("5")}],
            statement=[{"statementid": 2, "loanid": 7, "loan_number": "GONE1L1", "date": now,
                        "transactiontype": "addColl", "amountpaid": D("1")}],
        )
        report = backup_codec.inspect(doc)
        self.assertEqual(report["counts"], {"branches": 0, "customers": 2, "loans": 2, "entries": 2, "settings": 1})
        self.assertEqual(report["branch_prefixes"], ["SAN"])
        self.assertEqual((report["created_by"], report["kind"], report["format_version"]), ("root", "manual", 3))
        text = " ".join(report["warnings"])
        for expected in ("1 customer(s) have no branch", "1 loan(s) belong to a customer",
                         "1 ledger entry belong", "1 loan(s) have no opening"):
            self.assertIn(expected, text)
        self.assertEqual(backup_codec.inspect(self.document())["warnings"], [])
        with self.assertRaises(BackupFormatError):
            backup_codec.inspect({"format_version": 3})

    def test_file_stamp_is_ist(self):
        self.assertEqual(backup_codec.file_stamp(datetime(2025, 10, 20, 18, 31, tzinfo=timezone.utc)),
                         "2025-10-21_0001IST")

    def test_cash_ledger_tables_round_trip_and_are_checked(self):
        now = self.NOW
        cash_day = {"id": 1, "branch_prefix": "SAN", "day": date(2025, 10, 20), "carried_forward": D("-12.50"),
                    "opening_counted": D("1000.00"), "opened_by": "User1", "opened_at": now,
                    "client_request_id": "start-1", "closing_expected": D("1200.00"), "closing_counted": D("1200.00"),
                    "closed_by": "system", "closed_at": now, "closed_automatically": True}
        entry = {"id": 1, "day_id": 1, "direction": "out", "category": "other", "description": "Tea",
                 "reference": None, "amount": D("45.50"), "client_request_id": "entry-1", "created_by": "User1",
                 "created_at": now, "voided_at": now, "voided_by": "User1", "void_reason": "Typed twice"}
        tables = list(backup_codec.TABLES)
        self.assertEqual(tables[tables.index("app_settings") + 1:], ["cash_days", "cash_entries"])
        doc = self.document(cash_days=[cash_day], cash_entries=[entry])
        self.assertEqual(doc["manifest"]["tables"]["cash_entries"]["rows"], 1)
        decoded = backup_codec.decode(backup_codec.loads(backup_codec.pack(backup_codec.canonical(doc))))
        self.assertEqual(dict(zip(backup_codec.columns("cash_days"), decoded["cash_days"][0])), cash_day)
        self.assertEqual(dict(zip(backup_codec.columns("cash_entries"), decoded["cash_entries"][0])), entry)
        self.assertEqual(backup_codec.decode(v2_of(self.document()))["cash_days"], [], "v2 files have no cash ledger")
        flag_at = backup_codec.columns("cash_days").index("closed_automatically")
        bad = {
            "flag is not a boolean": tamper(doc, lambda d: d["tables"]["cash_days"]["rows"][0].__setitem__(flag_at, 1)),
            "same branch and day twice": self.document(cash_days=[cash_day, dict(cash_day, id=2)]),
            "day id twice": self.document(cash_days=[cash_day, dict(cash_day, day=date(2025, 10, 21))]),
            "entry id twice": self.document(cash_days=[cash_day], cash_entries=[entry, dict(entry, client_request_id=None)]),
            "entry request twice": self.document(cash_days=[cash_day],
                                                 cash_entries=[entry, dict(entry, id=2)]),
            "entry without its day": self.document(cash_entries=[entry]),
        }
        for name, document in bad.items():
            with self.subTest(name), self.assertRaises(BackupFormatError) as caught:
                backup_codec.decode(v2_of(document) if name == "flag is not a boolean" else document)
            if name == "same branch and day twice":
                self.assertIn("SAN 2025-10-20", str(caught.exception))
        allowed = self.document(cash_days=[cash_day], cash_entries=[dict(entry, client_request_id=None),
                                                                    dict(entry, id=2, client_request_id=None)])
        self.assertEqual(len(backup_codec.decode(allowed)["cash_entries"]), 2, "missing request ids are not duplicates")


if __name__ == "__main__":
    unittest.main()

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


if __name__ == "__main__":
    unittest.main()

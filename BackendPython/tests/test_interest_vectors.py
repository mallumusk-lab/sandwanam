import json
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.domain.ledger import LoanTerms, Position, quote

VECTORS = Path(__file__).resolve().parents[2] / "test-vectors" / "interest.json"


class SharedInterestVectors(unittest.TestCase):
    def test_every_vector(self):
        cases = json.loads(VECTORS.read_text(encoding="utf-8"))["cases"]
        self.assertGreater(len(cases), 5)
        for case in cases:
            with self.subTest(case["name"]):
                start = date.fromisoformat(case["start"])
                terms = LoanTerms.of(start, Decimal(case["rate"]) if case["rate"] is not None else None)
                position = Position(start, Decimal(case["principal"]), Decimal("0.00"))
                q = quote(terms, position, date.fromisoformat(case["as_of"]), closing=case["closing"])
                expected = case["expected"]
                self.assertEqual(q.principal, Decimal(expected["principal"]))
                self.assertEqual(q.interest, Decimal(expected["interest"]))
                self.assertEqual(q.period_days, expected["period_days"])
                self.assertEqual(len(q.compoundings), expected["compoundings"])


if __name__ == "__main__":
    unittest.main()

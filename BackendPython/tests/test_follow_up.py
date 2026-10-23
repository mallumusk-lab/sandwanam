"""Follow-ups (day 364 unless staff set a date, listed from 10 days before) and overdue loans (after 365 days)."""
import unittest
from datetime import date, timedelta

from app.domain import reports
from app.services import customers_service, import_service, loans_service, reports_service
from tests.fakes import utc
from tests.test_services import NOW, Fixture, run


def at(day: date):
    """11:30 IST on `day`."""
    return utc(day.year, day.month, day.day, 6, 0)


class Rules(unittest.TestCase):
    def test_defaults_and_boundaries(self):
        start = date(2025, 1, 1)
        self.assertEqual((reports.FOLLOW_UP_AFTER_DAYS, reports.OVERDUE_AFTER_DAYS, reports.FOLLOW_UP_NOTICE_DAYS),
                         (364, 365, 10))
        self.assertEqual(reports.default_follow_up(start), date(2025, 12, 31))
        self.assertEqual(reports.overdue_from(start), date(2026, 1, 1))
        self.assertEqual(reports.default_follow_up(date(2024, 1, 1)), date(2024, 12, 30), "leap year: still 364 days")

    def test_effective_follow_up(self):
        start = date(2025, 1, 1)
        self.assertEqual(reports.effective_follow_up(None, start, True), date(2025, 12, 31))
        self.assertEqual(reports.effective_follow_up(date(2025, 6, 1), start, True), date(2025, 6, 1), "stored wins")
        self.assertIsNone(reports.effective_follow_up(date(2025, 6, 1), start, False), "closed loans have none")
        self.assertIsNone(reports.effective_follow_up(None, None, True))


class Portfolio(Fixture):
    START = date(2025, 3, 10)  # NOW's business day: loans made by self.loan() start here

    def portfolio(self, day: date):
        return run(reports_service.portfolio(self.repos, self.san, None, at(day)))

    def test_follow_up_listed_from_10_days_before_day_364_and_overdue_after_day_365(self):
        number = self.loan()["loan_number"]
        quiet = self.portfolio(self.START + timedelta(days=353))
        self.assertEqual((quiet["follow_ups"], quiet["overdue"], quiet["follow_up_notice_days"]), ([], [], 10))
        for offset, days in ((354, 10), (360, 4), (364, 0), (365, -1)):
            with self.subTest(offset):
                book = self.portfolio(self.START + timedelta(days=offset))
                self.assertEqual(book["overdue"], [], "not overdue until after day 365")
                (entry,) = book["follow_ups"]
                self.assertEqual((entry["loan_number"], entry["follow_up_date"], entry["follow_up_set"], entry["follow_up_days"]),
                                 (number, "2026-03-09", False, days))
                self.assertEqual((entry["loan_date"], entry["due_date"]), ("2025-03-10", "2026-03-10"))
                for key in ("customer_id", "customer_name", "phone", "branch", "total"):
                    self.assertIn(key, entry)
        late = self.portfolio(self.START + timedelta(days=366))
        self.assertEqual(late["follow_ups"], [])
        (overdue,) = late["overdue"]
        self.assertEqual((overdue["due_date"], overdue["days_overdue"], overdue["followed_up"], overdue["follow_up_days"]),
                         ("2026-03-10", 1, False, -2))

    def test_overdue_loan_counts_the_days_to_its_follow_up(self):
        number = self.loan()["loan_number"]
        run(loans_service.set_follow_up(self.repos, self.san, number, date(2026, 3, 20), at(self.START + timedelta(days=364))))
        for day, days, followed_up in ((date(2026, 3, 15), 5, True), (date(2026, 3, 20), 0, False), (date(2026, 3, 23), -3, False)):
            with self.subTest(day):
                (overdue,) = self.portfolio(day)["overdue"]
                self.assertEqual((overdue["follow_up_date"], overdue["follow_up_set"], overdue["follow_up_days"], overdue["followed_up"]),
                                 ("2026-03-20", True, days, followed_up))

    def test_stored_date_wins_and_clearing_restores_the_automatic_date(self):
        number = self.loan()["loan_number"]
        day = self.START + timedelta(days=364)
        run(loans_service.set_follow_up(self.repos, self.san, number, date(2026, 4, 1), at(day)))
        self.assertEqual(self.portfolio(day)["follow_ups"], [])
        loan = run(loans_service.detail(self.repos, self.san, number, at(day)))["loan"]
        self.assertEqual((loan["follow_up_date"], loan["follow_up_set"]), ("2026-04-01", True))
        late = self.portfolio(date(2026, 3, 20))["overdue"][0]
        self.assertTrue(late["followed_up"], "a future follow-up marks the overdue loan as followed up")
        run(loans_service.set_follow_up(self.repos, self.san, number, None, at(day)))
        loan = run(loans_service.detail(self.repos, self.san, number, at(day)))["loan"]
        self.assertEqual((loan["follow_up_date"], loan["follow_up_set"]), ("2026-03-09", False))
        self.assertEqual(len(self.portfolio(day)["follow_ups"]), 1)

    def test_follow_ups_are_sorted_by_date_then_loan_number(self):
        first = self.loan()["loan_number"]
        other = self.customer(phone="9000000005", name="Second Customer")["id"]
        second = self.loan(customer_id=other, request_id="req-second")["loan_number"]
        third = self.loan(customer_id=other, request_id="req-third", now=NOW - timedelta(days=1))["loan_number"]
        listed = self.portfolio(self.START + timedelta(days=364))["follow_ups"]
        self.assertEqual([e["loan_number"] for e in listed], [third, first, second])

    def test_imported_old_loan_is_overdue_at_once(self):
        loan = import_service.HistoryLoan([{"name": "Chain", "qty": 1}], "20", "1", "50000", "18", 12, date(2024, 1, 15))
        result = run(import_service.commit(self.repos, self.san, customer_id=None,
                                           new_customer=customers_service.NewCustomer("Anil Das", "9123456789", "Vizhinjam"),
                                           loan=loan, entries=[], request_id="imp-old", now=NOW))
        book = self.portfolio(self.START)
        self.assertEqual(book["follow_ups"], [])
        (overdue,) = book["overdue"]
        self.assertEqual((overdue["loan_number"], overdue["due_date"], overdue["days_overdue"]),
                         (result["loan_number"], "2025-01-14", 55))
        self.assertEqual(overdue["follow_up_date"], "2025-01-13")

    def test_closed_loan_has_no_follow_up(self):
        number = self.loan()["loan_number"]
        later = NOW + timedelta(days=9)
        quote = run(loans_service.closing_quote(self.repos, self.san, number, later))
        run(loans_service.close(self.repos, self.san, number, amount_received=quote["total"], write_off_remaining=False,
                                expected_total=quote["total"], request_id="close-fu", now=later))
        (loan,) = run(customers_service.detail(self.repos, self.san, 1, later))["loans"]
        self.assertEqual((loan["status"], loan["follow_up_date"], loan["follow_up_set"]), ("closed", None, False))


if __name__ == "__main__":
    unittest.main()

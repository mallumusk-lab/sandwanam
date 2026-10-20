import unittest
from datetime import date, datetime, timezone

from app.domain.dates import (
    IST,
    business_date,
    business_datetime,
    ist_day_bounds_utc,
    parse_business_date,
    parse_timestamp,
)


class BusinessDates(unittest.TestCase):
    def test_early_morning_ist_is_still_today_in_ist(self):
        # 02:00 IST on 1 March is 20:30 UTC on 29 February.
        utc = datetime(2024, 2, 29, 20, 30, tzinfo=timezone.utc)
        self.assertEqual(business_date(utc), date(2024, 3, 1))

    def test_naive_values_are_treated_as_utc(self):
        self.assertEqual(business_date(datetime(2024, 2, 29, 20, 30)), date(2024, 3, 1))

    def test_iso_strings_with_z(self):
        self.assertEqual(business_date("2024-02-29T20:30:00.000Z"), date(2024, 3, 1))
        self.assertEqual(parse_timestamp("2024-02-29T20:30:00Z").tzinfo, timezone.utc)

    def test_strict_date_parsing(self):
        self.assertEqual(parse_business_date("2025-10-20"), date(2025, 10, 20))
        for bad in ("20-10-2025", "2025-13-01", "", "2025-10-20T00:00"):
            with self.subTest(bad), self.assertRaises(ValueError):
                parse_business_date(bad)

    def test_past_days_are_stored_at_ist_noon(self):
        now = datetime(2025, 10, 20, 6, 0, tzinfo=timezone.utc)
        stored = business_datetime(date(2025, 10, 1), now)
        self.assertEqual(stored.astimezone(IST).hour, 12)
        self.assertEqual(business_date(stored), date(2025, 10, 1))

    def test_today_is_stored_at_the_current_instant(self):
        now = datetime(2025, 10, 20, 6, 0, tzinfo=timezone.utc)
        self.assertEqual(business_datetime(date(2025, 10, 20), now), now)

    def test_day_bounds_cover_whole_ist_days(self):
        lower, upper = ist_day_bounds_utc(date(2025, 3, 1), date(2025, 3, 1))
        self.assertEqual(lower, datetime(2025, 2, 28, 18, 30, tzinfo=timezone.utc))
        self.assertEqual(upper, datetime(2025, 3, 1, 18, 30, tzinfo=timezone.utc))
        with self.assertRaises(ValueError):
            ist_day_bounds_utc(date(2025, 3, 2), date(2025, 3, 1))


if __name__ == "__main__":
    unittest.main()

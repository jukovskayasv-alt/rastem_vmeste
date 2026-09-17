import copy
import csv
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from skif_agents.finance import build_schedule, export_schedule


class ScheduleTests(unittest.TestCase):
    def test_initial_payment_and_last_kopeck_reconcile(self):
        schedule = build_schedule("1000.01", "100", 3, "2026-01-31")
        self.assertEqual(schedule, {
            "price": "1000.01", "down_payment": "100.00", "months": 3,
            "start_date": "2026-01-31", "rows": [
                {"number": 0, "date": "2026-01-31", "amount": "100.00", "balance": "900.01"},
                {"number": 1, "date": "2026-02-28", "amount": "300.00", "balance": "600.01"},
                {"number": 2, "date": "2026-03-31", "amount": "300.00", "balance": "300.01"},
                {"number": 3, "date": "2026-04-30", "amount": "300.01", "balance": "0.00"},
            ],
        })

    def test_leap_year_does_not_shift_original_day(self):
        schedule = build_schedule("400", "0", 4, "2028-01-31")
        self.assertEqual([row["date"] for row in schedule.get("rows", [])],
                         ["2028-01-31", "2028-02-29", "2028-03-31", "2028-04-30", "2028-05-31"])

    def test_zero_down_payment_keeps_day_zero(self):
        schedule = build_schedule("1", "0", 1, "2026-12-30")
        self.assertEqual(schedule.get("rows"), [
            {"number": 0, "date": "2026-12-30", "amount": "0.00", "balance": "1.00"},
            {"number": 1, "date": "2027-01-30", "amount": "1.00", "balance": "0.00"},
        ])

    def test_total_and_balances_at_long_term_limit(self):
        schedule = build_schedule("999999999999.99", "0.01", 360, "2026-09-17")
        self.assertEqual(len(schedule.get("rows", [])), 361)
        self.assertEqual(sum(Decimal(row["amount"]) for row in schedule["rows"]),
                         Decimal("999999999999.99"))
        self.assertTrue(all(Decimal(row["balance"]) >= 0 for row in schedule["rows"]))
        self.assertEqual(schedule["rows"][-1]["balance"], "0.00")

    def test_comma_money_is_normalized_without_rounding(self):
        self.assertEqual(build_schedule(" 100,50 ", "0", 1, "2026-01-01").get("price"), "100.50")

    def test_invalid_money_never_rounds_or_accepts_nonfinite(self):
        for value in ["NaN", "Infinity", "-1", "1.001", "1.000", "1e3", "", "+1", 100, 1.5, True,
                      "1000000000000", "1_000", "1 000"]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    build_schedule(value, "0", 1, "2026-01-01")
        for value in ["NaN", "-0.01", "0.001", "100", "101"]:
            with self.subTest(down_payment=value):
                with self.assertRaises(ValueError):
                    build_schedule("100", value, 1, "2026-01-01")
        with self.assertRaises(ValueError):
            build_schedule("0", "0", 1, "2026-01-01")

    def test_invalid_months_and_too_small_installments_are_rejected(self):
        for months in [0, -1, 361, 1.2, "12", True, None]:
            with self.subTest(months=months):
                with self.assertRaises(ValueError):
                    build_schedule("100", "0", months, "2026-01-01")
        with self.assertRaises(ValueError):
            build_schedule("0.02", "0", 3, "2026-01-01")

    def test_invalid_dates_and_calendar_overflow_are_rejected(self):
        for start in ["2026-02-30", "20260101", "2026-1-1", "tomorrow", "9999-12-31", 20260101]:
            with self.subTest(start=start):
                with self.assertRaises(ValueError):
                    build_schedule("100", "0", 1, start)


class ExportTests(unittest.TestCase):
    def test_csv_preserves_exact_amounts_and_ics_uses_folded_all_day_events(self):
        schedule = build_schedule("1000.01", "100", 3, "2026-01-31")
        with tempfile.TemporaryDirectory() as temporary:
            outputs = export_schedule(schedule, Path(temporary))
            self.assertEqual([path.suffix for path in outputs], [".csv", ".ics"])
            with outputs[0].open(encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(rows[-1], {"number": "3", "date": "2026-04-30", "amount": "300.01", "balance": "0.00"})
            raw = outputs[1].read_bytes()
            self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
            lines = raw.split(b"\r\n")
            self.assertTrue(all(len(line) <= 75 for line in lines))
            self.assertTrue(any(line.startswith(b" ") for line in lines))
            unfolded = raw.replace(b"\r\n ", b"").decode("utf-8")
            self.assertEqual(unfolded.count("BEGIN:VEVENT"), 4)
            self.assertIn("DTSTART;VALUE=DATE:20260228", unfolded)
            self.assertIn("DURATION:P1D", unfolded)
            self.assertIn("300.01 RUB", unfolded)
            self.assertNotIn("VALARM", unfolded)
            self.assertNotIn("ATTENDEE", unfolded)

    def test_export_rejects_modified_payment_before_creating_files(self):
        schedule = build_schedule("100", "10", 2, "2026-01-01")
        self.assertIn("rows", schedule)
        altered = copy.deepcopy(schedule)
        altered["rows"][-1]["amount"] = "0.01"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "new"
            with self.assertRaises(ValueError):
                export_schedule(altered, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()

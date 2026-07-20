import datetime as dt
from datetime import datetime

from django.test import SimpleTestCase
from django.utils import timezone as django_tz

from core.views import _parse_rotor_recorded_at


class ParseRotorRecordedAtTests(SimpleTestCase):
    def test_excel_datetime_and_time_cells(self):
        date_val = datetime(2026, 6, 15, 0, 0, 0)
        time_val = dt.time(12, 30, 45)
        recorded_at = _parse_rotor_recorded_at(date_val, time_val)
        self.assertIsNotNone(recorded_at)
        self.assertEqual(recorded_at.hour, 12)
        self.assertEqual(recorded_at.minute, 30)
        self.assertTrue(django_tz.is_aware(recorded_at))

    def test_excel_datetime_time_cell_uses_time_portion(self):
        date_val = datetime(2026, 6, 15, 0, 0, 0)
        time_val = datetime(1899, 12, 30, 12, 30, 45)
        recorded_at = _parse_rotor_recorded_at(date_val, time_val)
        self.assertIsNotNone(recorded_at)
        self.assertEqual(recorded_at.hour, 12)
        self.assertEqual(recorded_at.minute, 30)
        self.assertEqual(recorded_at.second, 45)

    def test_excel_numeric_time_fraction(self):
        date_val = datetime(2026, 6, 15, 0, 0, 0)
        time_val = 0.5213541666666667
        recorded_at = _parse_rotor_recorded_at(date_val, time_val)
        self.assertIsNotNone(recorded_at)
        self.assertEqual(recorded_at.hour, 12)
        self.assertEqual(recorded_at.minute, 30)
        self.assertEqual(recorded_at.second, 45)

    def test_excel_timedelta_time_cell(self):
        date_val = datetime(2026, 6, 15, 0, 0, 0)
        time_val = dt.timedelta(hours=12, minutes=30, seconds=45)
        recorded_at = _parse_rotor_recorded_at(date_val, time_val)
        self.assertIsNotNone(recorded_at)
        self.assertEqual(recorded_at.hour, 12)
        self.assertEqual(recorded_at.minute, 30)
        self.assertEqual(recorded_at.second, 45)

    def test_excel_numeric_date_and_time(self):
        recorded_at = _parse_rotor_recorded_at(46188, 0.5213541666666667)
        self.assertIsNotNone(recorded_at)
        self.assertEqual(recorded_at.year, 2026)
        self.assertEqual(recorded_at.month, 6)
        self.assertEqual(recorded_at.day, 15)
        self.assertEqual(recorded_at.hour, 12)
        self.assertEqual(recorded_at.minute, 30)
        self.assertEqual(recorded_at.second, 45)

    def test_string_date_formats(self):
        recorded_at = _parse_rotor_recorded_at('15-06-26', '12:30:45')
        self.assertIsNotNone(recorded_at)
        self.assertEqual(recorded_at.day, 15)
        self.assertEqual(recorded_at.month, 6)

    def test_invalid_values_return_none(self):
        self.assertIsNone(_parse_rotor_recorded_at(None, None))
        self.assertIsNone(_parse_rotor_recorded_at('bad', 'data'))

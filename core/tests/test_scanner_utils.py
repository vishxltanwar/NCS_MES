from django.test import SimpleTestCase

from utils.scanner import clean_scan_data


class ScannerUtilsTests(SimpleTestCase):
    def test_clean_scan_data_normalizes_scanner_noise(self):
        raw = "  ABC\x00  123\r\nDEF   GHI  "

        self.assertEqual(clean_scan_data(raw), "ABC 123DEF GHI")

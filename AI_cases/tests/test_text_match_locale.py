#!/usr/bin/env python3
"""Unit test cho text_match_locale. Chạy: python3 -m unittest test_text_match_locale -v"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import unittest
from shared.text_match_locale import detect_separator, parse_number, input_numbers, normalize, covered


class TestAnglo(unittest.TestCase):
    """Hành vi với tài liệu tiếng Anh phải GIỮ NGUYÊN so với bản gốc của Fabrion."""

    def test_thousands_and_decimal(self):
        self.assertEqual(parse_number("2,742.5"), 2742.5)
        self.assertEqual(parse_number("2742.50"), 2742.5)
        self.assertEqual(parse_number("12,756.6"), 12756.6)

    def test_parentheses_negative(self):
        self.assertEqual(parse_number("(2,742.5)"), -2742.5)
        self.assertEqual(parse_number("(1,250)"), -1250.0)

    def test_leading_minus_variants(self):
        self.assertEqual(parse_number("-4,763.8"), -4763.8)
        self.assertEqual(parse_number("–4,763.8"), -4763.8)   # en-dash
        self.assertEqual(parse_number("−4,763.8"), -4763.8)   # minus U+2212

    def test_currency_and_percent(self):
        self.assertEqual(parse_number("$1,250"), 1250.0)
        self.assertEqual(parse_number("32%"), 32.0)

    def test_plain_thousands_group(self):
        self.assertEqual(parse_number("1,250"), 1250.0)


class TestEuropean(unittest.TestCase):
    """Dạng châu Âu — chỗ bản gốc sai 1000 lần."""

    def test_dot_is_thousands(self):
        self.assertEqual(parse_number("24.308", ","), 24308.0)
        self.assertEqual(parse_number("13.920.157"), 13920157.0)
        self.assertEqual(parse_number("154.270.286"), 154270286.0)

    def test_comma_is_decimal(self):
        self.assertEqual(parse_number("1.234,5"), 1234.5)
        self.assertEqual(parse_number("13,9"), 13.9)

    def test_negative_en_dash(self):
        self.assertEqual(parse_number("–13.975", ","), -13975.0)
        self.assertEqual(parse_number("–1.180", ","), -1180.0)


class TestAmbiguity(unittest.TestCase):
    """'1.234' thật sự nhập nhằng — phải theo locale của tài liệu, không tự đoán."""

    def test_single_group_follows_locale(self):
        """"1.234" một nhóm ba chữ số là nhập nhằng thật -> theo locale tài liệu."""
        self.assertEqual(parse_number("1.234", "."), 1.234)    # tài liệu Anh -> thập phân
        self.assertEqual(parse_number("1.234", ","), 1234.0)   # tài liệu Âu  -> nghìn
        self.assertEqual(parse_number("1,250", "."), 1250.0)
        self.assertEqual(parse_number("1,250", ","), 1.25)

    def test_multi_group_ignores_locale(self):
        """Từ hai nhóm trở lên thì không còn nhập nhằng, locale không đổi được kết quả."""
        self.assertEqual(parse_number("13.920.157", "."), 13920157.0)
        self.assertEqual(parse_number("1,234,567", ","), 1234567.0)

    def test_both_separators_ignores_locale(self):
        # dấu sau là thập phân, không cần locale và không phụ thuộc locale
        self.assertEqual(parse_number("1.234,5", "."), 1234.5)
        self.assertEqual(parse_number("1,234.5", ","), 1234.5)


class TestDetect(unittest.TestCase):
    def test_detect_european(self):
        self.assertEqual(detect_separator("Umsatzerlöse 24.308 und 13.920.157 sowie 1.234,5"), ",")

    def test_detect_anglo(self):
        self.assertEqual(detect_separator("Revenue 12,756.6 and 1,234,567 plus 2,742.5"), ".")

    def test_no_evidence_defaults_anglo(self):
        self.assertEqual(detect_separator("no numbers here"), ".")
        self.assertEqual(detect_separator("just 42 and 7"), ".")


class TestRegression(unittest.TestCase):
    """Ba giá trị thật đã xác minh thủ công trên tài liệu gốc."""

    OMV = "Scope-1- und Scope-2-Treibhausgasemissionen 13.920.157 10.769.800 10.286.093"
    AKP = "Total scope 1 and 2 GHG emissions 1,250 853 625 125"

    def test_omv_real_row(self):
        nums = input_numbers(self.OMV)
        for v in (13_920_157, 10_769_800, 10_286_093):
            self.assertTrue(covered(v, nums), f"{v} không tìm thấy")

    def test_akerbp_real_row(self):
        nums = input_numbers(self.AKP)
        for v in (1250, 853, 625, 125):
            self.assertTrue(covered(v, nums), f"{v} không tìm thấy")

    def test_omv_not_misread_as_decimal(self):
        """Lỗi cũ: 24.308 -> 24.308. Phải KHÔNG còn khi tài liệu đã nhận là châu Âu."""
        nums = input_numbers("Umsatzerlöse 24.308 26.194 sowie 13.920.157", ",")
        self.assertTrue(covered(24308, nums))
        self.assertFalse(covered(24.308, nums), "vẫn đọc nhầm thành số thập phân")


class TestTextMatching(unittest.TestCase):
    """Giá trị không phải số phải khớp bằng chuỗi con đã chuẩn hoá."""

    HAY = normalize("Konzernabschluss der OMV Aktiengesellschaft, In EUR Mio")

    def test_text_value_found(self):
        self.assertTrue(covered("EUR", set(), self.HAY))
        self.assertTrue(covered("OMV Aktiengesellschaft", set(), self.HAY))

    def test_text_value_absent(self):
        self.assertFalse(covered("USD", set(), self.HAY))

    def test_numeric_value_ignores_haystack(self):
        self.assertTrue(covered(24308, {24308.0}, ""))
        self.assertFalse(covered(24308, {24.308}, ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)

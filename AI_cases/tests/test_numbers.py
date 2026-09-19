#!/usr/bin/env python3
"""Unit test cho shared/numbers.py — bộ đọc số fail-closed."""
import pathlib
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from shared.numbers import parse_number, is_number_token


def val(tok, sep="."):
    return parse_number(tok, sep)[0]


class TestHopLe(unittest.TestCase):
    def test_anh_my(self):
        self.assertEqual(val("12,756.6"), Decimal("12756.6"))
        self.assertEqual(val("1,250"), Decimal("1250"))
        self.assertEqual(val("838"), Decimal("838"))
        self.assertEqual(val("2742.50"), Decimal("2742.50"))

    def test_chau_au(self):
        self.assertEqual(val("24.308", ","), Decimal("24308"))
        self.assertEqual(val("13.920.157", ","), Decimal("13920157"))
        self.assertEqual(val("13,9", ","), Decimal("13.9"))

    def test_dau_am(self):
        for s in ("-4,763.8", "–4,763.8", "−4,763.8"):
            self.assertEqual(val(s), Decimal("-4763.8"), s)
        self.assertEqual(val("(1,250)"), Decimal("-1250"))

    def test_thap_phan_dung_dau(self):
        """".3333" không nhập nhằng trong locale dấu chấm — hồ sơ iXBRL của SEC
        dùng dạng này. Từ chối nó là từ chối quá tay, cũng làm mất dòng."""
        self.assertEqual(val(".3333"), Decimal("0.3333"))
        self.assertEqual(val(",5", ","), Decimal("0.5"))

    def test_thap_phan_dung_dau_sai_locale_thi_tu_choi(self):
        self.assertIsNone(val(".3333", ","))     # dấu chấm là phân cách nghìn
        self.assertIsNone(val(",5"))             # dấu phẩy là phân cách nghìn

    def test_phan_tram(self):
        self.assertEqual(val("32%"), Decimal("32"))


class TestTuChoi(unittest.TestCase):
    """Fail closed: không chắc thì từ chối, KHÔNG đoán."""

    def assertRejected(self, tok, sep="."):
        v, nil = parse_number(tok, sep)
        self.assertIsNone(v, f"{tok!r} đáng lẽ bị từ chối, lại ra {v}")
        self.assertFalse(nil, f"{tok!r} bị nhầm thành ô trống")

    def test_ngoac_lech(self):
        for s in ("(123", "123)", "((123))", "(12(3)", "(1,250"):
            self.assertRejected(s)

    def test_dau_chong_nhau(self):
        for s in ("--123", "+-123", "-+123", "−−5", "(-123)"):
            self.assertRejected(s)

    def test_nhom_khong_phai_ba_chu_so(self):
        self.assertRejected("1,23,4")
        self.assertRejected("1,2345")
        self.assertRejected("12,34")          # đúng ra là 12.34 kiểu Âu -> không đoán
        self.assertRejected("1.23.4", ",")
        self.assertRejected("1.2.3", ",")

    def test_rac(self):
        for s in (".", ",", "..", "(.)", "(,)", "-.", "%", "12%%", "1..2"):
            self.assertRejected(s)


class TestOTrong(unittest.TestCase):
    def test_gach_ngang_don_le_la_o_trong(self):
        for s in ("-", "–", "—", "−", "", "   "):
            self.assertEqual(parse_number(s), (None, True), s)

    def test_khong_cong_bo(self):
        for s in ("N/A", "n/a", "NULL", "n.a.", "NM"):
            self.assertEqual(parse_number(s), (None, True), s)

    def test_gach_ngang_kem_so_van_la_so(self):
        self.assertEqual(val("-123"), Decimal("-123"))


class TestCongVaBoDocKhongLechNhau(unittest.TestCase):
    """is_number_token pass thì parse_number PHẢI ra kết quả — và ngược lại."""

    CASES = ["(", ")", "(.)", ".", ",", "..", "(,)", "-", "+", "( )", "%",
             "1.2.3", "1,23,4", "--1", "(1", "1)", "-.", "0", "123", "1,250",
             "(1,250)", "12,756.6", "N/A", "", "24.308", "-", "12%%"]

    def test_khong_lech(self):
        for sep in (".", ","):
            for tok in self.CASES:
                v, nil = parse_number(tok, sep)
                self.assertEqual(is_number_token(tok, sep), v is not None or nil,
                                 f"lệch ở {tok!r} locale {sep!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

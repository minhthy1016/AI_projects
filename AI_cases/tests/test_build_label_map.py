#!/usr/bin/env python3
"""Unit test cho extraction/build_label_map.py — sinh bảng tên gọi từ iXBRL."""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from extraction import build_label_map as B


class TestChotLoaiNhan(unittest.TestCase):
    def test_nhan_la_chinh_con_so_bi_loai(self):
        """Hàng tổng phụ không in tên: ô đầu không rỗng lại là ô giá trị.
        Shell có '106,143' và '107,173' đứng làm nhãn theo đúng kiểu đó."""
        for bad in ("106,143", "(1.234)", "-12", "24.308", "3,5 %"):
            self.assertTrue(B.NUMERIC_LABEL.match(bad), bad)

    def test_nhan_that_khong_bi_loai(self):
        for ok in ("Total assets", "Umsatzerlöse", "Sum eiendeler",
                   "Ricavi della gestione caratteristica", "Ventas"):
            self.assertFalse(B.NUMERIC_LABEL.match(ok), ok)

    def test_nhan_ngay_thang_bi_loai(self):
        """Bảng biến động vốn đánh nhãn hàng bằng ngày, không bằng khoản mục."""
        for bad in ("At January 1, 2025", "31/12/2024", "Saldi al 31 dicembre 2024"):
            self.assertTrue(B.DATE_LIKE.match(bad), bad)

    def test_nhan_co_nam_o_giua_thi_giu(self):
        self.assertIsNone(B.DATE_LIKE.match("Revenue 2024 adjusted"))


class TestPhanLoaiBaoCao(unittest.TestCase):
    def test_ky_tuc_thoi_la_bang_can_doi(self):
        self.assertEqual(B.statement_of("Assets", ["instant"]), "balance_sheet")
        self.assertEqual(B.statement_of("Equity", ["instant"]), "balance_sheet")

    def test_goc_ten_luong_tien(self):
        self.assertEqual(
            B.statement_of("CashFlowsFromUsedInOperatingActivities", ["duration"]), "cash_flow")
        self.assertEqual(
            B.statement_of("IncreaseDecreaseInCashAndCashEquivalents", ["duration"]), "cash_flow")

    def test_con_lai_la_ket_qua_kinh_doanh(self):
        self.assertEqual(B.statement_of("Revenue", ["duration"]), "income_statement")
        self.assertEqual(B.statement_of("ProfitLoss", ["duration"]), "income_statement")

    def test_tien_uu_tien_ky_tuc_thoi(self):
        """CashAndCashEquivalents là kỳ tức thời -> bảng cân đối, kể cả khi nhãn
        nằm trong báo cáo lưu chuyển ('at beginning of year'). Nhờ vậy nhãn đó
        không bao giờ khớp trong bảng lưu chuyển và không sinh fact sai năm."""
        self.assertEqual(B.statement_of("CashAndCashEquivalents", ["instant"]), "balance_sheet")


class TestQuyUocDau(unittest.TestCase):
    """needs_flip là phép XOR giữa 'dấu có hiện ra' và 'thẻ khai sign=-'."""

    class FakeEl:
        def __init__(self, inner, parent_text, sign=None):
            self._inner, self._ptext, self._sign = inner, parent_text, sign
        def get(self, k, d=None):
            return self._sign if k == "sign" else d
        def itertext(self):
            return [self._inner]
        def getparent(self):
            outer = self
            class P:
                def itertext(self_inner): return [outer._ptext]
                def getparent(self_inner): return None
            return P()

    def flip(self, inner, ptext, sign=None):
        return B.needs_flip(self.FakeEl(inner, ptext, sign))

    def test_ngoac_hien_va_co_sign_thi_khong_doi(self):
        """Shell: cả hai đều có -> Docling đã đọc ra số âm, đổi nữa là sai."""
        self.assertFalse(self.flip("3,248", "(3,248)", "-"))

    def test_ngoac_hien_khong_sign_thi_doi(self):
        """Eni: in (3.262) nhưng XBRL khai +3262."""
        self.assertTrue(self.flip("3.262", "(3.262)", None))

    def test_khong_ngoac_co_sign_thi_doi(self):
        self.assertTrue(self.flip("1834", "1834", "-"))

    def test_khong_ngoac_khong_sign_thi_khong_doi(self):
        self.assertFalse(self.flip("24308", "24308", None))

    def test_dau_tru_cung_tinh_la_hien(self):
        self.assertFalse(self.flip("500", "-500", "-"))


class TestBangDaSinh(unittest.TestCase):
    """Kiểm trên bảng thật đã sinh, nếu có."""
    DIR = pathlib.Path(__file__).resolve().parents[1] / "data/labelmaps"

    def maps(self):
        return sorted(self.DIR.glob("*.json"))

    def setUp(self):
        if not self.maps():
            self.skipTest("chưa sinh bảng tên gọi nào")

    def test_dinh_dang_ba_phan_tu(self):
        for f in self.maps():
            for lab, v in json.loads(f.read_text(encoding="utf-8")).items():
                self.assertEqual(len(v), 3, f"{f.name}: {lab}")
                self.assertIn(":", v[0])
                self.assertIn(v[1], ("balance_sheet", "income_statement", "cash_flow"))
                self.assertIsInstance(v[2], bool)

    def test_shell_anh_xa_dung_tong_tai_san(self):
        """Ca từng sai khi viết tay: 'Total assets' phải ra ifrs-full:Assets."""
        f = self.DIR / "shell-2025.json"
        if not f.exists():
            self.skipTest("chưa sinh bảng Shell")
        m = json.loads(f.read_text(encoding="utf-8"))
        self.assertEqual(m["Total assets"][0], "ifrs-full:Assets")

    def test_nhieu_nhan_hon_bang_viet_tay(self):
        from extraction.doc_extract import PROFILES
        f = self.DIR / "shell-2025.json"
        if not f.exists():
            self.skipTest("chưa sinh bảng Shell")
        auto = len(json.loads(f.read_text(encoding="utf-8")))
        self.assertGreater(auto, len(PROFILES["shell-en"]["labels"]) * 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)

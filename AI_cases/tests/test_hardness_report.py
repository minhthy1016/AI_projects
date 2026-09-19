#!/usr/bin/env python3
"""Unit test cho validation/hardness_report.py — bảng điểm xuất ra CSV."""
import csv
import io
import contextlib
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from validation import hardness_report as H


class TestNenNgauNhien(unittest.TestCase):
    class F:
        def __init__(self, v): self.value = v

    def test_khop_het_khi_tui_so_chua_dung_gia_tri(self):
        gt = {1: self.F(100.0), 2: self.F(250.0)}
        self.assertEqual(H.chance_floor(gt, [{100.0, 250.0}]), 1.0)

    def test_khong_khop_gi(self):
        gt = {1: self.F(100.0), 2: self.F(250.0)}
        self.assertEqual(H.chance_floor(gt, [{7.0, 9.0}]), 0.0)

    def test_dung_sai_tuong_doi(self):
        """0,5% — đủ hấp thụ làm tròn hiển thị, không đủ để nhận nhầm."""
        gt = {1: self.F(10000.0)}
        self.assertEqual(H.chance_floor(gt, [{10040.0}]), 1.0)
        self.assertEqual(H.chance_floor(gt, [{10800.0}]), 0.0)

    def test_thieu_du_lieu_thi_tra_None(self):
        self.assertIsNone(H.chance_floor({}, [{1.0}]))
        self.assertIsNone(H.chance_floor({1: self.F(5.0)}, []))


class TestDocSo(unittest.TestCase):
    def test_doc_ca_hai_loi_viet(self):
        n = H.numbers_of("24.308 và 12,756.6")
        self.assertIn(24308.0, n)      # kiểu Âu
        self.assertIn(12756.6, n)      # kiểu Anh-Mỹ

    def test_bo_dau_va_ngoac(self):
        self.assertIn(1234.0, H.numbers_of("(1,234)"))


class TestBaoCaoThat(unittest.TestCase):
    """Chạy thật nếu đã có bản parse."""

    def setUp(self):
        have = [d for d in H.DOCS
                if (H.ROOT / f"data/parsed/{d[2]}.docling.json").exists()]
        if not have:
            self.skipTest("chưa có bản parse nào")

    def run_main(self, *extra):
        out = pathlib.Path(tempfile.mkdtemp()) / "r.csv"
        with contextlib.redirect_stdout(io.StringIO()):
            rc = H.main(["--out", str(out), *extra])
        self.assertEqual(rc, 0)
        return list(csv.DictReader(out.open(encoding="utf-8")))

    def test_co_dong_tong(self):
        rows = self.run_main()
        self.assertEqual(rows[-1]["company"], "TOTAL")

    def test_diem_tin_cay_dung_cong_thuc(self):
        """trust = precision × verifiability, không lẫn recall."""
        for r in self.run_main():
            if r["trust"]:
                self.assertAlmostEqual(
                    float(r["trust"]),
                    float(r["precision"]) * float(r["verifiability"]), places=3)

    def test_recall_khong_nam_trong_diem(self):
        """Hồi quy cho lỗi thiết kế đã sửa: recall_inscope thưởng cho việc khai
        ít nhãn, nên bảng sinh tự động phủ gấp 4 lần tài liệu lại bị chấm thấp
        hơn. Nó phải nằm ngoài điểm tin cậy."""
        for r in self.run_main():
            if r["trust"] and r["recall_inscope"]:
                t, p, v = (float(r[k]) for k in ("trust", "precision", "verifiability"))
                self.assertAlmostEqual(t, p * v, places=3)

    def test_nen_thap_hon_pham_vi(self):
        """Nếu nền cao ngang phạm vi thì kết quả là trùng hợp, không phải tín hiệu."""
        for r in self.run_main():
            if r["chance_floor"] and r["coverage_filing"]:
                self.assertLess(float(r["chance_floor"]), float(r["coverage_filing"]), r["company"])

    def test_moi_cot_deu_co_mat(self):
        need = {"company", "language", "label_map", "pdf_pages", "label_count",
                "guard_no_scale", "guard_no_section", "facts_extracted",
                "facts_comparable", "facts_exact", "gt_total", "gt_inscope",
                "gt_caught", "precision", "verifiability", "recall_inscope",
                "coverage_filing", "trust", "chance_floor", "signal_margin"}
        self.assertTrue(need <= set(self.run_main()[0]))


if __name__ == "__main__":
    unittest.main(verbosity=2)

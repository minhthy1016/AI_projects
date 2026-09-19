#!/usr/bin/env python3
"""Unit test cho shared/bbox.py — chuyển bbox đầu ra về TOPLEFT 4 số."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from shared.bbox import normalize_rows, page_heights, to_topleft

ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestToTopleft(unittest.TestCase):
    def test_bottomleft_lat_truc_y(self):
        # trang cao 792: t=598 (gần đỉnh) -> 194 tính từ đỉnh
        self.assertEqual(to_topleft([137.0, 598.0, 473.0, 286.0, "BOTTOMLEFT"], 792.0),
                         [137.0, 194.0, 473.0, 506.0])

    def test_ket_qua_y0_nho_hon_y1(self):
        l, y0, r, y1 = to_topleft([10, 700, 200, 650, "BOTTOMLEFT"], 792)
        self.assertLess(y0, y1)

    def test_enum_dang_chuoi_day_du(self):
        self.assertEqual(to_topleft([0, 10, 5, 2, "CoordOrigin.BOTTOMLEFT"], 100), [0, 90, 5, 98])

    def test_topleft_giu_nguyen_chi_cat_goc(self):
        self.assertEqual(to_topleft([1, 2, 3, 4, "TOPLEFT"], None), [1.0, 2.0, 3.0, 4.0])

    def test_khong_co_goc_coi_la_topleft(self):
        self.assertEqual(to_topleft([1, 2, 3, 4], None), [1.0, 2.0, 3.0, 4.0])

    def test_fail_closed(self):
        # thiếu chiều cao trang: không đoán, trả null
        self.assertIsNone(to_topleft([1, 2, 3, 4, "BOTTOMLEFT"], None))
        self.assertIsNone(to_topleft([1, 2, 3, 4, "WEIRD"], 792))
        self.assertIsNone(to_topleft([1, None, 3, 4, "BOTTOMLEFT"], 792))
        self.assertIsNone(to_topleft(None, 792))


class TestNormalizeRows(unittest.TestCase):
    def test_doi_tai_cho_va_dem_so_null(self):
        rows = [{"source_ref": {"page_no": 1, "bbox": [0, 90, 10, 80, "BOTTOMLEFT"]}},
                {"source_ref": {"page_no": 2, "bbox": [0, 90, 10, 80, "BOTTOMLEFT"]}},
                {"source_ref": {"page_no": 1, "bbox": None}}]
        self.assertEqual(normalize_rows(rows, {1: 100.0}), 1)
        self.assertEqual(rows[0]["source_ref"]["bbox"], [0.0, 10.0, 10.0, 20.0])
        self.assertIsNone(rows[1]["source_ref"]["bbox"])
        self.assertIsNone(rows[2]["source_ref"]["bbox"])


class TestPageHeights(unittest.TestCase):
    DOC = ROOT / "data/parsed/akerbp-canon.docling.json"

    @unittest.skipUnless(DOC.exists(), "cần data/parsed (bị gitignore)")
    def test_doc_tu_docling(self):
        h = page_heights(self.DOC)
        self.assertTrue(h)
        self.assertTrue(all(isinstance(k, int) and v > 0 for k, v in h.items()))


if __name__ == "__main__":
    unittest.main()

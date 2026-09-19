#!/usr/bin/env python3
"""Unit test cho tầng Gold.

File này trước đây KHÔNG CÓ test, vì toàn bộ là code mức module — không import
được thì không test được. Và chính vì không ai chạy nó dưới kính hiển vi nên một
dấu hiệu tồn tại dưới dạng `if ... pass` suốt mà không ai thấy.
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from signals.compute_signals import build_series, change, compute

REF = {"page_no": 1, "table_id": "t", "col_header_path": ["x", "2025"], "verbatim_span": "1"}


def q(scope, year, value, own=False, subtotal=True):
    return {"claim_type": "quantitative", "is_subtotal": subtotal, "scope": scope,
            "is_company_specific": own, "period_end": f"{year}-12-31", "value": value,
            "source_ref": REF}


def target(scope, year, covers3=False, base_mt=None, base_year=None):
    return {"claim_type": "target", "scope": scope, "target_year": year,
            "target_covers_scope3": covers3, "baseline_value_mt": base_mt,
            "baseline_year": base_year, "source_ref": REF}


class TestChuoiSoLieu(unittest.TestCase):
    def test_bo_qua_o_trong(self):
        """value=None là KHÔNG CÔNG BỐ, không phải 0 — không được vào chuỗi."""
        series, _, _ = build_series([q("scope_1", 2024, None), q("scope_1", 2025, 5)])
        self.assertEqual(series[("scope_1", "esrs")], {2025: 5})

    def test_phat_hien_ghi_de(self):
        """Hai giá trị khác nhau cho cùng (scope, năm) phải được cảnh báo, không
        được lặng lẽ lấy cái sau."""
        _, _, warn = build_series([q("scope_1", 2025, 5), q("scope_1", 2025, 9)])
        self.assertEqual(len(warn), 1)
        self.assertIn("2025", warn[0])

    def test_trung_gia_tri_thi_khong_canh_bao(self):
        _, _, warn = build_series([q("scope_1", 2025, 5), q("scope_1", 2025, 5)])
        self.assertEqual(warn, [])


class TestPhanTramThayDoi(unittest.TestCase):
    def test_goc_bang_0_tra_none_thay_vi_sap(self):
        series = {("s", "esrs"): {2019: 0, 2025: 100}}
        self.assertIsNone(change(series, ("s", "esrs")))

    def test_mot_nam_thi_khong_tinh_duoc(self):
        self.assertIsNone(change({("s", "esrs"): {2025: 100}}, ("s", "esrs")))

    def test_tinh_dung(self):
        r = change({("s", "esrs"): {2019: 200, 2025: 100}}, ("s", "esrs"))
        self.assertEqual(r[0], -50.0)


class TestDauHieuPhanChiPhoiKhongCoMucTieu(unittest.TestCase):
    """Dấu hiệu này từng là khối `if ... pass` — tính rồi không phát gì."""

    def test_kich_hoat_khi_scope3_lon_ma_khong_co_muc_tieu(self):
        rows = [q("combined_1_2_reported", 2017, 1_250_000),
                q("combined_1_2_reported", 2024, 853_000),
                q("scope_3", 2024, 71_458_000),
                target("combined_1_2_reported", 2030),
                target("combined_1_2_reported", 2050)]
        names = [s["signal"] for s in compute(rows)[0]]
        self.assertIn("dominant_scope_not_targeted", names)

    def test_khong_kich_hoat_khi_da_co_muc_tieu_scope3(self):
        rows = [q("combined_1_2_market", 2019, 13_920_157),
                q("combined_1_2_market", 2025, 10_286_093),
                q("scope_3", 2019, 134_419_405), q("scope_3", 2025, 154_270_286),
                target("scope_3", 2030, covers3=True)]
        names = [s["signal"] for s in compute(rows)[0]]
        self.assertNotIn("dominant_scope_not_targeted", names)

    def test_khong_kich_hoat_khi_scope3_khong_chi_phoi(self):
        rows = [q("combined_1_2_market", 2024, 1_000_000),
                q("combined_1_2_market", 2025, 900_000),
                q("scope_3", 2025, 2_000_000),
                target("combined_1_2_market", 2030)]
        names = [s["signal"] for s in compute(rows)[0]]
        self.assertNotIn("dominant_scope_not_targeted", names)


class TestDoiChieuNamGoc(unittest.TestCase):
    def test_in_du_moi_dong_khong_dung_o_dong_dau(self):
        """Bản cũ có `break` nên chỉ in MỘT dòng dù có nhiều năm gốc."""
        rows = [q("combined_1_2_market", 2019, 13_900_000),
                q("combined_1_2_market", 2025, 10_000_000),
                q("scope_3", 2019, 113_700_000, own=True),
                q("scope_3", 2025, 91_000_000, own=True),
                target("combined_1_2_market", 2030, base_mt=13.9, base_year=2019),
                target("scope_3", 2030, covers3=True, base_mt=113.7, base_year=2019)]
        _, lines, _ = compute(rows)
        self.assertEqual(len(lines), 2)

    def test_lech_thi_phat_dau_hieu(self):
        rows = [q("combined_1_2_market", 2019, 13_900_000),
                q("combined_1_2_market", 2025, 10_000_000),
                target("combined_1_2_market", 2030, base_mt=99.9, base_year=2019)]
        names = [s["signal"] for s in compute(rows)[0]]
        self.assertIn("baseline_mismatch", names)


class TestMoiDauHieuDeuCoBangChung(unittest.TestCase):
    def test_khong_dau_hieu_nao_thieu_bang_chung(self):
        """Sản phẩm mang tính cáo buộc: không bằng chứng thì không phát."""
        import json
        for name in ("omv-2025-signals.jsonl", "akerbp-2024-signals.jsonl"):
            f = pathlib.Path(__file__).resolve().parents[1] / "data/extracted" / name
            if not f.exists():
                self.skipTest(f"chưa có {name}")
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                s = json.loads(line)
                self.assertTrue(s["evidence"], f"{s['signal']} không có bằng chứng")
                for e in s["evidence"]:
                    self.assertTrue(e.get("verbatim_span"), s["signal"])
                    self.assertTrue(e.get("page_no"), s["signal"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

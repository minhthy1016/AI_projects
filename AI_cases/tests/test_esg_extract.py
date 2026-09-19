#!/usr/bin/env python3
"""Unit test cho esg_extract — nhận cột và hình dạng bản ghi Silver B."""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from extraction.esg_extract import column_map, unify_keys, PROFILES

DATA = pathlib.Path(__file__).resolve().parents[1] / "data/extracted"


class TestNhanDienCot(unittest.TestCase):
    def test_bo_qua_cot_nhan(self):
        """Năm ở cột 0 là nhãn dòng. Bảng mốc của OMV có hàng "2030"."""
        self.assertEqual(column_map([["2030"], ["Absolute Reduktion um ≥30%"]])[1], [])

    def test_header_hai_tang_lay_dung_nhom(self):
        grid = [["", "", "Operational control", "Operational control", "Equity"],
                ["Emission source", "Unit", "2024", "2030 target", "2024"],
                ["Gross scope 1", "1,000 t", "838", "", "405"]]
        _, cols = column_map(grid)
        self.assertEqual([(c[0], c[3], c[2]) for c in cols],
                         [(2, "2024", "operational control"),
                          (3, "2030", "operational control"),
                          (4, "2024", "equity")])

    def test_nhan_lap_lai_mo_nhom_moi_khi_hang_nhom_trong(self):
        """Không có hàng nhóm thì mốc sang nhóm hai là nhãn cột LẶP LẠI."""
        grid = [["Emission source", "Unit", "Base year (2017)", "2024", "Base year (2017)", "2024"],
                ["Gross scope 1", "1,000 t", "1,250", "838", "666", "405"]]
        _, cols = column_map(grid)
        self.assertEqual([c[2] for c in cols],
                         ["operational control"] * 2 + ["equity"] * 2)


class TestNamGoc(unittest.TestCase):
    def test_nhan_duoc_ca_hai_ngon_ngu(self):
        """"Basisjahr" KHÔNG chứa "base" — dùng chuỗi tiếng Anh cứng là sai
        toàn bộ dòng của OMV."""
        import re
        omv, akp = PROFILES["omv"]["baseline_re"], PROFILES["akerbp"]["baseline_re"]
        self.assertTrue(re.search(omv, "2019 (Basisjahr)", re.I))
        self.assertTrue(re.search(akp, "Base year (2017)", re.I))
        self.assertFalse(re.search(omv, "2024", re.I))


class TestHinhDangBanGhi(unittest.TestCase):
    def test_unify_keys_dien_none(self):
        rows = [{"a": 1, "b": 2}, {"a": 3, "c": 4}]
        out = unify_keys(rows)
        self.assertEqual({frozenset(r) for r in out}, {frozenset({"a", "b", "c"})})
        self.assertIsNone(out[0]["c"])

    def test_file_that_chi_co_mot_hinh_dang(self):
        """Một bảng thì phải có một hình dạng — hai nhánh ghi vào cùng bảng
        Silver B từng sinh ra hai tập trường khác nhau."""
        for name in ("omv-2025-esg.jsonl", "akerbp-2024-esg.jsonl"):
            f = DATA / name
            if not f.exists():
                self.skipTest(f"chưa có {name}")
            rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
            self.assertEqual(len({frozenset(r) for r in rows}), 1, name)

    def test_muc_tieu_khong_co_ky_bao_cao(self):
        for name in ("omv-2025-esg.jsonl", "akerbp-2024-esg.jsonl"):
            f = DATA / name
            if not f.exists():
                self.skipTest(f"chưa có {name}")
            rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
            for r in rows:
                if r["claim_type"] == "target":
                    self.assertIsNone(r["period_end"], r["claim_id"])


class TestKhongTrungId(unittest.TestCase):
    def test_claim_id_duy_nhat(self):
        for name in ("omv-2025-esg.jsonl", "akerbp-2024-esg.jsonl"):
            f = DATA / name
            if not f.exists():
                self.skipTest(f"chưa có {name}")
            rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
            ids = [r["claim_id"] for r in rows]
            self.assertEqual(len(ids), len(set(ids)), f"{name}: trùng claim_id")


if __name__ == "__main__":
    unittest.main(verbosity=2)

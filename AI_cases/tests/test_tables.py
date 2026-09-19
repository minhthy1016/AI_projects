#!/usr/bin/env python3
"""Unit test cho shared/tables.py — nguồn duy nhất nhận diện hàng tiêu đề.

Logic này từng có HAI BẢN (year_columns trong doc_extract, column_map trong
esg_extract) và bản sao đó đã tự chứng minh là tai hại: lỗi "không bỏ qua cột 0"
được sửa ở một bên, bên kia vẫn còn và chỉ lộ ra ở vòng rà soát sau.

Nên các test ở đây chạy trên CẢ HAI chế độ, để một quy tắc không thể chỉ đúng
với một họ tài liệu.
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from shared.tables import header_columns

BOTH = (True, False)      # bare_year_only


class TestQuyTacApDungChoCaHaiCheDo(unittest.TestCase):

    def test_bo_qua_cot_nhan(self):
        """Năm ở cột 0 là NHÃN DÒNG, không phải tiêu đề cột — đúng ở cả hai."""
        grid = [["1. Jänner 2025", "327", "1.520"]]
        for bare in BOTH:
            self.assertEqual(header_columns(grid, bare_year_only=bare)[1], [],
                             f"bare_year_only={bare}")

    def test_chon_hang_nhieu_cot_nam_nhat(self):
        grid = [["", "", "Nhóm 2024", ""],
                ["Nhãn", "Đơn vị", "2024", "2023"]]
        for bare in BOTH:
            ri, cols = header_columns(grid, bare_year_only=bare)
            self.assertEqual(ri, 1, f"bare_year_only={bare}")
            self.assertEqual([c.year for c in cols], ["2024", "2023"])

    def test_luoi_rong(self):
        for bare in BOTH:
            self.assertEqual(header_columns([], bare_year_only=bare), (None, []))
            self.assertEqual(header_columns([[]], bare_year_only=bare), (None, []))


class TestKhacBietCoLyDo(unittest.TestCase):
    """Hình dạng ô tiêu đề là khác biệt THẬT giữa hai họ tài liệu, không phải
    trùng lặp ngẫu nhiên — nên nó được tham số hoá chứ không bị xoá."""

    def test_tai_chinh_chi_nhan_nam_tran(self):
        for cell in ("2024)", "2024€", "FY2024x", "2024 target"):
            self.assertEqual(header_columns([["", cell]], bare_year_only=True)[1], [],
                             f"{cell!r} không được nhận bên tài chính")

    def test_esg_nhan_cum_tu_chua_nam(self):
        for cell in ("Base year (2017)", "2030 target", "31.12.2024"):
            _, cols = header_columns([["", cell]], bare_year_only=False)
            self.assertEqual(len(cols), 1, f"{cell!r} phải nhận được bên ESG")

    def test_marker_chi_co_o_che_do_tai_chinh(self):
        _, cols = header_columns([["", "2024 1"]], bare_year_only=True)
        self.assertEqual(cols[0].marker, "1")
        _, cols = header_columns([["", "2024 1"]], bare_year_only=False)
        self.assertEqual(cols[0].marker, "")


class TestNhomCot(unittest.TestCase):

    def test_lay_tu_hang_tren_khi_co(self):
        grid = [["", "", "Operational control", "Equity"],
                ["Nhãn", "Đơn vị", "2024", "2024"]]
        _, cols = header_columns(grid)
        self.assertEqual([c.group for c in cols], ["operational control", "equity"])

    def test_nhan_lap_lai_mo_nhom_moi_khi_hang_tren_trong(self):
        grid = [["Nhãn", "Base year (2017)", "2024", "Base year (2017)", "2024"]]
        _, cols = header_columns(grid)
        self.assertEqual([c.group for c in cols],
                         ["operational control"] * 2 + ["equity"] * 2)

    def test_is_target(self):
        _, cols = header_columns([["", "2024", "2030 target"]])
        self.assertEqual([c.is_target for c in cols], [False, True])


class TestHaiBoDocDongYNhau(unittest.TestCase):
    """Hai hàm bọc phải trả về đúng cái header_columns đưa ra."""

    def test_doc_extract_va_esg_extract_dung_chung_nguon(self):
        from extraction.doc_extract import year_columns
        from extraction.esg_extract import column_map
        grid = [["", "Anhangangabe", "2025", "2024 1"]]
        ri_doc, cols_doc = year_columns(grid)
        ri_esg, cols_esg = column_map(grid)
        self.assertEqual(ri_doc, ri_esg)
        self.assertEqual([c[0] for c in cols_doc], [c[0] for c in cols_esg])


if __name__ == "__main__":
    unittest.main(verbosity=2)

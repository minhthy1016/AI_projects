#!/usr/bin/env python3
"""Unit test cho phần chuẩn hoá nhãn của doc_extract.

Lý do file này tồn tại: `norm_label` từng dùng r"\s*[\d¹²³\*†]{1,2}\)?$", coi mọi
chữ số cuối nhãn là ký hiệu chú thích. "Revenue 2024" thành "Revenue 20", và
"Equity as of 31.12.2022 / 2023 / 2024" gộp hết thành một nhãn. Lỗi không làm
chương trình dừng — nó lặng lẽ đổi nhãn, nên không có test thì không ai biết.
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from extraction.doc_extract import norm_label, squash, year_columns, YEAR_CELL


class TestKhongCatPhanMangNghia(unittest.TestCase):
    """Chữ số trần ở cuối nhãn PHẢI được giữ — nó thường là năm hoặc kỳ."""

    def test_nam_o_cuoi(self):
        for s in ("Revenue 2024", "Q1 2025", "Scope 3 emissions 2019",
                  "Equity as of 31.12.2022", "Anhangangabe 7", "davon CH 4 2"):
            self.assertEqual(norm_label(s), s, f"{s!r} bị cắt mất đuôi")

    def test_cac_nam_khac_nhau_khong_gop_lam_mot(self):
        """Hỏng kiểu nguy hiểm nhất: ba dòng khác nhau thành cùng một nhãn."""
        labels = [f"Equity as of 31.12.{y}" for y in (2022, 2023, 2024)]
        self.assertEqual(len({norm_label(x) for x in labels}), 3)


class TestCatKyHieuChuThich(unittest.TestCase):
    """Chỉ cắt những dạng chắc chắn là chú thích."""

    def test_so_kem_ngoac(self):
        self.assertEqual(norm_label("Total assets 1)"), "Total assets")
        self.assertEqual(norm_label("Emission source/category 1) 2) 3)"),
                         "Emission source/category")

    def test_chu_so_mu(self):
        self.assertEqual(norm_label("Umsatzerlöse¹"), "Umsatzerlöse")
        self.assertEqual(norm_label("Total²³"), "Total")

    def test_ky_hieu(self):
        self.assertEqual(norm_label("Revenue*"), "Revenue")
        self.assertEqual(norm_label("Total†"), "Total")
        self.assertEqual(norm_label("Net income‡"), "Net income")


class TestChuanHoaKhoangTrang(unittest.TestCase):
    def test_gop_khoang_trang(self):
        self.assertEqual(norm_label("  Summe   Aktiva  "), "Summe Aktiva")

    def test_squash_bo_khoang_trang(self):
        """Docling thỉnh thoảng nuốt dấu cách: 'Summe Aktiva' -> 'SummeAktiva'."""
        self.assertEqual(squash("Summe Aktiva"), squash("SummeAktiva"))
        self.assertEqual(squash("von OMV"), squash("vonOMV"))

    def test_squash_khong_gop_nhan_khac_nhau(self):
        self.assertNotEqual(squash("Total assets"), squash("Total liabilities"))


class TestNhanThat(unittest.TestCase):
    """Mọi nhãn trong LABEL_MAP phải đi qua norm_label mà không đổi —
    nếu đổi, nghĩa là quy tắc chuẩn hoá đang đụng vào chính dữ liệu cấu hình."""

    def test_label_map_khong_bi_bien_dang(self):
        from extraction.doc_extract import PROFILES
        import re
        for pname, prof in PROFILES.items():
            for k in prof["labels"]:
                self.assertEqual(norm_label(k), re.sub(r"\s+", " ", k.strip()),
                                 f"[{pname}] nhãn {k!r} bị chuẩn hoá làm biến dạng")


class TestNhanDienHangTieuDe(unittest.TestCase):
    """year_columns từng nhận nhầm HÀNG DỮ LIỆU làm hàng tiêu đề."""

    def test_bo_qua_cot_nhan(self):
        """Năm nằm ở cột 0 là NHÃN DÒNG, không phải tiêu đề cột.

        Bảng biến động vốn chủ của OMV có hàng "1. Jänner 2025" ở cột 0; bản
        trước nhận nó làm hàng tiêu đề rồi bảng đó tranh mất concept ProfitLoss
        với báo cáo kết quả kinh doanh thật.
        """
        grid = [["1. Jänner 2025", "327", "1.520"],
                ["Jahresüberschuss", "—", "1.520"]]
        self.assertEqual(year_columns(grid), (None, []))

    def test_chon_hang_nhieu_cot_nam_nhat(self):
        """Header hai tầng: hàng 0 lẫn một năm, hàng 1 mới là tiêu đề thật."""
        grid = [["", "", "Operational control 2024", ""],
                ["Emission source", "Unit", "2024", "2023"],
                ["Gross scope 1", "1,000 t", "838", "812"]]
        ri, cols = year_columns(grid)
        self.assertEqual(ri, 1)
        self.assertEqual([c[1] for c in cols], ["2024", "2023"])

    def test_giu_duoc_marker_chu_thich(self):
        grid = [["", "Anhangangabe", "2025", "2024 1"]]
        ri, cols = year_columns(grid)
        self.assertEqual(cols, [(2, "2025", ""), (3, "2024", "1")])

    def test_duoi_la_khong_nhan_thi_khong_phai_cot_nam(self):
        """"2024)" / "2024€" từng ra marker ")" và "€" rồi lọt vào provenance."""
        for cell in ("2024)", "2024€", "FY2024x"):
            self.assertIsNone(YEAR_CELL.search(cell), f"{cell!r} không được nhận là cột năm")

    def test_duoi_la_chu_thich_that_thi_nhan(self):
        for cell, marker in (("2024*", "*"), ("2024¹", "¹"), ("2024 1", "1")):
            m = YEAR_CELL.search(cell)
            self.assertIsNotNone(m, cell)
            self.assertEqual(m.group(2), marker)


class TestDongRongKhongGianhNhan(unittest.TestCase):
    """Hồi quy: dòng khớp nhãn nhưng không có số không được chiếm chỗ concept.

    Bảng cân đối Aker BP có hai dòng cùng nhãn 'Cash and cash equivalents':
    một tiêu đề phụ rỗng, một dòng số thật ngay dưới. Bản cũ gọi claimed.add()
    trước khi đọc số, nên dòng rỗng giành mất concept và dòng có số bị loại là
    'trùng' — mất 2 fact, chỉ hiện ra dưới dạng bộ đếm dup tăng thêm 1.
    """
    DOC = pathlib.Path(__file__).resolve().parents[1] / "data/parsed/akerbp-canon.docling.json"

    def setUp(self):
        if not self.DOC.exists():
            self.skipTest("chưa có bản parse Aker BP")
        import io, contextlib
        from extraction.doc_extract import extract
        with contextlib.redirect_stderr(io.StringIO()):
            self.rows = extract(str(self.DOC), "AKERBP", "akerbp-en")

    def test_cash_ra_du_hai_ky(self):
        got = {r["period_end"]: r["value"] for r in self.rows
               if r["line_item_canonical"] == "ifrs-full:CashAndCashEquivalents"}
        self.assertEqual(got, {"2024-12-31": 4146900000, "2023-12-31": 3388400000})

    def test_khong_sinh_khoa_trung(self):
        import collections
        keys = [(r["line_item_canonical"], r["period_end"]) for r in self.rows]
        dup = [k for k, n in collections.Counter(keys).items() if n > 1]
        self.assertEqual(dup, [], "nới claimed không được làm concept ra hai lần")


class TestDonViSuyTuCaTaiLieu(unittest.TestCase):
    """document_scale() chỉ được suy khi cả tài liệu khai ĐÚNG MỘT cặp."""

    def prof(self):
        return dict(scale_re=r"In\s+([A-Z]{3})\s+(Mio|Tsd)",
                    scale_map={"Tsd": 1_000, "Mio": 1_000_000})

    def txt(self, *ss):
        return [dict(text=x, page_no=1, label="text", bbox=None) for x in ss]

    def test_mot_cap_duy_nhat_thi_suy_duoc(self):
        from extraction.doc_extract import document_scale
        self.assertEqual(document_scale(self.txt("In EUR Mio"), [], self.prof()),
                         (1_000_000, "EUR"))

    def test_hai_cap_thi_tu_choi(self):
        """Vừa Mio vừa Tsd -> không biết bảng nào theo bậc nào, phải bỏ."""
        from extraction.doc_extract import document_scale
        self.assertIsNone(document_scale(
            self.txt("In EUR Mio", "In EUR Tsd"), [], self.prof()))

    def test_khong_khai_gi_thi_tu_choi(self):
        from extraction.doc_extract import document_scale
        self.assertIsNone(document_scale(self.txt("không có gì"), [], self.prof()))

    def test_lay_ca_trong_o_bang(self):
        from extraction.doc_extract import document_scale
        tables = [dict(grid=[["In EUR Mio", "2025"]])]
        self.assertEqual(document_scale([], tables, self.prof()), (1_000_000, "EUR"))


class TestKyHieuTienTe(unittest.TestCase):
    def test_do_la_ra_USD(self):
        from extraction.doc_extract import CURRENCY_SYMBOL
        self.assertEqual(CURRENCY_SYMBOL["$"], "USD")

    def test_ky_hieu_la_giu_nguyen(self):
        """Fail closed: không đoán, để lộ ra ở kiểm tra hợp đồng dữ liệu."""
        from extraction.doc_extract import CURRENCY_SYMBOL
        self.assertIsNone(CURRENCY_SYMBOL.get("¥"))


class TestOtNamMergeNgang(unittest.TestCase):
    """Một năm ứng với nhiều cột: phải chọn đúng một, hoặc bỏ cả năm.

    Bảng KQKD của Eni có ô "2024" merge ngang hai cột con "Totale" và
    "di cui verso parti correlate". docling_io trải span nên grid mang "2024" ở
    cả hai cột, và bản cũ phát ra hai fact Revenue cho cùng 2024: 88.797 (đúng)
    và 2.997 (phần bên liên quan). Cả hai đều là số đọc đúng nên không cổng số
    học nào bắt được.
    """
    GRID = [
        ["", "", "2024", "2024", "2023", "2023"],
        ["(€ milioni)", "Note", "Totale", "di cui verso parti correlate",
         "Totale", "di cui verso parti correlate"],
        ["Ricavi", "", "88.797", "2.997", "93.717", "4.322"],
    ]

    def cols(self, value_subheader=None):
        from extraction.doc_extract import year_columns
        return year_columns(self.GRID, value_subheader)[1]

    def test_khong_khai_thi_bo_ca_nam(self):
        """Fail closed: thà mất năm còn hơn hai con số mâu thuẫn."""
        self.assertEqual(self.cols(), [])

    def test_khai_dung_thi_chon_cot_tong(self):
        self.assertEqual(self.cols("Totale"), [(2, "2024", ""), (4, "2023", "")])

    def test_khai_sai_thi_bo(self):
        self.assertEqual(self.cols("Total"), [])

    def test_bang_binh_thuong_khong_bi_anh_huong(self):
        from extraction.doc_extract import year_columns
        grid = [["", "Note", "2025", "2024"], ["Doanh thu", "", "1", "2"]]
        self.assertEqual(year_columns(grid)[1], [(2, "2025", ""), (3, "2024", "")])


class TestSectionTheoTrang(unittest.TestCase):
    def test_repsol_khai_du_bon_trang(self):
        """Bản render Repsol mất hết tiêu đề báo cáo; section khai theo trang."""
        from extraction.doc_extract import PROFILES
        m = PROFILES["repsol-es"]["section_by_page"]
        self.assertEqual(set(m.values()), {"income_statement", "balance_sheet", "cash_flow"})

    def test_cac_profile_khac_khong_dung_den(self):
        """Khai tay là ngoại lệ, không phải mặc định."""
        from extraction.doc_extract import PROFILES
        for name, pr in PROFILES.items():
            if name != "repsol-es":
                self.assertNotIn("section_by_page", pr, name)


class TestBangTiepNoi(unittest.TestCase):
    """Bảng tiếp nối kế thừa báo cáo của bảng ngay trước, nếu cùng bộ cột năm.

    Chrome ngắt trang giữa một báo cáo; nửa sau rơi xuống trang mới không còn
    tiêu đề nào phía trên. TotalEnergies mất Income taxes và dòng financing
    theo đúng cách đó — 6 nhãn chết, recall 75%.
    """
    DOC = pathlib.Path(__file__).resolve().parents[1] / "data/parsed/tte-canon.docling.json"

    def setUp(self):
        if not self.DOC.exists():
            self.skipTest("chưa có bản parse TotalEnergies")
        import io, contextlib
        from extraction.doc_extract import extract
        with contextlib.redirect_stderr(io.StringIO()):
            self.rows = extract(str(self.DOC), "TTE", "tte-en")

    def test_ke_thua_ra_dung_fact(self):
        got = {(r["line_item_canonical"].split(":")[-1], r["period_end"]): r["value"]
               for r in self.rows}
        self.assertEqual(got.get(("IncomeTaxExpenseContinuingOperations", "2025-12-31")),
                         9092000000)
        self.assertEqual(got.get(("CashFlowsFromUsedInFinancingActivities", "2025-12-31")),
                         -9934000000)

    def test_co_ghi_nguon_section(self):
        """Fact đi đường kế thừa phải truy được, không lẫn với heading thật."""
        srcs = {r["section_source"] for r in self.rows}
        self.assertIn("continuation", srcs)
        self.assertIn("heading", srcs)

    def test_khong_sinh_khoa_trung(self):
        import collections
        keys = [(r["line_item_canonical"], r["period_end"]) for r in self.rows]
        self.assertEqual([k for k, n in collections.Counter(keys).items() if n > 1], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

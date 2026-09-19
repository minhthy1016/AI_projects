#!/usr/bin/env python3
"""Unit test cho validation/compare_to_truth.py — đo cả hai chiều, fail closed."""
import pathlib
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from validation import compare_to_truth as C


class TestScaleExponent(unittest.TestCase):
    def test_1000x(self):
        self.assertEqual(C.scale_exponent(Decimal(1000), Decimal(1)), 3)
        self.assertEqual(C.scale_exponent(Decimal(1), Decimal(1000)), -3)

    def test_trieu_duoc_bat(self):
        """Hồi quy: 'In EUR Mio' là lỗi thang đo phổ biến nhất của corpus này,
        bản cũ chỉ bắt đúng 1000 nên nó rơi vào rổ 'sai khác'."""
        self.assertEqual(C.scale_exponent(Decimal(24308), Decimal(24308000000)), -6)

    def test_thang_do_kem_lam_tron(self):
        """24.3 so với 24308: tỷ số 0.00099967, không đúng 0.001."""
        self.assertEqual(C.scale_exponent(Decimal("24.3"), Decimal(24308)), -3)

    def test_lech_that_thi_khong_nhan_nham(self):
        self.assertIsNone(C.scale_exponent(Decimal(1500), Decimal(1)))
        self.assertIsNone(C.scale_exponent(Decimal(1100), Decimal(1)))

    def test_khong_coi_bang_nhau_la_thang_do(self):
        self.assertIsNone(C.scale_exponent(Decimal(5), Decimal(5)))

    def test_zero_khong_chia(self):
        self.assertIsNone(C.scale_exponent(Decimal(0), Decimal(5)))
        self.assertIsNone(C.scale_exponent(Decimal(5), Decimal(0)))


class TestSplitCanonical(unittest.TestCase):
    def test_dang_chuan(self):
        self.assertEqual(C.split_canonical("ifrs-full:Revenue", "x"), ("ifrs-full", "Revenue"))

    def test_thieu_tien_to_thi_dung_han(self):
        """Bản cũ .split(':')[1] ném IndexError giữa vòng lặp."""
        with self.assertRaises(SystemExit):
            C.split_canonical("Revenue", "x")

    def test_hai_dau_hai_cham_thi_tu_choi(self):
        with self.assertRaises(SystemExit):
            C.split_canonical("a:b:c", "x")

    def test_rong_thi_tu_choi(self):
        for bad in ("", ":Revenue", "ifrs-full:"):
            with self.assertRaises(SystemExit):
                C.split_canonical(bad, "x")

    def test_giu_taxonomy_khong_cat_cut(self):
        """us-gaap:Revenue phải giữ tiền tố, nếu không sẽ khớp sai với
        ground truth ifrs-full:Revenue."""
        self.assertEqual(C.split_canonical("us-gaap:Revenue", "x")[0], "us-gaap")


class TestPeriodOf(unittest.TestCase):
    def test_balance_sheet_la_thoi_diem(self):
        r = dict(statement="balance_sheet", period_end="2025-12-31", period_start=None)
        self.assertEqual(C.period_of(r, "x"), ("2025-12-31",))

    def test_income_statement_la_ky(self):
        r = dict(statement="income_statement", period_start="2025-01-01", period_end="2025-12-31")
        self.assertEqual(C.period_of(r, "x"), ("2025-01-01", "2025-12-31"))

    def test_thieu_statement_thi_dung_han(self):
        with self.assertRaises(SystemExit):
            C.period_of(dict(period_end="2025-12-31"), "x")

    def test_thieu_period_thi_dung_han(self):
        with self.assertRaises(SystemExit):
            C.period_of(dict(statement="balance_sheet"), "x")
        with self.assertRaises(SystemExit):
            C.period_of(dict(statement="income_statement", period_end="2025-12-31"), "x")


class TestLoadExtracted(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.d = pathlib.Path(tempfile.mkdtemp())

    def write(self, text):
        p = self.d / "e.jsonl"
        p.write_text(text, encoding="utf-8")
        return p

    def test_doc_binh_thuong(self):
        p = self.write('{"line_item_canonical":"ifrs-full:Revenue","statement":"balance_sheet",'
                       '"period_end":"2025-12-31","value":5}\n')
        rows = C.load_extracted(p)
        self.assertEqual(rows[0]["key"], ("ifrs-full", "Revenue", ("2025-12-31",)))
        self.assertEqual(rows[0]["value"], Decimal(5))

    def test_value_none_la_o_trong_hop_le(self):
        """value=null là ô trống ("-" trong tài liệu), KHÔNG phải lỗi định dạng.

        Bản đầu gọi Decimal(str(None)) rồi chết; bản thứ hai dừng cả chương
        trình có nêu lý do — vẫn sai, vì chỉ một ô trống trong 136 dòng là
        không đối chiếu được gì. Đúng ra phải bỏ qua và đếm riêng.
        """
        p = self.write('{"line_item_canonical":"ifrs-full:Revenue","statement":"balance_sheet",'
                       '"period_end":"2025-12-31","value":null}\n'
                       '{"line_item_canonical":"ifrs-full:Assets","statement":"balance_sheet",'
                       '"period_end":"2025-12-31","value":7}\n')
        rows = C.load_extracted(p)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["key"][1], "Assets")

    def test_value_rac_van_dung_han(self):
        """Ô trống thì bỏ qua, nhưng chuỗi không đọc được thành số thì phải dừng."""
        p = self.write('{"line_item_canonical":"ifrs-full:Revenue","statement":"balance_sheet",'
                       '"period_end":"2025-12-31","value":"khong-phai-so"}\n')
        with self.assertRaises(SystemExit):
            C.load_extracted(p)

    def test_json_hong_thi_dung_han(self):
        with self.assertRaises(SystemExit):
            C.load_extracted(self.write("{khong phai json\n"))

    def test_dong_trong_duoc_bo_qua(self):
        p = self.write('{"line_item_canonical":"ifrs-full:Revenue","statement":"balance_sheet",'
                       '"period_end":"2025-12-31","value":5}\n\n')
        self.assertEqual(len(C.load_extracted(p)), 1)


class TestProfileConcepts(unittest.TestCase):
    def test_tra_ve_cap_taxonomy_concept(self):
        got = C.profile_concepts("omv-de")
        self.assertIn(("ifrs-full", "Revenue"), got)

    def test_profile_khong_co_thi_dung_han(self):
        with self.assertRaises(SystemExit):
            C.profile_concepts("khong-ton-tai")


class TestMaThoat(unittest.TestCase):
    """Chạy thật trên dữ liệu trong repo."""
    OMV_T = "data/esef/549300V62YJ9HTLRI486/2025-12-31/omvag-2025-12-31-1-de.json"

    def setUp(self):
        self.root = pathlib.Path(__file__).resolve().parents[1]
        if not (self.root / self.OMV_T).exists():
            self.skipTest("chưa tải corpus ESEF")

    def run_main(self, *extra):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = C.main(["--extracted", str(self.root / "data/extracted/omv-2025.jsonl"),
                         "--truth", str(self.root / self.OMV_T), *extra])
        return rc, buf.getvalue()

    def test_bo_sot_trong_pham_vi_lam_that_bai(self):
        """Bản cũ luôn thoát 0, kể cả khi lệch hoàn toàn."""
        rc, out = self.run_main("--profile", "omv-de")
        self.assertEqual(rc, 1)
        self.assertIn("bỏ sót", out.lower())

    def test_bao_cao_ca_hai_chieu(self):
        rc, out = self.run_main("--profile", "omv-de")
        self.assertIn("độ chính xác", out)
        self.assertIn("recall", out)

    def test_khong_co_profile_van_chay(self):
        rc, out = self.run_main()
        self.assertIn("BỎ SÓT", out)

    def test_khac_taxonomy_khong_bi_coi_la_khop(self):
        """Hồi quy: bản cũ cắt tiền tố rồi so, nên us-gaap:Revenue khớp với
        ground truth ifrs-full:Revenue và được tính là đúng 100%."""
        import io, contextlib, json, tempfile
        rec = dict(line_item_canonical="us-gaap:Revenue", statement="income_statement",
                   period_start="2025-01-01", period_end="2025-12-31", value=24308000000.0)
        f = pathlib.Path(tempfile.mkdtemp()) / "x.jsonl"
        f.write_text(json.dumps(rec) + "\n", encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = C.main(["--extracted", str(f), "--truth", str(self.root / self.OMV_T)])
        out = buf.getvalue()
        self.assertIn("khác taxonomy", out)
        self.assertNotIn("100.0%", out)
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

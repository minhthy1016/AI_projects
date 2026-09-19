#!/usr/bin/env python3
"""Unit test cho validation/coverage_esef.py — trần phải đi kèm nền ngẫu nhiên."""
import io
import contextlib
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from validation import coverage_esef as CV
from shared.text_match_locale import detect_separator, input_numbers, normalize, covered


class TestChiaCoBaoVe(unittest.TestCase):
    def test_mau_so_0_khong_nem_loi(self):
        """Bản cũ chia thẳng sub[2]/sub[0] và grand['fixed']/grand['n']."""
        self.assertIsNone(CV.pct(5, 0))
        self.assertIsNone(CV.pct(0, 0))

    def test_chia_binh_thuong(self):
        self.assertEqual(CV.pct(1, 2), 50.0)

    def test_fmt_none_ra_gach(self):
        self.assertIn("—", CV.fmt(None))
        self.assertIn("50", CV.fmt(50.0))


class TestNenNgauNhien(unittest.TestCase):
    """Phép đo trần khớp trên túi số của TOÀN tài liệu, không theo vị trí.

    Nên phải biết nền: bao nhiêu phần trăm khớp được chỉ do trùng hợp.
    """

    @classmethod
    def setUpClass(cls):
        if not all(CV.parse_path(d).exists() for d in CV.DOCS):
            raise unittest.SkipTest("chưa có bản parse — chạy parsing/docling_convert.py")
        cls.prep = {}
        for did in CV.DOCS:
            t = CV.doc_text(did)
            sep = detect_separator(t)
            cls.prep[did] = (input_numbers(t, sep), normalize(t))

    def do(self, gold_doc, text_doc):
        nums, hay = self.prep[text_doc]
        n = m = 0
        for k, v in CV.gold_values(gold_doc):
            if k in CV.ENCODED:
                continue
            n += 1
            m += bool(covered(v, nums, hay))
        return m / n * 100

    def test_nen_phai_thap_tren_ban_parse_canon(self):
        """Trên bản parse đầy đủ 300 trang, nền là 87% — trần 99% gần như vô
        nghĩa. Thu hẹp về các trang báo cáo tài chính kéo nền xuống dưới 20%.
        Nếu con số này vọt lên, phạm vi parse đã nở ra và trần phải đọc lại."""
        sai = self.do("akerbp_ar_fy2024", "omv_ar_fy2025")
        self.assertLess(sai, 20)

    def test_tran_cao_hon_nen(self):
        dung = self.do("akerbp_ar_fy2024", "akerbp_ar_fy2024")
        sai = self.do("akerbp_ar_fy2024", "omv_ar_fy2025")
        self.assertGreater(dung, sai)

    def test_unit_khong_con_mien_phi(self):
        """Trên bản parse đầy đủ, unit='USD' khớp 42/42 vào tài liệu OMV vì
        báo cáo 300 trang nào cũng nhắc USD. Trên bản canon thì không."""
        nums, hay = self.prep["omv_ar_fy2025"]
        units = [v for k, v in CV.gold_values("akerbp_ar_fy2024") if k == "unit"]
        self.assertTrue(units)
        self.assertFalse(any(covered(v, nums, hay) for v in units))

    def test_lech_quy_uoc_dau_duoc_tach_rieng(self):
        """Gold OMV ghi chi phí thuế +1834, tài liệu in -1.834."""
        nums, hay = self.prep["omv_ar_fy2025"]
        self.assertTrue(CV.sign_flipped(1834.0, nums, hay))
        self.assertFalse(CV.sign_flipped(0, nums, hay), "0 không có số đối")
        self.assertFalse(CV.sign_flipped("USD", nums, hay), "chuỗi không áp dụng")


class TestBaoCao(unittest.TestCase):
    def setUp(self):
        if not all(CV.parse_path(d).exists() for d in CV.DOCS):
            self.skipTest("chưa có bản parse — chạy parsing/docling_convert.py")

    def run_main(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = CV.main(list(argv))
        return rc, buf.getvalue()

    def test_in_ca_tran_va_nen(self):
        rc, out = self.run_main()
        self.assertEqual(rc, 0)
        self.assertIn("nền", out)
        self.assertIn("khoảng cách thật", out)

    def test_nguong_headroom_lam_that_bai(self):
        rc, out = self.run_main("--min-headroom", "90")
        self.assertEqual(rc, 1)

    def test_nguong_thap_thi_qua(self):
        rc, _ = self.run_main("--min-headroom", "5")
        self.assertEqual(rc, 0)


class TestThieuInput(unittest.TestCase):
    def test_thieu_gold_thi_bao_ro(self):
        """Bản cũ ném traceback từ trong docling_io, không nói thiếu gì."""
        old = CV.GOLD_DIR
        try:
            CV.GOLD_DIR = pathlib.Path("/khong/ton/tai/o/dau/ca")
            with self.assertRaises(SystemExit) as cm:
                CV.check_inputs()
            self.assertIn("gold", str(cm.exception).lower())
        finally:
            CV.GOLD_DIR = old

    def test_gold_nam_trong_AI_cases(self):
        """Yêu cầu chạy độc lập: không còn phụ thuộc repo fabrion."""
        for d in CV.DOCS:
            self.assertTrue(CV.gold_path(d).exists())
            self.assertIn("AI_cases", str(CV.gold_path(d)))
        src = pathlib.Path(CV.__file__).read_text(encoding="utf-8")
        self.assertNotIn("FABRION", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)

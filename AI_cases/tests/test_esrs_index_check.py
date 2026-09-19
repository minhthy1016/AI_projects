#!/usr/bin/env python3
"""Unit test cho đối soát mục lục ESRS.

Công cụ này SINH RA CÁO BUỘC, nên cái đáng test nhất không phải là nó tìm được
gì, mà là nó BIẾT KHI NÀO KHÔNG NÊN KẾT LUẬN.
"""
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from extraction.esrs_index_check import (INDEX_MIN_ROWS, MIN_DETECTION_RATE,
                                         find_index_pages, parse_index)

SCRIPT = ROOT / "extraction/esrs_index_check.py"
OMV = ROOT / "data/ir-pdf/omv/omv-2025.txt"
AKP = ROOT / "data/ir-pdf/akerbp/akerbp-2024.txt"


def run(txt, out):
    return subprocess.run([sys.executable, str(SCRIPT), "--txt", str(txt),
                           "--company-id", "TEST", "--out", str(out)],
                          capture_output=True, text=True, cwd=ROOT)


class TestNhanDienTrangMucLuc(unittest.TestCase):
    def test_theo_chu(self):
        pages = ["ESRS-Angabepflicht   Seite\nBP-1 Grundlagen   83\n", "khac"]
        self.assertEqual(find_index_pages(pages), [1])

    def test_theo_hinh_dang_khi_khong_co_tieu_de(self):
        """Hồ sơ Aker BP mở đầu trang bằng breadcrumb, không phải tiêu đề bảng."""
        body = "\n".join(f"  BP-{i}   section 1.{i}" for i in range(1, INDEX_MIN_ROWS + 1))
        self.assertEqual(find_index_pages(["breadcrumb dieu huong\n" + body]), [1])

    def test_it_dong_thi_khong_phai_muc_luc(self):
        """Trang nội dung cũng có mã ở tiêu đề mục, nhưng chỉ một hai cái."""
        self.assertEqual(find_index_pages(["E4-4 Ziele im Zusammenhang mit..."]), [])


class TestLoaiThamChieu(unittest.TestCase):
    def test_so_trang(self):
        rows = parse_index(["ESRS-Angabepflicht  Seite\nBP-1 Allgemeine Grundlagen    83\n"])
        self.assertEqual((rows[0]["claimed_page"], rows[0]["ref_kind"]), (83, "page"))

    def test_so_muc(self):
        body = "\n".join(f"  BP-{i}   section 1.{i}" for i in range(1, 6))
        rows = parse_index(["x\n" + body])
        self.assertEqual(rows[0]["ref_kind"], "section")

    def test_so_muc_khong_bi_coi_la_tieu_de(self):
        body = "\n".join(f"  BP-{i}   section 1.{i}" for i in range(1, 6))
        rows = parse_index(["x\n" + body])
        self.assertNotIn("section", rows[0]["title"].lower())


class TestKhiNaoKHONGKetLuan(unittest.TestCase):
    """Phần quan trọng nhất: công cụ phải phân biệt được
    "không tìm thấy mục lục" / "phương pháp không hợp" / "mọi thứ đều ổn"."""

    def test_khong_co_muc_luc_thi_bao_loi_va_khong_ghi_file(self):
        tmp = pathlib.Path("/tmp/_t_empty.txt"); tmp.write_text("khong co gi\f", encoding="utf-8")
        out = pathlib.Path("/tmp/_t_out1.jsonl")
        out.unlink(missing_ok=True)
        r = run(tmp, out)
        self.assertEqual(r.returncode, 2)
        self.assertFalse(out.exists(), "file rỗng sẽ bị hiểu nhầm là đối soát sạch")

    def test_phuong_phap_khong_hop_thi_khong_cao_buoc(self):
        """Aker BP: 46 dòng mục lục, 0 tag trong toàn tài liệu. Báo cả 46 là
        'khai có nhưng không thấy' sẽ là 46 cáo buộc sai."""
        if not AKP.exists():
            self.skipTest("chưa có tài liệu Aker BP")
        out = pathlib.Path("/tmp/_t_out2.jsonl"); out.unlink(missing_ok=True)
        r = run(AKP, out)
        self.assertEqual(r.returncode, 3)
        self.assertFalse(out.exists())
        self.assertIn("KHÔNG ÁP DỤNG ĐƯỢC", r.stderr)

    def test_phuong_phap_hop_thi_chay_binh_thuong(self):
        if not OMV.exists():
            self.skipTest("chưa có tài liệu OMV")
        out = pathlib.Path("/tmp/_t_out3.jsonl"); out.unlink(missing_ok=True)
        r = run(OMV, out)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(out.exists())
        self.assertEqual(len(out.read_text(encoding="utf-8").strip().splitlines()), 70)

    def test_nguong_duoc_khai_tuong_minh(self):
        self.assertGreater(MIN_DETECTION_RATE, 0)
        self.assertLess(MIN_DETECTION_RATE, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

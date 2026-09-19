#!/usr/bin/env python3
"""Unit test cho ingest/fetch_corpus.py — manifest phải không mất provenance."""
import json
import pathlib
import sys
import tempfile
import unittest
import urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ingest import fetch_corpus as fc


def row(path, source="esef", n=10):
    return dict(sha256="a" * 64, bytes=n, local_path=path, source=source,
                fetched_at="2026-01-01T00:00:00+00:00")


class ManifestBase(unittest.TestCase):
    def setUp(self):
        self.d = pathlib.Path(tempfile.mkdtemp())
        self.root = self.d / "data"
        self.root.mkdir()
        self._old = (fc.ROOT, fc.MANIFEST, list(fc._rows), list(fc._fail), set(fc._have))
        fc.ROOT, fc.MANIFEST = self.root, self.root / "manifest.jsonl"
        fc._rows.clear(); fc._fail.clear(); fc._have.clear()

    def tearDown(self):
        fc.ROOT, fc.MANIFEST = self._old[0], self._old[1]
        fc._rows[:], fc._fail[:] = self._old[2], self._old[3]
        fc._have.clear(); fc._have.update(self._old[4])
        fc.SKIP_EXISTING = False

    def write(self, rows):
        with fc.MANIFEST.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    def read(self):
        return [json.loads(l) for l in
                fc.MANIFEST.read_text(encoding="utf-8").splitlines() if l.strip()]


class TestGopManifest(ManifestBase):
    def test_tang_hong_khong_xoa_provenance_tang_kia(self):
        """Hồi quy: ESEF hỏng toàn phần từng xoá 16 dòng / 676 MB khỏi manifest."""
        cu = [row("data/esef/a.json"), row("data/esef/b.json"),
              row("data/sec/x.htm", source="sec-edgar")]
        self.write(cu)
        fc._rows.append(row("data/sec/x.htm", source="sec-edgar", n=99))  # chỉ SEC chạy
        merged = fc.write_manifest(fc.load_manifest())

        self.assertEqual(len(merged), 3)
        sau = self.read()
        self.assertEqual(sum(1 for r in sau if r["source"] == "esef"), 2,
                         "dòng ESEF phải còn nguyên khi tầng ESEF hỏng")

    def test_ghi_de_cung_local_path(self):
        self.write([row("data/sec/x.htm", n=10)])
        fc._rows.append(row("data/sec/x.htm", n=77))
        merged = fc.write_manifest(fc.load_manifest())
        self.assertEqual(len(merged), 1)
        self.assertEqual(self.read()[0]["bytes"], 77, "bản mới phải thay bản cũ")

    def test_manifest_trong(self):
        fc._rows.append(row("data/sec/x.htm"))
        fc.write_manifest(fc.load_manifest())
        self.assertEqual(len(self.read()), 1)

    def test_ghi_nguyen_tu_khong_de_lai_tmp(self):
        fc._rows.append(row("data/sec/x.htm"))
        fc.write_manifest(fc.load_manifest())
        self.assertEqual(list(self.root.glob("*.tmp")), [])


class TestDocManifestFailClosed(ManifestBase):
    def test_dong_hong_thi_dung_han(self):
        fc.MANIFEST.write_text('{"local_path": "a"}\n{khong phai json\n', encoding="utf-8")
        with self.assertRaises(SystemExit) as cm:
            fc.load_manifest()
        self.assertIn("dòng 2", str(cm.exception))

    def test_thieu_local_path_thi_dung_han(self):
        fc.MANIFEST.write_text('{"sha256": "x"}\n', encoding="utf-8")
        with self.assertRaises(SystemExit):
            fc.load_manifest()

    def test_dong_trong_duoc_bo_qua(self):
        fc.MANIFEST.write_text('{"local_path": "a"}\n\n', encoding="utf-8")
        self.assertEqual(len(fc.load_manifest()), 1)


class TestSkipExisting(ManifestBase):
    def test_mac_dinh_khong_skip(self):
        fc.SKIP_EXISTING = False
        fc._have.add("data/sec/x.htm")
        self.assertFalse(fc.have(self.root / "sec" / "x.htm"))

    def test_skip_can_ca_file_lan_dong_manifest(self):
        fc.SKIP_EXISTING = True
        p = self.root / "sec" / "x.htm"
        p.parent.mkdir(parents=True); p.write_bytes(b"x")
        self.assertFalse(fc.have(p), "có file nhưng chưa có dòng manifest -> phải tải lại")
        fc._have.add("data/sec/x.htm")
        self.assertTrue(fc.have(p))

    def test_co_dong_manifest_nhung_mat_file(self):
        fc.SKIP_EXISTING = True
        fc._have.add("data/sec/x.htm")
        self.assertFalse(fc.have(self.root / "sec" / "x.htm"))


class TestRetry(unittest.TestCase):
    def err(self, code, retry_after=None):
        hdrs = {"Retry-After": retry_after} if retry_after else {}
        return urllib.error.HTTPError("u", code, "m", hdrs, None)

    def test_403_khong_nam_trong_retry(self):
        """403 = UA sai hoặc IP bị chặn; thử lại chỉ làm SEC chặn lâu hơn."""
        self.assertNotIn(403, fc.RETRY_STATUS)

    def test_429_va_5xx_co_retry(self):
        for c in (429, 500, 502, 503, 504):
            self.assertIn(c, fc.RETRY_STATUS)

    def test_ton_trong_retry_after(self):
        self.assertEqual(fc._backoff(self.err(429, "7"), 0), 7.0)

    def test_retry_after_hong_thi_backoff_mu(self):
        self.assertEqual(fc._backoff(self.err(429, "Wed, 21 Oct 2026 07:28:00 GMT"), 3), 8)
        self.assertEqual(fc._backoff(self.err(503), 2), 4)

    def test_retry_after_bi_chan_tran(self):
        self.assertEqual(fc._backoff(self.err(429, "99999"), 0), 60.0)


class TestTargets(ManifestBase):
    def test_khong_de_len_ban_sua_tay(self):
        t = self.root / "ir-pdf" / "TARGETS.md"
        t.parent.mkdir(parents=True)
        t.write_text("ghi chú của tôi", encoding="utf-8")
        fc.write_targets()
        self.assertEqual(t.read_text(encoding="utf-8"), "ghi chú của tôi")

    def test_tao_khi_chua_co(self):
        fc.write_targets()
        self.assertTrue((self.root / "ir-pdf" / "TARGETS.md").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

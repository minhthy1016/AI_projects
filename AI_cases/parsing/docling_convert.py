#!/usr/bin/env python3
"""
Tầng 1 — PDF -> DoclingDocument JSON chính tắc.

Bản đầu tự định nghĩa một schema JSON riêng để chứa bảng và text. Đó là sai:
DoclingDocument đã có serialization chuẩn (`save_as_json`, schema 1.10.0), và
tầng schema_extraction của fabrion-extraction-evaluation đọc thẳng định dạng đó.
Tự chế thêm một format là dựng nguồn sự thật thứ hai cho cùng một dữ liệu —
đúng cái bẫy đã cảnh báo khi bàn về ClickHouse.

Ghi hai file cạnh nhau:
  <name>.docling.json  — DoclingDocument nguyên bản, không thêm bớt
  <name>.meta.json     — provenance của lần chạy (sha256 nguồn, page_range,
                          phiên bản parser, thời gian). Tách riêng để file
                          chính tắc giữ nguyên schema chuẩn.

Chạy bằng venv có docling:
  <fabrion>/.venv/bin/python docling_convert.py --pdf ... --pages 147-152 --out ...
"""
import argparse, hashlib, json, os, pathlib, sys, time

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--pages", default=None, help="vd 147-152 (1-indexed theo PDF gốc)")
    ap.add_argument("--out", required=True, help="đường dẫn .docling.json")
    ap.add_argument("--mps", action="store_true",
                    help="chạy model trên GPU Apple Silicon. Đo trên corpus này: "
                         "CHẬM HƠN CPU (84,9s vs 77,9s / 11 trang). Mặc định tắt.")
    a = ap.parse_args()

    # đặt trước khi import docling/torch, theo tools/parse/run/docling.py của Fabrion
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    from docling.document_converter import DocumentConverter

    kw = {}
    if a.pages:
        lo, hi = (a.pages.split("-") + [a.pages])[:2]
        kw["page_range"] = (int(lo), int(hi))
    if a.mps:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            AcceleratorDevice, AcceleratorOptions, PdfPipelineOptions)
        from docling.document_converter import PdfFormatOption
        po = PdfPipelineOptions()
        po.accelerator_options = AcceleratorOptions(device=AcceleratorDevice.MPS)
        conv = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=po)})
    else:
        conv = DocumentConverter()

    t0 = time.time()
    doc = conv.convert(a.pdf, **kw).document
    dt = time.time() - t0

    out = pathlib.Path(a.out)
    doc.save_as_json(out)
    meta = {
        "source": str(pathlib.Path(a.pdf).resolve()),
        "source_sha256": hashlib.sha256(pathlib.Path(a.pdf).read_bytes()).hexdigest(),
        "page_range": a.pages, "accelerator": "mps" if a.mps else "cpu",
        "parser": "docling",
        "parser_version": __import__("importlib.metadata", fromlist=["version"]).version("docling"),
        "convert_seconds": round(dt, 1),
    }
    out.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    print(f"    [docling] {len(doc.tables)} bảng, {len(doc.texts)} text, {dt:.1f}s", file=sys.stderr)
    print(f"{out.name} + {out.with_suffix('.meta.json').name}")

if __name__ == "__main__":
    main()

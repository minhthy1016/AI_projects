#!/usr/bin/env python3
"""Đọc DoclingDocument JSON chính tắc mà KHÔNG cần cài docling.

Docling kéo theo torch và bộ model; chỉ tầng chuyển đổi mới cần chúng. Các tầng
sau chỉ cần đọc JSON, nên parse thẳng bằng thư viện chuẩn. Nhờ vậy
doc_extract/esg_extract chạy được bằng python3 hệ thống.

Chuẩn hoá về đúng ba thứ mà extractor cần:
    tables : [{page_no, bbox, num_rows, num_cols, grid[[str]], cells[...]}]
    texts  : [{page_no, bbox, label, text}]
    meta   : nội dung .meta.json (sha256 nguồn, phiên bản parser, ...)

Lưu ý toạ độ: `prov.bbox` dùng gốc BOTTOMLEFT (t lớn = cao trên trang), còn
bbox của từng ô dùng TOPLEFT. Trộn hai hệ là so sánh sai chiều.
"""
import json, pathlib

def _bbox(b):
    if not b:
        return None
    return [b.get("l"), b.get("t"), b.get("r"), b.get("b"), b.get("coord_origin")]

def load(path):
    p = pathlib.Path(path)
    d = json.loads(p.read_text(encoding="utf-8"))
    if d.get("schema_name") != "DoclingDocument":
        raise ValueError(f"{p} không phải DoclingDocument (schema_name={d.get('schema_name')!r})")

    tables = []
    for t in d.get("tables", []):
        prov = (t.get("prov") or [{}])[0]
        data = t.get("data", {})
        grid = [[(c.get("text") or "").strip() for c in row] for row in data.get("grid", [])]
        cells = [{
            "text": (c.get("text") or "").strip(),
            "r0": c.get("start_row_offset_idx"), "r1": c.get("end_row_offset_idx"),
            "c0": c.get("start_col_offset_idx"), "c1": c.get("end_col_offset_idx"),
            "col_span": c.get("col_span"), "header": bool(c.get("column_header")),
            "bbox": _bbox(c.get("bbox")),
        } for c in data.get("table_cells", [])]
        tables.append(dict(page_no=prov.get("page_no"), bbox=_bbox(prov.get("bbox")),
                           num_rows=data.get("num_rows"), num_cols=data.get("num_cols"),
                           grid=grid, cells=cells))

    texts = []
    for x in d.get("texts", []):
        prov = (x.get("prov") or [{}])[0]
        txt = (x.get("text") or "").strip()
        if txt:
            texts.append(dict(page_no=prov.get("page_no"), bbox=_bbox(prov.get("bbox")),
                              label=str(x.get("label")), text=txt))

    meta_p = p.with_suffix(".meta.json")
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    meta.setdefault("source_sha256", str(d.get("origin", {}).get("binary_hash", "")))
    meta.setdefault("parser_version", d.get("version", "?"))
    return dict(tables=tables, texts=texts, meta=meta, origin=d.get("origin", {}))

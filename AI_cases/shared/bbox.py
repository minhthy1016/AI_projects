"""Chuẩn hoá bbox trong source_ref về gốc TOPLEFT, đúng 4 số.

Tầng parse (`parsing/docling_io.py`) CỐ Ý giữ nguyên toạ độ Docling kèm gốc:
`[l, t, r, b, "BOTTOMLEFT"]`. Logic ghép tiêu đề–bảng trong doc_extract và
esg_extract so sánh `bbox[1]` theo đúng hệ đó (t lớn = cao trên trang) —
đổi hệ ở tầng parse là đảo chiều mọi phép so sánh ấy.

Nên việc chuyển hệ chỉ làm ở ĐẦU RA, trên các row đã trích xong: không động
tới logic, không động tới metric, chỉ đổi thứ được ghi vào source_ref.
Hợp đồng (contracts/*.json) yêu cầu `[x0, y0, x1, y1]`, gốc trên-trái, y0 < y1.
"""
import json
import pathlib


def page_heights(parsed_path) -> dict:
    """{page_no: chiều cao trang} đọc thẳng từ khối `pages` của DoclingDocument."""
    d = json.loads(pathlib.Path(parsed_path).read_text(encoding="utf-8"))
    out = {}
    for k, p in (d.get("pages") or {}).items():
        h = (p.get("size") or {}).get("height")
        if h:
            out[int(p.get("page_no", k))] = float(h)
    return out


def to_topleft(bbox, height):
    """[l, t, r, b, origin?] -> [l, top, r, bottom] gốc trên-trái.

    None khi không chuyển được (thiếu bbox, thiếu chiều cao trang, gốc lạ) —
    hợp đồng cho phép bbox null, còn một toạ độ sai chiều thì không ai bắt được.
    """
    if not bbox or len(bbox) < 4 or any(v is None for v in bbox[:4]):
        return None
    l, t, r, b = (float(v) for v in bbox[:4])
    origin = str(bbox[4]).upper() if len(bbox) > 4 and bbox[4] else "TOPLEFT"
    if origin.endswith("TOPLEFT"):
        return [l, t, r, b]
    if origin.endswith("BOTTOMLEFT") and height:
        return [l, height - t, r, height - b]
    return None


def normalize_rows(rows, heights) -> int:
    """Đổi source_ref.bbox của từng row tại chỗ. Trả về số bbox phải để null."""
    dropped = 0
    for r in rows:
        sr = r.get("source_ref") or {}
        if sr.get("bbox") is None:
            continue
        sr["bbox"] = to_topleft(sr["bbox"], heights.get(sr.get("page_no")))
        dropped += sr["bbox"] is None
    return dropped

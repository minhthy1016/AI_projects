#!/usr/bin/env python3
"""
Nhận diện hàng tiêu đề và cột năm trong một lưới bảng của Docling.

Trước đây logic này tồn tại HAI BẢN: `year_columns` trong doc_extract và
`column_map` trong esg_extract. Hậu quả đã xảy ra thật: lỗi "không bỏ qua cột 0"
được sửa ở bản thứ nhất nhưng bản thứ hai vẫn còn, và chỉ lộ ra ở vòng rà soát
sau. Logic giống nhau ở hai chỗ thì lỗi cũng ở hai chỗ.

Cái gì gộp được, cái gì không
-----------------------------
Gộp: quét N hàng đầu, bỏ cột nhãn, chọn hàng có NHIỀU cột năm nhất, nhận nhóm
cột, tách ký hiệu chú thích. Đã đối chiếu trên toàn bộ bảng thật của cả hai
công ty: cách chọn hàng tiêu đề của hai bản cho kết quả GIỐNG NHAU 100%, nên
thống nhất về cách chặt hơn ("nhiều cột năm nhất") không mất gì.

KHÔNG gộp: hình dạng ô tiêu đề. Đây là khác biệt thật giữa hai họ tài liệu,
không phải trùng lặp ngẫu nhiên:

    báo cáo tài chính   ô là năm trần, có thể kèm ký hiệu chú thích
                        "2025"  ·  "2024 1"  ·  "31.12.2024"
    báo cáo ESG         ô là CỤM TỪ chứa năm
                        "Base year (2017)"  ·  "2030 target"

Ép chung một biểu thức sẽ hoặc làm trượt toàn bộ header ESG (nếu neo cuối),
hoặc mở cho "2024)" và "2024€" lọt vào bên tài chính (nếu tìm bất kỳ đâu).
Nên tham số `bare_year_only` mô tả đúng sự khác biệt đó, thay vì xoá nó đi.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["Column", "header_columns", "YEAR_ANYWHERE", "YEAR_BARE"]

# Năm nằm bất kỳ đâu trong ô — cho ô tiêu đề dạng cụm từ.
YEAR_ANYWHERE = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
# Ô CHỈ là năm, tuỳ chọn kèm một ký hiệu chú thích. Đuôi lạ ("2024)", "2024€")
# bị từ chối: không đoán một ô mà mình không hiểu.
YEAR_BARE = re.compile(r"(?<!\d)(20\d{2})(?!\d)\s*([¹²³⁴⁵⁶⁷⁸⁹⁰*†‡§]|\d{1,2})?\s*$")

NBSP = " "


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").replace(NBSP, " ")).strip()


@dataclass(frozen=True)
class Column:
    """Một cột dữ liệu đã nhận diện được."""

    index: int          # chỉ số cột trong lưới
    text: str           # nguyên văn ô tiêu đề
    year: str           # năm trích ra
    marker: str         # ký hiệu chú thích đi kèm, "" nếu không có
    group: str          # nhóm cột (cơ sở tính), chữ thường
    is_target: bool     # cột này là mục tiêu, không phải số đã thực hiện


def header_columns(grid, *, max_rows: int = 4, bare_year_only: bool = False,
                   default_group: str = "operational control",
                   second_group: str = "equity") -> tuple[int | None, list[Column]]:
    """(chỉ_số_hàng_tiêu_đề, danh sách Column). Không tìm thấy -> (None, []).

    Ba ràng buộc, cả ba rút ra từ lỗi thật trên dữ liệu:

    1. BỎ CỘT 0. Cột 0 là cột nhãn dòng, nên một năm ở đó là NHÃN chứ không phải
       tiêu đề. Bỏ qua ràng buộc này thì hàng dữ liệu "1. Jänner 2025" hay
       "Equity as of 31.12.2022" bị nhận làm hàng tiêu đề.

    2. CHỌN HÀNG NHIỀU CỘT NĂM NHẤT, không phải hàng đầu tiên có một cột. Header
       hai tầng nằm ở hàng 1, còn hàng 0 có thể lẫn một năm đơn lẻ.

    3. NHÓM CỘT lấy từ hàng ngay trên hàng tiêu đề khi hàng đó có chữ. Khi trống,
       mốc sang nhóm thứ hai được nhận ra bằng việc MỘT NHÃN CỘT LẶP LẠI — quy
       tắc không phụ thuộc ngôn ngữ và không phụ thuộc toạ độ, nên không dính
       lỗi nhãn nhóm căn giữa nằm lệch khỏi cột của chính nó.
    """
    if not grid:
        return None, []
    pattern = YEAR_BARE if bare_year_only else YEAR_ANYWHERE

    best_i, best_hits = None, []
    for ri, row in enumerate(grid[:max_rows]):
        hits = []
        for ci, cell in enumerate(row):
            if ci == 0:
                continue
            text = _norm(cell)
            if not text:
                continue
            m = pattern.search(text)
            if m:
                marker = (m.group(2) or "") if bare_year_only else ""
                hits.append((ci, text, m.group(1), marker))
        if len(hits) > len(best_hits):
            best_i, best_hits = ri, hits
    if not best_hits:
        return None, []

    above = [_norm(c) for c in grid[best_i - 1]] if best_i and best_i > 0 else []
    cols, seen, group_idx = [], set(), 0
    for ci, text, year, marker in best_hits:
        if text in seen:                     # nhãn cột lặp lại -> sang nhóm sau
            group_idx += 1
            seen = set()
        seen.add(text)
        explicit = above[ci] if ci < len(above) else ""
        group = explicit or (second_group if group_idx else default_group)
        cols.append(Column(index=ci, text=text, year=year, marker=marker,
                           group=group.lower(), is_target="target" in text.lower()))
    return best_i, cols

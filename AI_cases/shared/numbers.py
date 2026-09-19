#!/usr/bin/env python3
"""
Đọc token số theo nguyên tắc FAIL CLOSED: định dạng không chắc chắn thì từ chối.

Với một bộ benchmark, chuẩn hoá quá tay nguy hiểm hơn là bỏ sót. Bỏ sót làm mất
một dòng — và mất dòng thì đếm được, báo cáo được. Chuẩn hoá nhầm thì tạo ra một
con số trông hợp lý ở đúng chỗ nó không thuộc về, và không ai đếm được.

Bản trước dùng strip()/lstrip()/replace() nên chấp nhận rất nhiều thứ không phải
số hợp lệ, tất cả đều IM LẶNG:

    "(123"      -> 123      ngoặc lệch, và mất luôn dấu âm
    "((123))"   -> -123
    "--123"     -> -123     hai dấu âm
    "+-123"     ->  123     dấu bị nuốt, số ÂM thành DƯƠNG
    "1,23,4"    -> 1234     nhóm không phải ba chữ số
    "12,34"     -> 1234     đúng ra là 12.34 nếu đọc kiểu châu Âu — sai 100 lần

Thay bằng một VĂN PHẠM tường minh, và `is_number_token` gọi thẳng vào chính
hàm parse, nên cổng lọc và bộ đọc KHÔNG THỂ lệch nhau — trước đây NUMISH cho qua
7 chuỗi mà parse_number trả None.

    GIÁ_TRỊ := DẤU? THÂN | "(" THÂN ")"          ngoặc phải cân, nghĩa là số âm
    DẤU     := một ký tự trong - – − +            đúng MỘT, không chồng
    THÂN    := chữ_số{1,3} (NHÓM chữ_số{3})+ (THẬP_PHÂN chữ_số+)?
             | chữ_số+ (THẬP_PHÂN chữ_số+)?
             | THẬP_PHÂN chữ_số+                  dạng ".3333"
    hậu tố % được phép, đúng một lần
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

__all__ = ["NIL_TOKENS", "parse_number", "is_number_token"]

NBSP = " "
NARROW_NBSP = " "
SIGN_NEG = "-–−"          # hyphen · en-dash · minus
SIGN_ANY = SIGN_NEG + "+"

# Ô trống theo quy ước trình bày. So sánh đã hạ chữ thường, nên chỉ cần dạng thường.
# "-" và các gạch ngang là ô trống KHI ĐỨNG MỘT MÌNH; "-123" vẫn là số âm.
NIL_TOKENS = frozenset({
    "", "-", "–", "—", "−", "―",
    "n/a", "na", "n.a.", "n.a", "null", "nm", "n.m.", "n.m", "–", "—",
})

_GRAMMAR_CACHE: dict[str, re.Pattern] = {}


def _grammar(decimal_separator: str) -> re.Pattern:
    """Văn phạm thân số cho một locale. Nhóm phân cách phải ĐÚNG ba chữ số."""
    if decimal_separator not in _GRAMMAR_CACHE:
        dec = re.escape(decimal_separator)
        grp = re.escape("," if decimal_separator == "." else ".")
        # Nhánh thứ ba cho dạng ".3333" — dấu thập phân đứng đầu, không có chữ
        # số nguyên. Hồ sơ iXBRL của SEC dùng dạng này. Nó KHÔNG nhập nhằng:
        # trong locale dấu chấm, ".3333" chỉ có một cách đọc. Fail closed nghĩa
        # là từ chối cái MƠ HỒ, không phải từ chối cái hợp lệ — từ chối quá tay
        # cũng làm mất dòng, chỉ khác là mất một cách có chủ đích.
        _GRAMMAR_CACHE[decimal_separator] = re.compile(
            rf"^(?:\d{{1,3}}(?:{grp}\d{{3}})+(?:{dec}\d+)?"
            rf"|\d+(?:{dec}\d+)?"
            rf"|{dec}\d+)$"
        )
    return _GRAMMAR_CACHE[decimal_separator]


def parse_number(token, decimal_separator: str = ".",
                 nil_tokens=NIL_TOKENS) -> tuple[Decimal | None, bool]:
    """(giá_trị, là_ô_trống). Giá trị None kèm là_ô_trống False nghĩa là TỪ CHỐI.

    Ba trạng thái phân biệt rõ, và sự phân biệt đó là điều quan trọng:
        (Decimal, False)  đọc được
        (None,    True)   ô trống có chủ đích — công ty không công bố
        (None,    False)  không đọc được  -> phải bỏ dòng, KHÔNG được coi là 0
    """
    t = str(token or "").replace(NBSP, " ").replace(NARROW_NBSP, " ").strip()
    if t.lower() in nil_tokens:
        return None, True

    percent = False
    if t.endswith("%"):
        percent, t = True, t[:-1].strip()
        if t.endswith("%"):                      # "12%%" -> từ chối
            return None, False

    negative = False
    if t.startswith("(") or t.endswith(")"):
        # Ngoặc phải CÂN và bao trọn. "(123" hay "((123))" bị từ chối, vì một
        # ngoặc lệch thường là lỗi cắt ô — và nó từng biến số âm thành dương.
        if not (t.startswith("(") and t.endswith(")")):
            return None, False
        t = t[1:-1].strip()
        if "(" in t or ")" in t:
            return None, False
        negative = True

    # Lưu ý: dùng `t and t[0] in ...`, KHÔNG dùng `t[:1] in ...`.
    # "" là chuỗi con của mọi chuỗi, nên `"" in "-–−+"` trả True — cùng lớp bẫy
    # với những lỗi im lặng khác trong file này.
    if t and t[0] in SIGN_ANY:
        if negative:                             # "(-123)" -> hai cách báo âm
            return None, False
        negative = t[0] in SIGN_NEG
        t = t[1:].strip()
        if t and t[0] in SIGN_ANY:               # "--123", "+-123" -> từ chối
            return None, False

    if not t or not _grammar(decimal_separator).fullmatch(t):
        return None, False

    if decimal_separator == ",":
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", "")
    try:
        value = Decimal(t)
    except InvalidOperation:
        return None, False
    if percent:
        pass                                     # giữ nguyên con số, đơn vị là %
    return (-value if negative else value), False


def is_number_token(token, decimal_separator: str = ".",
                    nil_tokens=NIL_TOKENS) -> bool:
    """Ô này có phải số hoặc ô trống hợp lệ không.

    Gọi thẳng parse_number nên cổng lọc và bộ đọc dùng CHUNG một định nghĩa —
    không thể xuất hiện chuỗi qua được cổng rồi làm bộ đọc trả None.
    """
    value, nil = parse_number(token, decimal_separator, nil_tokens)
    return value is not None or nil

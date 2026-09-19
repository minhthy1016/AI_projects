#!/usr/bin/env python3
"""
Đọc token số có nhận biết locale — bản dùng riêng cho dự án greenwashing.

Vì sao cần: `tools/shared/text_match.py` của fabrion-extraction-evaluation strip
`[(),$\\s-]` — tức bỏ dấu phẩy nhưng KHÔNG xử lý dấu chấm. Với tài liệu châu Âu,
"24.308" bị đọc thành 24,308 thay vì 24308: sai đúng 1000 lần. Đo trên báo cáo
OMV: 33/37 giá trị gold chỉ tồn tại ở dạng châu Âu, nên coverage của tài liệu đó
bị hạ xuống một cách giả tạo.

File này KHÔNG sửa repo kia. Nó là bản thay thế cục bộ, chỉ dùng trong dự án này,
giữ nguyên hành vi với tài liệu tiếng Anh để so sánh được với điểm số cũ.

Vấn đề cốt lõi là "1.234" THẬT SỰ nhập nhằng: 1234 kiểu châu Âu hay 1.234 kiểu
Anh-Mỹ. Không token đơn lẻ nào giải được. Nên:
  - token có CẢ hai dấu  -> dấu xuất hiện SAU là dấu thập phân (chắc chắn)
  - token có nhiều nhóm cùng một dấu ("13.920.157") -> dấu đó là phân cách nghìn
  - còn lại              -> theo locale của TÀI LIỆU, suy từ các token chắc chắn
Không đoán theo từng token; đoán theo tài liệu rồi áp nhất quán.
"""
from __future__ import annotations
import re

__all__ = ["detect_separator", "parse_number", "input_numbers", "normalize", "covered"]

# token số: cho phép ngoặc, dấu âm (kể cả en-dash/minus), tiền tệ, %, phân cách
# Token số. KHÔNG cho phép khoảng trắng bên trong: "13.920.157 10.769.800" phải ra
# HAI token. Bản đầu nhận cả \s nên nuốt luôn dấu cách và gộp cả dòng thành một số —
# test bắt được ngay, và đó là lý do file này có test trước khi đem dùng.
_TOKEN = re.compile(r"\(?[-–−+]?[$€£]?\d[\d.,]*\d%?\)?|\(?[-–−+]?\d%?\)?")
# Chắc chắn châu Âu / chắc chắn Anh-Mỹ: từ HAI nhóm trở lên thì không còn cách đọc khác.
_DOT_GROUPS_MULTI = re.compile(r"^\d{1,3}(?:\.\d{3}){2,}$")
_COMMA_GROUPS_MULTI = re.compile(r"^\d{1,3}(?:,\d{3}){2,}$")
_EU_DEFINITE = re.compile(r"\d{1,3}(?:\.\d{3})+,\d+|\d{1,3}(?:\.\d{3}){2,}")
_EN_DEFINITE = re.compile(r"\d{1,3}(?:,\d{3})+\.\d+|\d{1,3}(?:,\d{3}){2,}")


def detect_separator(text: str) -> str:
    """'.' (Anh-Mỹ) hoặc ',' (châu Âu), suy từ các token KHÔNG nhập nhằng.

    Chỉ đếm những dạng chỉ có một cách đọc: "1.234.567" hoặc "1.234,5" là châu Âu;
    "1,234,567" hoặc "1,234.5" là Anh-Mỹ. Hoà hoặc không có bằng chứng -> Anh-Mỹ,
    để tài liệu tiếng Anh giữ nguyên hành vi cũ.
    """
    eu = len(_EU_DEFINITE.findall(text))
    en = len(_EN_DEFINITE.findall(text))
    return "," if eu > en else "."


def parse_number(token: str, decimal_separator: str = ".") -> float | None:
    """Một token -> float, hoặc None nếu không phải số."""
    t = token.strip().replace(" ", " ")
    negative = t.startswith("(") and t.rstrip().endswith(")")
    t = t.strip("()").strip()
    if t[:1] in "-–−":
        negative = True
        t = t[1:].strip()
    elif t[:1] == "+":
        t = t[1:].strip()
    t = re.sub(r"[$€£%\s]", "", t)
    if not t or not re.fullmatch(r"[\d.,]+", t):
        return None

    has_dot, has_comma = "." in t, "," in t
    if has_dot and has_comma:
        # dấu xuất hiện SAU là dấu thập phân — không cần locale
        sep = "." if t.rfind(".") > t.rfind(",") else ","
    elif _DOT_GROUPS_MULTI.fullmatch(t):
        sep = ","        # "13.920.157" — hai nhóm trở lên, chắc chắn là phân cách nghìn
    elif _COMMA_GROUPS_MULTI.fullmatch(t):
        sep = "."        # "1,234,567" — tương tự
    elif re.search(r"[.,](\d+)$", t) and len(re.search(r"[.,](\d+)$", t).group(1)) != 3:
        # Nhóm cuối KHÔNG đúng ba chữ số thì không thể là phân cách nghìn:
        # "13,9" và "2742.50" chỉ có một cách đọc, không cần locale.
        sep = t[len(t) - len(re.search(r"[.,](\d+)$", t).group(1)) - 1]
    else:
        # Một nhóm ba chữ số ("24.308", "1,250") là NHẬP NHẰNG THẬT: 24308 hay 24,308?
        # Không tự quyết theo token — theo locale của tài liệu. Đây là lý do
        # detect_separator() tồn tại, và là lý do không thể sửa lỗi này chỉ bằng
        # cách đổi ký tự strip.
        sep = decimal_separator

    t = t.replace(".", "") .replace(",", ".") if sep == "," else t.replace(",", "")
    if not re.fullmatch(r"\d+(?:\.\d+)?", t):
        return None
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if negative else v


def input_numbers(text: str, decimal_separator: str | None = None) -> set[float]:
    """Tập số trong một đoạn văn. decimal_separator=None -> tự suy từ chính đoạn đó."""
    sep = decimal_separator or detect_separator(text)
    out: set[float] = set()
    for tok in _TOKEN.findall(text):
        v = parse_number(tok, sep)
        if v is not None:
            out.add(v)
    return out


def normalize(text) -> str:
    """Chữ thường, dấu câu và khoảng trắng gộp về một dấu cách — để khớp chuỗi."""
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def covered(value, numbers: set[float], norm_haystack: str = "", *,
            rel_tol: float = 0.005) -> bool:
    """Giá trị gold có mặt trong input không.

    Số thì khớp theo GIÁ TRỊ trong dung sai làm tròn; không phải số thì khớp
    chuỗi con đã chuẩn hoá. Thiếu vế thứ hai là bỏ sót mọi trường chữ
    (đơn vị tiền tệ, tên công ty) và hạ coverage một cách vô nghĩa.
    """
    try:
        target = float(value)
    except (TypeError, ValueError):
        needle = normalize(value)
        return bool(needle) and needle in norm_haystack
    tol = max(0.5, abs(target) * rel_tol)
    return any(abs(n - target) <= tol for n in numbers)

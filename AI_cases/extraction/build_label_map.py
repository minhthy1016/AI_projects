#!/usr/bin/env python3
"""Sinh bảng tên gọi từ CHÍNH file iXBRL, thay cho viết tay.

Vì sao làm được
---------------
Trong file iXBRL, mỗi giá trị được gắn thẻ nằm ngay trong hàng bảng mang nhãn
in ra của nó:

    <tr><td>Total assets</td> … <ix:nonFraction name="ifrs-full:Assets">370,350</…>

Tức tài liệu tự nó là một bảng tên gọi — bằng ngôn ngữ của chính công ty, do
chính công ty khai. Không cần tải taxonomy IFRS, không cần đoán bản dịch, và
không cần ai gõ tay "Umsatzerlöse", "Salgsinntekter", "Ricavi della gestione
caratteristica" về cùng một khái niệm.

Vì sao đáng đổi
---------------
Bảng viết tay là điểm yếu kiến trúc lớn nhất còn lại: ~15 dòng mỗi công ty,
sáu ngôn ngữ, và một bảng TRÔNG ĐÚNG vẫn ra số sai — ánh xạ "Total assets" của
Shell từng cho 107.173 thay vì 370.350 vì Docling gán nhãn lệch dòng. Bản sinh
tự động lấy nhãn và khái niệm từ CÙNG một hàng, nên không lệch được.

Ba chốt fail-closed
-------------------
1. Một nhãn ứng với NHIỀU khái niệm -> bỏ. "Other changes" xuất hiện ở cả bảng
   biến động vốn lẫn nơi khác với ý nghĩa khác nhau; giữ lại là mời khớp sai.
2. Nhãn trông như NGÀY THÁNG -> bỏ. Bảng biến động vốn chủ đánh nhãn hàng bằng
   "At January 1, 2025" chứ không bằng tên khoản mục.
3. Nhãn rỗng hoặc chỉ có chữ số -> bỏ.

Báo cáo nào
-----------
Suy từ chính tài liệu chứ không khai tay: gom các thẻ theo BẢNG chứa chúng,
rồi phân loại từng bảng — bảng toàn kỳ tức thời là bảng cân đối; bảng theo kỳ
mà có khái niệm luồng tiền là báo cáo lưu chuyển; còn lại là kết quả kinh
doanh. Một quy tắc chung thay cho 8×15 dòng gõ tay.

Chạy:
    <fabrion>/.venv/bin/python extraction/build_label_map.py \\
        --ixbrl data/esef/<LEI>/<period>/<file>.xhtml \\
        --out   data/labelmaps/<ten>.json
"""
import argparse, collections, json, pathlib, re, sys

X = "{http://www.w3.org/1999/xhtml}"
IX = "{http://www.xbrl.org/2013/inlineXBRL}"

# Gốc tên khái niệm luồng tiền theo IFRS. Dùng để phân loại BÁO CÁO, không phải
# để ánh xạ nhãn — nên một danh sách ngắn là đủ và không phụ thuộc ngôn ngữ.
# Đây là toàn bộ phần "viết tay" còn lại: 9 gốc tên, dùng chung cho mọi công ty
# và mọi ngôn ngữ, thay cho 8×15 dòng nhãn gõ riêng từng công ty.
CASHFLOW_ROOTS = ("CashFlows", "IncreaseDecreaseInCash", "EffectOfExchangeRateChangesOnCash",
                  "ProceedsFrom", "PaymentsFor", "PaymentsTo", "AdjustmentsFor",
                  "CashAndCashEquivalentsAtBeginning", "CashAndCashEquivalentsAtEnd")

DATE_LIKE = re.compile(
    r"^(?:\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{2,4}"          # 31/12/2024
    r"|.*\b(19|20)\d{2}\b\s*$"                                   # … 2025
    r")$", re.I)
# Nhãn là CHÍNH CON SỐ: hàng tổng phụ không in tên, ô đầu không rỗng lại là ô
# giá trị. Shell có "106,143" và "107,173" đứng làm nhãn theo đúng kiểu đó —
# và "107,173" chính là con số từng được gán nhầm cho "Total assets".
NUMERIC_LABEL = re.compile(r"^[(\-–−+]?[\d.,\s]+[)%]?$")
FOOTNOTE = re.compile(r"\s*(?:\[[A-Za-z0-9]{1,3}\]|\((?:see\s+)?[Nn]ote[^)]*\))\s*$")


def sign_is_visible(el):
    """Dấu âm có HIỆN RA trên trang không — ngoặc đơn hay dấu trừ nằm ngoài thẻ."""
    inner = "".join(el.itertext())
    if not inner:
        return False
    # Ngoặc có thể nằm cách thẻ vài cấp: <td>(<span><ix:…>18,131</ix:…></span>)</td>.
    # Chỉ soi cha trực tiếp thì bỏ sót — đó là lý do 13 dòng luồng tiền của
    # TotalEnergies và Repsol bị đổi dấu thừa.
    q = el
    for _ in range(4):
        q = q.getparent()
        if q is None:
            return False
        whole = "".join(q.itertext())
        i = whole.find(inner)
        if i < 0:
            continue
        before = whole[max(0, i - 3):i]
        after = whole[i + len(inner): i + len(inner) + 3]
        if "(" in before or ")" in after or any(c in before for c in "-–−"):
            return True
    return False


def needs_flip(el):
    """Bộ trích xuất có phải đổi dấu giá trị đọc được không.

    Ba đại lượng, đừng lẫn:
      - chữ TRONG thẻ ix            : "3.262"
      - thuộc tính sign="-"         : giá trị XBRL = −(chữ trong thẻ)
      - chữ DỰNG RA TRANG           : "(3.262)" — ngoặc nằm NGOÀI thẻ

    Docling đọc cái thứ ba, ta cần cái mà XBRL khai. Hai cái đó lệch nhau đúng
    khi một bên có dấu còn bên kia không:

        ngoặc hiện   sign="-"   XBRL      Docling đọc   đổi dấu?
        có           có         −3.262    −3.262        không
        có           không      +3.262    −3.262        CÓ      <- Eni
        không        có         −3.262    +3.262        CÓ
        không        không      +3.262    +3.262        không

    Tức là phép XOR. Bản đầu tôi chỉ xét sign="-" nên Shell — vốn khai cả hai —
    bị đổi dấu thừa và tụt từ 126 xuống 117; bản thứ hai chỉ xét "dấu không
    hiện" nên bỏ sót Eni, 18 giá trị đúng số mà ngược dấu.
    """
    return sign_is_visible(el) != (el.get("sign") == "-")


def cell_text(el):
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


# Phần chữ mở đầu một hàng, trước con số đầu tiên. Dùng cho bản trình bày
# bằng div, nơi cả hàng nằm gọn trong một phần tử:
#     'Total assets 42,192.9 39,046.5 42,192.8 39,055.0'  ->  'Total assets'
LEAD_TEXT = re.compile(r"^([^\d]{2,}?)\s+[(\-–−+]?\d")
MAX_ROW_CHARS = 250          # dài hơn thế thì không còn là một hàng

def row_label(node):
    """Nhãn của hàng chứa thẻ.

    Hai kiểu trình bày, cùng một ý: lấy phần chữ mở đầu hàng.

    a) Bảng HTML thật (Shell, OMV, Eni một phần): ô không rỗng đầu tiên của <tr>.
    b) Div định vị (Aker BP, Galp, phần lớn Eni): không có <tr> nào — cả hàng là
       MỘT div, ví dụ 'Total assets 42,192.9 39,046.5'. Lấy phần trước số đầu.
       Bản đầu chỉ xử lý (a) nên Aker BP và Galp ra 0 nhãn, còn Eni chỉ ra 60
       trong 637 thẻ — im lặng, vì "không có nhãn" trông giống "tài liệu nghèo".

    Chặn lấy nhầm cả trang: bỏ qua phần tử dài quá MAX_ROW_CHARS.
    """
    tr = node.getparent()
    while tr is not None and tr.tag != X + "tr":
        tr = tr.getparent()
    if tr is not None:
        for c in list(tr):
            if c.tag in (X + "td", X + "th"):
                t = cell_text(c)
                if t:
                    return t, tr
        return None, tr

    q = node.getparent()
    while q is not None:
        t = cell_text(q)
        if len(t) > MAX_ROW_CHARS:
            return None, None
        m = LEAD_TEXT.match(t)
        if m:
            return m.group(1).strip(), q
        q = q.getparent()
    return None, None


def harvest(path, taxonomy="ifrs-full"):
    """Trả (danh sách bản ghi thô, thống kê)."""
    try:
        import lxml.etree as ET
    except ImportError:
        sys.exit("cần lxml. Chạy bằng venv của Fabrion:\n"
                 "  ~/Desktop/Fabrion/fabrion-extraction-evaluation/.venv/bin/python " + sys.argv[0])
    root = ET.parse(str(path), ET.XMLParser(huge_tree=True, recover=True)).getroot()

    inst = "{http://www.xbrl.org/2003/instance}"
    ctx = {c.get("id"): ("instant" if c.find(f".//{inst}instant") is not None else "duration")
           for c in root.iter(inst + "context")}

    # Đơn vị: chỉ giữ khái niệm đo bằng MỘT đồng tiền.
    #
    # Lãi cơ bản trên cổ phiếu có đơn vị USD/shares (thẻ <divide>), giá trị thật
    # là 3,03 — nhưng bộ trích xuất nhân mọi ô với hệ số của bảng ("$ million"),
    # nên nó thành 3.030.000. Số sai một triệu lần, mà trông vẫn như một con số
    # tiền tệ hợp lý. Tỷ lệ phần trăm (xbrli:pure) cũng vậy.
    #
    # Bảng viết tay né được lỗi này do chưa bao giờ khai EPS; bảng sinh tự động
    # thì khai, nên phải lọc ngay tại nguồn.
    money = set()
    for u in root.iter(inst + "unit"):
        ms = [m.text.strip() for m in u.iter(inst + "measure") if m.text]
        if u.find(inst + "divide") is None and len(ms) == 1 and ms[0].startswith("iso4217:"):
            money.add(u.get("id"))

    recs, st = [], collections.Counter()
    for el in root.iter(IX + "nonFraction"):
        name = el.get("name", "")
        st["the"] += 1
        if not name.startswith(taxonomy + ":"):
            st["ngoai_taxonomy"] += 1
            continue
        if el.get("unitRef") not in money:
            st["khong_phai_tien_te"] += 1
            continue
        lab, _ = row_label(el)
        if not lab:
            st["khong_co_nhan"] += 1
            continue
        recs.append(dict(label=lab, concept=name.split(":", 1)[1],
                         period=ctx.get(el.get("contextRef", ""), "duration"),
                         flip=needs_flip(el)))
    return recs, st


def statement_of(concept, periods):
    """Báo cáo nào, suy từ CHÍNH khái niệm và kiểu kỳ — không cần gom nhóm.

    Bản trước gom thẻ thành "khối báo cáo" rồi phân loại cả khối. Hỏng theo hai
    đường: bản trình bày bằng div không có <table> nên cả tài liệu thành một
    khối, và chỉ cần MỘT khái niệm luồng tiền trong khối là nhiễm toàn bộ —
    Shell tụt từ 17 nhãn bảng cân đối xuống 0.

    Quy tắc này không gom gì cả:
      kỳ tức thời                      -> bảng cân đối
      kỳ có độ dài + gốc tên luồng tiền -> lưu chuyển tiền tệ
      còn lại                           -> kết quả kinh doanh

    Nó dựa vào một danh sách gốc tên ngắn thay cho 8×15 dòng gõ tay, và đúng
    theo định nghĩa của IFRS chứ không theo cách trình bày của từng công ty.

    Nó cũng tự xử lý một cái bẫy: "Cash and cash equivalents at beginning of
    year" nằm trong báo cáo lưu chuyển, nhưng khái niệm của nó là kỳ tức thời
    nên được xếp vào bảng cân đối. Bộ trích xuất chỉ dùng nhãn trong đúng loại
    báo cáo, nên nhãn đó không bao giờ khớp trong bảng lưu chuyển — tránh được
    việc gán số dư đầu kỳ 2024 thành số dư cuối 2025, mà không cần luật riêng.
    """
    if periods and all(pd == "instant" for pd in periods):
        return "balance_sheet"
    if concept.startswith(CASHFLOW_ROOTS):
        return "cash_flow"
    return "income_statement"


def build(recs, min_count=1):
    """Gộp thành bảng tên gọi. Nhãn mơ hồ bị loại, có nêu lý do."""
    seen = collections.defaultdict(collections.Counter)   # nhãn -> concept -> đếm
    flips = collections.defaultdict(collections.Counter)  # nhãn -> có đổi dấu -> đếm
    stmt = collections.defaultdict(collections.Counter)   # nhãn -> báo cáo -> đếm
    for r in recs:
        lab = FOOTNOTE.sub("", r["label"]).strip()
        if not lab or DATE_LIKE.match(lab) or NUMERIC_LABEL.match(lab):
            continue
        seen[lab][r["concept"]] += 1
        stmt[lab][r["period"]] += 1
        flips[lab][r["flip"]] += 1

    keep, drop = {}, collections.Counter()
    for lab, concepts in seen.items():
        if len(concepts) > 1:
            drop["nhiều khái niệm"] += 1
            continue
        concept, n = concepts.most_common(1)[0]
        if n < min_count:
            drop["quá ít lần"] += 1
            continue
        # Quy ước dấu, lấy từ chính tài liệu.
        #
        # ix:nonFraction có thuộc tính sign="-" khi giá trị THẬT là số đối của
        # số in ra: IFRS quy định chi phí là số dương, còn báo cáo in nó trong
        # ngoặc. Bộ trích xuất đọc chữ in ra, nên phải đổi dấu lại.
        #
        # Đây là phần hay bị bỏ sót nhất: trên bảy công ty, 59 trong 62 giá trị
        # sai của bản sinh tự động ĐẦU TIÊN đều là sai dấu — đọc đúng con số,
        # ngược dấu. Bảng viết tay né được vì chỉ khai một khái niệm chi phí.
        #
        # Chỉ đổi dấu khi MỌI thẻ của nhãn đó đều khai sign="-". Lẫn lộn thì
        # không suy được, nên giữ như in và để bộ đối chiếu bắt.
        f = flips[lab]
        flip = len(f) == 1 and True in f
        keep[lab] = [f"ifrs-full:{concept}", statement_of(concept, list(stmt[lab])), flip]
    for r in recs:
        lab = FOOTNOTE.sub("", r["label"]).strip()
        if not lab or DATE_LIKE.match(lab):
            drop["ngày tháng / rỗng"] += 1
        elif NUMERIC_LABEL.match(lab):
            drop["nhãn là chính con số"] += 1
    return keep, drop


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ixbrl", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--taxonomy", default="ifrs-full")
    ap.add_argument("--min-count", type=int, default=1,
                    help="số lần một cặp (nhãn, khái niệm) phải xuất hiện mới được giữ")
    a = ap.parse_args(argv)

    src = pathlib.Path(a.ixbrl)
    if not src.exists():
        sys.exit(f"không thấy: {src}")
    recs, st = harvest(src, a.taxonomy)
    if not recs:
        sys.exit(f"không lấy được thẻ {a.taxonomy} nào từ {src.name} — sai taxonomy hoặc sai file?")
    keep, drop = build(recs, a.min_count)
    if not keep:
        sys.exit("không nhãn nào qua được các chốt — không ghi file rỗng")

    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(keep, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                   encoding="utf-8")
    byst = collections.Counter(v[1] for v in keep.values())
    print(f"  {src.name}")
    print(f"    {st['the']} thẻ · {st['ngoai_taxonomy']} ngoài taxonomy · "
          f"{st['khong_phai_tien_te']} không phải đơn vị tiền tệ · "
          f"{st['khong_co_nhan']} không tìm được nhãn")
    print(f"    giữ {len(keep)} nhãn  ({', '.join(f'{k} {v}' for k, v in sorted(byst.items()))})")
    print(f"    loại: {', '.join(f'{k} {v}' for k, v in sorted(drop.items()) if v)}")
    print(f"    -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

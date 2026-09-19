#!/usr/bin/env python3
"""
Đối soát ESRS content index — tín hiệu rẻ nhất trong toàn hệ thống.

Công ty tự khai trong bảng index: "Angabepflicht X được công bố ở trang N".
Việc của ta là kiểm xem X có thật sự được công bố hay không. Không cần đọc
một con số nào, không cần LLM, và tỷ lệ "khai reported nhưng không có" cao
đến bất ngờ.

Hai nguồn độc lập TRONG CÙNG một tài liệu:
  A. bảng index  (mã + tiêu đề + số trang tự khai)
  B. tag ESRS trong ngoặc vuông rải khắp phần nội dung  [E1-4.32] [MDR-T-80a]
Đối chiếu A với B.

GIỚI HẠN đã biết — phải nói rõ: bản PDF này render từ xhtml bằng Chrome, và
Chrome PHÂN TRANG LẠI tài liệu. Không tồn tại độ lệch trang cố định
(BP-1: index 83 -> PDF 31, lệch -52; GOV-4: index 97 -> PDF 36, lệch -61).
Nên ở đây kiểm "mã có được tag ở đâu đó không", KHÔNG kiểm "đúng trang đã khai".
Với PDF gốc tải từ IR page thì kiểm được cả số trang.
"""
import argparse, collections, hashlib, json, pathlib, re, sys

CODE = r"(?:E[1-5]|S[1-4]|G1|BP|GOV|SBM|IRO|MDR)"
INDEX_ROW = re.compile(rf"^\s*({CODE}-[A-Z0-9]+)\s+(.+?)\s{{2,}}(?:(.*?)\s{{2,}})?(\d{{1,3}})\s*$")
INLINE = re.compile(r"\[([^\]]{2,80})\]")
INLINE_CODE = re.compile(rf"(?:ESRS[\s-]*)?\b({CODE}[-\s]?[A-Z]?[-\s]?\d+)")
NOTE_REF = re.compile(r"Anhangangabe\s+(\d+)\s*[–-]\s*(.{3,60})")

ROW_START = re.compile(rf"^\s*({CODE}-[A-Z0-9]+)\s+(\S.*)$")
# Số trang tự khai ở cuối dòng index. Regex này CŨNG cắt đuôi chuỗi bằng sub(),
# cùng lớp rủi ro với FOOTNOTE_TAIL trong doc_extract — nhưng an toàn nhờ hai
# ràng buộc, ghi lại đây để không ai nới lỏng chúng mà không biết hậu quả:
#   \s{2,}   phải có khoảng trống rộng phía trước -> chỉ khớp cột trang, không
#             khớp con số nằm trong câu ("Angaben zu Scope 3" giữ nguyên)
#   \d{1,3}  tối đa ba chữ số -> năm bốn chữ số không bao giờ bị nuốt
#             ("Emissionen 2024", "Ziele bis 2030" giữ nguyên)
# Nới bất kỳ ràng buộc nào cũng sẽ lặng lẽ cắt mất phần mang nghĩa của tiêu đề.
TRAIL_PAGE = re.compile(r"(?:^|\s{2,})(\d{1,3})\s*$")

INDEX_ANCHORS = ("ESRS-Angabepflicht", "ESRS Angabepflicht",
                 "Disclosure Requirement", "ESRS index", "ESRS Index")
INDEX_MIN_ROWS = 5
# Tỉ lệ tối thiểu số mã trong mục lục mà bộ dò tìm thấy được, để KẾT LUẬN được.
# Dưới ngưỡng này nghĩa là phương pháp dò không hợp với cách trình bày của tài
# liệu, chứ không phải công ty không công bố — và phân biệt hai điều đó là toàn
# bộ giá trị của phép đối soát này.
MIN_DETECTION_RATE = 0.20
REF_SECTION = re.compile(r"\bsection\s+([\d.]+)", re.I)
DUPLICATE_CODES: list[str] = []


def find_index_pages(pages) -> list[int]:
    """Trang nào mở đầu bảng mục lục. Hai cách, dùng theo thứ tự.

    1. Theo CHỮ — chuỗi neo ở DÒNG ĐẦU trang. Phải ở dòng đầu, vì trong văn xuôi
       và breadcrumb điều hướng thì "ESRS index" xuất hiện khắp nơi.
    2. Theo HÌNH DẠNG — trang có >= 5 dòng mở đầu bằng mã disclosure thì là bảng
       mục lục, bất kể tiêu đề viết bằng ngôn ngữ gì.

    Cần cách (2) vì hồ sơ Aker BP mở đầu trang bằng breadcrumb chứ không phải
    tiêu đề bảng: cách (1) trượt sạch và công cụ báo "0 dòng" như thể mọi thứ ổn.
    """
    by_text = [i for i, pg in enumerate(pages, 1)
               if any(pg.strip().split("\n")[0].strip().startswith(a) for a in INDEX_ANCHORS)]
    if by_text:
        return by_text
    return [i for i, pg in enumerate(pages, 1)
            if sum(1 for l in pg.split("\n") if ROW_START.match(l)) >= INDEX_MIN_ROWS]


def parse_index(pages):
    """Bảng index, chịu được dòng bị xuống hàng.

    Hai lỗi của bản đầu, cả hai đều tạo ra cáo buộc sai:
      1. Neo bằng `"ESRS-Angabepflicht" in page` — chuỗi này còn xuất hiện trong
         văn xuôi ở phần nội dung, nên parser bắt đầu từ trang nội dung và đưa
         trang đó vào index_pages. Những trang ấy bị loại khỏi vùng quét tag,
         khiến SBM-1 (10 tag) và E1-5 (34 tag) bị báo là "không được công bố".
         Neo đúng: chuỗi phải nằm ở DÒNG ĐẦU của trang, tức là header bảng.
      2. Chỉ nhận dòng có đủ mã + tiêu đề + số trang trên MỘT dòng -> phủ 60%.
         Tiêu đề dài bị xuống hàng và số trang rơi xuống dòng sau.
    """
    starts = find_index_pages(pages)
    if not starts:
        return []
    DUPLICATE_CODES.clear()
    # Quét tới khi HAI trang liền không còn dòng index, thay vì cửa sổ cứng 6
    # trang — mục lục dài hơn thì bản trước lặng lẽ cắt bớt.
    rows, seen, dry = [], set(), 0
    for pno in range(starts[0], len(pages) + 1):
        if dry >= 2:
            break
        page = pages[pno - 1]
        cur = None
        for l in page.split("\n"):
            m = ROW_START.match(l)
            if m:
                if cur:
                    rows.append(cur)
                cur = dict(code=m.group(1), title=m.group(2).strip(),
                           incorporated_ref=None, claimed_page=None, ref_kind=None,
                           index_pdf_page=pno, _buf=[m.group(2)])
            elif cur is not None and l.strip():
                cur["_buf"].append(l.strip())
            if cur and cur["claimed_page"] is None:
                pm, sm = TRAIL_PAGE.search(l.rstrip()), REF_SECTION.search(l)
                if pm:
                    cur["claimed_page"], cur["ref_kind"] = int(pm.group(1)), "page"
                elif sm:
                    # Aker BP khai tham chiếu là SỐ MỤC ("section 1.1"), không phải
                    # số trang. Bản trước chỉ nhận số trang nên mọi dòng của hồ sơ
                    # đó bị loại vì claimed_page is None.
                    cur["claimed_page"], cur["ref_kind"] = sm.group(1), "section"
        if cur:
            rows.append(cur)
        dry = 0 if any(ROW_START.match(l) for l in page.split("\n")) else dry + 1
    out = []
    for r in rows:
        if r["claimed_page"] is None:
            continue
        if r["code"] in seen:
            DUPLICATE_CODES.append(r["code"])   # trùng thật (IRO-1 lặp ở mỗi chuẩn chủ đề)
            continue
        seen.add(r["code"])
        buf = " ".join(r.pop("_buf"))
        buf = TRAIL_PAGE.sub("", buf).strip()
        # phần "Aufnahme mittels Verweis" nằm sau khoảng trắng lớn
        buf = REF_SECTION.sub("", buf).strip()   # số mục là THAM CHIẾU, không phải tiêu đề
        parts = re.split(r"\s{3,}", buf)
        r["title"] = parts[0].strip()
        ref = " ".join(parts[1:]).strip()
        r["incorporated_ref"] = ref if "Anhangangabe" in ref else None
        out.append(r)
    return out

HEADING = re.compile(rf"^\s*({CODE}-[A-Z0-9]+)\s+[A-ZÄÖÜ]\S", re.M)

def inline_map(pages, index_pages):
    """Nơi một Angabepflicht thật sự xuất hiện trong phần nội dung.

    Hai dạng đánh dấu, phải nhận cả hai:
      - tag trong ngoặc vuông:  [E1-6.44a] [MDR-T-80a]
      - TIÊU ĐỀ MỤC:            "E4-4 Ziele im Zusammenhang mit biologischer..."
    Chỉ dò dạng đầu sẽ báo E4-4 là "không công bố" trong khi nó có hẳn một mục
    riêng ở PDF 78. Đây là cáo buộc sai sinh ra từ giới hạn của phương pháp dò,
    không phải từ dữ liệu — loại lỗi nguy hiểm nhất với sản phẩm kiểu này.
    """
    loc = collections.defaultdict(set)
    for pno, page in enumerate(pages, 1):
        if pno in index_pages:            # bảng index không tính là nơi công bố
            continue
        for m in INLINE.finditer(page):
            for c in INLINE_CODE.findall(m.group(1)):
                loc[re.sub(r"\s+", "-", c.strip()).upper()].add(pno)
        for m in HEADING.finditer(page):
            loc[m.group(1).upper()].add(pno)
    return loc

def note_exists(pages, num):
    """Thuyết minh số N có tồn tại trong phần báo cáo tài chính không.

    Bản đầu chỉ quét 6 DÒNG ĐẦU mỗi trang, nên trượt Anhangangabe 7 (thật sự
    nằm giữa trang PDF 167) và báo `reference_not_found` cho SBM-1, E1-5, E1-6.
    Ba cáo buộc sai chỉ vì một cửa sổ tìm kiếm quá hẹp.
    """
    pat = re.compile(rf"^\s*{num}\s*\|\s*\S", re.M)
    for pno, page in enumerate(pages, 1):
        if pat.search(page):
            return pno
    return None

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--txt", required=True)
    ap.add_argument("--company-id", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    txt = pathlib.Path(a.txt)
    pages = txt.read_text(encoding="utf-8", errors="replace").split("\f")
    doc_hash = hashlib.sha256(txt.read_bytes()).hexdigest()

    idx = parse_index(pages)
    if not idx:
        # Bản trước trả về 0 dòng, ghi FILE RỖNG và thoát mã 0 — trông y như chạy
        # thành công. Với công cụ đối soát thì "không tìm thấy mục lục" và "mọi
        # thứ đều ổn" phải phân biệt được, nếu không một thay đổi cách trình bày
        # sẽ lặng lẽ tắt cả phép kiểm mà không ai biết.
        print(f"KHÔNG ĐỌC ĐƯỢC MỤC LỤC ESRS trong {txt.name}.", file=sys.stderr)
        print(f"  neo theo chữ: {', '.join(INDEX_ANCHORS)}", file=sys.stderr)
        print(f"  neo theo hình dạng: trang có >= {INDEX_MIN_ROWS} dòng mở đầu bằng mã",
              file=sys.stderr)
        print("  KHÔNG ghi file kết quả — file rỗng sẽ bị hiểu nhầm là đối soát sạch.",
              file=sys.stderr)
        sys.exit(2)
    index_pages = {r["index_pdf_page"] for r in idx}
    loc = inline_map(pages, index_pages)

    # Bộ dò có áp dụng được cho tài liệu này không?
    hit = sum(1 for r in idx if r["code"].upper() in loc)
    rate = hit / len(idx)
    if rate < MIN_DETECTION_RATE:
        print(f"\n{'=' * 100}\nPHƯƠNG PHÁP DÒ KHÔNG ÁP DỤNG ĐƯỢC CHO TÀI LIỆU NÀY\n{'=' * 100}",
              file=sys.stderr)
        print(f"  Đọc được {len(idx)} dòng mục lục, nhưng chỉ tìm thấy dấu vết công bố của "
              f"{hit} mã ({rate:.0%}).", file=sys.stderr)
        print("  Bộ dò tìm tag dạng [E1-6.44a] và tiêu đề mục dạng 'E4-4 ...'. Tài liệu này "
              "dùng cách đánh dấu khác.", file=sys.stderr)
        print(f"  KHÔNG kết luận gì: báo {len(idx)} mã là 'khai có nhưng không thấy' ở đây sẽ là "
              f"{len(idx)} cáo buộc sai,", file=sys.stderr)
        print("  sinh ra từ giới hạn của công cụ chứ không phải từ dữ liệu.", file=sys.stderr)
        sys.exit(3)

    out, stat = [], collections.Counter()
    for r in idx:
        found = sorted(loc.get(r["code"].upper(), []))
        verified = bool(found)
        status = "verified" if verified else "claimed_but_untagged"
        ref_ok = None
        if r["incorporated_ref"]:
            m = NOTE_REF.search(r["incorporated_ref"])
            ref_ok = bool(note_exists(pages, m.group(1))) if m else None
            if ref_ok is False:
                status = "reference_not_found"
        stat[status] += 1
        out.append(dict(
            claim_id=hashlib.sha256(f"{doc_hash}{r['code']}idx".encode()).hexdigest()[:32],
            doc_hash=doc_hash, company_id=a.company_id, report_year=2025,
            framework="ESRS", framework_version="ESRS-2023",
            gri_code=r["code"], gri_code_reported=r["code"],
            claim_type="methodology", claim_text=r["title"],
            disclosure_status_claimed="reported",
            disclosure_verified=verified,
            omission_reason=None,
            claimed_page=r["claimed_page"],
            found_on_pdf_pages=found[:6],
            incorporated_ref=r["incorporated_ref"],
            incorporated_ref_resolves=ref_ok,
            status=status,
            source_ref=dict(page_no=r["index_pdf_page"], bbox=None,
                            verbatim_span=f"{r['code']} {r['title'][:60]}",
                            table_id="ESRS-index", row_idx=None, col_idx=None,
                            col_header_path=["ESRS-Angabepflicht", "Seite"],
                            extraction_path="native_text"),
            groundedness_verified=True, confidence=0.95,
            extractor_version="esrs-index-check@0.1.0", model_id="none-rule-based",
            prompt_hash="-", schema_version="1.0"))

    orphan = sorted(set(loc) - {r["code"].upper() for r in idx})
    print(f"\n{'='*100}\nĐỐI SOÁT ESRS CONTENT INDEX\n{'='*100}")
    kinds = collections.Counter(r.get("ref_kind") for r in idx)
    print(f"  dòng index đọc được      : {len(idx)}  ({dict(kinds)})")
    if DUPLICATE_CODES:
        print(f"  mã lặp trong mục lục     : {len(DUPLICATE_CODES)} "
              f"(giữ lần đầu) — {sorted(set(DUPLICATE_CODES))[:6]}")
    print(f"  mã có tag inline         : {len(loc)}")
    for k, v in stat.most_common():
        print(f"  {k:26s}: {v}")
    untagged = [r for r in out if r["status"] == "claimed_but_untagged"]
    refbad = [r for r in out if r["status"] == "reference_not_found"]
    if untagged:
        print(f"\n  --- {len(untagged)} mã khai 'reported' nhưng KHÔNG có tag ở đâu trong nội dung ---")
        for r in untagged:
            print(f"    {r['gri_code']:8s} trang khai {r['claimed_page']:>3}  {r['claim_text'][:58]}")
    if refbad:
        print(f"\n  --- {len(refbad)} mã dẫn chiếu tới thuyết minh không giải được ---")
        for r in refbad:
            print(f"    {r['gri_code']:8s} -> {r['incorporated_ref'][:60]}")
    # Phần lớn "orphan" là MDR-* (Minimum Disclosure Requirements) và IRO-*,
    # vốn là yêu cầu xuyên suốt chứ không phải dòng index độc lập — cộng thêm
    # vài biến thể do chuẩn hoá (IRO--3, MDR-A68). KHÔNG coi đây là tín hiệu.
    real_orphan = [c for c in orphan
                   if not c.startswith(("MDR", "IRO")) and "--" not in c]
    if real_orphan:
        print(f"\n  --- {len(real_orphan)} mã có trong nội dung nhưng KHÔNG có dòng index ---")
        print("    " + ", ".join(real_orphan[:24]))
    print(f"  ({len(orphan) - len(real_orphan)} mã MDR-*/IRO-* bỏ qua: yêu cầu xuyên suốt, "
          f"không phải dòng index)")
    if a.out:
        pathlib.Path(a.out).write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in out) + "\n", encoding="utf-8")
        print(f"\n{len(out)} claim -> {a.out}")

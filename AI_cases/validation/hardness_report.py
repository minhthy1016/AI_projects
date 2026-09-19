#!/usr/bin/env python3
"""Chấm điểm độ khó và độ tin cậy của pipeline trích xuất, xuất ra CSV.

Dùng để làm gì
--------------
Trước khi biến pipeline này thành một kỹ năng agent chạy thật, phải trả lời
được bằng số: tài liệu nào khó, chỗ nào hệ thống còn yếu, và con số đẹp có
phải do trùng hợp không. File này gom mọi phép đo rời rạc thành MỘT bảng, một
dòng cho mỗi tài liệu, để nạp thẳng vào công cụ vẽ biểu đồ.

Bốn câu hỏi, không gộp làm một
------------------------------
1. ĐÚNG KHÔNG      precision = khớp chính xác / đối chiếu được
2. KIỂM ĐƯỢC KHÔNG verifiability = đối chiếu được / lấy ra
                   Phần không đối chiếu được là phần ta phát ra mà KHÔNG có gì
                   để kiểm. Với một agent chạy thật, đây là rủi ro chính.
3. ĐỦ KHÔNG        recall_inscope = bắt được / số nhãn đã khai có trong đáp án
                   coverage_filing = bắt được / TOÀN BỘ đáp án của tài liệu
                   Hai mẫu số khác nhau; cái thứ hai mới nói phạm vi thật.
4. CÓ HƠN NGẪU NHIÊN KHÔNG
                   chance_floor = đem đáp án của tài liệu này so với BẢN PARSE
                   CỦA CÔNG TY KHÁC. Trần không có nền là con số không đọc
                   được: đo trên cả tài liệu 300 trang, nền lên tới 87%.

Hai điểm, không gộp làm một
---------------------------
    trust = precision × verifiability      "cái ta phát ra có tin được không"
    coverage_filing                        "ta phủ được bao nhiêu tài liệu"

Nhân chứ không lấy trung bình cho `trust`: một hệ thống đúng 100% nhưng chỉ
kiểm được 10% sản lượng thì CHƯA đáng tin, và phép nhân phản ánh điều đó còn
trung bình thì không.

VÌ SAO recall_inscope KHÔNG nằm trong điểm — đây là chỗ tôi làm sai trước rồi
sửa. Mẫu số của nó là "số nhãn đã khai", nên nó THƯỞNG CHO VIỆC KHAI ÍT. Đo
thật trên 8 tài liệu:

    bảng tên gọi   recall_inscope   coverage_filing
    viết tay  (91 nhãn)    92,9%          11,6%
    sinh ra  (592 nhãn)    60,2%          44,1%

Bảng sinh tự động phủ gấp gần 4 lần tài liệu, nhưng recall_inscope lại thấp
hơn — chỉ vì nó dám khai nhiều hơn. Đưa nó vào điểm tổng hợp là tự thưởng cho
tham vọng hẹp. Nó vẫn được xuất ra cột riêng, để đọc kèm số nhãn đã khai chứ
không đứng một mình.

Trust và coverage cũng không nên nhân với nhau: phạm vi hẹp là một LỰA CHỌN
(chỉ lấy khoản mục cần cho tín hiệu greenwashing), còn sai số thì không.

Cột "chốt chặn" (guard_*)
-------------------------
Số bảng bị BỎ vì không xác định được đơn vị / không rõ thuộc báo cáo nào. Đây
là con số TỐT: fail-closed đang hoạt động. Theo dõi nó để biết khi nào một
thay đổi vô tình mở cổng ra.

Chạy:
    python3 validation/hardness_report.py --out data/hardness_report.csv
    python3 validation/hardness_report.py --labels-dir data/labelmaps --out ...
"""
import argparse, collections, contextlib, csv, io, json, pathlib, re, sys
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from extraction.doc_extract import PROFILES, extract, load_label_map
from parsing import docling_io
from validation import validate_identities as V

ROOT = pathlib.Path(__file__).resolve().parents[1]

# tên · profile · bản parse · file kết quả · đường dẫn xBRL-JSON · ngôn ngữ · PDF
DOCS = [
 ("OMV",           "omv-de",     "omv-canon",     "omv-2025",
  "549300V62YJ9HTLRI486/2025-12-31/omvag-2025-12-31-1-de.json",       "de", "omv/omv-2025-esef-rendered.pdf"),
 ("Aker BP",       "akerbp-en",  "akerbp-canon",  "akerbp-2024",
  "549300NFTY73920OYK69/2024-12-31/549300NFTY73920OYK69-2024-12-31-en.json", "en", "akerbp/akerbp-2024-esef-rendered.pdf"),
 ("Shell",         "shell-en",   "shell-canon",   "shell-2025",
  "21380068P1DRHMJ8KU70/2025-12-31/shel-2025-12-31-en.json",          "en", "shell/shell-2025-esef-rendered.pdf"),
 ("Equinor",       "equinor-nb", "equinor-canon", "equinor-2024",
  "OW6OFBNCKXC4US5C7523/2024-12-31/eqnr-2024-12-31-0-nb.json",        "nb", "equinor/equinor-2024-esef-rendered.pdf"),
 ("Eni",           "eni-it",     "eni-canon",     "eni-2025",
  "BUCRF72VH5RBN7X3VL35/2025-12-31/BUCRF72VH5RBN7X3VL35-2025-12-31-1-it.json", "it", "eni/eni-2025-esef-rendered.pdf"),
 ("Repsol",        "repsol-es",  "repsol-canon",  "repsol-2024",
  "BSYCX13Y0NOTV14V9N85/2024-12-31/BSYCX13Y0NOTV14V9N85-20241231-es.json", "es", "repsol/repsol-2024-esef-rendered.pdf"),
 ("Galp",          "galp-en",    "galp-canon",    "galp-2024",
  "2138003319Y7NM75FG53/2024-12-31/023179-2024-12-31.json",           "en", "galp/galp-2024-wide.pdf"),
 ("TotalEnergies", "tte-en",     "tte-canon",     "totalenergies-2025",
  "529900S21EQ1BO4ESM68/2025-12-31/529900S21EQ1BO4ESM68-2025-12-31.json", "en", "totalenergies/totalenergies-2025-wide.pdf"),
]

NUM = re.compile(r"\d")
STAT = re.compile(r"v2\] (\d+) bảng có cột năm, (\d+) fact, (\d+) nhãn trùng.*?"
                  r"(\d+) dòng khớp nhãn nhưng không có số, (\d+) bảng dùng đơn vị suy.*?"
                  r"(\d+) bảng tiếp nối.*?(\d+) bảng bỏ vì không rõ.*?(\d+) bảng bỏ vì không xác định")


def quiet(fn, *a, **k):
    """Chạy hàm và nuốt mọi thứ nó in ra — báo cáo này tự lo phần hiển thị."""
    err = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
        out = fn(*a, **k)
    return out, err.getvalue()


def key_of(r):
    tax, local = r["line_item_canonical"].split(":", 1)
    per = ((r["period_end"],) if r["statement"] == "balance_sheet"
           else (r["period_start"], r["period_end"]))
    return (tax, local, per)


def ground_truth(rel):
    facts, _ = quiet(V.from_xbrl_json, ROOT / "data/esef" / rel)
    return {(f.taxonomy, f.concept, f.period): f for f in facts if f.taxonomy == "ifrs-full"}


def parsed_text(stem):
    d = docling_io.load(ROOT / f"data/parsed/{stem}.docling.json")
    parts = [t["text"] for t in d["texts"]]
    for tb in d["tables"]:
        for row in tb["grid"]:
            parts += [c for c in row if c]
    return " ".join(parts), d


def chance_floor(gt, others):
    """Bao nhiêu phần đáp án khớp được với bản parse của công ty KHÁC.

    Khớp theo giá trị với dung sai tương đối, đúng như coverage_esef, nhưng ở
    đây chạy được cho cả 8 tài liệu vì dùng xBRL-JSON làm đáp án thay vì bộ
    gold của Fabrion (chỉ có cho 2 công ty).
    """
    if not gt or not others:
        return None
    vals = [abs(float(f.value)) for f in gt.values() if f.value]
    if not vals:
        return None
    hit = 0
    for v in vals:
        tol = max(0.5, v * 0.005)
        if any(any(abs(n - v) <= tol for n in bag) for bag in others):
            hit += 1
    return hit / len(vals)


def numbers_of(text):
    out = set()
    for tok in re.findall(r"[-–−(]?\d[\d.,]*\d|\d", text):
        t = tok.strip("(–−-")
        for cand in (t.replace(",", ""), t.replace(".", "").replace(",", ".")):
            try:
                out.add(abs(float(cand)))
            except ValueError:
                pass
    return out


def row_for(doc, label_map_dir):
    name, prof, parsed, exname, truth, lang, pdf = doc
    gt = ground_truth(truth)
    txt, d = parsed_text(parsed)

    lm = None
    mode = "hand"
    if label_map_dir:
        f = pathlib.Path(label_map_dir) / f"{exname}.json"
        if f.exists():
            lm = load_label_map(f)
            mode = "generated"

    rows, err = quiet(extract, str(ROOT / f"data/parsed/{parsed}.docling.json"), name, prof,
                      label_map=lm)
    m = STAT.search(err)
    g = (lambda i: int(m.group(i)) if m else 0)

    keys = {key_of(r) for r in rows if r.get("value") is not None}
    comparable = exact = 0
    for r in rows:
        if r.get("value") is None:
            continue
        k = key_of(r)
        if k in gt:
            comparable += 1
            if Decimal(str(r["value"])) == gt[k].value:
                exact += 1

    labels = lm[0] if lm else PROFILES[prof]["labels"]
    mapped = {tuple(v[0].split(":", 1)) for v in labels.values()}
    inscope = {k for k in gt if (k[0], k[1]) in mapped}
    caught = len(inscope & keys)

    ident, _ = quiet(lambda: None)
    pdf_path = ROOT / "data/ir-pdf" / pdf
    try:
        import pypdf
        pages = len(pypdf.PdfReader(str(pdf_path)).pages)
    except Exception:
        pages = ""

    prec = exact / comparable if comparable else None
    verif = comparable / len(rows) if rows else None
    rec = caught / len(inscope) if inscope else None
    cov = caught / len(gt) if gt else None
    trust = (prec * verif) if None not in (prec, verif) else None

    return dict(
        company=name, language=lang, label_map=mode,
        # độ khó đầu vào
        pdf_pages=pages,
        parsed_tables=len(d["tables"]),
        numeric_cells=sum(1 for tb in d["tables"] for row in tb["grid"]
                          for c in row if c and NUM.search(c)),
        label_count=len(labels),
        # chốt chặn — số càng khác 0 nghĩa là fail-closed đang chặn thật
        guard_no_scale=g(8), guard_no_section=g(7),
        guard_empty_row=g(4), guard_dup_label=g(3),
        assist_doc_scale=g(5), assist_continuation=g(6),
        # sản lượng
        facts_extracted=len(rows),
        facts_comparable=comparable,
        facts_exact=exact,
        gt_total=len(gt), gt_inscope=len(inscope), gt_caught=caught,
        # điểm
        precision=round(prec, 4) if prec is not None else "",
        verifiability=round(verif, 4) if verif is not None else "",
        recall_inscope=round(rec, 4) if rec is not None else "",
        coverage_filing=round(cov, 4) if cov is not None else "",
        trust=round(trust, 4) if trust is not None else "",
    ), gt, txt


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/hardness_report.csv")
    ap.add_argument("--labels-dir", help="dùng bảng tên gọi sinh từ iXBRL nếu có "
                                         "(vd data/labelmaps); thiếu file nào thì công ty đó "
                                         "vẫn dùng bảng viết tay, cột label_map ghi rõ")
    a = ap.parse_args(argv)

    rows, gts, texts = [], {}, {}
    for doc in DOCS:
        parsed_file = ROOT / f"data/parsed/{doc[2]}.docling.json"
        if not parsed_file.exists():
            print(f"  bỏ qua {doc[0]}: chưa có {parsed_file.name}")
            continue
        r, gt, txt = row_for(doc, a.labels_dir)
        rows.append(r); gts[doc[0]] = gt; texts[doc[0]] = numbers_of(txt)

    if not rows:
        sys.exit("không chấm được tài liệu nào — chạy parsing/docling_convert.py trước")

    # nền ngẫu nhiên: đáp án của công ty này so với bản parse của các công ty khác
    for r in rows:
        others = [texts[k] for k in texts if k != r["company"]]
        f = chance_floor(gts[r["company"]], others)
        r["chance_floor"] = round(f, 4) if f is not None else ""
        r["signal_margin"] = (round(r["coverage_filing"] - f, 4)
                              if f is not None and r["coverage_filing"] != "" else "")

    out = ROOT / a.out if not pathlib.Path(a.out).is_absolute() else pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0])
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
        tot = {c: "" for c in cols}
        tot["company"] = "TOTAL"
        tot["label_map"] = rows[0]["label_map"]
        for c in ("pdf_pages", "parsed_tables", "numeric_cells", "label_count",
                  "guard_no_scale", "guard_no_section", "guard_empty_row", "guard_dup_label",
                  "assist_doc_scale", "assist_continuation",
                  "facts_extracted", "facts_comparable", "facts_exact",
                  "gt_total", "gt_inscope", "gt_caught"):
            tot[c] = sum(r[c] for r in rows if isinstance(r[c], int))
        if tot["facts_comparable"]:
            tot["precision"] = round(tot["facts_exact"] / tot["facts_comparable"], 4)
            tot["verifiability"] = round(tot["facts_comparable"] / tot["facts_extracted"], 4)
        if tot["gt_inscope"]:
            tot["recall_inscope"] = round(tot["gt_caught"] / tot["gt_inscope"], 4)
            tot["coverage_filing"] = round(tot["gt_caught"] / tot["gt_total"], 4)
            tot["trust"] = round(tot["precision"] * tot["verifiability"], 4)
        w.writerow(tot)

    hdr = (f"{'công ty':14}{'ngôn':5}{'đúng':>7}{'kiểm được':>11}{'tin cậy':>9}"
           f"{'phạm vi':>9}{'nền':>7}{'đủ/đã khai':>12}")
    print(hdr); print("-" * len(hdr))
    for r in rows + [tot]:
        p = lambda k: f"{r[k]*100:>6.1f}%" if isinstance(r[k], float) else f"{'—':>7}"
        print(f"{r['company']:14}{r['language']:5}{p('precision')}{p('verifiability'):>11}"
              f"{p('trust'):>9}{p('coverage_filing'):>9}{p('chance_floor')}"
              f"{p('recall_inscope'):>12}")
    print(f"\nbảng tên gọi: {rows[0]['label_map']}  ·  {len(rows)} tài liệu  ·  -> {out}")
    print("tin cậy = đúng × kiểm được  ·  phạm vi = bắt được / TOÀN BỘ đáp án")
    print("đủ/đã khai = bắt được / số nhãn đã khai — đọc kèm cột label_count, vì mẫu số")
    print("này thưởng cho việc khai ít nhãn nên không được đưa vào điểm tin cậy.")
    print("nền = đáp án của công ty này khớp được bao nhiêu với bản parse công ty khác.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

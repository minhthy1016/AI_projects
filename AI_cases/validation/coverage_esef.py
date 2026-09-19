#!/usr/bin/env python3
"""
Đo trần recall cho bộ ESEF — bản dùng riêng, có nhận biết locale.

Cùng ý tưởng với `tools/schema_extraction/evaluate/coverage.py` của fabrion:
đếm bao nhiêu giá trị gold thực sự có mặt trong input Docling, TRƯỚC khi bất
kỳ extractor nào chạy. Chạy độc lập trong AI_cases, không cần repo fabrion.

Khác bản gốc ở bốn chỗ, cả bốn đều cần cho corpus này:

  1. Đọc số theo locale của tài liệu (text_match_locale), nên "24.308" ra 24308
     thay vì 24,308. Bản gốc chỉ strip dấu phẩy nên hạ coverage của tài liệu Đức
     một cách giả tạo — đo được: 33/37 giá trị gold của OMV chỉ tồn tại ở dạng Âu.
  2. Báo cáo TÁCH THEO TRƯỜNG. Gộp `scale` và `data_period` vào một tỉ lệ chung
     là tự hạ trần: gold ghi 1000000 và "FY2025" trong khi tài liệu viết
     "In EUR Mio" và "2025" — hai trường này không đọc được từ văn bản ở bất kỳ
     parser nào, nên đếm chúng vào mẫu số chỉ làm con số khó hiểu hơn.
  3. Báo cáo kèm NỀN NGẪU NHIÊN. Một trần không có nền là con số không đọc được.
  4. Tách riêng ca LỆCH QUY ƯỚC DẤU (xem dưới), vì đó không phải lỗi parser.

PHẠM VI: đo trên bản parse của AI_cases
---------------------------------------
`data/parsed/*-canon.docling.json` chỉ chứa các trang báo cáo tài chính, không
phải cả 300 trang. Đó đúng là thứ extractor nhìn thấy, nên câu hỏi được trả lời
ở đây là "giá trị có nằm trong phần ta đã parse không" — sát với pipeline hơn
là "có nằm đâu đó trong tài liệu không".

Đo trên bản parse đầy đủ của fabrion cho trần 99% nhưng nền 80%. Trên bản
canon: trần 98%, nền 11%. Cùng một trần, nhưng thu hẹp phạm vi làm nền sụp,
và phần chênh mới là thông tin.

NỀN NGẪU NHIÊN
--------------
`covered()` khớp theo giá trị trong dung sai tương đối, trên túi số của toàn
bản parse, không quan tâm số nằm ở trang nào. Trường chữ còn dễ hơn: `unit` =
"USD" chỉ cần chuỗi "USD" xuất hiện một lần ở đâu đó.

Nên mỗi tỉ lệ đi kèm nền: cùng bộ gold đó đo bằng bản parse của công ty KHÁC
trong corpus. Khoảng cách giữa hai cột mới là phần thông tin thật.

LỆCH QUY ƯỚC DẤU
----------------
Gold ghi theo quy ước taxonomy (chi phí thuế là số DƯƠNG), tài liệu in theo
quy ước trình bày (–1.834). `covered()` so có dấu nên trượt, dù giá trị nằm
ngay đó và extractor xử lý đúng bằng sign_flip. Đếm riêng, không gộp vào phần
"không đọc được".

Chính hai ca này lộ ra vì sao nền quan trọng: trên bản parse đầy đủ, +1834 và
+2163 KHỚP — nhưng khớp vào một con số khác ở trang khác. Trần 99% cũ có hai
điểm là trùng hợp.

Chạy:
    python3 validation/coverage_esef.py
"""
import argparse, collections, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from parsing import docling_io
from shared.text_match_locale import detect_separator, input_numbers, normalize, covered

ROOT = pathlib.Path(__file__).resolve().parents[1]
GOLD_DIR = ROOT / "data/gold"
# did -> (tên hiển thị, bản parse của AI_cases)
DOCS = {"omv_ar_fy2025":    ("OMV",     ROOT / "data/parsed/omv-canon.docling.json"),
        "akerbp_ar_fy2024": ("Aker BP", ROOT / "data/parsed/akerbp-canon.docling.json")}
# Trường không đọc được từ văn bản: quy ước mã hoá của gold, không phải nội dung.
ENCODED = {"scale", "data_period", "report_period"}


def parse_path(did):
    return DOCS[did][1]

def gold_path(did):
    return GOLD_DIR / f"{did}.gold.json"

def check_inputs():
    """Thiếu input thì nói rõ thiếu gì, thay vì ném traceback từ trong thư viện."""
    missing = [(p, hint) for d in DOCS for p, hint in (
        (gold_path(d), "bộ gold nằm trong git"),
        (parse_path(d), "sinh lại bằng parsing/docling_convert.py"),
    ) if not p.exists()]
    if missing:
        def show(p):
            try:
                return str(p.relative_to(ROOT))
            except ValueError:      # đường dẫn bị trỏ ra ngoài repo
                return str(p)
        sys.exit("thiếu input:\n" + "\n".join(
            f"  {show(p)}   ({hint})" for p, hint in missing))

def doc_text(did):
    d = docling_io.load(parse_path(did))
    parts = [t["text"] for t in d["texts"]]
    for tb in d["tables"]:
        for row in tb["grid"]:
            parts += [c for c in row if c]
    return " ".join(parts)


def gold_values(did):
    g = json.loads(gold_path(did).read_text(encoding="utf-8"))
    for sec, flds in g.items():
        if sec == "meta":
            for k, v in flds.items():
                yield k, v
            continue
        for fld, items in flds.items():
            for it in items:
                for k, v in it.items():
                    yield k, v


def sign_flipped(v, numbers, hay):
    """Giá trị trượt, nhưng SỐ ĐỐI của nó có mặt.

    Gold ghi theo quy ước taxonomy (chi phí thuế dương), tài liệu in theo quy
    ước trình bày (–1.834). Đây không phải lỗi parser: giá trị nằm ngay đó và
    extractor xử lý đúng bằng sign_flip. Gộp nó vào phần "không đọc được" là
    đổ lỗi nhầm chỗ.
    """
    try:
        t = float(v)
    except (TypeError, ValueError):
        return False
    return t != 0 and not covered(t, numbers, hay) and covered(-t, numbers, hay)


def pct(a, b):
    """Chia có bảo vệ: mẫu số 0 thì trả None chứ không ném ZeroDivisionError."""
    return None if not b else a / b * 100

def fmt(p, w=6):
    return f"{'—':>{w}}" if p is None else f"{p:>{w-1}.0f}%"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min-headroom", type=float, default=0.0,
                    help="thoát 1 nếu khoảng cách trần−nền của tổng nhỏ hơn ngưỡng này "
                         "(điểm phần trăm). Mặc định 0 = chỉ báo cáo.")
    a = ap.parse_args(argv)
    check_inputs()

    # Chuẩn bị túi số + text đã chuẩn hoá cho mọi tài liệu, dùng cho cả nền.
    prep = {}
    for did in DOCS:
        t = doc_text(did)
        sep = detect_separator(t)
        prep[did] = dict(sep=sep, fixed=input_numbers(t, sep),
                         anglo=input_numbers(t, "."), hay=normalize(t))

    print(f"{'tài liệu':10s}{'locale':7s}{'trường':22s}{'tổng':>5}{'trần':>6}"
          f"{'nền':>6}{'cách':>6}")
    print("-" * 68)
    grand, flips = collections.Counter(), collections.Counter()
    for did, (name, _) in DOCS.items():
        p = prep[did]
        others = [o for o in DOCS if o != did]
        st = collections.defaultdict(lambda: [0, 0, 0, 0, 0])  # n, anglo, trần, nền, đổi dấu
        for k, v in gold_values(did):
            st[k][0] += 1
            st[k][1] += bool(covered(v, p["anglo"], p["hay"]))
            st[k][2] += bool(covered(v, p["fixed"], p["hay"]))
            # Nền: khớp được ở BẤT KỲ tài liệu nào khác = khớp do trùng hợp.
            st[k][3] += any(covered(v, prep[o]["fixed"], prep[o]["hay"]) for o in others)
            st[k][4] += sign_flipped(v, p["fixed"], p["hay"])
        sub = [0, 0, 0, 0]
        for k, (n, anglo, hit, base, flip) in sorted(st.items()):
            tag = "  (mã hoá)" if k in ENCODED else ""
            if flip:
                tag = f"  +{flip} lệch quy ước dấu" + tag
                flips[k] += flip
            if anglo != hit:
                tag = f"  chỉ-Anh-Mỹ {pct(anglo, n):.0f}%" + tag
            print(f"{name:10s}{'Âu' if p['sep']==',' else 'Anh':7s}{k[:22]:22s}{n:>5}"
                  f"{fmt(pct(hit, n))}{fmt(pct(base, n))}"
                  f"{fmt(pct(hit - base, n))}{tag}")
            if k not in ENCODED:
                sub = [sub[i] + x for i, x in enumerate((n, anglo, hit, base))]
                for i, key in enumerate(("n", "anglo", "fixed", "base")):
                    grand[key] += (n, anglo, hit, base)[i]
        print(f"{'':17s}{'ĐỌC ĐƯỢC TỪ VĂN BẢN':22s}{sub[0]:>5}"
              f"{fmt(pct(sub[2], sub[0]))}{fmt(pct(sub[3], sub[0]))}"
              f"{fmt(pct(sub[2]-sub[3], sub[0]))}\n")

    print("-" * 68)
    ceil, base = pct(grand["fixed"], grand["n"]), pct(grand["base"], grand["n"])
    print(f"{'TỔNG (bỏ trường mã hoá)':39s}{grand['n']:>5}"
          f"{fmt(ceil)}{fmt(base)}{fmt(pct(grand['fixed']-grand['base'], grand['n']))}")
    if ceil is None:
        sys.exit("không có trường nào đọc được từ văn bản — không đo được gì")
    print(f"\ntrần {ceil:.0f}% | nền ngẫu nhiên {base:.0f}% | khoảng cách thật "
          f"{ceil-base:.0f} điểm")
    if flips:
        nf = sum(flips.values())
        print(f"Trong phần trượt có {nf} ca LỆCH QUY ƯỚC DẤU — giá trị có mặt nhưng "
              f"tài liệu in dấu\nngược với gold. Không phải lỗi parser; extractor xử "
              f"lý đúng bằng sign_flip.\nTrần thực chất là "
              f"{pct(grand['fixed'] + nf, grand['n']):.0f}%.")
    print("Nền = cùng bộ gold đó khớp được với tài liệu của công ty khác. Phần "
          "chênh mới là\nthông tin; trần đứng một mình là con số không đọc được.")

    headroom = ceil - base
    if headroom < a.min_headroom:
        print(f"\n!! khoảng cách {headroom:.0f} điểm < ngưỡng {a.min_headroom:.0f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

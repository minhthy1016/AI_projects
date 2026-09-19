#!/usr/bin/env python3
"""So output extraction với xBRL-JSON của CHÍNH tài liệu đó.

Báo cáo tách theo từng lớp lỗi, không gộp thành một con số accuracy — vì
lỗi 1000× và lệch làm tròn không cùng mức nghiêm trọng.

Quan trọng: báo cáo cả hai chiều.

  - Chiều thuận (precision): fact trích ra có đúng giá trị không.
  - Chiều ngược (recall)   : fact CÓ trong ground truth mà extraction bỏ sót.

Bản cũ chỉ duyệt fact trích ra, nên in "khớp tuyệt đối 100%" trong khi 201/233
fact ground truth chưa bao giờ được chạm tới. Một bộ trích xuất chỉ đọc đúng
một dòng cũng đạt 100% theo cách đo đó.

Recall được tách làm hai, vì hai loại này đòi hai hành động khác nhau:

  - BỎ SÓT trong phạm vi : concept đã có nhãn trong profile mà vẫn không ra
                           -> lỗi thật của bộ trích xuất, tính là thất bại.
  - NGOÀI phạm vi        : concept chưa được khai nhãn trong profile
                           -> backlog mở rộng, không tính là thất bại.

Mã thoát: 0 = không sai lệch nào, 1 = có giá trị sai hoặc bỏ sót trong phạm vi.
"""
import argparse, json, pathlib, sys
from decimal import Decimal, InvalidOperation
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from validation import validate_identities as V

# Sai thang đo hay đi kèm làm tròn hiển thị: bảng in "24,3" cho 24.308 nghìn.
# Tỷ số khi đó là 0.00099967 chứ không đúng 0.001, nên so khớp phải có dung sai
# tương đối, nếu không mọi lỗi thang đo có làm tròn đều rơi vào rổ "sai khác".
SCALE_REL_TOL = Decimal("0.005")

def scale_exponent(d, g, rel_tol=SCALE_REL_TOL):
    """Trả k nếu d/g ≈ 10^k (k≠0), ngược lại None.

    Bản cũ chỉ bắt đúng hai giá trị 1000 và 0.001. Lỗi phổ biến nhất của corpus
    này lại là 10^6 ("In EUR Mio"), và nó lặng lẽ rơi vào rổ "sai khác".
    """
    if not d or not g:
        return None
    ratio = abs(Decimal(d) / Decimal(g))
    for k in range(-9, 10):
        if k == 0:
            continue
        p = Decimal(10) ** k
        if abs(ratio - p) <= rel_tol * p:
            return k
    return None

def split_canonical(canon, where):
    """Tách 'ifrs-full:Revenue' -> ('ifrs-full', 'Revenue'). Fail closed.

    Bản cũ dùng canon.split(":")[1]:
      - nhãn không có tiền tố  -> IndexError, cả script chết giữa chừng;
      - 'us-gaap:Revenue'      -> cắt cụt thành 'Revenue' rồi đem so với ground
                                  truth 'ifrs-full:Revenue' và báo KHỚP. Đây là
                                  khớp sai xuyên taxonomy, đúng loại false
                                  positive im lặng mà evaluator phải chặn.
    """
    parts = canon.split(":")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        sys.exit(f"line_item_canonical không đúng dạng 'taxonomy:Concept': {canon!r} ({where})")
    return parts[0], parts[1]

def period_of(r, where):
    """balance_sheet là thời điểm (1 phần tử), còn lại là kỳ (2 phần tử)."""
    st = r.get("statement")
    if not st:
        sys.exit(f"thiếu trường 'statement' ({where})")
    if st == "balance_sheet":
        if not r.get("period_end"):
            sys.exit(f"balance_sheet thiếu period_end ({where})")
        return (r["period_end"],)
    if not r.get("period_start") or not r.get("period_end"):
        sys.exit(f"{st} thiếu period_start/period_end ({where})")
    return (r["period_start"], r["period_end"])

def load_extracted(path):
    rows, nil = [], 0
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        where = f"{path.name} dòng {n}"
        try:
            r = json.loads(line)
        except json.JSONDecodeError as e:
            sys.exit(f"{where}: không đọc được JSON ({e})")
        tax, local = split_canonical(r.get("line_item_canonical", ""), where)
        # Ô trống hợp lệ: tài liệu in "-" hoặc "n/a", bộ trích xuất ghi
        # value=None kèm value_raw_text. Đó KHÔNG phải lỗi định dạng — bỏ qua
        # và đếm riêng. Bản trước dừng cả chương trình ở đây, nên chỉ cần một ô
        # trống trong 136 dòng là không đối chiếu được gì.
        if r.get("value") is None:
            nil += 1
            continue
        try:
            val = Decimal(str(r["value"]))
        except (KeyError, InvalidOperation, TypeError):
            sys.exit(f"{where}: value không đọc được thành số: {r.get('value')!r}")
        rows.append(dict(key=(tax, local, period_of(r, where)), value=val, where=where))
    if nil:
        print(f"  ({nil} ô trống hợp lệ, không đối chiếu)")
    return rows

def profile_concepts(profile_name):
    """Tập concept mà profile đã khai nhãn — mẫu số cho recall trong phạm vi."""
    from extraction.doc_extract import PROFILES
    if profile_name not in PROFILES:
        sys.exit(f"profile không có: {profile_name!r} (có: {', '.join(PROFILES)})")
    out = set()
    for v in PROFILES[profile_name]["labels"].values():
        concept = v[0] if isinstance(v, (tuple, list)) else v
        out.add(tuple(concept.split(":", 1)))
    return out

def show(rows, limit=8, fmt=None):
    for item in rows[:limit]:
        print(fmt(item))
    if len(rows) > limit:
        print(f"    … còn {len(rows) - limit} dòng nữa")

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--extracted", required=True)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--taxonomy", default="ifrs-full", help="taxonomy của ground truth")
    ap.add_argument("--profile", help="profile trong doc_extract để chia recall "
                                      "trong/ngoài phạm vi (vd omv-de)")
    a = ap.parse_args(argv)

    gt = {(f.taxonomy, f.concept, f.period): f
          for f in V.from_xbrl_json(pathlib.Path(a.truth)) if f.taxonomy == a.taxonomy}
    ex = load_extracted(pathlib.Path(a.extracted))

    print(f"\n{'='*100}\n{a.name or a.extracted}\n{'='*100}")

    # Trùng khoá: hai dòng cùng (concept, kỳ) nhưng khác giá trị nghĩa là bộ
    # trích xuất đọc một con số hai lần từ hai chỗ và không nhất quán.
    seen, dups = {}, []
    for r in ex:
        if r["key"] in seen and seen[r["key"]]["value"] != r["value"]:
            dups.append((r["key"], seen[r["key"]]["value"], r["value"]))
        seen.setdefault(r["key"], r)

    cls = {"khớp": [], "sai dấu": [], "sai thang đo": [], "sai khác": [],
           "filer không tag": [], "khác taxonomy": []}
    for r in ex:
        tax, local, per = r["key"]
        g = gt.get(r["key"])
        d = r["value"]
        row = (local, per[-1], d, g.value if g else None)
        if g is None:
            other = any(k[1] == local and k[2] == per for k in gt)
            cls["khác taxonomy" if other else "filer không tag"].append(row)
        elif d == g.value:
            cls["khớp"].append(row)
        elif g.value and d == -g.value:
            cls["sai dấu"].append(row)
        elif (k := scale_exponent(d, g.value)) is not None:
            cls["sai thang đo"].append(row + (k,))
        else:
            cls["sai khác"].append(row)

    cmp_n = sum(len(cls[x]) for x in ("khớp", "sai dấu", "sai thang đo", "sai khác"))
    print(f"{len(ex)} fact trích ra | {cmp_n} đối chiếu được | "
          f"khớp tuyệt đối {len(cls['khớp'])}"
          + (f" = {len(cls['khớp'])/cmp_n:.1%} (độ chính xác)" if cmp_n else " — không đối chiếu được"))

    for lab in ("sai thang đo", "sai dấu", "sai khác", "khác taxonomy", "filer không tag"):
        if cls[lab]:
            print(f"\n  [{lab}] {len(cls[lab])}")
            show(cls[lab], fmt=lambda t: (
                f"    {t[0][:48]:48s} {t[1]}  ext={t[2]:>16,.1f}  "
                + (f"gt={t[3]:>16,.1f}" if t[3] is not None else f"gt={'—':>16s}")
                + (f"  ×10^{t[4]}" if len(t) > 4 else "")))

    if dups:
        print(f"\n  [trùng khoá, giá trị lệch nhau] {len(dups)}")
        show(dups, fmt=lambda t: f"    {t[0][1][:48]:48s} {t[0][2][-1]}  {t[1]:,.1f} ≠ {t[2]:,.1f}")

    # ---- chiều ngược: ground truth có mà extraction không ra -----------------
    keys = {r["key"] for r in ex}
    missed = sorted(set(gt) - keys)
    print(f"\n  BỎ SÓT: {len(missed)}/{len(gt)} fact ground truth không được trích ra")

    in_scope_missed = []
    if a.profile:
        mapped = profile_concepts(a.profile)
        in_scope_missed = [k for k in missed if (k[0], k[1]) in mapped]
        out_scope = len(missed) - len(in_scope_missed)
        hit = len([k for k in gt if (k[0], k[1]) in mapped and k in keys])
        denom = hit + len(in_scope_missed)
        print(f"    trong phạm vi profile {a.profile}: bắt {hit}/{denom}"
              + (f" = {hit/denom:.1%} (recall)" if denom else ""))
        # Hai mức nghiêm trọng khác hẳn nhau: concept có nhãn mà KHÔNG ra fact
        # nào là nhãn chết (sai chính tả, sai section, bảng không được quét);
        # còn concept ra rồi mà thiếu một kỳ thường chỉ là cột so sánh nằm
        # ngoài bảng được đọc.
        got_concepts = {(k[0], k[1]) for k in keys}
        dead = [k for k in in_scope_missed if (k[0], k[1]) not in got_concepts]
        partial = [k for k in in_scope_missed if (k[0], k[1]) in got_concepts]
        if dead:
            print(f"\n  [nhãn chết — có khai nhưng không ra fact nào] {len(dead)}")
            show(dead, fmt=lambda k: f"    {k[1][:48]:48s} {k[2]}  gt={gt[k].value:>16,.1f}")
        if partial:
            print(f"\n  [thiếu kỳ — concept có ra, kỳ này không] {len(partial)}")
            show(partial, fmt=lambda k: f"    {k[1][:48]:48s} {k[2]}  gt={gt[k].value:>16,.1f}")
        print(f"    ngoài phạm vi (chưa khai nhãn): {out_scope} — backlog mở rộng")
    else:
        print("    (thêm --profile để tách bỏ sót thật khỏi phần chưa khai nhãn)")

    bad = len(cls["sai dấu"]) + len(cls["sai thang đo"]) + len(cls["sai khác"]) \
        + len(cls["khác taxonomy"]) + len(dups) + len(in_scope_missed)
    if bad:
        print(f"\n  => {bad} sai lệch cần xử lý")
        return 1
    print("\n  => không sai lệch nào trong phạm vi")
    return 0

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Gold layer — tính dấu hiệu nghi vấn từ Silver B, mỗi dấu hiệu kèm bằng chứng.

Rule-based, KHÔNG phải máy học: greenwashing không có đáp án đúng/sai để huấn
luyện, nên đây là chấm mâu thuẫn có bằng chứng truy được, không phải phân loại.

Bản trước có ba khuyết tật về cấu trúc, và cả ba đều nguy hiểm theo cùng một
kiểu: chúng làm hệ thống TRÔNG như đang kiểm nhiều hơn thực tế.

  - Dấu hiệu #3 là khối `if ... pass` — tính điều kiện rồi không phát gì. Mà
    Aker BP thoả đúng điều kiện đó: 0 mục tiêu phủ Scope 3, trong khi Scope 3
    lớn gấp 84 lần Scope 1+2. Phát hiện đó đã nằm trong báo cáo, nhưng do người
    tính tay chứ không phải do hệ thống sinh ra.
  - Không ghi ra file. Mọi tầng khác đều xuất JSONL; tầng này chỉ in ra màn hình,
    nên không diff được giữa hai lần chạy và không tầng sau nào dùng được.
  - Toàn bộ là code mức module, không có hàm — nên không import được, và đó là
    lý do nó là file duy nhất không có test.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

# Ngưỡng: scope lớn hơn scope được đặt mục tiêu bao nhiêu lần thì mới coi là
# "phần chi phối". 5x là bảo thủ — với dầu khí, tỉ lệ thực tế là hàng chục lần.
DOMINANT_RATIO = 5.0
# Sai lệch cho phép khi đối chiếu baseline giữa hai chỗ công bố, đơn vị Mio t.
BASELINE_TOL_MT = 0.1

SCOPE_12 = ("combined_1_2_market", "combined_1_2_reported")


def load(path) -> list[dict]:
    return [json.loads(l) for l in pathlib.Path(path).read_text(encoding="utf-8").splitlines()
            if l.strip()]


def build_series(rows) -> tuple[dict, dict, list[str]]:
    """(chuỗi theo năm, bằng chứng theo năm, cảnh báo).

    Phát hiện GHI ĐÈ: hai bản ghi cùng (scope, loại chỉ tiêu, năm) mà khác giá
    trị thì bản sau sẽ đè bản trước. Bản cũ ghi đè im lặng — với một tầng sinh
    cáo buộc thì việc lặng lẽ chọn một trong hai con số là không chấp nhận được.
    """
    series, ev, warn = collections.defaultdict(dict), collections.defaultdict(dict), []
    for r in rows:
        if r.get("claim_type") != "quantitative" or not r.get("is_subtotal"):
            continue
        if r.get("value") is None or not r.get("period_end"):
            continue                      # ô trống: không công bố, không phải 0
        key = (r["scope"], "company_specific" if r.get("is_company_specific") else "esrs")
        year = int(r["period_end"][:4])
        if year in series[key] and series[key][year] != r["value"]:
            warn.append(f"hai giá trị khác nhau cho {key} năm {year}: "
                        f"{series[key][year]:,.0f} và {r['value']:,.0f}")
        series[key][year] = r["value"]
        ev[key][year] = r["source_ref"]
    return series, ev, warn


def change(series, key):
    """(phần_trăm, năm_đầu, năm_cuối, giá_trị_đầu, giá_trị_cuối) hoặc None.

    Trả None khi không đủ dữ liệu HOẶC khi gốc bằng 0 — chia cho 0 ở đây sẽ làm
    sập cả tầng, và một chuỗi bắt đầu từ 0 thì "phần trăm thay đổi" cũng vô nghĩa.
    """
    s = series.get(key)
    if not s or len(s) < 2:
        return None
    years = sorted(s)
    first, last = s[years[0]], s[years[-1]]
    if not first:
        return None
    return (last - first) / first * 100, years[0], years[-1], first, last


def _sig(name, severity, detail, evidence, **extra):
    return dict(signal=name, severity=severity, detail=detail,
                evidence=[e for e in evidence if e], **extra)


def scope12_down_scope3_up(series, ev):
    """Phần được đo thì giảm, phần chi phối thì tăng."""
    a12 = next((change(series, (s, "esrs")) for s in SCOPE_12 if change(series, (s, "esrs"))), None)
    a3 = change(series, ("scope_3", "esrs"))
    if not (a12 and a3) or not a12[4]:
        return []
    if not (a12[0] < 0 < a3[0]):
        return []
    key12 = next(s for s in SCOPE_12 if change(series, (s, "esrs")))
    base = a3[3] + a12[3]
    return [_sig("scope12_down_scope3_up", "high",
                 f"Scope 1+2 {a12[0]:+.1f}% ({a12[1]}→{a12[2]}) nhưng Scope 3 {a3[0]:+.1f}%; "
                 f"Scope 3 lớn gấp {a3[4] / a12[4]:.0f}× Scope 1+2",
                 [ev[(key12, "esrs")].get(a12[2]), ev[("scope_3", "esrs")].get(a3[2])],
                 net_change_pct=round((a3[4] + a12[4] - base) / base * 100, 1) if base else None)]


def target_anchored_to_company_metric(series, ev, targets):
    """Mục tiêu neo vào chỉ tiêu tự định nghĩa thay vì chỉ tiêu bắt buộc."""
    cs, es = series.get(("scope_3", "company_specific")), series.get(("scope_3", "esrs"))
    t3 = [x for x in targets if x.get("scope") == "scope_3" and x.get("baseline_value_mt")]
    if not (cs and es and t3):
        return []
    base_mt, by = t3[0]["baseline_value_mt"], t3[0].get("baseline_year")
    if by is None:
        return []
    near = lambda s: abs(s.get(by, 0) / 1e6 - base_mt) < BASELINE_TOL_MT
    if not (near(cs) and not near(es)):
        return []
    c_cs, c_es = change(series, ("scope_3", "company_specific")), change(series, ("scope_3", "esrs"))
    if not (c_cs and c_es):
        return []
    return [_sig("target_anchored_to_company_specific_metric", "high",
                 f"Mục tiêu Scope 3 neo vào chỉ tiêu tự định nghĩa ({base_mt} Mio t, {by}) "
                 f"đang giảm {c_cs[0]:+.1f}%, không neo vào chỉ tiêu ESRS bắt buộc "
                 f"({es[by] / 1e6:.1f} Mio t) đang tăng {c_es[0]:+.1f}%",
                 [ev[("scope_3", "company_specific")].get(by),
                  ev[("scope_3", "esrs")].get(by), t3[0].get("source_ref")])]


def dominant_scope_not_targeted(series, ev, targets):
    """Phần phát thải lớn nhất không có mục tiêu nào phủ.

    Đây là dấu hiệu mà bản trước TÍNH RỒI BỎ (`if ... pass`). Aker BP thoả đúng
    điều kiện: Scope 3 gấp 84 lần Scope 1+2 và không có mục tiêu nào phủ nó, nên
    phần lớn nhất vừa không có đích đến vừa không đo được tiến độ.
    """
    latest = lambda k: (series.get(k) or {}).get(max(series[k])) if series.get(k) else None
    v3 = latest(("scope_3", "esrs"))
    v12 = next((latest((s, "esrs")) for s in SCOPE_12 if latest((s, "esrs"))), None)
    if not (v3 and v12) or v3 / v12 < DOMINANT_RATIO:
        return []
    if any(x.get("target_covers_scope3") for x in targets):
        return []
    n_t = len(targets)
    covered = v12 / (v3 + v12) * 100
    s3 = series[("scope_3", "esrs")]
    no_baseline = len(s3) < 2
    detail = (f"Scope 3 = {v3:,.0f} t CO2e, gấp {v3 / v12:.0f}× Scope 1+2, nhưng "
              f"{n_t} mục tiêu đều chỉ phủ Scope 1+2 — tức khoảng {covered:.1f}% lượng phát thải")
    if no_baseline:
        detail += ". Scope 3 cũng không có năm gốc nên không đo được tiến độ"
    return [_sig("dominant_scope_not_targeted", "high", detail,
                 [ev[("scope_3", "esrs")].get(max(s3))] +
                 [x.get("source_ref") for x in targets[:1]],
                 scope3_share_pct=round(100 - covered, 1))]


def baseline_consistency(series, targets):
    """Đối chiếu năm gốc khai trong khối mục tiêu với bảng phát thải.

    Trả về (dòng báo cáo, dấu hiệu). Bản trước tính logic này HAI LẦN — một lần
    để phát dấu hiệu, một lần để in — và bản in có `break` nên chỉ in một dòng.
    Hai bản sao của cùng một phép so sánh là cách chắc chắn để chúng trôi lệch.
    """
    lines, signals, seen = [], [], set()
    for x in targets:
        base_mt, by = x.get("baseline_value_mt"), x.get("baseline_year")
        if not base_mt or by is None:
            continue
        key = ((x.get("scope"), "esrs") if x.get("scope") in SCOPE_12
               else ("scope_3", "company_specific"))
        v = series.get(key, {}).get(by)
        if not v:
            continue
        if (key, by) in seen:
            continue
        seen.add((key, by))
        ok = abs(v / 1e6 - base_mt) <= BASELINE_TOL_MT
        lines.append(f"  {x['scope']:22s} E1-4={base_mt:>6.1f} Mio t | "
                     f"E1-6={v / 1e6:>7.3f} Mio t | {'khớp' if ok else 'LỆCH'}")
        if not ok:
            signals.append(_sig("baseline_mismatch", "review",
                                f"{x['scope']} {x.get('target_year')}: E1-4 khai {base_mt} Mio t, "
                                f"E1-6 cho {v / 1e6:.2f} Mio t", [x.get("source_ref")]))
    return lines, signals


def compute(rows):
    """(danh sách dấu hiệu, dòng đối chiếu nội bộ, cảnh báo dữ liệu)."""
    series, ev, warn = build_series(rows)
    targets = [r for r in rows if r.get("claim_type") == "target"]
    lines, sig_base = baseline_consistency(series, targets)
    signals = (scope12_down_scope3_up(series, ev)
               + target_anchored_to_company_metric(series, ev, targets)
               + dominant_scope_not_targeted(series, ev, targets)
               + sig_base)
    return signals, lines, warn


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--esg", required=True, help="file esg_claim JSONL")
    ap.add_argument("--out", help="ghi dấu hiệu ra JSONL (tầng Gold)")
    a = ap.parse_args()

    rows = load(a.esg)
    signals, lines, warn = compute(rows)

    for w in warn:
        print(f"  [cảnh báo dữ liệu] {w}", file=sys.stderr)

    print(f"\n{'=' * 100}\nTÍN HIỆU — {len(signals)} phát hiện\n{'=' * 100}")
    for s in signals:
        print(f"\n[{s['severity'].upper()}] {s['signal']}")
        print(f"  {s['detail']}")
        for e in s["evidence"]:
            print(f"    bằng chứng: trang {e['page_no']}, bảng {e['table_id']}, "
                  f"cột {e['col_header_path']}, nguyên văn \"{e['verbatim_span']}\"")
    print(f"\n{'=' * 100}\nKIỂM NHẤT QUÁN NỘI BỘ\n{'=' * 100}")
    print("\n".join(lines) if lines else "  (không có năm gốc nào để đối chiếu)")

    if a.out:
        pathlib.Path(a.out).write_text(
            "\n".join(json.dumps(s, ensure_ascii=False) for s in signals) + "\n",
            encoding="utf-8")
        print(f"\n{len(signals)} dấu hiệu -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

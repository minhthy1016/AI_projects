#!/usr/bin/env python3
"""
esg-extract v2 — Silver B từ DoclingDocument, một file cho cả hai công ty.

Bản v1 là HAI file riêng (esg_extract.py + esg_extract_akerbp.py, giữ ở *.bak)
vì đọc theo vị trí ký tự thì hai cách trình bày không dùng chung code được.
Với lưới ô của Docling, khác biệt thu về dữ liệu cấu hình:

  OMV      đơn vị khai một lần cho cả bảng ("In t CO2e"), header một tầng
  Aker BP  đơn vị khai TRÊN TỪNG DÒNG ("1,000 t CO 2 e"), header HAI TẦNG
           (Operational control | Equity)

Ba lỗi nặng nhất của v1 biến mất theo:
  - hai bảng chung dòng đơn vị -> lấy nhầm header -> cả bảng lệch một cột
  - nhãn nhóm "Equity" căn giữa dùng làm biên cột -> đọc nhầm sang khối equity,
    mà gate scope1+scope2=total VẪN PASS vì số equity tự nhất quán với nhau
  - "2030" và "target" cách nhau nhiều khoảng trắng bị ghép thành một cột

Nhóm cột giờ đọc thẳng từ hàng header thứ nhất. Khi hàng đó để trống, mốc bắt
đầu nhóm mới được nhận ra bằng việc MỘT NHÃN CỘT LẶP LẠI — quy tắc không phụ
thuộc ngôn ngữ và không phụ thuộc hình học.
"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import argparse, hashlib, json, pathlib, re, sys
from decimal import Decimal

from parsing import docling_io
from shared.numbers import is_number_token, parse_number as _parse_number
from shared.tables import YEAR_ANYWHERE as YEAR, header_columns

NBSP = " "

def norm(s):
    s = (s or "").replace(NBSP, " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def squash(s):
    return re.sub(r"\s+", "", norm(s)).lower()

PROFILES = {
 "omv": dict(
    decimal_separator=",",   # ô trống và quy ước dấu: xem shared/numbers.py
    unit_mode="table",                      # đơn vị khai một lần cho cả bảng
    unit_re=r"In\s+t\s*CO\s*2?\s*e", unit_mult=1, unit_label="t CO2e",
    # Nhận cột năm gốc. Không dùng chuỗi "base" cứng: nhãn của OMV là
    # "2019 (Basisjahr)" — tiếng Đức, KHÔNG chứa "base", nên cờ is_baseline_column
    # của mọi dòng OMV đều sai thành False. Phép kiểm nhất quán E1-4 ↔ E1-6 không
    # phát hiện ra vì nó tra theo năm chứ không theo cờ này.
    baseline_re=r"Basisjahr|Bezugsjahr|base\s*year",
    framework="ESRS", report_year=2025, boundary="operational_control",
    emissions={
      "Scope-1- und Scope-2-Treibhausgasemissionen (marktbezogen)": ("combined_1_2_market", True),
      "Scope-1-THG-Bruttoemissionen": ("scope_1", True),
      "Standortbezogene Scope-2-THG-Bruttoemissionen": ("scope_2_location", True),
      "Marktbezogene Scope-2-THG-Bruttoemissionen": ("scope_2_market", True),
      "Gesamte indirekte (Scope-3-)THG-Bruttoemissionen (alle wesentlichen Kategorien)": ("scope_3", True),
      "Gesamte indirekte (Scope-3-)THG-Bruttoemissionen (z.r.) [unternehmensspezifisch]": ("scope_3", True),
      "davon aus Energiesegmenten von OMV": ("scope_1", False),
      "davon aus Nichtenergiesegmenten von OMV": ("scope_1", False),
    },
    target_header=r"Absolutes Ziel:\s*Scope\s*([13])",
    attr_keys=dict(baseline_year="Basisjahr", baseline_value="Bezugswert in Mio t CO2e",
                   in_scope="Im Umfang enthalten", out_scope="Nicht im Umfang enthalten"),
    target_re=r"um\s*≥?\s*(\d+)\s*%", netzero_re=r"Netto-Null",
 ),
 "akerbp": dict(
    decimal_separator=".",   # ô trống và quy ước dấu: xem shared/numbers.py
    unit_mode="column",                     # đơn vị nằm ở cột "Unit" từng dòng
    unit_re=r"1[,\s]?000\s*t\s*CO\s*2?\s*e", unit_mult=1000, unit_label="1,000 t CO2e",
    baseline_re=r"base\s*year|Basisjahr",
    framework="ESRS", report_year=2024, boundary="operational_control",
    emissions={
      "Gross scope 1 GHG emissions": ("scope_1", True),
      "Gross location-based scope 2 GHG emissions": ("scope_2_location", True),
      "Gross market-based scope 2 GHG emissions": ("scope_2_market", True),
      "Total scope 1 and 2 GHG emissions": ("combined_1_2_reported", True),
      "Total gross indirect (scope 3) GHG emissions": ("scope_3", True),
      "Total GHG emissions (location-based)": ("total_location", True),
      "Total GHG emissions (market-based)": ("total_market", True),
    },
    target_header=None, attr_keys=None, target_re=None, netzero_re=None,
 ),
}

# 20[0-4]\d chỉ phủ 2000-2049 -> KHÔNG khớp "2050 target". Mục tiêu net-zero
# 2050 là mốc quan trọng nhất trong cả báo cáo, và nó biến mất không một lời báo.


def parse_number(tok, prof):
    """Bọc mỏng quanh shared.numbers — cùng một văn phạm với doc_extract.

    Bản trước ở đây là bản sao của parse_number trong doc_extract, nên mang y hệt
    các lỗ hổng: strip("()") nhận ngoặc lệch, lstrip nhận dấu chồng nhau,
    replace() nhận nhóm phân cách sai ba chữ số. Hai bản sao còn có nguy cơ trôi
    lệch nhau theo thời gian. Nay chung một nguồn.
    """
    return _parse_number(tok, prof["decimal_separator"])


def _num(d):
    return int(d) if d == d.to_integral_value() else float(d)


def unify_keys(rows):
    """Ép mọi bản ghi có CÙNG một tập trường, thiếu thì điền None.

    Hai nhánh (extract_emissions và extract_targets_paired) ghi vào cùng một
    bảng Silver B nhưng trước đây sinh ra hai tập trường khác nhau — 5 trường
    chỉ có ở nhánh này, 5 trường chỉ có ở nhánh kia. Các trường BẮT BUỘC thì cả
    hai đều có, nên bộ kiểm hợp đồng không kêu; nhưng mọi bên đọc phải nhớ dùng
    .get() cho từng trường tuỳ nhánh, và quên một lần là KeyError lúc chạy.

    Một bảng thì phải có một hình dạng. Trường không áp dụng được mang giá trị
    None — khác hẳn với việc trường đó biến mất.
    """
    if not rows:
        return rows
    keys = sorted({k for r in rows for k in r})
    return [{k: r.get(k) for k in keys} for r in rows]

def column_map(grid):
    """Bọc mỏng quanh shared.tables.header_columns.

    bare_year_only=False vì ô tiêu đề ESG là CỤM TỪ chứa năm — "Base year (2017)",
    "2030 target". Neo cuối như bên tài chính sẽ làm trượt toàn bộ.

    Logic nhận hàng tiêu đề, bỏ cột nhãn và nhận nhóm cột trước đây là bản sao
    của year_columns bên doc_extract. Bản sao đó đã tự chứng minh là tai hại: lỗi
    "không bỏ qua cột 0" được sửa ở một bên, bên kia vẫn còn.
    """
    ri, cols = header_columns(grid, bare_year_only=False)
    return (ri if ri is not None else 0,
            [(c.index, c.text, c.group, c.year, c.is_target) for c in cols])


def table_unit(tb, texts, prof):
    if prof["unit_mode"] == "table":
        for x in texts:
            if x["page_no"] == tb["page_no"] and re.search(prof["unit_re"], norm(x["text"]), re.I):
                return prof["unit_mult"]
        for row in tb["grid"][:3]:
            for c in row:
                if re.search(prof["unit_re"], norm(c), re.I):
                    return prof["unit_mult"]
    return None

def row_unit(row, prof):
    for c in row[:3]:
        if re.search(prof["unit_re"], norm(c), re.I):
            return prof["unit_mult"]
    return None

def extract_emissions(d, prof, company_id, doc_hash, run_id):
    out, stats = [], {"table": 0, "row": 0, "no_unit": 0, "other_boundary": 0}
    lab_index = {squash(k): v for k, v in prof["emissions"].items()}
    for tb in d["tables"]:
        grid = tb["grid"]
        table_id = f"p{tb['page_no']}-{tb['num_rows']}x{tb['num_cols']}"
        hdr_i, cols = column_map(grid)
        if not cols:
            continue
        tmult = table_unit(tb, d["texts"], prof)
        used = False
        for ri in range(hdr_i + 1, len(grid)):
            key = lab_index.get(squash(grid[ri][0] if grid[ri] else ""))
            if not key:
                continue
            scope, is_total = key
            mult = tmult if prof["unit_mode"] == "table" else row_unit(grid[ri], prof)
            if mult is None:
                # KHÔNG phát ra fact khi chưa biết đơn vị. Mặc định về 1 là cách
                # sinh lỗi 1000× im lặng nhất — gate số học không bắt được vì
                # raw × 1 == value vẫn tự nhất quán.
                stats["no_unit"] += 1
                continue
            stats["row"] += 1
            used = True
            for ci, lab, grp, yr, is_target in cols:
                if grp != prof["boundary"].replace("_", " "):
                    stats["other_boundary"] += 1
                    continue                 # chỉ lấy cơ sở chính, không trộn equity
                if ci >= len(grid[ri]):
                    continue
                raw = norm(grid[ri][ci])
                if not raw or not is_number_token(raw, prof["decimal_separator"]):
                    continue
                val, is_nil = parse_number(raw, prof)
                if val is None and not is_nil:
                    continue
                out.append({
                    # gồm table_id: trang 64 có 4 bảng, trang 67 có 2 — thiếu nó
                    # thì hai bảng cùng trang có ô ở cùng (ri, ci) ra trùng id.
                    "claim_id": hashlib.sha256(
                        f"{doc_hash}|{tb['page_no']}|{table_id}|{ri}|{ci}".encode()).hexdigest()[:32],
                    "run_id": run_id, "doc_hash": doc_hash, "company_id": company_id,
                    "report_year": prof["report_year"],
                    "framework": prof["framework"], "framework_version": "ESRS-2023",
                    "gri_standard_version": None,
                    "gri_code": "E1-4" if is_target else "E1-6",
                    "gri_code_reported": lab,
                    "claim_type": "target" if is_target else "quantitative",
                    "claim_text": norm(grid[ri][0]),
                    "value": None if is_nil else _num(val * Decimal(mult)),
                    "value_raw_text": raw,
                    "unit_reported": prof["unit_label"], "unit_canonical": "tCO2e",
                    "unit_conversion_factor": float(mult),
                    "is_intensity_metric": False, "denominator_basis": None,
                    "scope": scope, "scope3_categories": None,
                    "boundary": prof["boundary"], "boundary_changed_vs_prior": None,
                    "baseline_year": None,
                    "is_baseline_column": bool(re.search(prof["baseline_re"], lab, re.I)),
                    # Mục tiêu KHÔNG có kỳ báo cáo — nó là một cam kết, không phải
                    # một lần công bố số. Hợp đồng esg_claim quy định period_end
                    # phải null khi claim_type=target; nhánh này trước đây vẫn
                    # điền, trong khi nhánh extract_targets_paired thì không —
                    # hai nhánh trong cùng một file bất đồng với nhau.
                    "period_end": None if is_target else f"{yr}-12-31",
                    "target_year": int(yr) if is_target else None,
                    "target_type": "absolute" if is_target else None,
                    "target_covers_scope3": None,
                    "is_company_specific": "unternehmensspezifisch" in norm(grid[ri][0]).lower(),
                    "is_subtotal": is_total, "offsets_included": None,
                    "assurance_level": None, "assurance_covers_this_claim": None,
                    "is_restated": None,
                    "source_ref": {
                        "page_no": tb["page_no"], "bbox": tb["bbox"], "verbatim_span": raw,
                        "table_id": table_id,
                        "row_idx": ri, "col_idx": ci,
                        "col_header_path": [grp, lab], "extraction_path": "native_text",
                    },
                    "groundedness_verified": True, "confidence": 0.98,
                    "decimal_separator": prof["decimal_separator"],
                    "extractor_version": "esg-extract@2.0.0-docling",
                    "model_id": f"docling-{d['meta']['parser_version']}",
                    "prompt_hash": "-", "schema_version": "1.0",
                })
        stats["table"] += 1 if used else 0
    return out, stats

def extract_targets_paired(d, prof, company_id, doc_hash, run_id):
    """Mục tiêu dạng CẶP BẢNG (OMV): bảng 1 cột liệt kê mốc, ngay dưới là bảng
    2 cột chứa Basisjahr / Bezugswert / phạm vi. Ghép theo toạ độ dọc, và scope
    lấy từ tiêu đề mục gần nhất phía trên."""
    if not prof.get("target_header"):
        return []
    out = []
    heads = [(x["page_no"], x["bbox"][1], re.search(prof["target_header"], norm(x["text"])))
             for x in d["texts"] if "header" in x["label"]]
    heads = [(p, t, m.group(1)) for p, t, m in heads if m]
    ak = prof["attr_keys"]
    for tb in d["tables"]:
        if tb["num_cols"] != 2:
            continue
        flat = {squash(r[0]): norm(r[1]) for r in tb["grid"] if len(r) > 1}
        if squash(ak["baseline_year"]) not in flat:
            continue
        top = tb["bbox"][1]
        cand = [(t, s) for p, t, s in heads if p == tb["page_no"] and t >= top]
        if not cand:
            continue
        scope_no = min(cand, key=lambda x: x[0] - top)[1]
        scope = "combined_1_2_market" if scope_no == "1" else "scope_3"
        by = re.search(r"(\d{4})", flat.get(squash(ak["baseline_year"]), "") or "")
        bv = re.search(r"(\d+[,.]\d+)", flat.get(squash(ak["baseline_value"]), "") or "")
        # bảng mốc là bảng 1 cột gần nhất PHÍA TRÊN bảng thuộc tính này
        mile = [t for t in d["tables"] if t["page_no"] == tb["page_no"] and t["num_cols"] == 1
                and t["bbox"][1] > top]
        mile = min(mile, key=lambda t: t["bbox"][1] - top) if mile else None
        if not mile:
            continue
        cells = [norm(r[0]) for r in mile["grid"]]
        page_txt = " ".join(norm(x["text"]) for x in d["texts"] if x["page_no"] == tb["page_no"])
        # Bảng mốc có thể khuyết: Docling đánh rơi nhãn năm "2040" ở khối
        # Scope 1+2 (lưới ra ['2030', mô_tả, mô_tả, '2050']), và các dòng năm
        # cuối không có mô tả đi kèm. KHÔNG suy ra năm còn thiếu — phát hành
        # bản ghi với target_year=None kèm cờ, để thiếu sót nhìn thấy được thay
        # vì biến mất, và tuyệt đối không bịa ra một cái năm.
        pairs = []
        for i, c in enumerate(cells):
            nxt = cells[i + 1] if i + 1 < len(cells) else ""
            is_year = bool(re.fullmatch(r"20\d{2}", c))
            is_desc = bool(re.search(prof["target_re"], c) or re.search(prof["netzero_re"], c))
            if is_year:
                if re.search(prof["target_re"], nxt) or re.search(prof["netzero_re"], nxt):
                    pairs.append((c, nxt, []))
                else:
                    m = re.search(rf"{c}[^.]{{0,80}}?{prof['netzero_re']}|{prof['netzero_re']}[^.]{{0,80}}?{c}",
                                  page_txt)
                    pairs.append((c, m.group(0) if m else "", []
                                  if m else ["description_not_found"]))
            elif is_desc and (i == 0 or not re.fullmatch(r"20\d{2}", cells[i - 1])):
                pairs.append((None, c, ["year_label_missing"]))
        for c, desc, flags in pairs:
            red = re.search(prof["target_re"], desc)
            nz = bool(re.search(prof["netzero_re"], desc))
            if not red and not nz and not flags:
                continue
            out.append({
                "claim_id": hashlib.sha256(f"{doc_hash}{tb['page_no']}{scope}{c}{desc[:30]}t".encode()).hexdigest()[:32],
                "run_id": run_id, "doc_hash": doc_hash, "company_id": company_id,
                "report_year": prof["report_year"], "framework": prof["framework"],
                "framework_version": "ESRS-2023", "gri_standard_version": None,
                "gri_code": "E1-4", "gri_code_reported": "Absolutes Ziel",
                "claim_type": "target", "claim_text": desc[:300],
                "value": float(red.group(1)) if red else None,
                "value_raw_text": red.group(1) if red else desc[:40],
                "unit_reported": "%" if red else None, "unit_canonical": "pct" if red else None,
                "unit_conversion_factor": 1.0,
                "is_intensity_metric": False, "denominator_basis": None,
                "scope": scope, "scope3_categories": None,
                "target_year": int(c) if c else None,
                "target_type": "net_zero" if nz else "absolute",
                "interim_target_present": True,
                "target_covers_scope3": scope == "scope_3",
                "boundary": prof["boundary"],
                "baseline_year": int(by.group(1)) if by else None,
                "baseline_value_mt": float(bv.group(1).replace(",", ".")) if bv else None,
                "in_scope_text": flat.get(squash(ak["in_scope"]), "")[:300] or None,
                "out_of_scope_text": flat.get(squash(ak["out_scope"]), "")[:300] or None,
                "offsets_included": None,
                "assurance_level": None, "assurance_covers_this_claim": None,
                "is_restated": None,
                "source_ref": {
                    "page_no": tb["page_no"], "bbox": tb["bbox"], "verbatim_span": desc[:80],
                    "table_id": f"E1-4-p{tb['page_no']}-{scope}",
                    "row_idx": i, "col_idx": 0,
                    "col_header_path": [f"Absolutes Ziel: Scope {scope_no}", c or "?"],
                    "extraction_path": "native_text",
                },
                "validation_flags": flags,
                "groundedness_verified": True, "confidence": 0.95 if not flags else 0.6,
                "decimal_separator": prof["decimal_separator"],
                "extractor_version": "esg-extract@2.0.0-docling",
                "model_id": f"docling-{d['meta']['parser_version']}",
                "prompt_hash": "-", "schema_version": "1.0",
            })
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--parsed", required=True)
    ap.add_argument("--company-id", required=True)
    ap.add_argument("--profile", required=True, choices=list(PROFILES))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    prof = PROFILES[a.profile]
    d = docling_io.load(a.parsed)
    doc_hash = d["meta"]["source_sha256"]
    run_id = f"esg-extract-docling-{d['meta']['parser_version']}"
    em, st = extract_emissions(d, prof, a.company_id, doc_hash, run_id)
    tg = extract_targets_paired(d, prof, a.company_id, doc_hash, run_id)
    seen, uniq = set(), []
    for r in em + tg:
        k = (r["scope"], r["claim_type"], r.get("target_year"),
             r.get("period_end") if r["claim_type"] != "target" else None,
             r.get("is_company_specific"), r["claim_text"][:60])
        if k in seen:
            continue
        seen.add(k); uniq.append(r)
    uniq = unify_keys(uniq)
    pathlib.Path(a.out).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in uniq) + "\n", encoding="utf-8")
    print(f"    [esg-extract v2] {st['table']} bảng, {st['row']} dòng khớp nhãn, "
          f"{len(em)} claim định lượng, {len(tg)} claim mục tiêu, "
          f"{st['no_unit']} dòng bỏ vì không rõ đơn vị, "
          f"{st['other_boundary']} ô thuộc cơ sở khác", file=sys.stderr)
    print(f"{len(uniq)} claim -> {a.out}")

#!/usr/bin/env python3
"""
Dựng fixture output extraction theo contracts/extraction_contract.json, rồi tiêm lỗi.

Số lấy từ XOM FY2025 thật (companyfacts) nên fixture sạch PHẢI pass toàn bộ.
Từ đó tiêm từng lớp lỗi và xem cổng nào bắt được — đây là test cho chính
validator, thứ mà bộ eval nào cũng cần nhưng hay bị bỏ qua: nếu không biết
validator bắt được gì, con số PASS của nó không có ý nghĩa.

    python3 make_fixture.py                 # bản sạch
    python3 make_fixture.py --defect all    # tiêm đủ 6 lớp lỗi
"""
import argparse, hashlib, json, pathlib
from decimal import Decimal

ROOT = pathlib.Path(__file__).resolve().parents[1]
CF = ROOT / "data/xbrl/companyfacts/CIK0000034088.json"
DOC_HASH = "0" * 64

# concept tham gia các đẳng thức us-gaap + statement tương ứng
PLAN = [
    ("Assets", "balance_sheet", "Total assets"),
    ("Liabilities", "balance_sheet", "Total liabilities"),
    ("LiabilitiesAndStockholdersEquity", "balance_sheet", "Total liabilities and equity"),
    ("StockholdersEquity", "balance_sheet", "Total ExxonMobil share of equity"),
    ("MinorityInterest", "balance_sheet", "Noncontrolling interests"),
    ("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "balance_sheet", "Total equity"),
    ("Revenues", "income_statement", "Total revenues and other income"),
    ("CostsAndExpenses", "income_statement", "Total costs and other deductions"),
    ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
     "income_statement", "Income before income taxes"),
    ("IncomeTaxExpenseBenefit", "income_statement", "Income tax expense"),
    ("ProfitLoss", "income_statement", "Net income including noncontrolling interests"),
    ("NetIncomeLoss", "income_statement", "Net income attributable to ExxonMobil"),
    ("NetIncomeLossAttributableToNoncontrollingInterest", "income_statement",
     "Net income attributable to noncontrolling interests"),
    ("NetCashProvidedByUsedInOperatingActivities", "cash_flow", "Cash provided by operating activities"),
    ("NetCashProvidedByUsedInInvestingActivities", "cash_flow", "Cash used in investing activities"),
    ("NetCashProvidedByUsedInFinancingActivities", "cash_flow", "Cash used in financing activities"),
    ("EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
     "cash_flow", "Effects of exchange rate changes on cash"),
    ("CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
     "cash_flow", "Increase (decrease) in cash"),
    ("CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "balance_sheet",
     "Cash and cash equivalents at end of year"),
]

DEFECTS = {
    "scale_1000x":      "value nhân 1000 nhưng raw text giữ nguyên (cổng bắt)",
    "scale_consistent": "value VÀ raw text cùng nhân 1000 — số học tự nhất quán, chỉ đẳng thức bắt được",
    "sign_flip":        "đảo dấu NCI, sign_rule khai khớp — tự nhất quán, chỉ đẳng thức bắt được",
    "header_mismatch":  "col_header_path ghi 2024 trong khi period_end là 2025",
    "hallucination":    "verbatim_span không tồn tại trong tài liệu",
    "missing_source":   "xoá source_ref",
    "groundedness":     "groundedness_verified = false",
}

def latest(facts, concept, year, instant):
    vs = [v for v in facts.get(concept, {}).get("units", {}).get("USD", [])
          if str(v.get("form", "")).startswith("10-K")
          and v["end"] == f"{year}-12-31"
          and (("start" not in v) if instant else (str(v.get("start", "")).startswith(str(year))))]
    return max(vs, key=lambda v: v.get("filed", "")) if vs else None

def build(year=2025, defects=()):
    facts = json.loads(CF.read_text(encoding="utf-8"))["facts"]["us-gaap"]
    rows = []
    for i, (concept, stmt, label) in enumerate(PLAN):
        instant = stmt == "balance_sheet"
        v = latest(facts, concept, year, instant)
        if not v:
            continue
        val = int(v["val"])
        millions = Decimal(val) / Decimal(1_000_000)
        raw = f"{millions:,.0f}" if millions == millions.to_integral() else f"{millions:,.1f}"
        neg = val < 0
        if neg:
            raw = "(" + raw.lstrip("-") + ")"
        row = {
            "fact_id": hashlib.sha256(f"{concept}{year}".encode()).hexdigest()[:32],
            "run_id": "fixture-2026-09-15", "doc_hash": DOC_HASH,
            "company_id": "CIK0000034088", "statement": stmt,
            "line_item_reported": label,
            "line_item_canonical": f"us-gaap:{concept}",
            "canonical_taxonomy": "us-gaap", "mapping_confidence": 0.93,
            "period_start": None if instant else f"{year}-01-01",
            "period_end": f"{year}-12-31",
            "period_duration_months": None if instant else 12,
            "period_basis": "audited", "is_comparative": False,
            "value_raw_text": raw, "value": val, "declared_precision": -6,
            "scale_multiplier": 1_000_000, "scale_source": "statement_header",
            "currency": "USD", "currency_source": "statement_header",
            "sign_rule_applied": "parenthesis_negative" if neg else "as_printed",
            "is_nil": False,
            "source_ref": {
                "page_no": 60 + i, "bbox": [72.0, 300.0 + i, 540.0, 312.0 + i],
                "verbatim_span": raw.strip("()"),
                "table_id": f"t-{stmt}", "row_idx": i, "col_idx": 1,
                "col_header_path": ["", str(year)], "extraction_path": "native_text",
            },
            "groundedness_verified": True, "extraction_confidence": 0.96,
            "footnote_refs": [], "footnote_texts": [], "validation_flags": [],
            "extractor_version": "doc-extract@0.3.1", "model_id": "qwen3-vl-32b",
            "prompt_hash": "b7f21c04", "schema_version": "1.0",
        }
        rows.append(row)

    by_concept = {r["line_item_canonical"].split(":")[1]: r for r in rows}
    if "scale_1000x" in defects and "Revenues" in by_concept:
        by_concept["Revenues"]["value"] *= 1000
    if "scale_consistent" in defects and "Revenues" in by_concept:
        # extractor đọc nhầm multiplier từ một mục khác của tài liệu: value và
        # raw text khớp nhau hoàn hảo, không cổng nào trong một dòng phát hiện được
        r = by_concept["Revenues"]
        r["value"] *= 1000
        r["value_raw_text"] = f"{Decimal(r['value']) / Decimal(1_000_000):,.0f}"
        r["source_ref"]["verbatim_span"] = r["value_raw_text"]
    if "sign_flip" in defects:
        # đảo dấu NHƯNG khai sign_rule khớp -> số học trong dòng hoàn toàn hợp lệ.
        # Đây là ca Repsol: chỉ quan hệ giữa các số mới lộ ra lỗi.
        r = by_concept.get("NetIncomeLossAttributableToNoncontrollingInterest")
        if r:
            r["value"] = -r["value"]
            txt = r["value_raw_text"].strip("()")
            r["value_raw_text"] = "(" + txt + ")"
            r["sign_rule_applied"] = "parenthesis_negative"
            r["source_ref"]["verbatim_span"] = txt
    if "header_mismatch" in defects and "Assets" in by_concept:
        by_concept["Assets"]["source_ref"]["col_header_path"] = ["", str(year - 1)]
    if "hallucination" in defects and "CostsAndExpenses" in by_concept:
        by_concept["CostsAndExpenses"]["source_ref"]["verbatim_span"] = "999,999"
    if "missing_source" in defects and "IncomeTaxExpenseBenefit" in by_concept:
        by_concept["IncomeTaxExpenseBenefit"].pop("source_ref", None)
    if "groundedness" in defects and "NetIncomeLoss" in by_concept:
        by_concept["NetIncomeLoss"]["groundedness_verified"] = False
    return rows

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2025)
    ap.add_argument("--defect", nargs="*", default=[],
                    help="all hoặc: " + " ".join(DEFECTS))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    d = tuple(DEFECTS) if a.defect == ["all"] else tuple(a.defect)
    rows = build(a.year, d)
    out = pathlib.Path(a.out or (ROOT / "data" /
          ("extraction_dirty.jsonl" if d else "extraction_clean.jsonl")))
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                   encoding="utf-8")
    try:
        shown = out.relative_to(ROOT)
    except ValueError:
        shown = out
    print(f"{len(rows)} dòng -> {shown}"
          + (f"  | đã tiêm: {', '.join(d)}" if d else "  | bản sạch"))

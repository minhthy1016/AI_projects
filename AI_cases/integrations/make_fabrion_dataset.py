#!/usr/bin/env python3
"""
Dựng một dataset entry ESEF cho fabrion-extraction-evaluation.

Điểm mấu chốt: gold KHÔNG phải annotate tay. Mỗi báo cáo ESEF đi kèm file
xBRL-JSON chứa chính các con số đó đã gắn thẻ, nên gold sinh ra bằng máy và
chính xác tuyệt đối. Đó là lý do corpus này là benchmark tốt hơn một bộ dataset
chung: nó có đáp án miễn phí, ở quy mô lớn, cho đúng loại tài liệu khó.

Ghi vào:  dataset/finance/esef/esef-schema.json
          dataset/finance/esef/pdf+gold/{id}.pdf + {id}.gold.json
"""
import argparse, json, pathlib, shutil, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from validation import validate_identities as V

# concept ifrs-full -> (section, field). Chỉ các dòng tổng mà doc_extract đọc.
FIELDS = {
    "Revenue": ("income_statement", "revenue"),
    "RevenueAndOperatingIncome": ("income_statement", "revenue"),
    "OperatingExpense": ("income_statement", "operating_expense"),
    "ProfitLossFromOperatingActivities": ("income_statement", "operating_profit"),
    "ProfitLossBeforeTax": ("income_statement", "profit_before_tax"),
    "IncomeTaxExpenseContinuingOperations": ("income_statement", "income_tax_expense"),
    "ProfitLoss": ("income_statement", "profit_loss"),
    "ProfitLossAttributableToOwnersOfParent": ("income_statement", "profit_attributable_to_owners"),
    "ProfitLossAttributableToNoncontrollingInterests": ("income_statement", "profit_attributable_to_nci"),
    "Assets": ("balance_sheet", "total_assets"),
    "NoncurrentAssets": ("balance_sheet", "non_current_assets"),
    "CurrentAssets": ("balance_sheet", "current_assets"),
    "Liabilities": ("balance_sheet", "total_liabilities"),
    "NoncurrentLiabilities": ("balance_sheet", "non_current_liabilities"),
    "CurrentLiabilities": ("balance_sheet", "current_liabilities"),
    "Equity": ("balance_sheet", "total_equity"),
    "EquityAttributableToOwnersOfParent": ("balance_sheet", "equity_attributable_to_owners"),
    "NoncontrollingInterests": ("balance_sheet", "non_controlling_interests"),
    "EquityAndLiabilities": ("balance_sheet", "total_equity_and_liabilities"),
    "CashAndCashEquivalents": ("balance_sheet", "cash_and_cash_equivalents"),
    "CashFlowsFromUsedInOperatingActivities": ("cash_flow_statement", "operating_activities"),
    "CashFlowsFromUsedInInvestingActivities": ("cash_flow_statement", "investing_activities"),
    "CashFlowsFromUsedInFinancingActivities": ("cash_flow_statement", "financing_activities"),
    "EffectOfExchangeRateChangesOnCashAndCashEquivalents": ("cash_flow_statement", "effect_of_exchange_rate"),
    "IncreaseDecreaseInCashAndCashEquivalentsBeforeEffectOfExchangeRateChanges":
        ("cash_flow_statement", "net_change_in_cash"),
}

DEFS = {
  "unit": {"type": "string", "evaluation_config": "string_case_insensitive",
           "description": "Currency of the reported value (e.g. 'EUR', 'USD')."},
  "scale": {"anyOf": [{"type": "null"}, {"type": "integer"}],
            "evaluation_config": "integer_exact",
            "description": "Numeric scale factor (1000000 for millions). Null if unspecified."},
  "value": {"anyOf": [{"type": "null"}, {"type": "number"}],
            "evaluation_config": {"metrics": [{"metric_id": "number_tolerance",
                                               "params": {"tolerance": 0.001}}]},
            "description": "Reported numeric value, excluding unit and scale."},
  "data_period": {"type": "string", "evaluation_config": "string_exact",
                  "description": "Canonical period label, e.g. 'FY2025'."},
}

def line_item():
    return {"type": "array", "items": {"type": "object", "properties": {
        "data_period": {"$ref": "#/$defs/data_period"}, "unit": {"$ref": "#/$defs/unit"},
        "scale": {"$ref": "#/$defs/scale"}, "value": {"$ref": "#/$defs/value"}}}}

def build_schema():
    sections = {}
    for _, (sec, fld) in FIELDS.items():
        sections.setdefault(sec, {})[fld] = line_item()
    props = {"meta": {"type": "object", "properties": {
        "company": {"type": "string", "evaluation_config": "string_case_insensitive"},
        "report_period": {"$ref": "#/$defs/data_period"},
        "report_period_end_date": {"type": "string", "evaluation_config": "string_exact"}}}}
    for sec, flds in sections.items():
        props[sec] = {"type": "object", "properties": flds}
    return {"type": "object", "$defs": DEFS, "properties": props,
            "description": "IFRS consolidated primary statements as tagged in an ESEF annual "
                           "financial report. Gold is derived from the filing's own xBRL-JSON."}

def build_gold(truth_json, company, scale):
    facts = [f for f in V.from_xbrl_json(pathlib.Path(truth_json)) if f.taxonomy == "ifrs-full"]
    gold, years = {}, set()
    for f in facts:
        tgt = FIELDS.get(f.concept)
        if not tgt:
            continue
        sec, fld = tgt
        yr = f.period[-1][:4]
        years.add(yr)
        gold.setdefault(sec, {}).setdefault(fld, []).append({
            "data_period": f"FY{yr}", "unit": f.unit, "scale": scale,
            "value": float(f.value) / scale})
    for sec in gold:
        for fld in gold[sec]:
            gold[sec][fld].sort(key=lambda r: r["data_period"], reverse=True)
    latest = max(years)
    gold["meta"] = {"company": company, "report_period": f"FY{latest}",
                    "report_period_end_date": f"{latest}-12-31"}
    return gold

DOCS = [
  dict(id="omv_ar_fy2025", company="OMV Aktiengesellschaft", scale=1_000_000,
       pdf="data/ir-pdf/omv/omv-2025-esef-rendered.pdf",
       truth="data/esef/549300V62YJ9HTLRI486/2025-12-31/omvag-2025-12-31-1-de.json"),
  dict(id="akerbp_ar_fy2024", company="Aker BP ASA", scale=1_000_000,
       pdf="data/ir-pdf/akerbp/akerbp-2024-esef-rendered.pdf",
       truth="data/esef/549300NFTY73920OYK69/2024-12-31/549300NFTY73920OYK69-2024-12-31-en.json"),
]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fabrion", required=True, help="đường dẫn repo fabrion-extraction-evaluation")
    ap.add_argument("--copy-pdf", action="store_true", help="chép cả PDF (36 + 55 MB)")
    a = ap.parse_args()
    root = pathlib.Path(a.fabrion) / "dataset" / "finance" / "esef"
    (root / "pdf+gold").mkdir(parents=True, exist_ok=True)
    (root / "esef-schema.json").write_text(
        json.dumps(build_schema(), indent=1, ensure_ascii=False), encoding="utf-8")
    here = pathlib.Path(__file__).resolve().parents[1]
    for doc in DOCS:
        gold = build_gold(here / doc["truth"], doc["company"], doc["scale"])
        n = sum(len(v) for s in gold if s != "meta" for v in gold[s].values())
        (root / "pdf+gold" / f"{doc['id']}.gold.json").write_text(
            json.dumps(gold, indent=1, ensure_ascii=False), encoding="utf-8")
        dst = root / "pdf+gold" / f"{doc['id']}.pdf"
        if a.copy_pdf and not dst.exists():
            shutil.copy2(here / doc["pdf"], dst)
        print(f"  {doc['id']:20s} {n:>3} gold fact | pdf={'đã chép' if dst.exists() else 'CHƯA (dùng --copy-pdf)'}")
    print(f"-> {root}")

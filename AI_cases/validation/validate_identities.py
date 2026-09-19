#!/usr/bin/env python3
"""
Accounting-identity validator — kiểm tra label-free, không cần annotation.

Điểm mấu chốt về thiết kế: validator nhận **fact đã chuẩn hoá theo shape Silver A**,
không nhận file. Nhờ vậy cùng một bộ luật chạy được trên cả ba nguồn:

  1. companyfacts JSON   -> kiểm tra chính label source (baseline: identity có đúng không)
  2. iXBRL HTML          -> kiểm tra bước parse tài liệu
  3. LLM extraction      -> kiểm tra bước extract (cắm adapter thứ ba vào, luật giữ nguyên)

Nếu (1) pass mà (2) fail thì lỗi nằm ở parser, không phải ở dữ liệu. Đó là thứ
một con số accuracy tổng không bao giờ nói cho bạn biết.

Tolerance lấy từ `decimals` của XBRL, không phải ngưỡng tự đặt:
decimals=-6 nghĩa là số đã làm tròn tới triệu, sai số tối đa 0.5e6 mỗi số hạng.
Đây chính là `declared_precision` trong schema Silver A.

Dùng:
    python3 validate_identities.py                      # cả hai nguồn, mọi kỳ
    python3 validate_identities.py --source ixbrl
    python3 validate_identities.py --ticker CVX --year 2025
"""
from __future__ import annotations
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import argparse, json, pathlib, re, sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from shared.numbers import parse_number as _parse_number

ROOT = pathlib.Path(__file__).resolve().parents[1] / "data"
TAXONOMIES = ("us-gaap", "ifrs-full")
ANNUAL_FORMS = ("10-K", "10-K/A", "20-F", "20-F/A")
# filer IFRS báo cáo bằng nhiều đồng tiền; identity chỉ hợp lệ trong cùng một unit
CURRENCIES = ("USD", "EUR", "GBP", "NOK", "BRL")

# --------------------------------------------------------------------------
# Luật. Mỗi identity: sum(lhs) phải bằng rhs, trong tolerance suy từ decimals.
# Chỉ dùng concept mà XOM thực sự tag (đã kiểm trên companyfacts trước khi viết).
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Identity:
    name: str
    kind: str                     # 'instant' | 'duration'
    lhs: tuple                    # ((concept, hệ số), ...)
    rhs: str
    note: str = ""
    since: int = 0          # năm bắt đầu có hiệu lực (convention tagging đổi theo thời gian)
    until: int = 9999
    taxonomy: str = "us-gaap"
    op: str = "eq"          # 'eq' = sum(lhs) == rhs | 'lte' = sum(lhs) <= rhs
    fallback_for: str = ""  # chỉ chạy khi luật này SKIP ở cùng kỳ
    severity: str = "blocker"   # 'blocker' chặn merge | 'review' chỉ gắn cờ

US_GAAP_IDENTITIES = [
    Identity("balance_sheet", "instant",
             (("Assets", 1),),
             "LiabilitiesAndStockholdersEquity",
             "tổng tài sản = tổng nguồn vốn"),
    Identity("balance_sheet_split", "instant",
             (("Liabilities", 1),
              ("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", 1)),
             "Assets",
             "nợ + vốn chủ (gồm NCI) = tài sản"),
    Identity("equity_split", "instant",
             (("StockholdersEquity", 1), ("MinorityInterest", 1)),
             "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
             "vốn chủ công ty mẹ + lợi ích cổ đông thiểu số"),
    Identity("income_before_tax", "duration",
             (("Revenues", 1), ("CostsAndExpenses", -1)),
             "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
             "doanh thu - chi phí = lợi nhuận trước thuế",
             # XOM đổi cách tag us-gaap:Revenues: trước FY2017 chỉ gồm "sales and other
             # operating revenue" (loại income from equity affiliates + other income),
             # từ FY2017 là "total revenues and other income". Áp luật cho cả hai thời kỳ
             # sẽ ra FAIL giả — đó là taxonomy_convention_change, không phải identity_break.
             since=2017),
    Identity("profit_after_tax", "duration",
             (("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", 1),
              ("IncomeTaxExpenseBenefit", -1)),
             "ProfitLoss",
             "trước thuế - thuế = lợi nhuận sau thuế"),
    Identity("net_income_split", "duration",
             (("NetIncomeLoss", 1), ("NetIncomeLossAttributableToNoncontrollingInterest", 1)),
             "ProfitLoss",
             "LN cổ đông mẹ + LN cổ đông thiểu số"),
    Identity("cash_flow_roll", "duration",
             (("NetCashProvidedByUsedInOperatingActivities", 1),
              ("NetCashProvidedByUsedInInvestingActivities", 1),
              ("NetCashProvidedByUsedInFinancingActivities", 1),
              ("EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", 1)),
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
             "HĐKD + đầu tư + tài chính + tỷ giá = biến động tiền"),
]

# --------------------------------------------------------------------------
# Bộ luật ifrs-full. Concept lấy từ chính companyfacts của SHEL / BP / EQNR,
# không lấy từ tài liệu taxonomy — cái gì công ty không tag thì luật phải SKIP,
# không được giả định.
#
# Ba khác biệt thật giữa ba filer, và đó là lý do phải có nhiều biến thể:
#   - EquityAndLiabilities : SHEL, EQNR có | BP không
#   - IncreaseDecreaseInCashAndCashEquivalents : SHEL, BP có | EQNR không
#         (EQNR chỉ tag bản ...BeforeEffectOfExchangeRateChanges)
#   - ProfitLossFromOperatingActivities : BP, EQNR có | SHEL không
# IFRS cũng không có concept tương đương us-gaap:CostsAndExpenses, nên không
# dựng được luật "doanh thu - chi phí = LN trước thuế" như bên US GAAP.
# --------------------------------------------------------------------------
IFRS = dict(taxonomy="ifrs-full")

IFRS_IDENTITIES = [
    Identity("balance_sheet", "instant",
             (("Assets", 1),), "EquityAndLiabilities",
             "tổng tài sản = vốn chủ + nợ (SHEL, EQNR; BP không tag)", **IFRS),
    Identity("balance_sheet_split", "instant",
             (("Liabilities", 1), ("Equity", 1)), "Assets",
             "nợ + vốn chủ (gồm NCI) = tài sản", **IFRS),
    Identity("equity_split", "instant",
             (("EquityAttributableToOwnersOfParent", 1), ("NoncontrollingInterests", 1)),
             "Equity",
             "vốn chủ công ty mẹ + lợi ích cổ đông thiểu số", **IFRS),
    Identity("profit_after_tax", "duration",
             (("ProfitLossBeforeTax", 1), ("IncomeTaxExpenseContinuingOperations", -1)),
             "ProfitLoss",
             "LN trước thuế - thuế = LN sau thuế", **IFRS),
    # Cùng tên = biến thể của một luật. Chỉ cần một biến thể PASS là luật đó đúng
    # với kỳ đó; biến thể còn lại bị loại khỏi báo cáo. Petrobras 2016-2019 có
    # divestment lớn nên phần discontinued operations nằm ngoài
    # IncomeTaxExpenseContinuingOperations -> luật cơ bản lệch 11-31%.
    Identity("profit_after_tax", "duration",
             (("ProfitLossBeforeTax", 1), ("IncomeTaxExpenseContinuingOperations", -1),
              ("ProfitLossFromDiscontinuedOperations", 1)),
             "ProfitLoss",
             "trước thuế - thuế + LN hoạt động đã ngừng = LN sau thuế", **IFRS),
    Identity("net_income_split", "duration",
             (("ProfitLossAttributableToOwnersOfParent", 1),
              ("ProfitLossAttributableToNoncontrollingInterests", 1)),
             "ProfitLoss",
             "LN cổ đông mẹ + LN cổ đông thiểu số", **IFRS),
    Identity("cash_flow_roll", "duration",
             (("CashFlowsFromUsedInOperatingActivities", 1),
              ("CashFlowsFromUsedInInvestingActivities", 1),
              ("CashFlowsFromUsedInFinancingActivities", 1),
              ("EffectOfExchangeRateChangesOnCashAndCashEquivalents", 1)),
             "IncreaseDecreaseInCashAndCashEquivalents",
             "HĐKD + đầu tư + tài chính + tỷ giá = biến động tiền (SHEL, BP)", **IFRS),
    Identity("cash_flow_roll_pre_fx", "duration",
             (("CashFlowsFromUsedInOperatingActivities", 1),
              ("CashFlowsFromUsedInInvestingActivities", 1),
              ("CashFlowsFromUsedInFinancingActivities", 1)),
             "IncreaseDecreaseInCashAndCashEquivalentsBeforeEffectOfExchangeRateChanges",
             "biến động tiền trước tỷ giá — chỉ dùng khi không có bản gồm tỷ giá",
             fallback_for="cash_flow_roll", **IFRS),
    # Không phải đẳng thức: IFRS 15 revenue là tập con của tổng doanh thu.
    # Vi phạm chiều này gần như luôn là lỗi gán nhãn line item.
    Identity("revenue_subset", "duration",
             (("RevenueFromContractsWithCustomers", 1),), "Revenue",
             "doanh thu IFRS 15 phải <= tổng doanh thu", op="lte", **IFRS),
]

RULESETS = {"us-gaap": US_GAAP_IDENTITIES, "ifrs-full": IFRS_IDENTITIES}

# Nối bảng cân đối với lưu chuyển tiền tệ — kiểm tra xuyên hai báo cáo,
# xử lý riêng vì trộn instant với duration.
# Số dư tiền: ưu tiên concept "tiền trong báo cáo LCTT" khi công ty có tag nó.
# BP 2024: bảng cân đối 39.204M, BCLCTT 39.269M — lệch 65M, và IFRS có hẳn một
# concept cho đúng chênh lệch này. Lấy nhầm vế là ra FAIL giả đúng bằng 65M.
CASH_CONTINUITY = {
    "us-gaap": (["CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect"),
    "ifrs-full": (["CashAndCashEquivalentsIfDifferentFromStatementOfFinancialPosition",
                   "CashAndCashEquivalents"],
                  "IncreaseDecreaseInCashAndCashEquivalents"),
}

# --------------------------------------------------------------------------
# Fact — shape Silver A rút gọn
# --------------------------------------------------------------------------
def infer_precision(facts):
    """SEC companyfacts KHÔNG mang `decimals` (0/5889 fact với SHEL, 0/8037 với XOM).
    Không có nó thì tolerance = 0 và mọi sai số làm tròn thành FAIL giả —
    toàn bộ 13 FAIL của EQNR đều đúng bằng ±1.000.000 trên số hàng trăm tỷ.

    Suy đơn vị báo cáo từ mode của số chữ số 0 ở cuối, tính riêng cho từng filing.
    Dùng mode chứ không dùng GCD: chỉ một giá trị lẻ là GCD tụt về 1 (EQNR bị đúng
    lỗi này). Fact nào được suy sẽ mang cờ `decimals_inferred` — trong schema đây là
    cùng loại với `scale_source = inferred`, tức phải coi là suy đoán, không phải khai báo.
    """
    def tz(v):
        v = abs(int(v))
        if v == 0:
            return None
        n = 0
        while v % 10 == 0:
            v //= 10; n += 1
        return n
    by_accn = defaultdict(list)
    for f in facts:
        if f.decimals is None:
            by_accn[f.accn].append(f)
    for accn, group in by_accn.items():
        counts = defaultdict(int)
        for f in group:
            if abs(f.value) >= 1_000_000:
                t = tz(f.value)
                if t is not None:
                    counts[min(t, 9)] += 1
        if not counts:
            continue
        prec = max(counts, key=counts.get)
        for f in group:
            f.decimals = -prec
            f.decimals_inferred = True
    return facts


@dataclass
class Fact:
    concept: str
    value: Decimal
    unit: str
    period: tuple                 # (start, end) hoặc (instant,)
    decimals: object              # int hoặc 'INF'
    source: str
    taxonomy: str = "us-gaap"
    accn: str = ""          # filing gốc. Identity chỉ đúng TRONG MỘT tài liệu.
    filed: str = ""
    decimals_inferred: bool = False
    raw: str = ""

    @property
    def tol(self) -> Decimal:
        """Sai số làm tròn tối đa mà chính tài liệu đã khai."""
        if self.decimals == "INF" or self.decimals is None:
            return Decimal(0)
        return Decimal(10) ** (-int(self.decimals)) / 2

# --------------------------------------------------------------------------
# Adapter 1 — companyfacts JSON (label source)
# --------------------------------------------------------------------------
def from_companyfacts(path: pathlib.Path) -> list[Fact]:
    d = json.loads(path.read_text(encoding="utf-8"))
    out, seen = [], {}
    for tax in ("us-gaap", "ifrs-full"):
      for concept, meta in d["facts"].get(tax, {}).items():
        for unit, vals in meta["units"].items():
            if unit not in CURRENCIES:
                continue
            for v in vals:
                # 20-F là filing thường niên của foreign private issuer, tương
                # đương 10-K. Thiếu nó thì mọi filer IFRS sẽ ra rỗng.
                if v.get("form") not in ANNUAL_FORMS:
                    continue
                period = (v["start"], v["end"]) if "start" in v else (v["end"],)
                out.append(Fact(concept, Decimal(str(v["val"])), unit, period,
                                v.get("decimals"), "companyfacts", taxonomy=tax,
                                accn=v.get("accn", ""), filed=v.get("filed", "")))
    # KHÔNG dedupe theo (concept, period) ở đây. Lấy "bản filed gần nhất" cho
    # từng concept độc lập sẽ ghép số từ nhiều filing khác nhau và tạo ra một bộ
    # số chưa từng cùng tồn tại trong tài liệu nào — identity vỡ vì lý do hoàn
    # toàn không liên quan tới chất lượng extraction. Việc chọn filing để ở check().
    dedup = {}
    for f in out:
        dedup[(f.taxonomy, f.concept, f.period, f.accn)] = f
    return infer_precision(list(dedup.values()))

# --------------------------------------------------------------------------
# Adapter 2 — iXBRL HTML (tài liệu thật)
# --------------------------------------------------------------------------
CTX_RE  = re.compile(r'<xbrli:context id="([^"]+)"(.*?)</xbrli:context>', re.S)
START_RE= re.compile(r'<xbrli:startDate>([^<]+)</xbrli:startDate>')
END_RE  = re.compile(r'<xbrli:endDate>([^<]+)</xbrli:endDate>')
INST_RE = re.compile(r'<xbrli:instant>([^<]+)</xbrli:instant>')
FACT_RE = re.compile(r'<ix:nonFraction\b([^>]*)>(.*?)</ix:nonFraction>', re.S)
ATTR_RE = re.compile(r'([\w:.-]+)\s*=\s*"([^"]*)"')
TAG_RE  = re.compile(r'<[^>]+>')

def _parse_contexts(s: str) -> dict:
    ctx = {}
    for cid, body in CTX_RE.findall(s):
        # context có chiều (segment/scenario) là fact theo phân khúc, không phải
        # số hợp nhất -> loại, nếu không doanh thu từng segment sẽ lẫn vào tổng.
        if "xbrli:segment" in body or "xbrldi:explicitMember" in body:
            continue
        m = INST_RE.search(body)
        if m:
            ctx[cid] = (m.group(1),)
            continue
        ms, me = START_RE.search(body), END_RE.search(body)
        if ms and me:
            ctx[cid] = (ms.group(1), me.group(1))
    return ctx

def from_ixbrl(path: pathlib.Path) -> list[Fact]:
    s = path.read_text(encoding="utf-8", errors="replace")
    accn = path.name
    ctx = _parse_contexts(s)
    out, dropped = [], defaultdict(int)
    for attrs_s, inner in FACT_RE.findall(s):
        a = dict(ATTR_RE.findall(attrs_s))
        if a.get("xsi:nil") == "true":
            dropped["nil"] += 1; continue
        name = a.get("name", "")
        tax = next((t for t in TAXONOMIES if name.startswith(t + ":")), None)
        if tax is None:
            dropped["ngoài taxonomy chuẩn"] += 1; continue
        cid = a.get("contextRef")
        if cid not in ctx:
            dropped["dimensional"] += 1; continue      # đã loại ở _parse_contexts
        # unitRef phải là MÃ TIỀN TỆ, không phải chuỗi có chứa mã đó.
        # Khớp chuỗi con làm "usdPerShare" ra USD — hồ sơ XOM có 59 fact như vậy,
        # tức 59 giá trị trên mỗi cổ phiếu bị coi là số tiền.
        uref = a.get("unitRef", "")
        token = re.split(r"[^A-Za-z]+", uref)[-1] if uref else ""
        cur = next((c for c in CURRENCIES
                    if uref.upper() == c or token.upper() == c
                    or re.fullmatch(rf"(?i)iso4217[_-]?{c}", uref)), None)
        if cur is None:
            dropped["đơn vị không phải tiền tệ"] += 1; continue
        txt = TAG_RE.sub("", inner).replace("&#160;", "").replace("\xa0", " ").strip()
        # iXBRL KHAI RÕ định dạng số trong thuộc tính `format`, không cần đoán:
        #   ixt:num-dot-decimal    -> kiểu Anh-Mỹ   (SEC XOM: 1338 fact)
        #   ixt5:num-comma-decimal -> kiểu châu Âu  (ESEF OMV:  414 fact)
        #   ixt*:fixed-zero        -> giá trị là 0, bất kể text hiển thị
        # Bản trước strip dấu phẩy vô điều kiện rồi để nguyên dấu chấm: với tài
        # liệu khai comma-decimal, "24.308" thành 24.308 thay vì 24308 — sai
        # 1000×, im lặng. Nó chưa cắn chỉ vì đường này mới chỉ chạy trên hồ sơ
        # SEC (đều là dot-decimal).
        fmt = a.get("format", "")
        if "fixed-zero" in fmt:
            val = Decimal(0)
        else:
            sep = "," if "comma-decimal" in fmt else "."
            val, nil = _parse_number(txt, sep)
            if val is None:
                dropped["nil" if nil else "unparseable"] += 1; continue
        # scale và sign là hai thuộc tính iXBRL, không phải thứ suy ra từ text hiển thị
        val *= Decimal(10) ** int(a.get("scale", 0) or 0)
        if a.get("sign") == "-":
            val = -val
        dec = a.get("decimals")
        dec = "INF" if dec == "INF" else (int(dec) if dec not in (None, "") else None)
        out.append(Fact(name[len(tax) + 1:], val, cur, ctx[cid], dec, "ixbrl",
                        taxonomy=tax, accn=accn, raw=txt))
    # cùng concept+period xuất hiện nhiều lần trong tài liệu (bảng chính + thuyết minh)
    dedup = {}
    for f in out:
        k = (f.taxonomy, f.concept, f.period)
        if k not in dedup:
            dedup[k] = f
        elif dedup[k].value != f.value:
            dedup[k] = f if (f.decimals or -99) > (dedup[k].decimals or -99) else dedup[k]
    print(f"    [parse] {len(out)} fact hợp nhất, {len(dedup)} sau dedup; "
          f"bỏ: {dict(dropped)}", file=sys.stderr)
    return infer_precision(list(dedup.values()))

def detect_restatements(path: pathlib.Path, min_rel=1e-9):
    """Cùng (concept, period) mang nhiều giá trị khác nhau giữa các lần filing.

    Không phải lỗi extraction — là công ty trình bày lại số cũ. Trong schema Silver A
    đây là `period_basis = restated` + `is_restated`, và với greenwashing thì bản thân
    tần suất restate đã là feature. Phát hiện được mà không cần nhãn nào.
    """
    d = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for tax in TAXONOMIES:
      for concept, meta in d["facts"].get(tax, {}).items():
        for unit, vals in meta["units"].items():
            if unit not in CURRENCIES:
                continue
            grp = defaultdict(dict)
            for v in vals:
                if v.get("form") not in ANNUAL_FORMS:
                    continue
                per = (v["start"], v["end"]) if "start" in v else (v["end"],)
                grp[per][v.get("filed", "")] = v["val"]
            for per, byfiled in grp.items():
                distinct = set(byfiled.values())
                if len(distinct) < 2:
                    continue
                first = byfiled[min(byfiled)]
                last = byfiled[max(byfiled)]
                if first == last or abs(first) < 1:
                    continue
                # đảo dấu thuần tuý là đổi sign convention khi tag, KHÔNG phải
                # trình bày lại số. Trong schema đây là `sign_rule_applied`, không phải
                # `is_restated`. Gộp hai thứ vào một cờ là tự làm nhiễu tín hiệu.
                kind = "sign_flip" if first == -last else "value_change"
                out.append(dict(taxonomy=tax, concept=concept, period=per, as_filed=first,
                                as_represented=last, delta=last - first,
                                rel=abs(last - first) / abs(first),
                                kind=kind, n_filings=len(byfiled)))
    return sorted(out, key=lambda x: (x["kind"] != "value_change", -x["rel"]))


# --------------------------------------------------------------------------
# Adapter 3 — xBRL-JSON (ESEF, filings.xbrl.org)
# --------------------------------------------------------------------------
# Hai khác biệt so với companyfacts, cả hai đều làm hỏng kết quả nếu bỏ qua:
#   1. `decimals` CÓ THẬT ở đây (537/696 với OMV) -> không phải suy đoán nữa,
#      dùng đúng precision công ty khai.
#   2. Mốc cuối kỳ là EXCLUSIVE: FY2025 ghi là 2026-01-01, instant cuối năm cũng
#      ghi 2026-01-01. Không lùi một ngày thì mọi period lệch một năm và
#      cash_continuity sẽ nối nhầm kỳ.
# --------------------------------------------------------------------------
NON_AXIS = {"concept", "entity", "period", "unit", "language", "noteId"}

def _iso(ts, exclusive):
    d = date(*map(int, ts[:10].split("-")))
    return str(d - timedelta(days=1)) if exclusive else str(d)

def from_xbrl_json(path: pathlib.Path) -> list[Fact]:
    d = json.loads(path.read_text(encoding="utf-8"))
    out, dropped = [], defaultdict(int)
    for fid, v in d.get("facts", {}).items():
        dim = v.get("dimensions", {})
        # chiều phụ = số theo phân khúc (OMV có 222 fact theo ComponentsOfEquityAxis),
        # không phải số hợp nhất
        if set(dim) - NON_AXIS:
            dropped["có chiều phụ"] += 1; continue
        concept = dim.get("concept", "")
        tax = next((t for t in TAXONOMIES if concept.startswith(t + ":")), None)
        if tax is None:
            dropped["ngoài taxonomy chuẩn"] += 1; continue
        unit = dim.get("unit") or ""
        if not unit.startswith("iso4217:") or "/" in unit:
            dropped["không phải đơn vị tiền tệ"] += 1; continue
        cur = unit.split(":", 1)[1]
        if cur not in CURRENCIES:
            dropped[f"đồng tiền {cur}"] += 1; continue
        per = dim.get("period", "")
        try:
            if "/" in per:
                a, b = per.split("/")
                period = (_iso(a, False), _iso(b, True))
            else:
                period = (_iso(per, True),)
        except Exception:
            dropped["period không đọc được"] += 1; continue
        try:
            val = Decimal(str(v["value"]))
        except (InvalidOperation, KeyError, TypeError):
            dropped["value không đọc được"] += 1; continue
        dec = v.get("decimals")
        out.append(Fact(concept.split(":", 1)[1], val, cur, period,
                        dec if dec is not None else None, "xbrl-json",
                        taxonomy=tax, accn=path.name))
    dedup = {}
    for f in out:
        dedup[(f.taxonomy, f.concept, f.period, f.accn)] = f
    print(f"    [xbrl-json] {len(out)} fact hợp nhất, {len(dedup)} sau dedup; "
          f"bỏ: {dict(dropped)}", file=sys.stderr)
    return infer_precision(list(dedup.values()))


# --------------------------------------------------------------------------
# Adapter 4 — output extraction từ PDF (Silver A JSONL, xem contracts/extraction_contract.json)
# --------------------------------------------------------------------------
# Adapter này làm được thứ ba adapter XBRL không làm được: nó có CẢ raw text lẫn
# giá trị đã chuẩn hoá, nên kiểm được chính bước normalize.
#
# Bốn cổng chạy TRƯỚC khi đụng tới đẳng thức kế toán. Đẳng thức bắt lỗi quan hệ
# giữa các số; bốn cổng này bắt lỗi bên trong một số — rẻ hơn nhiều bậc và bắt
# được những lỗi mà đẳng thức không bao giờ thấy (một số sai lẻ loi trong thuyết
# minh không tham gia đẳng thức nào).
# --------------------------------------------------------------------------
def _to_number(txt, decimal_sep="."):
    """(độ lớn, có_dấu_âm) — uỷ quyền cho shared.numbers.parse_number.

    Đây từng là BẢN SAO THỨ BA của bộ đọc số trong dự án, mang y hệt các lỗ hổng
    đã sửa ở hai bản kia: strip("()") nhận "(123" và "((123))", lstrip nhận
    "--123" và "+-123" (nuốt dấu, số ÂM thành DƯƠNG), replace() nhận "1,23,4".
    Trớ trêu là nó nằm trong CỔNG KIỂM TRA — thứ có nhiệm vụ bắt đúng loại lỗi đó.

    Đã đối chiếu trên toàn bộ value_raw_text thật của 5 file kết quả: bộ đọc mới
    cho kết quả y hệt, 0 chuỗi bị từ chối oan.
    """
    value, nil = _parse_number(txt, decimal_sep)
    if value is None:
        return None, False
    return abs(value), value < 0


def gate_extraction(row) -> list:
    """Trả về danh sách cờ lỗi. Rỗng = dòng sạch."""
    flags = []
    sr = row.get("source_ref") or {}

    # 1. provenance — luật cứng của schema: không source_ref thì không vào Silver
    if not sr.get("verbatim_span") or not sr.get("page_no"):
        flags.append("missing_source_ref")
    if row.get("groundedness_verified") is not True:
        flags.append("groundedness_failed")

    # 2. số học chuẩn hoá: raw_text × scale × sign có ra đúng `value` không.
    #    Đây là chỗ lỗi 1000× lộ ra — cùng raw text, sai multiplier.
    raw, paren_neg = _to_number(row.get("value_raw_text", ""),
                                row.get("decimal_separator", "."))
    val = row.get("value")
    if raw is not None and val is not None:
        mult = Decimal(str(row.get("scale_multiplier", 1)))
        expect = raw * mult
        rule = row.get("sign_rule_applied")
        if rule == "as_printed" and paren_neg:
            expect = -abs(expect)
        elif rule == "parenthesis_negative" and paren_neg:
            expect = -abs(expect)
        elif rule in ("less_prefix", "outflow_negative"):
            expect = -abs(expect)
        elif rule == "taxonomy_balance":
            # Quy tắc này CỐ Ý đảo dấu so với dấu in trên giấy, nên dấu kỳ vọng
            # là NGƯỢC dấu in. Bản trước không có nhánh này: expect giữ nguyên
            # độ lớn dương, nên cổng cho qua cả bản đã đảo đúng lẫn bản đánh rơi
            # dấu — tức là không kiểm gì cả cho đúng quy tắc duy nhất động tới dấu.
            expect = abs(expect) if paren_neg else -abs(expect)
        if abs(Decimal(str(val)) - expect) > Decimal("0.5"):
            ratio = (Decimal(str(val)) / expect) if expect else None
            flags.append("scale_arithmetic_mismatch"
                         + (f":{ratio:g}x" if ratio and abs(ratio) in
                            (Decimal(1000), Decimal(1000000), Decimal("0.001")) else ""))

    # 3. header vs kỳ: năm trong header cột phải khớp period_end.
    #    Đây là cách bắt lệch cell-header BẰNG MÁY, không cần người đọc lại.
    path = sr.get("col_header_path") or []
    yr = str(row.get("period_end", ""))[:4]
    if path and yr:
        joined = " ".join(str(x) for x in path)
        if re.search(r"\b(19|20)\d{2}\b", joined) and yr not in joined:
            flags.append("header_period_mismatch")

    # 4. scale suy đoán là mùi lỗi, không phải giá trị hợp lệ bình thường
    if row.get("scale_source") == "inferred":
        flags.append("scale_inferred")
    if row.get("period_basis") == "restated":
        flags.append("restated")
    return flags


def from_extraction(path: pathlib.Path, doc_text: str = None):
    """Đọc JSONL theo contracts/extraction_contract.json -> Fact, kèm báo cáo cổng.

    doc_text: nếu truyền vào, verbatim_span được string-match ngược lại tài liệu.
    Đây là groundedness check thật, không tin cờ mà model tự khai.
    """
    facts, gated, report_rows = [], defaultdict(int), []
    for ln, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        flags = gate_extraction(row)
        if doc_text is not None:
            span = ((row.get("source_ref") or {}).get("verbatim_span") or "").strip()
            if span and span not in doc_text:
                flags.append("hallucinated_span")
        report_rows.append(dict(line=ln, fact_id=row.get("fact_id"),
                                concept=row.get("line_item_canonical"),
                                period_end=row.get("period_end"), flags=flags))
        blocking = [f for f in flags if not f.startswith(("scale_inferred", "restated"))]
        if blocking:
            for f in blocking:
                gated[f.split(":")[0]] += 1
            continue
        canon = row.get("line_item_canonical")
        if not canon or ":" not in canon:
            gated["chưa canonicalize"] += 1
            continue
        tax, concept = canon.split(":", 1)
        if tax not in TAXONOMIES or row.get("value") is None:
            gated["ngoài taxonomy chuẩn"] += 1
            continue
        ps, pe = row.get("period_start"), row.get("period_end")
        period = (pe,) if row.get("statement") == "balance_sheet" or not ps else (ps, pe)
        facts.append(Fact(concept, Decimal(str(row["value"])), row["currency"], period,
                          row.get("declared_precision"), "extraction", taxonomy=tax,
                          accn=row.get("run_id", ""), raw=row.get("value_raw_text", "")))
    print(f"    [extraction] {len(facts)} fact vào Silver; "
          f"{sum(gated.values())} dòng bị cổng chặn: {dict(gated)}", file=sys.stderr)
    return infer_precision(facts), report_rows


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------
def period_kind(p):
    """Phân loại kỳ. Filer 20-F tag cả kỳ quý bên trong báo cáo thường niên
    (BP có 308 kỳ như vậy) và các kỳ đó chỉ mang một phần concept. Chạy đẳng thức
    toàn bộ báo cáo lên chúng chỉ sinh SKIP nhiễu, che mất SKIP có nghĩa thật.
    """
    if len(p) == 1:
        return "instant"
    a = date(*map(int, p[0].split("-")))
    b = date(*map(int, p[1].split("-")))
    m = round((b - a).days / 30.44)
    return "annual" if 11 <= m <= 13 else f"interim_{m}m"


def index(facts):
    """(taxonomy, period) -> accn -> concept -> Fact"""
    idx = defaultdict(lambda: defaultdict(dict))
    for f in facts:
        idx[(f.taxonomy, f.period)][f.accn][f.concept] = f
    return idx

def resolve(idx, taxonomy, period, concepts, cross_filing=False):
    """Lấy toàn bộ concept từ MỘT filing duy nhất, ưu tiên filing mới nhất.

    Đây là điểm dễ sai nhất của loại validator này: ghép số từ nhiều filing
    sẽ sinh FAIL giả. Một đẳng thức kế toán chỉ đúng bên trong một tài liệu.
    """
    by_accn = idx.get((taxonomy, period), {})
    if not by_accn:
        return None, set(concepts)
    if cross_filing:
        # Gộp mọi filing. Đo trên 7 filer: chỉ cứu được 2/323 SKIP kỳ năm, vì
        # concept thiếu thì thiếu ở mọi filing chứ không nằm rải rác. Đổi lại
        # rủi ro ghép số chưa từng cùng tồn tại (Shell FY2017 vỡ 50M vì đúng lỗi
        # này). Mặc định tắt; chỉ bật khi bạn chấp nhận đánh đổi đó.
        merged, conflict = {}, False
        for accn in sorted(by_accn, key=lambda a: max(
                (f.filed or "") for f in by_accn[a].values())):
            for c, f in by_accn[accn].items():
                if c in merged and merged[c].value != f.value:
                    conflict = True
                merged[c] = f
        missing = {c for c in concepts if c not in merged}
        if missing or conflict:
            return None, (missing or {"giá trị mâu thuẫn giữa các filing"})
        return {c: merged[c] for c in concepts}, set()
    best_missing = set(concepts)
    for accn in sorted(by_accn, key=lambda a: max(
            (f.filed or "") for f in by_accn[a].values()), reverse=True):
        got = by_accn[accn]
        missing = {c for c in concepts if c not in got}
        if not missing:
            return {c: got[c] for c in concepts}, set()
        if len(missing) < len(best_missing):
            best_missing = missing
    return None, best_missing

def check(facts, year_filter=None, periods="annual", cross_filing=False):
    idx = index(facts)
    taxes = {f.taxonomy for f in facts}
    periods_by_tax = defaultdict(lambda: defaultdict(set))
    for (tax, p) in idx:
        periods_by_tax[tax][len(p)].add(p)
    results = []
    skipped = set()          # (identity, period) đã SKIP -> cho luật fallback biết

    rules = [i for t in sorted(taxes) for i in RULESETS.get(t, [])]
    for ident in rules:
        per = periods_by_tax[ident.taxonomy]
        cand = sorted(per[1] if ident.kind == "instant" else per[2])
        for p in cand:
            if year_filter and year_filter not in p[-1]:
                continue
            kind = period_kind(p)
            if periods == "annual" and kind.startswith("interim"):
                results.append(dict(identity=ident.name, period=p, status="N/A",
                                    taxonomy=ident.taxonomy, period_kind=kind,
                                    reason=f"kỳ {kind} — đẳng thức toàn báo cáo "
                                           "không áp dụng cho kỳ giữa niên độ"))
                continue
            yr = int(p[-1][:4])
            if not (ident.since <= yr <= ident.until):
                results.append(dict(identity=ident.name, period=p, status="N/A",
                                    taxonomy=ident.taxonomy,
                                    reason=f"ngoài phạm vi luật ({ident.since}+): "
                                           "convention tagging khác"))
                continue
            # luật fallback chỉ chạy khi luật chính không áp dụng được cho kỳ này
            if ident.fallback_for and (ident.fallback_for, p) not in skipped:
                continue
            need = [c for c, _ in ident.lhs] + [ident.rhs]
            got, missing = resolve(idx, ident.taxonomy, p, need, cross_filing)
            if got is None:
                skipped.add((ident.name, p))
                results.append(dict(identity=ident.name, period=p, status="SKIP",
                                    taxonomy=ident.taxonomy,
                                    reason="không filing nào chứa đủ: " + ", ".join(sorted(missing))))
                continue
            terms = [(got[c], coef) for c, coef in ident.lhs]
            rhs = got[ident.rhs]
            # identity chỉ hợp lệ trong cùng một đồng tiền — filer IFRS tag
            # song song nhiều currency, cộng chéo là ra số vô nghĩa
            units = {f.unit for f, _ in terms} | {rhs.unit}
            if len(units) > 1:
                results.append(dict(identity=ident.name, period=p, status="SKIP",
                                    taxonomy=ident.taxonomy,
                                    reason=f"trộn đồng tiền: {sorted(units)}"))
                continue
            lhs_val = sum((f.value * coef for f, coef in terms), Decimal(0))
            delta = lhs_val - rhs.value
            tol = sum((f.tol for f, _ in terms), Decimal(0)) + rhs.tol
            ok = (delta <= tol) if ident.op == "lte" else (abs(delta) <= tol)
            bad = "FAIL" if ident.severity == "blocker" else "WARN"
            # Khi lệch: thử đảo dấu đúng MỘT số hạng. Nếu đẳng thức khớp lại thì
            # đây là sai sign convention, không phải sai giá trị — hai chẩn đoán
            # hoàn toàn khác nhau và trong schema là hai cột khác nhau
            # (`sign_rule_applied` vs `identity_break`). Repsol tag
            # ProfitLossAttributableToNoncontrollingInterests ngược dấu ở cả
            # FY2023 lẫn FY2024, và delta bằng đúng 2× giá trị đó.
            sign_suspect = None
            if not ok:
                for f, coef in terms:
                    if abs(lhs_val - 2 * f.value * coef - rhs.value) <= tol:
                        sign_suspect = f.concept
                        break
            results.append(dict(identity=ident.name, period=p, severity=ident.severity,
                                status="PASS" if ok else bad, taxonomy=ident.taxonomy,
                                lhs=lhs_val, rhs=rhs.value, delta=delta, tol=tol,
                                op=ident.op, unit=units.pop(), accn=rhs.accn,
                                sign_suspect=sign_suspect, note=ident.note))

    # cash continuity: tiền cuối kỳ - tiền đầu kỳ = biến động trong kỳ
    for tax in sorted(taxes):
      if tax not in CASH_CONTINUITY:
          continue
      bal_prefs, chg = CASH_CONTINUITY[tax]
      for p in sorted(periods_by_tax[tax][2]):
        if year_filter and year_filter not in p[1]:
            continue
        if periods == "annual" and period_kind(p).startswith("interim"):
            continue
        start, end = p
        prior = f"{int(start[:4]) - 1}-12-31"
        g_now, _ = resolve(idx, tax, p, [chg], cross_filing)
        f_chg = g_now[chg] if g_now else None
        f_end = f_beg = None
        bal = None
        for cand in bal_prefs:
            g_end, _ = resolve(idx, tax, (end,), [cand], cross_filing)
            g_beg, _ = resolve(idx, tax, (prior,), [cand], cross_filing)
            if g_end and g_beg:
                bal, f_end, f_beg = cand, g_end[cand], g_beg[cand]
                break
        if not (f_end and f_beg and f_chg):
            results.append(dict(identity="cash_continuity", period=p, status="SKIP",
                                taxonomy=tax,
                                reason="thiếu số dư tiền đầu hoặc cuối kỳ"))
            continue
        if len({f_end.unit, f_beg.unit, f_chg.unit}) > 1:
            results.append(dict(identity="cash_continuity", period=p, status="SKIP",
                                taxonomy=tax, reason="trộn đồng tiền"))
            continue
        delta = (f_end.value - f_beg.value) - f_chg.value
        tol = f_end.tol + f_beg.tol + f_chg.tol
        ok = abs(delta) <= tol
        results.append(dict(identity="cash_continuity", period=p, taxonomy=tax,
                            status="PASS" if ok else "WARN", severity="review",
                            lhs=f_end.value - f_beg.value, rhs=f_chg.value,
                            delta=delta, tol=tol, unit=f_end.unit, balance_concept=bal,
                            note="nối bảng cân đối với lưu chuyển tiền tệ"))
    passed = {(r["identity"], r["period"]) for r in results if r["status"] == "PASS"}
    results = [r for r in results
               if r["status"] == "PASS" or (r["identity"], r["period"]) not in passed]
    return results

def fmt(v):
    return f"{v:>18,.0f}" if isinstance(v, Decimal) else f"{str(v):>18s}"

def report(name, results):
    print(f"\n{'='*104}\n{name}\n{'='*104}")
    print(f"{'identity':24s} {'kỳ':23s} {'lhs':>18s} {'rhs':>18s} {'delta':>14s}  kq")
    print("-"*104)
    for r in sorted(results, key=lambda x: (str(x['period']), x['identity'])):
        p = "→".join(r["period"])
        if r["status"] in ("SKIP", "N/A"):
            print(f"{r['identity']:24s} {p:23s} {'':>18s} {'':>18s} {'':>14s}  "
                  f"{r['status']:4s}  {r['reason']}")
        else:
            mark = "ok" if r["status"] == "PASS" else r["status"]
            print(f"{r['identity']:24s} {p:23s} {fmt(r['lhs'])} {fmt(r['rhs'])} "
                  f"{r['delta']:>14,.0f}  {mark}"
                  + ("" if r["status"] == "PASS" else f"   (tol {r['tol']:,.0f})")
                  + (f"  ← nghi đảo dấu: {r['sign_suspect']}" if r.get("sign_suspect") else ""))
    n = {k: sum(1 for r in results if r["status"] == k) for k in ("PASS", "FAIL", "WARN", "SKIP", "N/A")}
    print("-"*104)
    print(f"PASS {n['PASS']}   FAIL {n['FAIL']}   WARN {n['WARN']}   "
          f"SKIP {n['SKIP']}   N/A {n['N/A']}")
    return n

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default="XOM")
    ap.add_argument("--source", default="both",
                    choices=["both", "ixbrl", "companyfacts", "esef", "extraction"])
    ap.add_argument("--file", default=None, help="đường dẫn JSONL output extraction")
    ap.add_argument("--doc", default=None,
                    help="tài liệu nguồn để string-match verbatim_span (groundedness thật)")
    ap.add_argument("--lei", default=None, help="chạy ESEF theo LEI thay vì ticker")
    ap.add_argument("--year", default=None, help="lọc theo năm, ví dụ 2025")
    ap.add_argument("--periods", default="annual", choices=["annual", "all"],
                    help="annual = bỏ kỳ giữa niên độ (mặc định)")
    ap.add_argument("--cross-filing", action="store_true",
                    help="cho phép ghép concept từ nhiều filing (đo được: cứu 2/323, "
                         "đổi lại rủi ro ghép số chưa từng cùng tồn tại)")
    ap.add_argument("--out", default="data/validation_results.jsonl")
    a = ap.parse_args()

    all_res, fails = [], 0
    manifest = [json.loads(l) for l in (ROOT / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    if a.source == "extraction":
        if not a.file:
            sys.exit("--source extraction cần --file <output.jsonl>")
        doc_text = None
        if a.doc:
            dp = pathlib.Path(a.doc)
            doc_text = dp.read_text(encoding="utf-8", errors="replace")
            # CHỈ strip tag khi tài liệu thật sự là HTML. Strip vô điều kiện là
            # phá chính dữ liệu đối chiếu: text layer của Aker BP có ký tự "<"
            # thông thường, và <[^>]+> ăn luôn đoạn văn giữa "<" và ">" kế tiếp
            # -> 10 fact bị gắn cờ hallucinated_span oan. Công cụ kiểm chứng
            # làm hỏng tài liệu tham chiếu là lỗi tệ hơn lỗi nó đi tìm.
            if dp.suffix.lower() in (".htm", ".html", ".xhtml") or \
               doc_text.lstrip()[:1] == "<":
                doc_text = TAG_RE.sub(" ", doc_text)
        facts, gate_report = from_extraction(pathlib.Path(a.file), doc_text)
        res = check(facts, a.year, a.periods, a.cross_filing)
        bad = [r for r in gate_report if r["flags"]]
        if bad:
            print(f"\n{'='*104}\nCỔNG TRƯỚC ĐẲNG THỨC — {len(bad)}/{len(gate_report)} dòng có cờ\n{'='*104}")
            print(f"{'dòng':>5s} {'concept':38s} {'kỳ':12s}  cờ")
            print("-"*104)
            for r in bad[:25]:
                print(f"{r['line']:>5d} {str(r['concept'])[:38]:38s} "
                      f"{str(r['period_end']):12s}  {', '.join(r['flags'])}")
        report(f"[extraction] {pathlib.Path(a.file).name}  ({len(facts)} fact qua cổng)", res)
        n_block = sum(1 for r in gate_report
                      if [f for f in r["flags"] if not f.startswith(("scale_inferred", "restated"))])
        sys.exit(1 if (n_block or any(r["status"] == "FAIL" for r in res)) else 0)

    if a.source == "esef":
        rows = [m for m in manifest if m.get("source") == "esef"
                and m["doc_kind"] == "xbrl_json"
                and (a.lei is None or m.get("lei") == a.lei)]
        if not rows:
            sys.exit("không thấy filing ESEF nào trong manifest")
        grand = defaultdict(int)
        for m in sorted(rows, key=lambda x: x["company"]):
            print(f"\n>> {m['company']}  [{m['lei']}]  {m['period_end']}", file=sys.stderr)
            facts = from_xbrl_json(ROOT.parent / m["local_path"])
            res = check(facts, a.year, a.periods, a.cross_filing)
            n = report(f"[ESEF] {m['company']} — {m['period_end']}  ({len(facts)} fact)", res)
            for k, v in n.items():
                grand[k] += v
            all_res += [dict(r, source="esef", company=m["company"],
                             lei=m["lei"], doc=m["local_path"]) for r in res]
        print(f"\n{'='*104}\nTỔNG ESEF {len(rows)} filing: " +
              "   ".join(f"{k} {v}" for k, v in grand.items()))
        outp = ROOT.parent / a.out
        with outp.open("w", encoding="utf-8") as fh:
            for r in all_res:
                fh.write(json.dumps({k: (str(v) if isinstance(v, Decimal) else v)
                                     for k, v in r.items()}, ensure_ascii=False,
                                    default=str) + "\n")
        print(f"{len(all_res)} kết quả -> {a.out}")
        sys.exit(1 if grand["FAIL"] else 0)

    rows = [m for m in manifest if m.get("ticker") == a.ticker]
    if not rows:
        sys.exit(f"không thấy {a.ticker} trong manifest")


    if a.source in ("both", "companyfacts"):
        cf = [m for m in rows if m["doc_kind"] == "xbrl_json"]
        for m in cf:
            p = ROOT.parent / m["local_path"]
            facts = from_companyfacts(p)
            res = check(facts, a.year, a.periods, a.cross_filing)
            n = report(f"[{a.ticker}] companyfacts  ({len(facts)} fact)  — kiểm tra LABEL SOURCE", res)
            fails += n["FAIL"]
            all_res += [dict(r, source="companyfacts", doc=m["local_path"]) for r in res]

    if a.source in ("both", "companyfacts"):
        for m in [x for x in rows if x["doc_kind"] == "xbrl_json"]:
            rs = detect_restatements(ROOT.parent / m["local_path"])
            print(f"\n{'='*104}\n[{a.ticker}] RESTATEMENT — cùng (concept, period), giá trị đổi giữa các filing\n{'='*104}")
            print(f"{'concept':58s} {'kỳ':12s} {'as filed':>16s} {'as re-presented':>16s} {'lệch %':>8s}   (chỉ value_change)")
            print("-"*104)
            for r in [x for x in rs if x["kind"] == "value_change"][:12]:
                print(f"{r['concept'][:58]:58s} {r['period'][-1][:10]:12s} "
                      f"{r['as_filed']:>16,.0f} {r['as_represented']:>16,.0f} {r['rel']*100:>7.1f}%")
            print("-"*104)
            nv = sum(1 for x in rs if x["kind"] == "value_change")
            print(f"{nv} trình bày lại thật (value_change) | "
                  f"{len(rs)-nv} đổi sign convention khi tag (sign_flip, không phải restatement)")
            all_res += [dict(r, status="RESTATED", source="companyfacts",
                             doc=m["local_path"], identity="restatement") for r in rs]

    if a.source in ("both", "ixbrl"):
        docs = [m for m in rows if m["doc_kind"] == "ixbrl_html"]
        for m in sorted(docs, key=lambda x: x["period_end"], reverse=True):
            p = ROOT.parent / m["local_path"]
            print(f"\n>> parse {m['local_path']}", file=sys.stderr)
            facts = from_ixbrl(p)
            res = check(facts, a.year, a.periods, a.cross_filing)
            n = report(f"[{a.ticker}] iXBRL {m['form']} {m['period_end']}  ({len(facts)} fact)  — kiểm tra PARSE", res)
            fails += n["FAIL"]
            all_res += [dict(r, source="ixbrl", doc=m["local_path"]) for r in res]

    outp = ROOT.parent / a.out
    with outp.open("w", encoding="utf-8") as fh:
        for r in all_res:
            fh.write(json.dumps({k: (str(v) if isinstance(v, Decimal) else v)
                                 for k, v in r.items()}, ensure_ascii=False, default=str) + "\n")
    print(f"\n{len(all_res)} kết quả -> {a.out}")
    # validation_flags trong schema Silver A: identity_break
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()

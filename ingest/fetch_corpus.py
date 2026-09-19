#!/usr/bin/env python3
"""
Tải starter corpus cho Greenwashing Signal Pipeline.

Nguồn:
  - SEC EDGAR   : 10-K / 20-F (iXBRL HTML) + companyfacts JSON   -> ground truth cho financial_fact
  - filings.xbrl.org : ESEF report (iXBRL HTML) + xBRL-JSON       -> ground truth cho công ty EU
  - IR page     : annual / sustainability report PDF              -> KHÔNG tự động, xem data/ir-pdf/TARGETS.md

Mỗi file tải về được ghi một dòng vào data/manifest.jsonl với sha256 làm content key,
đúng theo thiết kế Bronze: file chứa payload, manifest chứa trạng thái.

SEC yêu cầu User-Agent có thông tin liên hệ. Đặt biến môi trường trước khi chạy —
thiếu email thì tầng SEC bị bỏ qua (fail closed) chứ không chạy với UA sai:
    export SEC_UA="Ten Ban ban@email.com"

Cách chạy:
    python3 ingest/fetch_corpus.py                      # tải toàn bộ (~878 MB)
    python3 ingest/fetch_corpus.py --skip-existing      # chỉ bù file còn thiếu
    python3 ingest/fetch_corpus.py --only esef          # một tầng

Mã thoát: 0 = corpus đầy đủ, 1 = có thất bại (danh sách in ở cuối). Manifest được
gộp vào bản cũ và ghi nguyên tử, nên một lần chạy hỏng không xoá provenance đã có.
"""
import argparse, hashlib, json, os, pathlib, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1] / "data"
MANIFEST = ROOT / "manifest.jsonl"
SEC_UA = os.environ.get("SEC_UA", "AI-Cases Research Bot")
SEC_SLEEP = 0.15   # SEC: ~10 req/s

# ---- Tier 1: có XBRL trên SEC -> gold set tự động --------------------------
SEC_TARGETS = [
    ("XOM",  "ExxonMobil",    "US GAAP, native text, baseline dễ nhất"),
    ("CVX",  "Chevron",       "segment note nhiều tầng"),
    ("SHEL", "Shell plc",     "IFRS, dual-listed, cột restated"),
    ("BP",   "BP plc",        "nhiều non-GAAP trong MD&A"),
    ("TTE",  "TotalEnergies", "song ngữ FR/EN, tài liệu 400+ trang"),
    ("EQNR", "Equinor",       "NOK/USD trộn"),
    ("PBR",  "Petrobras",     "BRL, tiếng Bồ Đào Nha"),
]
SEC_FORMS = {"10-K", "20-F"}
# ticker -> CIK ghi đè: company_tickers.json trỏ XOM tới holdco mới (CIK 2115436),
# không chứa 10-K lịch sử. Filer thật là 0000034088.
CIK_OVERRIDE = {"XOM": "0000034088"}
SEC_PER_COMPANY = 2          # 2 kỳ gần nhất -> đủ để chạy YoY continuity check

# ---- ESEF: LEI đã xác thực qua filings.xbrl.org/api/entities ---------------
ESEF_TARGETS = [
    ("21380068P1DRHMJ8KU70", "SHELL PLC"),
    ("OW6OFBNCKXC4US5C7523", "EQUINOR ASA"),
    ("529900S21EQ1BO4ESM68", "TotalEnergies SE"),
    ("BUCRF72VH5RBN7X3VL35", "ENI S.P.A."),
    ("BSYCX13Y0NOTV14V9N85", "REPSOL SA"),
    ("549300V62YJ9HTLRI486", "OMV AKTIENGESELLSCHAFT"),
    ("2138003319Y7NM75FG53", "Galp Energia, SGPS, S.A."),
    ("549300NFTY73920OYK69", "AKER BP ASA"),
]
ESEF_PER_ENTITY = 1

_rows = []          # file tải được trong LẦN CHẠY NÀY
_fail = []          # mỗi thất bại -> mã thoát khác 0
_have = set()       # local_path đã có file trên đĩa + dòng manifest
SKIP_EXISTING = False
ESEF_UA = "AI-Cases Research Bot"   # filings.xbrl.org không đòi UA liên hệ

def fail(msg):
    """Ghi nhận thất bại. In ra NGAY, nhưng vẫn nhớ để main() trả mã thoát."""
    _fail.append(msg)
    print(f"  !! {msg}")

# 403 KHÔNG retry: SEC trả 403 khi User-Agent không đạt chuẩn hoặc IP đang bị chặn.
# Thử lại không tự lành, chỉ làm SEC kéo dài thời gian chặn.
RETRY_STATUS = (429, 500, 502, 503, 504)

def _backoff(err, i):
    """Tôn trọng Retry-After nếu server gửi; nếu không thì backoff 2^i."""
    v = err.headers.get("Retry-After") if err.headers else None
    if v:
        try:
            return max(0.0, min(60.0, float(v)))
        except ValueError:
            pass
    return 2 ** i

def get(url, ua=SEC_UA, retries=3):
    req = urllib.request.Request(url, headers={
        "User-Agent": ua, "Accept-Encoding": "gzip, deflate", "Accept": "*/*"})
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                data = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    import gzip; data = gzip.decompress(data)
                return data
        except urllib.error.HTTPError as e:
            if e.code in RETRY_STATUS and i < retries - 1:
                time.sleep(_backoff(e, i)); continue
            raise
        except Exception:
            if i < retries - 1:
                time.sleep(2 ** i); continue
            raise

def save(data, path, **meta):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    row = dict(sha256=sha, bytes=len(data),
               local_path=str(path.relative_to(ROOT.parent)),
               fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), **meta)
    _rows.append(row)
    print(f"  ok  {len(data):>10,}  {path.relative_to(ROOT)}")
    return sha

def have(path):
    """File đã nằm trên đĩa VÀ đã có dòng provenance trong manifest."""
    return SKIP_EXISTING and str(path.relative_to(ROOT.parent)) in _have and path.exists()

def fetch_sec():
    print("\n=== SEC EDGAR ===")
    tickers = json.loads(get("https://www.sec.gov/files/company_tickers.json"))
    lookup = {v["ticker"]: (str(v["cik_str"]).zfill(10), v["title"]) for v in tickers.values()}

    for ticker, label, why in SEC_TARGETS:
        if ticker not in lookup:
            fail(f"{ticker}: không có trong company_tickers.json"); continue
        cik, title = lookup[ticker]
        cik = CIK_OVERRIDE.get(ticker, cik)
        print(f"\n[{ticker}] {title}  (CIK {cik}) — {why}")

        time.sleep(SEC_SLEEP)
        try:
            sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik}.json"))
        except Exception as e:
            fail(f"{ticker}: submissions lỗi: {e}"); continue

        r = sub["filings"]["recent"]
        picked = []
        for i, form in enumerate(r["form"]):
            if form in SEC_FORMS:
                picked.append((form, r["accessionNumber"][i], r["primaryDocument"][i],
                               r["reportDate"][i]))
            if len(picked) >= SEC_PER_COMPANY:
                break
        if not picked:
            fail(f"{ticker}: không thấy 10-K/20-F trong recent filings")

        for form, acc, primary, period in picked:
            accn = acc.replace("-", "")
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/{primary}"
            out = ROOT / "sec" / ticker / f"{form}_{period}" / primary
            if have(out):
                print(f"  skip  {out.relative_to(ROOT)}"); continue
            time.sleep(SEC_SLEEP)
            try:
                save(get(url), out, source="sec-edgar", company=label, ticker=ticker,
                     cik=cik, form=form, period_end=period, url=url, doc_kind="ixbrl_html")
            except Exception as e:
                fail(f"{ticker} {form} {period}: {e}")

        # companyfacts = toàn bộ fact đã tag -> gold set cho financial_fact
        cf_out = ROOT / "xbrl" / "companyfacts" / f"CIK{cik}.json"
        cf_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        if have(cf_out):
            print(f"  skip  {cf_out.relative_to(ROOT)}"); continue
        time.sleep(SEC_SLEEP)
        try:
            save(get(cf_url), cf_out,
                 source="sec-xbrl", company=label, ticker=ticker, cik=cik,
                 form="companyfacts", period_end=None, url=cf_url, doc_kind="xbrl_json")
        except Exception as e:
            fail(f"{ticker} companyfacts: {e}")

def fetch_esef():
    print("\n=== ESEF (filings.xbrl.org) ===")
    base = "https://filings.xbrl.org"
    for lei, name in ESEF_TARGETS:
        print(f"\n[{lei}] {name}")
        try:
            d = json.loads(get(f"{base}/api/entities/{lei}/filings?page%5Bsize%5D=50",
                               ua=ESEF_UA))["data"]
        except Exception as e:
            fail(f"{name}: filings lỗi: {e}"); continue
        d.sort(key=lambda x: x["attributes"].get("period_end") or "", reverse=True)
        for f in d[:ESEF_PER_ENTITY]:
            a = f["attributes"]; period = a.get("period_end")
            for key, kind in (("json_url", "xbrl_json"), ("report_url", "ixbrl_html")):
                u = a.get(key)
                if not u:
                    continue
                url = base + u
                out = ROOT / "esef" / lei / str(period) / pathlib.Path(u).name
                if have(out):
                    print(f"  skip  {out.relative_to(ROOT)}"); continue
                try:
                    save(get(url, ua=ESEF_UA), out, source="esef",
                         company=name, lei=lei, form="ESEF annual financial report",
                         period_end=period, url=url, doc_kind=kind,
                         filing_package_sha256=a.get("sha256"),
                         filing_id=a.get("fxo_id"))
                except Exception as e:
                    fail(f"{name} {kind} {period}: {e}")

IR_NOTE = """# Báo cáo phải tải tay

Không có registry cho báo cáo ESG — GRI Sustainability Disclosure Database đã đóng từ
tháng 4/2021. Phần dưới phải vào IR page lấy thủ công, rồi đặt PDF vào đúng thư mục.

## Tier 2 — không có XBRL, đây là chỗ đáng tiêu ngân sách annotation

| Công ty   | Nguồn                          | Trục khó nó phủ                        | Thư mục            |
|-----------|--------------------------------|----------------------------------------|--------------------|
| Petronas  | petronas.com (Media/Reports)   | MYR, sustainability report nặng đồ hoạ  | `petronas/`        |
| Pertamina | pertamina.com                  | IDR, song ngữ ID/EN                     | `pertamina/`       |
| PVN       | pvn.vn                         | VND, tiếng Việt — khó nhất về layout/OCR| `pvn/`             |
| Saudi Aramco | aramco.com                  | SAR, niêm yết Tadawul, không SEC        | `aramco/`          |

## Tier 1 — bản PDF thiết kế đẹp, để đối chiếu với bản iXBRL đã tải tự động

Đây là mấu chốt của eval: **cùng công ty, cùng năm, hai định dạng**. Bản iXBRL trong
`data/sec/` và `data/esef/` là bản dễ và đã có số chuẩn; bản PDF dưới đây là bản khó.
Con số giống nhau, nên bản dễ chính là ground truth miễn phí cho bản khó —
không cần annotate tay phần financial.

| Công ty   | Trang                                                | Thư mục       |
|-----------|------------------------------------------------------|---------------|
| Equinor   | equinor.com/investors/annual-reports                  | `equinor/`    |
| Shell     | shell.com/investors/results-and-reporting             | `shell/`      |
| TotalEnergies | totalenergies.com (Document d'enregistrement universel) | `totalenergies/` |
| BP        | bp.com/en/global/corporate/investors                  | `bp/`         |

Chú ý khi tải: nhiều công ty EU bản 2025 xuất **ESRS Index** thay cho GRI content index.
Ghi lại framework thực tế của từng file — Silver B cần biết nó là GRI, ESRS, IFRS S1/S2
hay TCFD trước khi parse.
"""

def load_manifest():
    """Đọc manifest cũ. Dòng hỏng -> dừng hẳn, không đoán.

    Fail closed: manifest là bản ghi provenance duy nhất. Bỏ qua một dòng không
    đọc được rồi ghi đè nghĩa là xoá hẳn dòng đó.
    """
    rows = {}
    if not MANIFEST.exists():
        return rows
    for n, line in enumerate(MANIFEST.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError as e:
            sys.exit(f"manifest.jsonl dòng {n} không đọc được ({e}). "
                     f"Sửa hoặc xoá file rồi chạy lại — không ghi đè để tránh mất provenance.")
        key = r.get("local_path")
        if not key:
            sys.exit(f"manifest.jsonl dòng {n} thiếu local_path.")
        rows[key] = r
    return rows

def write_manifest(old_rows):
    """Gộp _rows vào manifest cũ rồi ghi nguyên tử.

    Ghi thẳng "w" từ _rows (bản cũ) sẽ xoá provenance của mọi file tải từ lần
    trước mà lần này không chạm tới: nếu tầng ESEF hỏng, 16 dòng / 676 MB biến
    mất khỏi manifest dù file vẫn nằm trên đĩa, và validate_identities.py --all
    sẽ dừng với "không thấy filing ESEF nào trong manifest".
    """
    merged = dict(old_rows)
    for r in _rows:
        merged[r["local_path"]] = r
    tmp = MANIFEST.with_name(MANIFEST.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for key in sorted(merged):
            fh.write(json.dumps(merged[key], ensure_ascii=False) + "\n")
    os.replace(tmp, MANIFEST)      # nguyên tử: không để lại manifest cụt
    return merged

def write_targets():
    """Chỉ ghi TARGETS.md khi chưa có. File này được sửa tay và nằm trong git."""
    t = ROOT / "ir-pdf" / "TARGETS.md"
    t.parent.mkdir(parents=True, exist_ok=True)
    if not t.exists():
        t.write_text(IR_NOTE, encoding="utf-8")
    elif t.read_text(encoding="utf-8") != IR_NOTE:
        print(f"[note] {t.relative_to(ROOT.parent)} đã bị sửa tay — giữ nguyên bản của bạn.")

def main(argv=None):
    global SKIP_EXISTING, _have
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-existing", action="store_true",
                    help="bỏ qua file đã có trên đĩa và đã có dòng manifest "
                         "(chạy lại không tốn 878 MB băng thông)")
    ap.add_argument("--only", choices=["sec", "esef"], help="chỉ chạy một tầng")
    a = ap.parse_args(argv)
    SKIP_EXISTING = a.skip_existing

    ROOT.mkdir(parents=True, exist_ok=True)
    write_targets()
    old_rows = load_manifest()
    _have = {k for k in old_rows if (ROOT.parent / k).exists()}

    if a.only != "esef":
        # Fail closed: SEC yêu cầu User-Agent có email liên hệ. Chạy với UA mặc định
        # là tự chuốc lấy 403 và có thể bị chặn IP — từ chối trước thay vì thử.
        if "@" not in SEC_UA:
            fail('SEC_UA chưa có email liên hệ — bỏ qua tầng SEC. '
                 'export SEC_UA="Ten Ban ban@email.com" rồi chạy lại.')
        else:
            try:
                fetch_sec()
            except Exception as e:
                fail(f"SEC hỏng toàn phần: {e}")

    if a.only != "sec":
        try:
            fetch_esef()
        except Exception as e:
            fail(f"ESEF hỏng toàn phần: {e}")

    merged = write_manifest(old_rows)
    total = sum(r["bytes"] for r in _rows)
    print(f"\n=== lần này {len(_rows)} file, {total/1e6:.1f} MB "
          f"| manifest {len(merged)} dòng -> data/manifest.jsonl ===")

    if _fail:
        print(f"\n!! {len(_fail)} thất bại:")
        for m in _fail:
            print(f"   - {m}")
        print("Corpus KHÔNG đầy đủ. Manifest đã giữ lại provenance cũ.")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())

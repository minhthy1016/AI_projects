# Starter corpus — Greenwashing Signal Pipeline

Tải bằng `python3 ../fetch_corpus.py`. Chạy lại là idempotent (ghi đè cùng đường dẫn,
sha256 trong manifest cho biết file có đổi hay không).

```
data/
  sec/<TICKER>/<form>_<period>/   10-K, 20-F dạng iXBRL HTML
  xbrl/companyfacts/CIK*.json     toàn bộ fact us-gaap/ifrs đã tag của từng công ty
  esef/<LEI>/<period>/            .json = xBRL-JSON facts, .xhtml = báo cáo iXBRL
  ir-pdf/TARGETS.md               danh sách PDF phải tải tay + lý do
  manifest.jsonl                  1 dòng / file: sha256, url, company, form, period_end
```

## Vì sao corpus này

Không phải để có nhiều dữ liệu, mà để phủ đúng các trục làm pipeline gãy:

| Trục khó            | Ở đâu trong corpus                                    |
|---------------------|-------------------------------------------------------|
| Baseline dễ nhất    | `sec/XOM` — US GAAP, native text                       |
| IFRS + cột restated | `sec/SHEL`, `sec/BP`                                   |
| Currency trộn       | `sec/EQNR` (NOK/USD)                                   |
| Đa ngôn ngữ         | esef: `nb` Na Uy, `it` Ý, `es` Tây Ban Nha, `de` Đức   |
| Tài liệu rất lớn    | `sec/BP` 20-F ~33 MB, Repsol ESEF ~115 MB              |
| YoY continuity      | mỗi công ty SEC có 2 kỳ liền nhau                      |

## companyfacts và xBRL-JSON là ground truth

Cả hai cho `concept + value + unit + period + decimals`. Khớp thẳng vào schema Silver A:

- `decimals` → `declared_precision` (dùng để so sánh exact, KHÔNG dùng tolerance tự đặt)
- `unit` → `currency`
- `period` → `period_start` / `period_end`
- `concept` → `line_item_canonical` (`us-gaap:Revenues`, `ifrs-full:Revenue`)

Kiểm chứng: XOM FY2025 `us-gaap:Revenues` = 332,238,000,000 USD;
OMV FY2025 `ifrs-full:Revenue` = 24,308,000,000 EUR, `decimals: -6`.

## Điều quan trọng nhất về corpus này

Bản iXBRL ở đây là **bản dễ** và đã có sẵn số chuẩn. Bản PDF thiết kế đẹp trên IR page
(xem `ir-pdf/TARGETS.md`) là **bản khó** — cùng công ty, cùng năm, cùng con số.
Nên bản dễ chính là ground truth miễn phí cho bản khó, và phần financial gần như
không cần annotate tay. Ngân sách annotation để dành cho ESG và các case khó có chủ đích.

## Chưa có trong corpus

- Sustainability / ESG report — không có registry, GRI Database đóng từ 4/2021
- Tier 2 không XBRL: Petronas, Pertamina, PVN, Aramco
- Cả hai đều nằm trong `ir-pdf/TARGETS.md`, phải tải tay

# Greenwashing Signal Pipeline

Đọc báo cáo tài chính và báo cáo bền vững của các công ty dầu khí, chuẩn hoá thành dữ liệu
có nguồn gốc truy được, rồi chỉ ra chỗ lời nói và con số không khớp nhau.

Mỗi con số trong kết quả đều ghi rõ **trang, bảng, tiêu đề cột và đoạn chữ nguyên văn** —
điều kiện bắt buộc với một sản phẩm mang tính cáo buộc.

**Trạng thái:** thử nghiệm. Tầng số liệu tài chính đã chạy trên **cả 8 công ty** trong bộ ESEF
(6 ngôn ngữ); tầng số liệu môi trường vẫn chỉ 2 công ty (OMV FY2025, Aker BP FY2024), vì báo cáo
bền vững không có file đối chứng như báo cáo tài chính. Chưa phải sản phẩm.

---

## Kết quả hiện tại

| Chỉ số | Giá trị |
|---|---|
| Công ty đã chạy | **8** — toàn bộ bộ ESEF: OMV (Đức), Aker BP, Shell, Galp, TotalEnergies (Anh), Equinor (Na Uy), Eni (Ý), Repsol (TBN) |
| Độ chính xác so với dữ liệu chuẩn | **100%** ở cả 8 — 238 fact trích ra, **223 đối chiếu được với XBRL, 223 đúng**, 0 sai |
| Recall trong phạm vi profile | 83–100% (Eni 82,9% · Equinor 88,2% · Repsol 92,3% · Galp 93,1% · Aker BP 94,4% · Shell 94,7% · OMV 97,0% · TotalEnergies 100%) |
| Trần đo được — số liệu có mặt trong phần đã parse | **97,5%** (158/162; **98,8%** = 160/162 nếu tính 2 ca lệch quy ước dấu) |
| Nền ngẫu nhiên của phép đo trần | 11% → khoảng cách thật **86 điểm** |
| Dữ liệu đã trích | 351 dòng / 13 file (238 tài chính · 113 môi trường & tín hiệu) |
| Tuân thủ hợp đồng dữ liệu | Validate đủ JSON Schema (schema 1.1): 238/238 dòng tài chính · 40/40 dòng môi trường, 0 lỗi |
| Đẳng thức kế toán | 0 FAIL ở 7/8. Aker BP 6/6 · Shell 6/6 · Eni 6/6 · Galp 4/4 · Repsol 2/2 · **OMV 4/8** · Equinor và TotalEnergies chưa đủ trường để chạy phép nào. 4 FAIL của OMV đều khớp đúng một dòng mà phép kiểm không có — xem dưới bảng |
| Dấu hiệu tìm được | 2 (OMV), 1 (Aker BP) — đều có bằng chứng truy được |
| Unit test | 195, tất cả pass |
| Bảng tên gọi sinh từ iXBRL | 7/8 công ty · **592 nhãn** thay cho 91 dòng viết tay · 814 fact, **99,1%** đúng |

**4 FAIL của OMV không phải lỗi đọc số.** Cả bốn chênh đúng bằng một dòng in trên trang 148
mà phép kiểm chưa tính tới:

| Phép kiểm | 2024 | 2025 | Dòng bị thiếu |
|---|---:|---:|---|
| `profit_after_tax` | −88 Mio | −307 Mio | *Jahresüberschuss aus aufgegebenen Geschäftsbereichen* — lãi hoạt động đã ngừng; profile `omv-de` chưa lấy `ProfitLossFromDiscontinuedOperations` nên biến thể có discontinued không chạy được |
| `net_income_split` | −64 Mio | −60 Mio | *davon den Hybridkapitalbesitzern zuzurechnen* — phần của chủ trái phiếu hybrid; phép kiểm chỉ có cổ đông mẹ + thiểu số |

Chi tiết trong [`reports/ho-so-du-an.md`](reports/ho-so-du-an.md) và
[`reports/ho-so-du-an.html`](reports/ho-so-du-an.html) (có biểu đồ).

### Từng công ty

| Công ty | Ngôn ngữ | Lấy ra | Đối chiếu được | Đúng | Recall trong phạm vi |
|---|---|---:|---:|---:|---:|
| Shell | Anh | 36 | 36 | **100%** | 94,7% |
| OMV | Đức | 34 | 32 | **100%** | 97,0% |
| Aker BP | Anh | 34 | 34 | **100%** | 94,4% |
| Eni | Ý | 31 | 29 | **100%** | 82,9% |
| Galp | Anh | 31 | 27 | **100%** | 93,1% |
| Repsol | Tây Ban Nha | 28 | 26 | **100%** | 92,3% |
| TotalEnergies | Anh | 27 | 24 | **100%** | **100%** |
| Equinor | Na Uy | 17 | 15 | **100%** | 88,2% |
| **Tổng** | 6 ngôn ngữ | **238** | **223** | **100%** | 82,9–100% |

Chênh giữa *lấy ra* và *đối chiếu được* là 15 giá trị mà chính công ty không gắn thẻ XBRL —
không có gì để đối chiếu, nên không tính vào tử số lẫn mẫu số.

**Đọc hai cột cuối cho đúng.** *Đúng* hỏi: những gì đã lấy có sai không. *Recall* hỏi: có bỏ
sót gì không. Chỉ báo cáo cột *Đúng* thì một hệ thống đọc đúng một dòng cũng đạt 100%. Và
*recall* chỉ tính trong phạm vi bảng tên gọi đã khai — Shell còn 232 giá trị trong XBRL mà
bảng tên gọi chưa nhắc tới, nên 94,7% nói về 38 giá trị được chọn quan tâm, không phải 270.

### Bảng tên gọi: viết tay so với sinh từ iXBRL

Điểm yếu kiến trúc lớn nhất từng là bảng tên gọi viết tay — ~15 dòng mỗi công ty, sáu
ngôn ngữ. `extraction/build_label_map.py` sinh nó từ **chính file iXBRL**: mỗi giá trị
được gắn thẻ nằm ngay trong hàng mang nhãn in ra của nó.

```
<tr><td>Total assets</td> … <ix:nonFraction name="ifrs-full:Assets">370,350</…>
```

Không cần tải taxonomy IFRS, không cần đoán bản dịch, không ai gõ tay "Umsatzerlöse"
hay "Ricavi della gestione caratteristica" về cùng một khái niệm.

| | Viết tay | Sinh từ iXBRL |
|---|---:|---:|
| Số nhãn | 91 | **592** |
| Fact đối chiếu được | 196 | **814** (4,2×) |
| Đúng | 100% | **99,1%** |

Bảng sinh tự động cũng suy luôn **loại báo cáo** (từ kiểu kỳ + gốc tên khái niệm) và
**quy ước dấu** (từ thuộc tính `sign` kết hợp với việc dấu có hiện ra trang hay không).
Phần "viết tay" còn lại chỉ là 9 gốc tên khái niệm luồng tiền, dùng chung cho mọi công ty.

7 lỗi còn lại: 3 của Shell là Docling gán nhãn lệch dòng (bảng sinh tự động không sửa
được lỗi của tầng parse), 4 của Repsol là quy ước dấu luồng tiền chưa suy đúng.
Galp không dựng được — bản iXBRL của họ không có cấu trúc hàng nào, xem
`data/labelmaps/README.md`.

```bash
<fabrion>/.venv/bin/python extraction/build_label_map.py \
    --ixbrl data/esef/<LEI>/<kỳ>/<file>.xhtml --out data/labelmaps/<tên>.json
python3 extraction/doc_extract.py --parsed … --labels data/labelmaps/<tên>.json --out …
```

### Bảng điểm cho vận hành thật

`validation/hardness_report.py` gom mọi phép đo rời rạc thành một CSV, một dòng mỗi
tài liệu — dùng để theo dõi khi phát triển thành kỹ năng agent chạy thật.

```bash
python3 validation/hardness_report.py --out data/hardness_report.csv
python3 validation/hardness_report.py --labels-dir data/labelmaps \
    --out data/hardness_report_generated.csv     # dùng bảng tên gọi sinh tự động
```

| Chỉ số | Viết tay | Sinh từ iXBRL |
|---|---:|---:|
| `precision` — khớp / đối chiếu được | 100,0% | 99,2% |
| `verifiability` — đối chiếu được / lấy ra | 93,7% | 99,1% |
| **`trust` = precision × verifiability** | **93,7%** | **98,2%** |
| `coverage_filing` — bắt được / toàn bộ đáp án | 11,6% | **44,1%** |
| `chance_floor` — nền ngẫu nhiên | 0,8–8,7% | 0,8–8,7% |

**Hai điểm, cố ý không gộp.** `trust` trả lời "cái ta phát ra có tin được không";
`coverage_filing` trả lời "ta phủ được bao nhiêu tài liệu". Phạm vi hẹp là một *lựa
chọn* (chỉ lấy khoản mục cần cho tín hiệu greenwashing), sai số thì không — nhân hai
thứ đó với nhau là trộn lẫn hai loại phán xét.

`recall_inscope` **không** nằm trong điểm: mẫu số của nó là "số nhãn đã khai", nên nó
thưởng cho việc khai ít. Bảng sinh tự động phủ gấp gần 4 lần tài liệu nhưng
`recall_inscope` lại tụt từ 92,9% xuống 60,2% — chỉ vì nó dám khai 592 nhãn thay vì 91.

Cột `guard_*` đếm số bảng bị **bỏ** vì không xác định được đơn vị hoặc không rõ thuộc
báo cáo nào. Đó là con số **tốt** — fail-closed đang chặn thật. Theo dõi nó để biết khi
nào một thay đổi vô tình mở cổng ra.

### Từ PDF thô đến số đã kiểm

| Bậc | Số lượng |
|---|---:|
| Trang PDF dựng từ tài liệu gốc | 2.543 |
| Trang chứa báo cáo tài chính pháp định | 54 |
| Bảng công cụ nhận ra | 73 |
| Ô có chứa chữ số | 4.285 |
| Số liệu lấy ra | 238 |
| Đối chiếu được với XBRL | 223 |
| **Khớp chính xác** | **223** |

Mỗi bậc là một lần thu hẹp có chủ ý, không phải hao hụt. Bậc `4.285 → 238` là bảng tên gọi chỉ
khai ~15 khái niệm mỗi công ty — đây là giới hạn thật, và nó nằm ở bảng tên gọi viết tay chứ
không ở công cụ đọc PDF.

---

## Bố cục thư mục

Chia theo **vai trò trong pipeline**, không theo loại file:

```
AI_cases/
├── ingest/         tải tài liệu về máy
├── parsing/        PDF -> DoclingDocument, và đọc lại nó
├── extraction/     DoclingDocument -> Silver A / Silver B
├── signals/        Silver -> Gold: tính dấu hiệu
├── validation/     đo chất lượng: đẳng thức, ground truth, trần recall
├── shared/         tiện ích dùng chung (đọc số theo locale, đường dẫn)
├── contracts/      hợp đồng dữ liệu (JSON Schema)
├── tests/          unit test
├── integrations/   nối sang fabrion-extraction-evaluation
├── legacy/         bản v1 giữ để đối chứng
├── reports/        4 trang báo cáo
└── data/           tài liệu + kết quả (phần lớn bị gitignore; `gold/` thì không)
```

Các thư mục có `__init__.py` nên import chéo được. Mọi đường dẫn tới `data/` đi qua
`shared/paths.py` chứ không qua `Path(__file__).parent` — sau khi chia thư mục, thư mục chứa
script không còn là gốc dự án.

## Bảng file

### Chương trình — chạy theo thứ tự

| # | File | Việc | Ghi chú |
|---|---|---|---|
| 1 | `ingest/fetch_corpus.py` | Tải báo cáo từ SEC và filings.xbrl.org | idempotent, chạy lại không sợ trùng |
| 2 | `parsing/docling_convert.py` | PDF → `DoclingDocument` JSON | **cần venv có Docling**; 13–80 giây |
| 3 | `extraction/build_label_map.py` | Sinh bảng tên gọi từ iXBRL | **cần lxml** (venv Fabrion); thay 91 dòng viết tay bằng 592 nhãn |
| 4 | `extraction/doc_extract.py` | Silver A — số liệu tài chính | 8 profile; `--labels` để dùng bảng sinh tự động |
| 5 | `extraction/esg_extract.py` | Silver B — phát thải và mục tiêu | profile `omv` \| `akerbp` |
| 6 | `extraction/esrs_index_check.py` | Đối soát mục lục ESRS | 70/70 với OMV |
| 7 | `signals/compute_signals.py` | Gold — tính dấu hiệu nghi vấn | mỗi dấu hiệu kèm evidence |

### Hạ tầng dùng chung

| File | Việc |
|---|---|
| `parsing/docling_io.py` | Đọc `DoclingDocument` **không cần cài Docling** — tách phụ thuộc nặng khỏi các tầng sau |
| `shared/text_match_locale.py` | Đọc số theo cách viết từng nước (`24.308` = 24308 ở châu Âu) |
| `shared/paths.py` | Neo mọi đường dẫn vào gốc dự án, không vào thư mục chứa script |
| `shared/bbox.py` | Chuyển `source_ref.bbox` về gốc trên-trái, 4 số — **chỉ ở đầu ra**, tầng parse giữ hệ BOTTOMLEFT của Docling vì logic ghép tiêu đề–bảng cần nó |
| `contracts/extraction_contract.json` | Hợp đồng cho Silver A (`financial_fact`) — 22 trường bắt buộc |
| `contracts/esg_contract.json` | Hợp đồng cho Silver B (`esg_claim`) — grain khác nên không dùng chung |

### Kiểm chứng

| File | Việc |
|---|---|
| `validation/validate_identities.py` | Đẳng thức kế toán, 4 adapter: `companyfacts` \| `ixbrl` \| `esef` \| `extraction` |
| `validation/compare_to_truth.py` | So với xBRL-JSON hai chiều: độ chính xác (sai thang đo / sai dấu / sai khác) và recall (nhãn chết / thiếu kỳ) |
| `validation/coverage_esef.py` | Trần recall **kèm nền ngẫu nhiên** — trần không có nền là con số không đọc được. Chạy độc lập, gold nằm ở `data/gold/` |
| `validation/make_fixture.py` | Sinh dữ liệu có lỗi cố ý để test chính bộ kiểm chứng |
| `validation/hardness_report.py` | **Bảng điểm độ khó + độ tin cậy, xuất CSV** — một dòng mỗi tài liệu, để nạp vào công cụ vẽ biểu đồ |
| `tests/` | 195 unit test — mỗi lỗi đã sửa đều có một test hồi quy |
| `validation/run_coverage_patched.py` | Chạy `make coverage` của Fabrion với bộ đọc số đã sửa, **không đụng repo đó** |

### Nối sang bộ đo chất lượng

| File | Việc |
|---|---|
| `integrations/make_fabrion_dataset.py` | Đóng gói 2 báo cáo thành dataset chấm điểm, **đáp án sinh tự động** từ xBRL-JSON |

### Báo cáo

| File | Cho ai |
|---|---|
| `reports/ho-so-du-an.html` · `.md` | Người đọc chung — **vào đây trước** |
| `reports/esg-findings.html` | Kết quả chi tiết, tiếng Anh |
| `reports/greenwashing-pipeline.html` | Quyết định kiến trúc |
| `reports/silver-schema.html` | Đặc tả từng trường, cho người viết code |

### Dữ liệu

```
data/
├── sec/          179 MB   10-K / 20-F của 7 công ty, dạng iXBRL
├── esef/         644 MB   8 công ty EU — mỗi bộ có file nội dung + file số liệu chuẩn
├── xbrl/          15 MB   companyfacts, trải 21 năm
├── ir-pdf/        92 MB   PDF render từ xhtml + text layer
├── parsed/       3.6 MB   kết quả Docling (DoclingDocument + .meta.json)
├── extracted/    228 KB   ← KẾT QUẢ CHÍNH, 5 file JSONL
├── manifest.jsonl         danh mục file đã tải: nguồn, sha256, kích thước
└── v_*.jsonl              kết quả kiểm chứng, 8 file
```

| File kết quả | Dòng | Chứa gì |
|---|---|---|
| `omv-2025.jsonl` | 34 | Silver A — OMV |
| `akerbp-2024.jsonl` | 32 | Silver A — Aker BP |
| `omv-2025-esg.jsonl` | 30 | Silver B — phát thải + mục tiêu |
| `akerbp-2024-esg.jsonl` | 10 | Silver B — phát thải + mục tiêu |
| `omv-2025-esrs-index.jsonl` | 70 | Đối soát mục lục ESRS |

---

## Chạy

Bước 2 cần môi trường có Docling. Dự án dùng venv của
`~/Desktop/Fabrion/fabrion-extraction-evaluation`; đặt `FAB` cho gọn:

```bash
FAB=~/Desktop/Fabrion/fabrion-extraction-evaluation
```

```bash
# 1. tải tài liệu
python3 ingest/fetch_corpus.py

# 2. PDF -> JSON cấu trúc
$FAB/.venv/bin/python parsing/docling_convert.py \
    --pdf   data/ir-pdf/omv/omv-2025-esef-rendered.pdf \
    --pages 147-152 \
    --out   data/parsed/omv-canon.docling.json

# 3. số liệu tài chính
python3 extraction/doc_extract.py \
    --parsed     data/parsed/omv-canon.docling.json \
    --company-id 549300V62YJ9HTLRI486 \
    --profile    omv-de \
    --out        data/extracted/omv-2025.jsonl

# 4. số liệu môi trường
$FAB/.venv/bin/python parsing/docling_convert.py \
    --pdf data/ir-pdf/omv/omv-2025-esef-rendered.pdf \
    --pages 62-69 --out data/parsed/omv-esg.docling.json

python3 extraction/esg_extract.py \
    --parsed     data/parsed/omv-esg.docling.json \
    --company-id 549300V62YJ9HTLRI486 \
    --profile    omv \
    --out        data/extracted/omv-2025-esg.jsonl

# 5. đối soát mục lục
python3 extraction/esrs_index_check.py \
    --txt        data/ir-pdf/omv/omv-2025.txt \
    --company-id 549300V62YJ9HTLRI486 \
    --out        data/extracted/omv-2025-esrs-index.jsonl

# 6. tính dấu hiệu
python3 signals/compute_signals.py --esg data/extracted/omv-2025-esg.jsonl
```

Kiểm chứng, chạy lúc nào cũng được:

```bash
python3 -m unittest discover -s tests -t . -v
python3 validation/compare_to_truth.py --extracted data/extracted/omv-2025.jsonl \
    --truth data/esef/549300V62YJ9HTLRI486/2025-12-31/omvag-2025-12-31-1-de.json \
    --profile omv-de        # --profile để đo cả recall, không chỉ độ chính xác
python3 validation/validate_identities.py --source extraction --file data/extracted/omv-2025.jsonl
python3 validation/coverage_esef.py
```

---

## Liên hệ với `fabrion-extraction-evaluation`

Dự án này **chỉ tham chiếu**, không sửa nhánh chính của repo đó.

- Dùng `.venv` của nó để chạy Docling
- Mọi thay đổi cho nó nằm trên nhánh **`mini_project_greenwashing`**: dataset `finance/esef`,
  runner `tools/schema_extraction/run/ifrs.py`, và một bản vá `run/docling.py` trả `ExtractResult`
- Bản sửa cách đọc số nằm **trong thư mục này** (`shared/text_match_locale.py`), không đưa vào repo đó —
  file gốc ở đó dùng chung cho nhiều tầng và cho cả điểm số cũ
- **Bộ gold ESEF đã được copy sang `data/gold/`** (10 KB, nằm trong git). `coverage_esef.py`
  vì thế chạy độc lập, không cần repo Fabrion. Nó cũng đo trên bản parse của AI_cases
  (`data/parsed/*-canon.docling.json`) thay vì bản 300 trang của Fabrion — thu hẹp phạm vi
  kéo nền ngẫu nhiên từ 87% xuống 11%, biến con số trần thành thứ đọc được
- Hai file **vẫn cần** repo đó khi chạy: `validation/run_coverage_patched.py` (chạy
  `make coverage` của họ) và `integrations/make_fabrion_dataset.py` (đóng gói dataset cho họ).
  Đó là chủ đích — chúng là công cụ liên repo

Khôi phục PDF khi cần chạy harness:

```bash
python3 integrations/make_fabrion_dataset.py --fabrion $FAB --copy-pdf
```

---

## Giới hạn đã biết

- **Bảng tên gọi chỉ 17 dòng** — đây là ràng buộc thật. Tài liệu OMV có 349 bảng / 10.605 ô số;
  hệ thống lấy 34. Chạy trên toàn tài liệu vẫn đúng 34, nên giới hạn không nằm ở chọn trang
  hay ở Docling. Cách mở rộng đúng là lấy ánh xạ từ label linkbase của taxonomy IFRS.
- **Hai company-year chưa phải dataset.** Đổi năm gốc, đổi phạm vi, trình bày lại số cũ đều là
  tín hiệu chuỗi thời gian, cần 5–10 năm và vài chục công ty.
- **Chưa kiểm được số trang trong mục lục** — PDF render lại từ xhtml nên bị đánh số lại.
  Cần PDF gốc từ trang quan hệ nhà đầu tư.
- **Chưa thu thập mức độ đảm bảo** (limited/reasonable assurance) — có trong schema, chưa điền.
- **Chưa có mô hình máy học, và cố ý như vậy.** Greenwashing không có đáp án đúng/sai để huấn
  luyện. Giai đoạn này là chấm mâu thuẫn theo luật, có bằng chứng, cần người xem lại.

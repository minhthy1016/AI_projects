# Hồ sơ dự án Greenwashing

> Bản Markdown của [`ho-so-du-an.html`](ho-so-du-an.html). Nội dung như nhau; bản HTML dễ đọc hơn.

Hệ thống đọc báo cáo tài chính và báo cáo bền vững của các công ty dầu khí, rồi chỉ ra chỗ
lời nói và con số không khớp nhau.

| | |
|---|---|
| Đang áp dụng | OMV (Áo) · Aker BP (Na Uy) |
| Kho tài liệu | 37 file · 878 MB |
| Dữ liệu đã trích | 176 dòng có nguồn gốc |
| Độ chính xác | 100% so với dữ liệu chuẩn |
| Trạng thái | Thử nghiệm, chưa phải sản phẩm |

---

## 1. Dự án này làm gì

**Greenwashing** là khi một công ty nói về môi trường hay hơn thực tế họ làm. Với ngành dầu khí,
chuyện này khó phát hiện bằng mắt vì bằng chứng nằm rải rác trong những tài liệu 200–300 trang:
một con số ở báo cáo tài chính, một cam kết ở báo cáo bền vững, một chú thích nhỏ ở cuối trang
làm thay đổi ý nghĩa của cả hai.

Ba việc, theo thứ tự:

1. **Đọc tài liệu thành dữ liệu** — chuyển PDF thành bảng số máy hiểu được, trong đó *mỗi con số
   đều nhớ nó đến từ trang nào*.
2. **Kiểm tra dữ liệu có đúng không** — dùng các đẳng thức kế toán bất biến (tổng tài sản phải
   bằng tổng nguồn vốn) để tự phát hiện chỗ đọc sai, không cần người soát từng dòng.
3. **Đối chiếu tìm mâu thuẫn** — so cam kết với con số, so năm nay với năm trước, so chỉ tiêu
   công ty tự chọn với chỉ tiêu quy định bắt buộc.

### Ba khái niệm cần biết

| Khái niệm | Nghĩa |
|---|---|
| **Scope 1, 2, 3** | Ba nhóm phát thải. Scope 1 là khí công ty tự thải; Scope 2 từ điện mua vào; Scope 3 từ chuỗi giá trị — quan trọng nhất là *khách hàng đốt sản phẩm công ty bán ra*. Với dầu khí, Scope 3 thường lớn gấp hàng chục lần hai nhóm kia. |
| **Năm gốc (baseline)** | Năm làm mốc so sánh cho mục tiêu giảm phát thải. Đổi năm gốc là một cách làm tỷ lệ giảm trông đẹp hơn mà không cần giảm thật. |
| **ESRS** | Bộ chuẩn công bố bền vững của EU, bắt buộc từ 2024 theo luật CSRD. Thay phần lớn vai trò của GRI với công ty lớn châu Âu. |

Cả OMV và Aker BP đều công bố theo ESRS, và phần bền vững nằm **ngay trong báo cáo thường niên**
chứ không phải một file riêng.

---

## 2. Kết quả mẫu — OMV FY2025

Phát thải, đơn vị tấn CO2e. Nguồn: bảng E1-6, trang 67.

| Loại | 2019 (gốc) | 2025 | Thay đổi |
|---|---:|---:|---:|
| Scope 1 + 2 | 13.920.157 | 10.286.093 | **−26,1%** |
| Scope 3 — chuẩn ESRS bắt buộc | 134.419.405 | 154.270.286 | **+14,8%** |
| Scope 3 — chỉ tiêu tự định nghĩa | 113.696.828 | 91.536.655 | −19,5% |

**Phần giảm là phần nhỏ.** Scope 1+2 giảm 26%, nhưng Scope 3 lớn gấp **15 lần** và đang tăng.
Cộng lại, tổng phát thải đã tăng trong chính giai đoạn công ty báo cáo là giảm.

**Mục tiêu neo vào con số đang giảm.** OMV công bố hai chỉ tiêu Scope 3 cạnh nhau. Mục tiêu giảm
20% đến 2030 đặt trên chỉ tiêu *tự định nghĩa* (113,7 triệu tấn, đang giảm), không phải chỉ tiêu
ESRS bắt buộc (134,4 triệu tấn, đang tăng).

**Mục lục ESRS sạch.** 70/70 mục công ty khai đã công bố đều tìm thấy thật. Đây là kết quả tốt,
và cũng là bằng chứng cho thấy công cụ không bịa ra dấu hiệu khi không có gì.

---

## 3. Kết quả mẫu — Aker BP FY2024

Đơn vị tấn CO2e. Nguồn: bảng 11, trang 68–69. Báo cáo in theo đơn vị nghìn tấn, đã quy đổi.

| Loại | 2017 (gốc) | 2024 | Mục tiêu 2030 | Mục tiêu 2050 |
|---|---:|---:|---:|---:|
| Scope 1 + 2 như công bố | 1.250.000 | 853.000 | 625.000 | 125.000 |
| Scope 3 | — | 71.458.000 | — | — |
| Scope 2 — cơ sở địa điểm | — | 14.000 | — | — |
| Scope 2 — cơ sở thị trường | — | 575.000 | — | — |

**Mục tiêu chỉ phủ khoảng 1% lượng phát thải.** Scope 3 gấp **84 lần** Scope 1+2, nhưng công ty
không công bố năm gốc và không đặt mục tiêu nào cho Scope 3 — phần lớn nhất vừa không có đích
đến, vừa không đo được tiến độ.

**Con số tổng dựa trên cơ sở có lợi hơn.** Công ty công bố hai cách tính Scope 2. Lấy cách "địa
điểm" (14 nghìn tấn) thì tổng khớp với số đã in. Lấy cách "thị trường" (575 nghìn tấn, gấp 41
lần) thì tổng 2024 *vượt* năm gốc 13%, thay vì giảm 31,8%.
*Ghi nhận để rà soát* — không khẳng định, vì công ty không công bố số theo cơ sở thị trường cho
năm gốc 2017 nên chưa so cùng cơ sở qua thời gian được.

---

## 4. Nâng cấp: đọc PDF bằng Docling

Bản đầu chuyển PDF sang chữ thuần rồi **cắt theo vị trí ký tự** để dựng lại cột. Mọi lỗi nặng
nhất đều sinh ra từ đó, và đều *im lặng*: số vẫn trông hợp lý, chỉ nằm sai cột hoặc sai năm.

Bản hiện tại dùng **Docling** — nhận diện cấu trúc bảng, trả về lưới ô có chỉ số hàng/cột.

| Lỗi của bản cũ | Hậu quả | Docling xử |
|---|---|---|
| Hai bảng chung một dòng đơn vị | Lấy nhầm tiêu đề → **cả bảng lệch một cột** | mỗi bảng là một đối tượng riêng |
| Nhãn nhóm căn giữa dùng làm ranh giới cột | Đọc nhầm khối số — và **phép kiểm nội bộ vẫn báo đạt** | tiêu đề hai tầng đọc thẳng từ lưới |
| Chú thích dính tiêu đề (`2024¹`) | Mất trọn một báo cáo, không một dòng lỗi | tiêu đề là một ô |
| Cột số tham chiếu lẫn vào dữ liệu | Đọc số tham chiếu thành giá trị | là một cột riêng |

### Kết quả đo được

| Công ty | Cách cũ | Docling |
|---|---|---|
| OMV 2025 | 32 số · 93,3% đúng | **34 số · 100% đúng** |
| Aker BP 2024 | 29 số · 100% đúng | **32 số · 100% đúng** |

**Đổi loại lỗi, không phải hết lỗi.** Docling cũng sinh lỗi mới: nuốt dấu cách
(`Summe Aktiva` → `SummeAktiva`), có lúc đánh rơi một nhãn năm. Khác biệt: lỗi cũ là lỗi hình
học, rất khó suy luận; lỗi mới là lỗi chữ nghĩa, nhìn ra ngay. Chỗ nào không chắc thì hệ thống
**gắn cờ và hạ độ tin cậy** chứ không đoán — nhãn năm bị mất thì mốc đó vẫn được ghi với năm để
trống, kèm cờ, thay vì bịa ra một cái năm.

---

## 5. Hệ thống đọc sót, hay tài liệu vốn không có?

Câu hỏi phải trả lời được trước khi tin bất kỳ con số nào. Dự án
`fabrion-extraction-evaluation` có sẵn công cụ đo: đếm xem bao nhiêu giá trị cần lấy thật sự
xuất hiện trong tài liệu, trước khi bất kỳ chương trình đọc nào chạy. Đó là **trần trên**.

Lần đo đầu cho **44%**. Con số đó sai, hai nguyên nhân:

- **Công cụ đo đọc số theo cách viết Anh-Mỹ.** Báo cáo Đức viết `24.308` để chỉ hai mươi tư
  nghìn; công cụ hiểu thành hai mươi tư phẩy ba. Đo cụ thể: **33/37** giá trị của OMV chỉ tồn
  tại ở dạng châu Âu. Aker BP viết tiếng Anh nên không dính.
- **Đếm cả trường không thể đọc từ văn bản.** Đáp án ghi hệ số `1000000` trong khi tài liệu viết
  "In EUR Mio"; ghi kỳ là `FY2025` trong khi tài liệu viết `2025`.

| Đo lại cho đúng | Trước | Sau |
|---|---:|---:|
| OMV — giá trị số | 27% | **100%** |
| OMV — tổng phần đọc được từ văn bản | 63% | **99%** |
| Aker BP — tổng phần đọc được | 99% | 99% |
| **Cả hai công ty** | 82% | **99%** |

**Đọc con số này cho đúng.** Phép đo khớp giá trị trên túi số của cả bản parse, không
theo vị trí, nên phải biết *nền*: cùng bộ gold đó khớp được bao nhiêu với tài liệu của
công ty khác.

Đo trên bản parse đầy đủ 300 trang của Fabrion: trần 99% nhưng **nền 87%** — con số
gần như vô nghĩa. Đo trên bản parse của AI_cases (chỉ các trang báo cáo tài chính,
đúng thứ extractor nhìn thấy): trần **98%**, nền **11%**, khoảng cách thật **86 điểm**.

Cùng một trần, nhưng thu hẹp phạm vi làm nền sụp — và phần chênh mới là thông tin.
Bản đầy đủ còn cho 2 khớp giả: gold ghi chi phí thuế `+1834` theo quy ước taxonomy,
tài liệu in `–1.834`; trong 300 trang tình cờ có một `+1834` khác. Hai ca này nay được
tách riêng thành "lệch quy ước dấu" — không phải lỗi parser, extractor xử lý đúng bằng
`sign_flip`, nên trần thực chất là **99%**.

`coverage_esef.py` nay in ba cột trần / nền / cách, và chạy độc lập: bộ gold đã nằm
trong `data/gold/`, không cần repo Fabrion.

Chỉ còn 1/162 không khớp: ngày kết thúc kỳ, đáp án ghi `2025-12-31` còn tài liệu viết
"31. Dezember 2025".

**Ý nghĩa:** gần như toàn bộ số liệu cần lấy đều có mặt và đều đọc được. Không có rào cản nào từ
công cụ đọc PDF. Khớp với kết quả thực tế (100%) và xác nhận giới hạn duy nhất là bảng tên gọi.

### Chạy lại `make coverage` của Fabrion với bộ đọc số đã sửa

| schema | budget | nguyên bản | có vá |
|---|---|---:|---:|
| 10kq | full | 36% | 36% |
| research | full | 48% | 48% |
| **esef** | **full** | **44%** | **61%** |

Hai schema tiếng Anh **không đổi một điểm** — bản sửa an toàn với mọi điểm số cũ. `esef` 61% chứ
không phải 99% vì `make coverage` gộp cả trường mã hoá vào mẫu số: 160/162 đọc được (99%) cộng
37/160 trường mã hoá (23%) ra 197/322 = 61%.

**Sửa ở đâu:** bản đọc số nằm trong thư mục này (`shared/text_match_locale.py`), **không** sửa vào
Fabrion — file gốc ở đó dùng chung cho nhiều tầng và cho cả điểm số cũ. Mọi thay đổi khác cho
Fabrion đã tách sang nhánh `mini_project_greenwashing`; nhánh chính giữ nguyên.

Phần khó nhất không phải viết code mà là **chấp nhận có chỗ không thể biết chắc**: `1.234` đứng
một mình có thể là một nghìn hai trăm ba mươi tư, cũng có thể là một phẩy hai ba tư. Cách xử lý:
chỗ nào chắc chắn thì quyết theo chính con số; chỗ nào không chắc thì quyết theo **cả tài liệu**
rồi áp nhất quán — không đoán riêng lẻ từng số.

---

## 6. Vì sao chỉ trích ra ngần ấy dòng?

| Trong tài liệu | OMV | Aker BP |
|---|---:|---:|
| Số bảng | 349 | 147 |
| Ô chứa số | 10.605 | 1.418 |
| Dòng có tên gọi | 3.833 | 1.639 |
| **Hệ thống lấy ra** | **34** | **32** |

**Nguyên nhân là bảng tên gọi chỉ có 17 dòng.** Hệ thống chỉ nhận ra 17 chỉ tiêu — tổng tài sản,
tổng vốn chủ, doanh thu, lợi nhuận, các dòng tiền. Mọi dòng khác không có tên tương ứng nên bị
bỏ qua.

Để loại trừ nghi ngờ khác, đã chạy trên **toàn bộ tài liệu** thay vì vài trang: vẫn đúng 34 dòng.
Giới hạn *không* nằm ở việc đọc một phần, cũng *không* ở công cụ đọc PDF.

**Lấy ít không có nghĩa là thiếu.** Phần lớn trong 10.605 ô là số trang, số tham chiếu chú thích,
bảng lương, đối chiếu thuế — không liên quan greenwashing. Mục tiêu là lấy đủ những con số mà các
dấu hiệu cần, và ở mức đó hiện đã đủ.

Muốn mở rộng, cách đúng **không phải** viết tay thêm vài trăm dòng tên gọi. Chuẩn IFRS có sẵn từ
điển ánh xạ tên gọi sang mã chỉ tiêu, kèm bản dịch từng ngôn ngữ.

---

## 7. Mặt được và hạn chế

### Mặt được

- **Mọi con số đều truy được nguồn** — trang, bảng, tiêu đề cột, đoạn chữ nguyên văn.
- **Chấm điểm không tốn công annotate** — tài liệu EU đi kèm file số liệu chuẩn. Cả hai công ty
  đúng 100%.
- **Dữ liệu ra tuân thủ hợp đồng** — 176 dòng, 0 thiếu trường, 0 sai enum. Hai hợp đồng riêng cho
  hai loại dữ liệu.
- **Hệ thống tự bắt lỗi của chính nó** — đẳng thức kế toán phát hiện ba lỗi đọc sai cột mà mắt
  thường không thấy.
- **Thà mất dòng còn hơn sai bậc** — không xác định được đơn vị thì từ chối phát ra số. Chạy trên
  241 trang, quy tắc này chặn 119 bảng không liên quan.
- **Không dùng AI để đoán số** — toàn bộ phần đọc là luật tất định, lặp lại và giải thích được.

### Hạn chế

- **Hai công ty chưa phải một bộ dữ liệu.**
- **Chưa kiểm được số trang trong mục lục** — PDF render lại nên bị đánh số lại.
- **Mỗi công ty vẫn cần một "profile" riêng** — phần bảng nhãn đáng lẽ lấy từ từ điển chuẩn kế
  toán chứ không viết tay.
- **Chưa thu thập mức độ đảm bảo** (limited/reasonable assurance).
- **Chưa có mô hình máy học, và cố ý như vậy.**

> **Cách đọc kết quả.** Các dấu hiệu ở trên **không chứng minh công ty gian dối**. Chúng chỉ ra
> chỗ cách công bố làm bức tranh trông khác đi so với dữ liệu đầy đủ. Việc tách riêng Scope 3 hay
> chọn một cơ sở tính toán đều có thể có lý do kỹ thuật chính đáng. Giá trị của hệ thống là **chỉ
> đúng chỗ cần hỏi**, kèm bằng chứng để người có chuyên môn tự đánh giá — không phải đưa ra phán
> quyết.

---

## 8. Việc tiếp theo

1. **Tải PDF gốc** của OMV và Aker BP từ trang nhà đầu tư, để khôi phục phép kiểm số trang.
2. **Lấy bảng tên gọi từ label linkbase** của taxonomy IFRS thay vì viết tay.
3. **Mở rộng lên ~20 công ty × 8 năm** để có phân phối tham chiếu cho ngành.
4. **Thu thập mức độ đảm bảo và thay đổi phạm vi** — hai trường đã có trong đặc tả.
5. **Chỉ khi có đủ dữ liệu đối chứng** mới tính đến mô hình dự đoán.

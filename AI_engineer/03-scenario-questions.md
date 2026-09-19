# Phần 3 — Câu hỏi tình huống (Senior AI/LLM Engineer)

> 5 tình huống hay gặp nhất ở vòng system/behavioral. Mỗi câu có: **khung trả lời**, **đáp án mẫu**, và **story thật từ CV của bạn** để gắn vào — vì câu trả lời có số liệu thật luôn thắng câu trả lời chung chung.
>
> Khung chung cho mọi tình huống production: **Đo trước → Khoanh vùng → Sửa nhỏ nhất → Chặn tái diễn (regression gate) → Ghi lại**.

---

## Tình huống 1 — "Agent NL-to-SQL đang chạy tốt, tuần này khách báo trả lời sai. Bạn làm gì?"

### Điều interviewer muốn thấy
Bạn có phương pháp debug hệ non-deterministic không, hay chỉ đoán và sửa prompt.

### Khung trả lời
**Bước 0 — Không sửa prompt vội.** Câu đầu tiên tôi hỏi: "sai theo nghĩa nào, và có tái lập được không?"

1. **Tái lập** — lấy đúng trace của các câu hỏi khách báo (prompt version, model version, tool call, SQL sinh ra, rowset trả về, thời điểm).
2. **Khoanh vùng theo tầng** — lỗi ở đâu trong 4 tầng:
   - *Routing*: gọi sai tool/sai datasource?
   - *Query construction*: sai measure/dimension/filter/granularity?
   - *Data*: query đúng nhưng mart đằng sau sai/trễ? (kiểm freshness + dbt test)
   - *Answer*: query đúng, số đúng, nhưng câu chữ diễn giải sai?
   → Cách nhanh: chạy lại cùng câu hỏi, so **tool-call args** với gold. Nếu args đúng mà số sai → lỗi data, không phải lỗi LLM.
3. **Kiểm cái gì đã thay đổi** — prompt version? model version của provider? schema mart mới? dữ liệu mới có giá trị NULL/category lạ? *Đa số "model tự nhiên dở đi" thật ra là schema hoặc data đổi.*
4. **Đưa ca lỗi vào golden set** ngay, kể cả trước khi sửa được.
5. **Sửa ở tầng rẻ nhất** — thường là: thêm mô tả cho dimension trong semantic layer, hoặc siết enum trong tool schema, chứ không phải viết lại prompt.
6. **Chạy regression** trên toàn bộ golden set để chắc chắn không đánh đổi ca khác.
7. **Chặn tái diễn** — thêm deterministic check cho lớp lỗi đó (ví dụ: so rowcount và column list với gold) vào CI.

### Story của bạn để gắn vào
> "Ở Fabrion tôi vận hành eval end-to-end cho một NL-to-SQL agent doanh nghiệp trên benchmark BEAVER 209 câu, với 7 scorer tự động — trong đó có SQL execution equivalence, tool-call correctness, answer grounding và rowset semantics. Chính vì có bộ scorer đó nên khi có ca sai tôi không phải đoán: tôi biết ngay lỗi nằm ở routing, ở query, hay ở data. Qua 33 vòng diagnose → fix → re-test, composite pass rate đi từ 0.14 lên 0.93."

**Câu chốt:** "Điểm mấu chốt không phải là tôi sửa được, mà là tôi *biết mình đã sửa được* — vì có phép đo tái lập."

---

## Tình huống 2 — "Kết quả eval của team đang bị nghi ngờ / hai lần chạy ra hai kết quả khác nhau."

### Điều interviewer muốn thấy
Sự chính trực về mặt kỹ thuật (integrity). Đây là câu bạn có lợi thế lớn nhất.

### Khung trả lời
1. **Phân tách nguồn variance** — có 3 nguồn, phải tách:
   - *LLM variance* (temperature, non-determinism của provider) → đo bằng N trial cùng input.
   - *Harness variance* (thứ tự chạy, cache, state rò rỉ giữa các test) → chạy trong workspace sạch mỗi trial.
   - *Infra variance* (resource contention, timeout, rate limit, OOM) → đây là thủ phạm hay bị nhầm thành "model dở".
2. **Kiểm bằng control** — chạy null agent (không làm gì) và cheater agent (cố gian lận grader). Cả hai *phải* ra 0 điểm. Nếu không, grader đang hỏng chứ không phải model.
3. **Nếu kết quả không đáng tin → quarantine, không im lặng.** Đánh dấu run đó là invalid, công bố lý do, chạy lại trên infra sạch, republish lịch sử đã sửa.
4. **Làm cho tái lập được** — fingerprint mọi thứ ảnh hưởng kết quả: scorer source code hash, prompt version, model + version, dataset version, rubric version. Đổi bất kỳ cái nào → invalidate experiment cũ, không so trực tiếp.
5. **Báo cáo có khoảng tin cậy** — không bao giờ báo một con số trần trụi từ 1 lần chạy.

### Story của bạn
> "Tôi từng phát hiện một loạt kết quả eval gây hiểu nhầm do hạ tầng hỏng và resource contention, cộng với variance của LLM. Tôi quarantine chúng và republish lại lịch sử eval đã sửa, để quyết định engineering dựa trên đo lường tái lập được chứ không dựa trên cải thiện giả. Với tôi, eval là một kỷ luật kỹ thuật, không phải một cái dashboard."

**Câu chốt:** "Một eval mà không ai dám phản biện thì không phải eval. Tôi thiết kế để bất kỳ ai cũng chạy lại được và ra cùng kết quả."

---

## Tình huống 3 — "Lãnh đạo muốn adopt một coding agent / vendor AI. Bạn chứng minh nên hay không nên thế nào?"

### Điều interviewer muốn thấy
Bạn biến quyết định mua-hay-không thành bằng chứng, và bạn nghĩ về fairness của phép so sánh.

### Khung trả lời
1. **Định nghĩa "tốt" trước khi thử** — chọn 5 task đại diện công việc thật, có một kết quả đúng rõ ràng, chấm bằng **grader ẩn** mà agent chưa từng thấy.
2. **Fairness** — giữ *cùng model, cùng task, cùng workspace sạch* cho mọi agent; chỉ đổi đúng một biến là agent. Adapter layer để mỗi agent chỉ là một seam thay được.
3. **Chống gaming** — grader phải chạy độc lập với config của agent (ví dụ pytest với `-c /dev/null --noconftest` để agent không tự nhét conftest ép pass). Dùng **mutant implementation** để chứng minh test mà agent tự viết là có răng.
4. **Control bắt buộc** — null agent và cheater agent phải ra 0/5.
5. **Đo nhiều chiều, không chỉ đúng/sai** — outcome, cost, token, số turn, wall-time, và *reliability qua 3 trial*. Rất thường gặp: hai agent cùng 100% outcome nhưng cost/turn chênh 3-5 lần → đó mới là quyết định.
6. **Kết luận có điều kiện** — không nói "tốt/xấu", nói "**adopt-with-guardrails**: dùng cho task loại A, không dùng cho loại B, kèm giới hạn ngân sách và review bắt buộc."

### Story của bạn
> "Tôi thiết kế một harness vendor-agnostic: 5 task lập trình × 3 trial, grader ẩn là pytest suite + structural check. Tôi thêm cả positive và negative control — một agent không làm gì và một agent cố gian lận grader — để chứng minh harness bắt được cả việc thiếu việc lẫn việc gian lận. Rồi tôi viết adapter để chạy pi.dev và OpenAI Codex CLI trên *đúng* cùng bộ task, với telemetry cost/token/turn. Khuyến nghị của tôi là adopt-with-guardrails, và lãnh đạo đã theo."

**Câu chốt:** "Tôi không đưa ý kiến về vendor, tôi đưa bằng chứng — và bằng chứng đó chạy lại được với vendor tiếp theo mà không phải viết lại harness."

---

## Tình huống 4 — "Chi phí LLM tháng này gấp 4 lần dự kiến, nhưng không được giảm chất lượng."

### Điều interviewer muốn thấy
Tư duy vận hành: đo trước, cắt theo ROI, và bảo vệ chất lượng bằng eval chứ bằng cảm giác.

### Khung trả lời
1. **Attribute trước khi cắt** — cost breakdown theo: endpoint/feature, tenant, model, input vs output token, retry/lỗi. Rất hay gặp: 80% chi phí đến từ 1 feature hoặc từ retry storm.
2. **Chốt baseline chất lượng** — snapshot điểm golden set hiện tại. Mọi tối ưu sau đó phải re-run bộ này; giảm quá X% thì revert.
3. **Cắt theo thứ tự ROI:**
   - Loại bỏ lãng phí: retry vô ích, prompt lặp, gọi LLM cho việc code làm được (regex, lookup, validation).
   - Prompt caching: đưa phần tĩnh lên đầu prompt.
   - Cắt context: bớt top-k, dedupe, nén lịch sử hội thoại.
   - Giới hạn output token.
   - Model routing/cascade: model rẻ xử lý phần lớn traffic, escalate lên model mạnh khi confidence thấp hoặc task khó.
   - Semantic cache cho câu hỏi lặp (key gồm tenant + data version).
   - Batch API cho workload offline.
4. **Chặn tái diễn** — budget alert theo feature/tenant, rate limit, circuit breaker, và cost hiển thị trong trace như một SLI bình thường.
5. **Đóng vòng lặp** — sau mỗi thay đổi: cost mới + điểm eval mới, trình cả hai cạnh nhau.

### Story của bạn
> "Trong các harness tôi xây, cost và token là first-class metric ngang với accuracy — tôi capture cost/token/turn/wall-time từ telemetry của chính agent cho từng trial. Nên khi cần tối ưu, tôi có sẵn đường cơ sở để nói 'giảm 40% chi phí, điểm eval giảm 1 điểm' thay vì đoán."

**Câu chốt:** "Cost mà không kèm điểm eval là con số vô nghĩa — phải luôn trình theo cặp."

---

## Tình huống 5 — "Hệ thống trả lời sai cho khách hàng lớn, có yếu tố tuân thủ. Xử lý 24h đầu?"

### Điều interviewer muốn thấy
Xử lý sự cố có thứ tự ưu tiên đúng: **chặn thiệt hại → điều tra → sửa → phòng ngừa**, và trung thực trong giao tiếp.

### Khung trả lời
**Giờ 0-1 — Chặn thiệt hại**
- Xác định phạm vi: bao nhiêu câu trả lời, khách nào, từ khi nào (query theo trace + prompt version).
- Giảm rủi ro ngay: bật chế độ thận trọng (bắt buộc citation, hạ ngưỡng refuse), hoặc tắt feature/rollback về prompt version trước. Rollback trước, tìm nguyên nhân sau.
- Báo stakeholder với sự thật đang có, kèm mốc cập nhật tiếp theo.

**Giờ 1-6 — Điều tra**
- Tái lập lỗi từ trace. Xác định tầng lỗi (retrieval / query / data / generation).
- Kiểm cái gì đã đổi: prompt, model version, schema, dữ liệu nguồn, index.
- Xác định "blast radius": các câu hỏi tương tự cũng sai không? (chạy lại lớp câu hỏi đó hàng loạt)

**Giờ 6-24 — Sửa & xác nhận**
- Sửa nhỏ nhất giải quyết được nguyên nhân gốc.
- Chạy full golden set + bộ ca lỗi mới → chỉ ship khi cả hai xanh.
- Nếu là lỗi grounding: thêm hard constraint (không có evidence → không trả lời), không chỉ sửa câu chữ prompt.

**Sau đó — Phòng ngừa**
- Ca lỗi vào golden set vĩnh viễn + regression gate trong CI.
- Thêm deterministic check cho lớp lỗi này.
- Postmortem không đổ lỗi: nêu lỗ hổng hệ thống (thiếu check nào), không nêu ai gõ sai.
- Nếu có yếu tố compliance: giữ audit trail đầy đủ (input, evidence, output, version) — và nếu chưa có, đó là action item số 1.

**Nguyên tắc phát ngôn:** không nói "AI đôi khi sai vậy đó". Nói: "hệ thống thiếu một guardrail cụ thể; đây là guardrail đó và đây là cách chúng tôi chứng minh nó hoạt động."

---

## Bonus — 6 câu behavioral phải có sẵn story (dùng STAR)

Chuẩn bị sẵn, mỗi câu 90 giây, có ít nhất 1 con số:

| Câu hỏi | Story nên dùng từ CV |
|---|---|
| "Kể về lúc bạn không đồng ý với leader" | Kết quả eval gây hiểu nhầm → bạn quarantine thay vì báo cáo con số đẹp |
| "Dự án khó nhất bạn từng làm" | LAAF — kiến trúc 2 tier + recovery controller + failure taxonomy |
| "Lúc bạn làm hỏng cái gì đó / học từ thất bại" | Composite pass rate 0.14 lúc đầu — nói về chuỗi 33 vòng diagnose→fix→re-test |
| "Bạn tự chủ tới đâu" | Delivered end-to-end analytics product một mình: Airbyte → 65 dbt models → 20+ Cube models → Taipy dashboard + chat agent → Dagster orchestration |
| "Thuyết phục người khác bằng dữ liệu" | Benchmark 4 PDF parser × 3 approach → đổi roadmap ingestion |
| "Làm việc với ambiguity" | Chuyển coding-agent-eval từ POC một lần thành framework LAAF cho toàn lifecycle |

**Mẫu STAR 90 giây:**
- **S** (10s) bối cảnh + vì sao khó
- **T** (10s) bạn chịu trách nhiệm gì cụ thể
- **A** (50s) bạn quyết định gì, đánh đổi gì, làm gì — nói "tôi", không nói "team"
- **R** (20s) **con số** + điều bạn rút ra / thay đổi cách làm về sau

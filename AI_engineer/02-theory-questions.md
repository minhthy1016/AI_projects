# Phần 2 — Câu hỏi lý thuyết (Senior AI/LLM Engineer)

> 5 câu lõi. Mỗi câu có: **cách trả lời 30 giây** (nói trước), **đáp án đầy đủ**, **follow-up interviewer sẽ hỏi tiếp**, và **bẫy thường gặp**.
> Nguyên tắc: senior không kể tên tool — senior nói **trade-off** và **cách đo**.

---

## Câu 1 — RAG hoạt động thế nào, và nó hỏng ở đâu?

### Trả lời 30 giây
"RAG có hai nửa: retrieval và generation. Phần lớn lỗi production nằm ở retrieval — nếu evidence sai thì prompt giỏi mấy cũng vô nghĩa. Nên tôi luôn đo hai tầng riêng: recall@k cho retrieval, faithfulness cho generation. Chỉ khi recall đủ tốt tôi mới tối ưu prompt."

### Đáp án đầy đủ

**Pipeline:** parse → chunk → embed → index → (query rewrite) → retrieve → rerank → assemble context → generate → cite.

**Các điểm hỏng, theo thứ tự tần suất thực tế:**

| Điểm hỏng | Triệu chứng | Cách sửa |
|---|---|---|
| Parse kém (bảng vỡ, sai reading order) | Số liệu trả về sai dù chunk "có chứa" | Đổi parser theo loại doc; benchmark có ground truth |
| Chunk cắt giữa ngữ nghĩa | Câu trả lời cụt, thiếu điều kiện | Chunk theo section/layout; parent-child retrieval (match chunk nhỏ, trả về parent lớn) |
| Vector search miss exact term | Hỏi mã lỗi "E-4021" không ra | Hybrid BM25 + vector, fuse bằng RRF |
| Top-k quá nhỏ / không rerank | Evidence đúng nằm ở rank 12 | Lấy top-50 rồi cross-encoder rerank xuống top-5 |
| Context nhiễu / trùng lặp | Model bị "lost in the middle" | MMR dedupe, nén context, đặt evidence quan trọng ở đầu & cuối |
| Không có đường từ chối | Bịa khi không có dữ liệu | Prompt contract bắt buộc cite; không cite được → refuse |
| Index cũ | Trả lời theo dữ liệu tuần trước | CDC/TTL, reindex có lịch, hiển thị as-of date |

**Metrics phải tách bạch:**
- Retrieval: `recall@k`, `MRR`, `nDCG` — cần golden set (query → chunk id đúng).
- Generation: `faithfulness/groundedness` (mỗi claim có evidence không), `answer relevance`.
- E2E: exact/semantic match với gold answer + `no-answer rate` + `citation precision`.

**Khi nào KHÔNG dùng RAG:** khi câu hỏi cần tổng hợp toàn corpus (thì cần aggregation/analytics, không phải top-k), hoặc khi dữ liệu là structured — lúc đó semantic layer + query tốt hơn RAG.

### Follow-up sẽ bị hỏi
- *"Chunk size bao nhiêu?"* → "Không có con số cố định; tôi bắt đầu 512 token / overlap 15%, rồi sweep trên golden set. Điều quan trọng hơn size là boundary — cắt theo heading."
- *"Recall@k thấp thì làm gì trước?"* → Query rewrite + hybrid trước, đổi embedding model sau (đắt hơn nhiều).
- *"Rerank có đáng không?"* → Đáng, thường là ROI cao nhất; đổi lại +50-200ms latency.

### Bẫy
- Nói "tôi tăng chunk overlap để tăng accuracy" mà không có số đo → mất điểm.
- Quên nói về **tenant isolation** khi RAG multi-tenant (filter phải ở tầng index, không lọc sau).

---

## Câu 2 — LLM-as-a-judge: khi nào tin được, khi nào không?

### Trả lời 30 giây
"LLM judge là công cụ đo có noise, nên tôi coi nó như một scorer cần được calibrate và không cho nó quyền quyết định cuối. Trong hệ tôi xây, deterministic grader quyết định PASS/FAIL, judge chỉ advisory — vì một quyết định ship/no-ship phải giải thích được trước bất kỳ ai."

### Đáp án đầy đủ

**Khi nào judge phù hợp:** output tự do (tóm tắt, tư vấn, viết), tiêu chí mờ (helpfulness, tone), hoặc khi không thể viết assertion.

**Khi nào KHÔNG:** khi tồn tại ground truth kiểm được bằng code — SQL trả đúng rowset, JSON đúng schema, test suite pass. Lúc đó dùng judge là tự thêm noise.

**Các bias phải biết tên:**
| Bias | Mô tả | Cách chống |
|---|---|---|
| Position bias | Ưu tiên đáp án đứng trước trong pairwise | Swap thứ tự, chấm 2 chiều, lấy trung bình |
| Verbosity bias | Dài = tưởng tốt hơn | Rubric phạt độ dài thừa; normalize |
| Self-preference | Model thiên vị output của chính family mình | Judge **cross-family** (đánh giá output Claude bằng judge DeepSeek/GPT và ngược lại) |
| Format/sycophancy | Bị dẫn dắt bởi prompt hoặc bởi confidence của câu trả lời | Rubric tuyệt đối thay vì pairwise; ẩn metadata |

**Làm judge đáng tin — checklist:**
1. **Rubric tuyệt đối + anchor examples** (mẫu điểm 1/3/5 cụ thể), không hỏi "cái nào hay hơn".
2. **temperature = 0**, judge_model **pin cứng version**, rubric có `rubric_version`.
3. Đưa judge_model + rubric_version vào **fingerprint** của experiment → đổi judge = invalidate kết quả cũ.
4. **Calibrate với human labels**: đo Cohen's kappa / agreement rate trên 50-100 mẫu. Dưới ngưỡng thì rubric sai, không phải model sai.
5. Yêu cầu judge xuất **lý do + trích dẫn evidence** trước khi cho điểm (giảm chấm bừa, và cho bạn cái để audit).
6. Đo **variance**: chạy lại cùng input nhiều lần; judge dao động lớn = không dùng để gate.

**Kiến trúc 2 tier (điểm mạnh nên kể):**
```
Tier 1 — Deterministic: safety gate G ∈ {0,1} × (execution equivalence, structural check, non-regression)
Tier 2 — LLM judge: chất lượng/diễn giải → advisory
Invariant: judge KHÔNG BAO GIỜ lật được kết quả deterministic.
Total = G × (W1·JudgeScore + W2·ExecScore)
```
G nhân (multiplicative) chứ không cộng: vi phạm safety → 0 tuyệt đối, không "bù điểm" được.

### Follow-up
- *"Đo judge tốt bằng gì?"* → agreement với human (kappa), độ ổn định khi lặp, và khả năng phân biệt (nếu judge cho mọi thứ 4/5 thì nó vô dụng — kiểm tra phân phối điểm).
- *"Dùng model nhỏ làm judge được không?"* → Được cho tiêu chí hẹp + rubric chặt, và rẻ hơn nhiều; phải calibrate lại.

### Bẫy
- Trả lời "tôi dùng GPT chấm, thấy khá ổn" → chết. Phải có **con số agreement**.
- Quên **control**: dùng null/cheater để chứng minh scorer bắt được failure.

---

## Câu 3 — Context engineering, prompt caching và bài toán cost/latency

### Trả lời 30 giây
"Context là tài nguyên có ngân sách, không phải chỗ nhét càng nhiều càng tốt. Tôi thiết kế prompt theo layout cố định-trước/động-sau để ăn prompt cache, cắt context theo budget token, và đo $/request như một SLI."

### Đáp án đầy đủ

**Cấu trúc prompt tối ưu cache:**
```
[STATIC   — cache được]  system + tool definitions + few-shot + policy
[SEMI     — ít đổi]      schema / semantic layer description
[DYNAMIC  — đổi mỗi call] retrieved evidence + user turn
```
Cache hoạt động theo **prefix**: chỉ cần đổi 1 ký tự ở đầu là mất toàn bộ cache phía sau. Nên: không bao giờ để timestamp/UUID/random ở đầu prompt.

**Đòn bẩy cost, xếp theo ROI:**
1. Prompt caching (giảm mạnh chi phí input với prompt dài lặp lại).
2. Chọn đúng model cho đúng task — route classify/extract sang model rẻ, chỉ reasoning mới dùng model mạnh (model cascade: chạy rẻ trước, escalate khi confidence thấp).
3. Giới hạn `max_tokens` output — output token đắt hơn input đáng kể.
4. Semantic cache cho query lặp (embed query, cosine ≥ ngưỡng → trả cache). Cẩn thận: cache theo tenant + theo version dữ liệu.
5. Batch API cho workload offline (eval, backfill).
6. Nén context: summarize lịch sử cũ, bỏ chunk trùng, chỉ giữ field cần.

**Latency:**
- **TTFT** quan trọng hơn total cho UX → stream.
- Parallel tool calls thay vì tuần tự.
- Hedging: gửi request thứ 2 khi vượt p95, lấy cái về trước (đổi cost lấy tail latency).
- Đo p50/p95/p99, không đo trung bình — trung bình che tail.

**Context rot:** chất lượng giảm khi context quá dài, thông tin ở giữa dễ bị bỏ qua ("lost in the middle"). → Đặt thứ quan trọng ở đầu và cuối; ít evidence chất lượng cao > nhiều evidence.

### Follow-up
- *"Cache invalidation khi nào?"* → khi đổi prompt version, đổi model, hoặc dữ liệu nguồn đổi (gắn data version vào cache key).
- *"Semantic cache có rủi ro gì?"* → false hit: hai câu hỏi gần nhau về ngữ nghĩa nhưng khác đáp án (khác thời gian, khác entity). Ngưỡng phải cao + key phải gồm tenant/filters.

### Bẫy
- Nhầm "context window lớn = bỏ RAG được". Không: cost, latency và context rot vẫn còn; RAG còn cho bạn citation và ACL.

---

## Câu 4 — Prompting vs RAG vs Fine-tuning: chọn cái nào?

### Trả lời 30 giây
"Ba thứ này giải ba vấn đề khác nhau: prompting sửa *hành vi*, RAG sửa *kiến thức*, fine-tuning sửa *phong cách/định dạng/độ chuyên biệt và cost*. Tôi luôn đi từ rẻ đến đắt và chỉ leo thang khi có số đo chứng minh tầng trước hết dư địa."

### Đáp án đầy đủ

| | Giải quyết | Chi phí | Cập nhật kiến thức | Khi nào chọn |
|---|---|---|---|---|
| Prompt/context eng. | hành vi, format, reasoning | thấp nhất | tức thì | luôn thử trước |
| RAG | kiến thức riêng, mới, có citation | trung bình | tức thì (reindex) | dữ liệu đổi, cần trích nguồn, cần ACL |
| Fine-tune (LoRA/QLoRA) | phong cách, tuân thủ format, task hẹp lặp lại, giảm prompt dài | cao (data + train + serve) | phải train lại | prompt đã dài/đắt, có ≥ vài nghìn mẫu chất lượng |
| Distillation | rẻ hóa: model nhỏ bắt chước model lớn | cao một lần, rẻ về sau | — | volume lớn, task ổn định |

**Điểm senior:**
- Fine-tune **không** dạy được fact mới đáng tin — nó dạy phân phối, không dạy tra cứu. Fact mới → RAG.
- **LoRA/QLoRA**: chỉ train adapter rank thấp (thường r=8-64) thay vì toàn bộ weight → rẻ, nhiều adapter/1 base model, dễ rollback. QLoRA thêm quantize base xuống 4-bit để vừa GPU.
- Chất lượng data > số lượng: 1000 mẫu sạch, đa dạng, đúng distribution production thắng 100k mẫu scrape.
- Phải giữ **held-out eval set** trước khi train, và đo cả **regression** trên năng lực chung (fine-tune hẹp dễ gây catastrophic forgetting).
- Chi phí thật của fine-tune là **vận hành**: versioning, retrain khi data drift, serving adapter.

### Follow-up
- *"RAG + fine-tune cùng lúc?"* → Có: fine-tune để model dùng đúng format/tool và tuân thủ contract, RAG cấp fact. Đây là combo phổ biến.
- *"Khi nào biết prompt hết dư địa?"* → khi error analysis cho thấy lỗi là *thiếu kiến thức* (→RAG) hoặc *không tuân thủ format dù đã few-shot* (→fine-tune), chứ không phải lỗi diễn đạt.

### Bẫy
- Đề xuất fine-tune ngay từ đầu → dấu hiệu thiếu kinh nghiệm production.

---

## Câu 5 — Thiết kế agent: kiến trúc, failure modes, guardrails

### Trả lời 30 giây
"Agent = LLM + tools + vòng lặp + điều kiện dừng. Phần khó không phải làm nó chạy, mà là làm nó *dừng đúng lúc* và *sai một cách an toàn*. Nên tôi thiết kế agent quanh 3 thứ: tool contract chặt, budget/stop condition, và telemetry đủ để dựng lại mọi turn."

### Đáp án đầy đủ

**Kiến trúc, từ đơn giản đến phức tạp — chọn cái đơn giản nhất đủ dùng:**
1. **Single-call + tools** — đủ cho 70% use case.
2. **ReAct loop** (think → act → observe) — cho task cần nhiều bước.
3. **Planner–Executor** — planner sinh kế hoạch, executor chạy từng bước; dễ audit hơn, tốt cho task dài.
4. **Multi-agent** — chỉ khi thật sự cần chuyên môn hóa + có thể chạy song song. Chi phí: coordination, context loss giữa các agent, khó debug. *Đừng đề xuất multi-agent nếu chưa bị bắt buộc.*

**Tool design (nơi quyết định thành bại):**
- Ít tool, tên rõ nghĩa, docstring viết cho *người mới vào* đọc; JSON schema chặt với enum thay vì free-text.
- Tool trả về lỗi **có hướng dẫn sửa** ("column `revenu` không tồn tại; các cột hợp lệ: ...") — agent phục hồi tốt hơn nhiều so với stack trace.
- Idempotent khi có thể; write tool cần dry-run.
- Với analytics: cho agent gọi **semantic layer** (measures/dimensions) thay vì sinh raw SQL → loại bỏ lỗi join/grain.

**Failure taxonomy (nên có sẵn để nói):**
| Loại | Ví dụ | Guardrail |
|---|---|---|
| Wrong tool | dùng search khi cần query DB | mô tả tool rõ + few-shot routing |
| Right tool, wrong args | sai granularity, sai filter | schema enum + validate + error message hướng dẫn |
| Grain mismatch | count row thay vì count distinct | deterministic check rowcount vs gold |
| Contract violation | trả text khi cần JSON | structured output + retry có sửa |
| Loop / no progress | lặp cùng tool 5 lần | max turns, phát hiện lặp state, budget $ |
| Ungrounded answer | bịa số | bắt buộc cite từ tool output |
| Unsafe action | DROP TABLE | read-only role, allowlist, HITL |

**Guardrail theo tầng:** input (injection, PII) → tool layer (permission, limit, timeout) → output (schema, grounding) → system (budget, circuit breaker, kill switch).

**Prompt injection qua tool output** là mối nguy hay bị quên: dữ liệu truy hồi có thể chứa lệnh. Cách chống: đánh dấu rõ ranh giới evidence là *dữ liệu không phải chỉ thị*, không cho tool output tự kích hoạt tool có side-effect, và luôn kiểm quyền ở tầng tool chứ không tin model.

### Follow-up
- *"Đo agent thế nào?"* → task success (deterministic grader), tool-call correctness, số turn, cost/task, pass@k qua nhiều trial.
- *"Agent non-deterministic thì test kiểu gì?"* → chạy N trial, báo cáo tỉ lệ + variance; assert lên *kết quả cuối* (state của workspace/DB), không assert lên chuỗi hành động.

### Bẫy
- Nói "tôi thêm reflection để nó tự sửa" mà không có grader → reflection không có tín hiệu ngoài thì chỉ là model tự thuyết phục mình.

---

## Bonus — 12 câu hỏi nhanh phải trả lời được trong 1 câu

1. **Temperature vs top-p** — temperature làm phẳng/nhọn phân phối; top-p cắt đuôi theo xác suất tích lũy. Chỉnh một cái thôi.
2. **Embedding vs completion model** — embedding cho retrieval/similarity, completion để sinh; đừng dùng cosine của LLM output làm metric chất lượng.
3. **Tại sao cosine chứ không Euclid** — vector thường được normalize; hướng mang ngữ nghĩa, độ dài thì không.
4. **HNSW vs IVF-PQ** — HNSW nhanh & recall cao, tốn RAM; IVF-PQ nén, rẻ RAM, mất chút recall.
5. **Cross-encoder vs bi-encoder** — bi-encoder embed độc lập (nhanh, index được); cross-encoder đọc cặp query-doc (chính xác hơn, chậm) → dùng để rerank.
6. **Structured output đảm bảo thế nào** — JSON schema / constrained decoding + validate Pydantic + retry có kèm lỗi validation.
7. **Hallucination là gì về mặt kỹ thuật** — model sinh token có xác suất cao nhưng không có cơ sở trong evidence; chống bằng grounding + refusal path, không bằng "bảo nó đừng bịa".
8. **Quantization** — giảm precision weight (8/4-bit) để rẻ RAM & nhanh; đổi lại mất chút chất lượng, phải đo lại.
9. **KV cache** — cache attention key/value của token đã sinh để không tính lại; lý do prefix ổn định lại rẻ.
10. **pass@k** — xác suất có ít nhất 1 trong k lần chạy đạt; đo reliability của hệ non-deterministic.
11. **Guardrail vs eval** — guardrail chặn tại runtime, eval đo trước khi ship. Cần cả hai.
12. **MCP (Model Control Protocol) là gì** — chuẩn giao thức để expose tool/resource cho model, giúp tool dùng lại được giữa các agent thay vì hardcode mỗi nơi một kiểu.

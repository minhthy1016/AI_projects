# Phần 4 — Coding Challenges (AI/LLM Engineer)

> 5 bài, tất cả **chỉ dùng Python stdlib**, tất cả **có lời giải chạy được** trong `code/`.
> Chạy toàn bộ: `cd code && for f in *.py; do python3 $f; done`
>
> **Cách ôn hiệu quả nhất:** đọc đề → tự code trong 25-40 phút → mới mở lời giải → đọc phần
> "Điều interviewer thực sự chấm" để biết mình thiếu gì.

| # | Bài | File | Thời gian | Kỹ năng lõi |
|---|---|---|---|---|
| 1 | Hybrid retrieval: BM25 + vector + RRF + MMR | `code/01_hybrid_retrieval.py` | 40 phút | RAG internals |
| 2 | Chunking + context budget packer | `code/02_context_packer.py` | 30 phút | Token economics |
| 3 | LLM client: structured output + retry + repair + circuit breaker | `code/03_llm_client.py` | 40 phút | Production reliability |
| 4 | SQL execution-equivalence scorer | `code/04_sql_exec_scorer.py` | 35 phút | Evaluation (thế mạnh của bạn) |
| 5 | Agent loop: tool registry, budget, loop detection, trace | `code/05_agent_loop.py` | 45 phút | Agent engineering |

---

## Bài 1 — Hybrid Retrieval (BM25 + Dense + RRF + MMR)

**Đề:** Cho một corpus. Implement BM25, dense retrieval bằng cosine, gộp hai ranking bằng
Reciprocal Rank Fusion, rồi chọn top-k đa dạng bằng MMR. Không dùng thư viện ngoài.

*** Tóm tắt về challenge này:*** 
BM25 captures exact lexical matches, while dense retrieval captures semantic similarity. I fuse their rankings with RRF because their raw scores are on incompatible scales. Then I optionally rerank a small candidate pool with a cross-encoder for deeper relevance, and apply MMR to reduce redundancy. Finally, I use a calibrated rejection threshold so the system can say "no relevant result" instead of always returning top-k. At scale, BM25 uses an inverted index and dense retrieval uses ANN such as HNSW or IVF-PQ. In multi-tenant systems, tenant filtering should happen before retrieval at the index layer.

Nếu hiểu được đoạn này và giải thích được tại sao từng bước tồn tại, thì bạn đã nắm được phần conceptual core của bài challenge rồi.

**Bạn phải tự nghĩ ra:**
- Công thức BM25: `idf(t) · (f·(k1+1)) / (f + k1·(1 - b + b·dl/avgdl))`, với `k1≈1.5`, `b=0.75`.
- RRF: `score(d) = Σ 1/(k + rank_i(d))`, `k=60`.
- MMR: chọn lặp `argmax [ λ·sim(q,d) − (1−λ)·max_{s∈đã chọn} sim(d,s) ]`.

**Điều interviewer thực sự chấm** (quan trọng hơn code):
1. Bạn có giải thích được **tại sao RRF fuse theo rank chứ không theo score** không?
   → Vì BM25 không chặn trên, cosine chặn trong [-1,1]; fuse theo rank thì khỏi normalize.
   Đây là câu trả lời tách senior khỏi junior.
2. Bạn có nêu được **vì sao cần lexical** khi đã có vector không?
   → Exact-match token: mã lỗi `E-4021`, part number, tên riêng hiếm. Vector hay miss.
3. Bạn có xử lý **ngưỡng từ chối** không? Vector search luôn trả về k doc gần nhất *kể cả
   khi corpus không có câu trả lời* — thiếu ngưỡng `min_sim` là một nguồn hallucination
   chính. Và ngưỡng đó phải **calibrate trên golden set**, không phải đoán.
4. **Độ phức tạp:** BM25 `O(|q|·N)` khi quét thẳng (production dùng inverted index → `O(|q|·df)`);
   MMR `O(k·|pool|)`.

**Follow-up hay bị hỏi:**
- *"Scale lên 10 triệu doc thì sao?"* → ANN index (HNSW/IVF-PQ) cho dense, inverted index cho lexical; RRF vẫn giữ nguyên vì nó chỉ cần rank.
- *"Rerank ở đâu?"* → giữa fuse và MMR: lấy pool ~50 → cross-encoder → top-10 → MMR → top-3.
- *"Multi-tenant?"* → filter ở tầng index (pre-filter), không lọc sau khi truy hồi, nếu không recall bị hụt và rò rỉ dữ liệu.


---

## Bài 2 — Chunking theo ngữ nghĩa + Context Budget Packer

**Đề:** (a) Cắt tài liệu thành chunk ≤ `max_tokens`, không cắt giữa câu, có overlap.
(b) Cho các chunk đã truy hồi kèm score và một ngân sách token, chọn tập chunk tối ưu:
khử trùng lặp, không vượt ngân sách, sắp xếp chống "lost in the middle".

**Ba cái bẫy trong đề:**
1. **Câu dài hơn cả chunk** (bảng, log, code) → phải có đường cắt cứng, nếu không chunk tràn.
2. **Overlap có hạt là câu** → nếu `overlap_ratio · max_tokens` nhỏ hơn một câu thì sao?
   (Lời giải: vẫn giữ đúng một câu, nhưng chặn trần ở nửa chunk.) Interviewer sẽ hỏi
   chính chỗ này.
3. **Quên trừ `reserved_output`** khỏi ngân sách → prompt vừa nhét vào context window
   nhưng không còn chỗ để model sinh. Đây là bug production kinh điển.
   `budget = window − system − output − safety_margin`.

**Điều interviewer thực sự chấm:**
- Nói được trade-off chunk nhỏ/lớn và giải pháp **parent-child retrieval** (match trên
  chunk nhỏ để chính xác, trả về parent lớn để đủ ngữ cảnh).
- Biết **"lost in the middle"**: đặt chunk điểm cao nhất ở đầu, cao nhì ở cuối.
- Biết đếm token là **xấp xỉ** và phải có safety margin.
- Prompt contract đánh dấu evidence là *dữ liệu, không phải chỉ thị* → phòng thủ
  prompt injection qua nội dung truy hồi.

**Follow-up:** *"Bài toán chọn chunk trong ngân sách là knapsack — sao dùng greedy?"*
→ Greedy theo score là đủ tốt trong thực tế và giữ được thứ tự ưu tiên chất lượng; DP tối ưu
theo *tổng score* có thể chọn nhiều chunk kém thay vì một chunk tốt, thường tệ hơn về chất
lượng câu trả lời. Nêu được nhận xét này là điểm cộng lớn.

---

## Bài 3 — Production LLM Client (structured output + retry + repair + breaker)

**Đề:** Viết hàm gọi LLM bắt buộc trả JSON đúng schema, có tự sửa, retry lỗi tạm thời,
circuit breaker, và theo dõi cost.

**Ý tưởng then chốt — đây là toàn bộ bài này:**

> **RETRY ≠ REPAIR.**
> - *Retry*: lỗi hạ tầng (429/5xx/timeout) → gửi lại **y nguyên** request, có backoff + jitter.
> - *Repair*: lỗi nội dung (JSON hỏng / sai schema) → gửi request **mới kèm thông báo lỗi**.
>
> Gộp hai cái là bug: retry một prompt sinh JSON hỏng thì nó sẽ hỏng tiếp.

**Checklist phải có:**
- [ ] Phân loại lỗi transient vs permanent — **không retry 401/400** (fail nhanh).
- [ ] Exponential backoff + **full jitter** (không jitter → thundering herd khi provider hồi phục).
- [ ] Thông báo lỗi validation **nói rõ cách sửa** (`must be one of [...], got 'happy'`),
      vì chính nó được đưa lại cho model.
- [ ] Trần số lần repair — prompt tồi có thể đốt tiền vô hạn.
- [ ] Circuit breaker CLOSED → OPEN → HALF_OPEN.
- [ ] Bóc JSON khỏi code fence / lời dẫn thừa, quét ngoặc **cân bằng có xét trạng thái chuỗi**
      (dấu `}` nằm trong string không được coi là đóng object).
- [ ] Đếm token + cost cho **cả lần thất bại** — repair và retry đều tốn tiền thật.

**Follow-up:**
- *"Có JSON mode / constrained decoding rồi thì cần validate không?"* → Có. JSON mode đảm bảo
  *cú pháp*, không đảm bảo *ngữ nghĩa* (enum sai, field thiếu, giá trị ngoài khoảng). Vẫn phải validate.
- *"Idempotency?"* → Gắn idempotency key cho các thao tác có side-effect, để retry không tạo bản ghi trùng.
- *"Breaker mở thì làm gì?"* → fallback model/provider khác, hoặc trả lời degraded **có báo cho người dùng** — tuyệt đối không im lặng trả kết quả kém.

---

## Bài 4 — SQL Execution-Equivalence Scorer ⭐

> Bài này khớp trực tiếp với kinh nghiệm trong CV của bạn (7 scorer, BEAVER 209 câu).
> Nếu công ty làm về data/analytics agent thì **đây gần như chắc chắn là bài họ hỏi**.

**Đề:** Chấm SQL do agent sinh so với gold SQL. Không so chuỗi. Phải xử lý: alias khác,
thứ tự dòng, dòng trùng lặp, sai số float, NULL, lỗi thực thi, và SQL không an toàn.

**Các quyết định thiết kế phải nói ra được:**

| Quyết định | Lựa chọn đúng | Vì sao |
|---|---|---|
| So chuỗi hay chạy? | Chạy rồi so kết quả | Hai câu SQL khác nhau hoàn toàn vẫn có thể tương đương |
| Thứ tự dòng | Chỉ bắt buộc khi **gold** có `ORDER BY` | Agent thêm ORDER BY thừa không phải lỗi |
| Set hay multiset? | **Multiset** | Mất `DISTINCT` là lỗi thật, so theo set sẽ bỏ sót |
| Tên cột | Bỏ qua, so theo vị trí | Alias khác nhau không phải lỗi |
| Float | So với dung sai | `0.1+0.2 ≠ 0.3` trong dấu phẩy động |
| Gold SQL lỗi | **Raise, không phải fail agent** | Lỗi của dataset, không phải của agent — rất quan trọng |

**Phần làm bạn khác biệt: taxonomy + recovery.**
Grader không chỉ nói "sai", nó nói **sai loại gì**:
`WRONG_ROWCOUNT` → *Grain Mismatch* (thiếu GROUP BY/DISTINCT/sai join) ·
`EXECUTION_ERROR` → *Contract Violation* · `WRONG_VALUES` → *Logic Error* ·
`WRONG_ORDER` → thiếu ORDER BY.
Từ taxonomy đó sinh gợi ý re-prompt cho vòng 2 — và **không bao giờ inject gold answer**
(làm thế là rò rỉ đáp án, eval mất hết giá trị). Đây chính là recovery controller.

**Safety gate — nói được cả hai tầng:**
- Whitelist (`^SELECT|WITH`), chặn stacked query (`;`), **bỏ comment trước khi kiểm**
  (nếu không, `-- \nDELETE` lách được).
- Nhưng: guardrail ứng dụng **không bao giờ là hàng phòng thủ duy nhất** — connection phải
  chạy bằng **role read-only** ở tầng database.
- Thêm: timeout / giới hạn số phép toán, để một query xấu không treo cả suite eval.

**Follow-up:**
- *"Nếu không có gold SQL, chỉ có gold answer?"* → so kết quả cuối, và bổ sung tool-call
  correctness ở tầng semantic layer (measures/dimensions/filters/granularity khớp không).
- *"Query trả 1 triệu dòng?"* → so checksum/hash của rowset đã sắp xếp + so aggregate,
  thay vì nạp hết vào bộ nhớ.
- *"Đây là hard-pass/fail. Muốn partial credit?"* → chấm theo từng thành phần
  (measures / dimensions / filters / time-grain / order-limit / result-shape) — chính là
  bộ scorer theo trường bạn đã xây.

---

## Bài 5 — Agent Loop có kiểm soát

**Đề:** Viết vòng lặp agent production: tool registry có schema, validate args trước khi
chạy, chạy song song tool độc lập, timeout mỗi tool, lỗi tool thành observation, và các
điều kiện dừng: max_turns, budget, loop detection. Có trace đầy đủ.

**Câu nói mở đầu nên dùng:**
> "Làm agent chạy thì dễ; làm nó **dừng đúng lúc** và **sai một cách an toàn** mới là việc khó.
> Nên tôi thiết kế quanh ba thứ: tool contract chặt, budget + stop condition, và telemetry
> đủ để dựng lại mọi turn."

**Checklist phải có:**
- [ ] **Validate args trước khi gọi tool** — đừng để model quyết định cái gì hợp lệ.
- [ ] **Lỗi tool → observation, không phải exception.** Agent chỉ phục hồi được nếu nó *đọc* được lỗi.
      Và lỗi phải **hướng dẫn cách sửa**: `'period' phải thuộc [daily, weekly, monthly]` chứ không phải stack trace.
- [ ] **Song song hóa** tool độc lập trong cùng turn (`asyncio.gather`) — cắt latency thẳng.
- [ ] **Timeout mỗi tool** — một tool treo không được treo cả agent.
- [ ] **Loop detection**: hash `(tool, args)`; lặp quá N lần = không tiến triển → dừng.
      *Đây là failure mode đắt tiền nhất ở production.*
- [ ] **Budget check trước khi gọi**, không phải sau.
- [ ] **Grounding check ở câu trả lời cuối**: trích dẫn phải trỏ tới tool result có thật;
      không có thì từ chối trả lời.
- [ ] **Tool mutating cần human approval.**
- [ ] **Trace**: tool, args, latency, ok/err, token, cost, `stop_reason`.

**`stop_reason` phải liệt kê được:** `COMPLETED · LOOP_DETECTED · BUDGET_EXCEEDED · MAX_TURNS · UNGROUNDED · NO_ACTION`.
Nói được danh sách này là dấu hiệu rõ nhất bạn từng vận hành agent thật.

**Follow-up:**
- *"Test agent non-deterministic kiểu gì?"* → assert lên **trạng thái cuối** (workspace/DB),
  không assert lên chuỗi hành động; chạy N trial, báo cáo pass@k + variance.
- *"Khi nào cần multi-agent?"* → chỉ khi thật sự cần chuyên môn hóa và song song hóa được.
  Chi phí là coordination + mất context giữa agent + khó debug. Đừng đề xuất mặc định.
- *"Streaming?"* → stream token cho UX (TTFT), nhưng chỉ commit side-effect **sau khi**
  tool call được validate xong.

---

## Ôn nhanh 30 phút trước phỏng vấn

Chạy cả 5 file, đọc lại **đúng những dòng comment in đậm** này:

1. RRF fuse theo **rank**, không theo score → khỏi normalize hai thang điểm.
2. Vector search không có ngưỡng → luôn trả về gì đó → **hallucination**.
3. `budget = window − system − **output** − margin`.
4. **Retry ≠ repair.**
5. Thông báo lỗi là prompt: phải **nói cách sửa**.
6. Có ground truth kiểm được bằng code → **không dùng LLM judge**.
7. Multiset, không phải set — **mất DISTINCT là lỗi thật**.
8. Gold hỏng thì **raise**, đừng đổ lỗi cho agent.
9. Lỗi tool → **observation**, không phải exception.
10. Loop detection + budget = hai thứ cứu bạn khỏi hóa đơn 10.000 USD.

# Case: Agent tuân thủ kém trong batch production

> Ngày soạn: 2026-08-14 · Dạng: câu hỏi tình huống (situational), trả lời theo hướng consulting + STAR

---

## 1. Đề bài (tóm tắt từ interviewer)

Người dùng ghép một stack ba lớp vì Antigravity tuân thủ ngày càng kém:

- **Antigravity IDE** — nhập lệnh ngôn ngữ tự nhiên, chọn model, quyết định lệnh mới đè lệnh cũ hay chờ.
- **Hermes** — nhận lệnh đã chuyển hoá, kiểm soát tuân thủ, gọi nhiều sub-agent chạy song song / quản lý chéo.
- **Antigravity CLI** — bộ não thực thi của các sub-agent.

Ràng buộc: chỉ dùng gói **Google Ultra**, quyết không mua API key của model khác. Repo đã đóng gói, có cả MCP tool.

**Workload thực tế:** sản xuất hàng loạt — tóm tắt sách, biên soạn slide, làm audiobook. Chạy bằng Claude thì không đáng tiền nên chọn hướng trên.

**Vấn đề nêu ra:**
- Khả năng tuân thủ một workflow cũ bị giảm, không nhất quán.
- Tăng rule / guardrail lại làm giảm chất lượng do loãng ngữ cảnh.
- Chia nhỏ bước thì AI tự ý bỏ bước, báo cáo láo, token tăng do chuyển tiếp context liên tục.
- Nhiều việc trước đây chạy trong 1 call, giờ phải bọc trong harness của Hermes mới đảm bảo chất lượng.
- *"Rất nhiều harness đẻ ra để ứng phó với chất lượng của harness native model có vấn đề."*

---

## 2. Bản trả lời (đọc được, ~2 phút)

### [Chẩn đoán]

Em nghĩ đây không phải vấn đề model. Nó giống chuyện một repo chạy ngon ở dev nhưng lên prod thì fail — cùng một code, đổi môi trường là hỏng. Ở đây cũng vậy: cùng một prompt, đổi context là hỏng. Vấn đề nằm ở **control flow đặt sai chỗ**.

Workload của anh — tóm tắt sách, soạn slide, làm audiobook — là **batch production**: lặp lại, cùng shape output. Nhưng nó đang chạy trên một agent harness hội thoại, tức là để model tự tool call, tự gọi skill, tự quyết trình tự bước, và tự báo cáo là xong. Với batch, **agency là chi phí chứ không phải giá trị**. Và "agent bảo xong" không phải là bằng chứng đã xong.

Còn triệu chứng anh mô tả — harness đẻ ra harness — theo em là dấu hiệu của một chuyện khác: **không lớp nào gỡ ra được, vì chưa ai đo xem lớp đó có đóng góp gì**. Nên phản xạ tự nhiên là tăng rule, tăng guardrail, và chính nó làm loãng context.

### [Dẫn chứng — STAR]

Em từng suýt kết luận sai đúng kiểu này. Em xây một coding agent làm nhiệm vụ Data Engineer: kéo data từ API về DB, dựng pipeline, rồi phải trả lời đúng bộ câu hỏi phân tích business. Lần chạy đầu chỉ **9/28**. Nhìn con số đó thì rất dễ kết luận "model yếu".

Em không kết luận, mà đi tách biến môi trường trước. Hoá ra là **confound env** — agent chạy sai binary. Fix env, chạy lại **n=3 trial → 3/3 pass**, ra ETL pipeline hoàn chỉnh, có schedule, có báo cáo.

Bài học em rút ra và giờ dùng như nguyên tắc: **một artifact đơn lẻ bị nhiễu thì nó nói dối.** Chưa loại confound và chưa chạy đủ n thì chưa được phép kết luận về model.

### [Đề xuất]

Nên trước khi bàn model nào mới hơn, rẻ hơn — em sẽ hỏi anh một câu: mình đã có **bộ regression 30–50 item có gold, chạy lại mỗi tuần và mỗi lần đổi model** chưa?

Nếu chưa thì "tuân thủ ngày càng kém" vẫn là cảm nhận, chưa phải dữ liệu track được. Nhất là chạy qua subscription thì model **không được pin version** — nó đổi dưới chân mình lúc nào không biết, và mình không có cách nào chứng minh.

Cụ thể em sẽ làm ba việc, theo thứ tự:

1. **Dựng regression set + checkpoint từng step** — mỗi bước ghi artifact ra file, "xong" được định nghĩa là *file tồn tại + validator pass*, không phải agent tự khai. Có checkpoint mới biết sai ở bước nào mà debug, và mới resume được thay vì chạy lại cả workflow.
2. **Đẩy control flow về code** — loop, retry, thứ tự bước, fan-out là việc của job runner. Model chỉ nhận một step, một input, một schema output.
3. **Đo lại từng lớp harness** và gỡ lớp nào không tạo ra lift.

Và chỉ số em sẽ theo không phải cost per token — mà là **cost per accepted artifact**, tính cả rework.

---

## 3. Cách nói

- Dừng hẳn một nhịp ở mỗi đầu mục `[ ]`.
- Đọc chậm hai con số **9/28** và **3/3** — đó là chỗ đắt nhất.
- Câu cuối nói dứt khoát rồi im, đừng giải thích thêm.

---

## 4. Đạn dự phòng (nếu interviewer đào sâu)

### a) "Tăng rule lại giảm chất lượng" — chứng minh được bằng số

| | |
|---|---|
| **S** | Nghi ngờ việc thêm skill/guardrail đang làm loãng context. |
| **T** | Kiểm chứng bằng số thay vì cảm nhận. |
| **A** | A/B sạch, n=3 trial, chỉ đổi một biến (có skill / không skill). |
| **R** | Cả hai đều 3/3 pass, bản có skill tốn **578K vs 456K token**. Kết luận đúng: **không đủ bằng chứng để giữ, và task đó không có sức phân biệt** — chưa đủ để nói skill vô dụng. |

> ⚠️ **Ceiling effect — phải nói đúng chỗ này, interviewer sẽ bắt.**
> 3/3 vs 3/3 **không** chứng minh skill vô dụng. Nó chứng minh **task không đủ khó để phân biệt hai nhánh**. Baseline đã kịch trần thì không còn chỗ cho lift.
>
> Phát biểu chuẩn khi nói ra miệng:
> *"Cả hai đều 3/3 nên em không kết luận được là skill vô dụng — em kết luận được là **task đó không có sức phân biệt**. Muốn đo lift thì item phải nằm ở vùng nhạy, baseline khoảng 40–80%. Task nào baseline đã 100% thì mọi layer đều 'không lift'; task nào baseline 0% thì mọi layer đều fail. Kết luận đúng của em lúc đó là: chưa đủ bằng chứng để giữ, và cần một task khó hơn để quyết."*
>
> Bản này mạnh hơn bản cũ vì nó cho thấy mình biết **giới hạn của chính phép đo mình vừa chạy**.

→ Nguyên tắc: **mỗi guardrail phải trả bằng Δ pass rate; nếu không, nó chỉ là context bloat.** Đây chính là cách gỡ được vòng xoáy "harness đẻ ra harness" — nhưng chỉ đo được nếu regression set nằm ở vùng nhạy.

### b) "AI bỏ bước — thêm rule không sửa được"

| | |
|---|---|
| **S** | Model liên tục viết sai một cú pháp DSL, dù skill đã ghi đúng. |
| **T** | Tìm xem là thiếu kiến thức hay thiếu lực ràng buộc. |
| **A** | Soi reasoning trace, đếm tần suất pattern đúng/sai. |
| **R** | Pattern đúng xuất hiện **0 lần** → đây là *instruction-strength problem*, không phải knowledge problem. |

→ Prose không thắng được prior của model. Cái sửa được là **validator chạy trong loop** buộc nó fail và sửa lại.

### c) "Agent báo cáo láo" — bằng chứng cứng

| | |
|---|---|
| **S** | Eval harness cho coding agent trên stack analytics. |
| **T** | Xác minh một lần chạy mà agent tự báo "thất bại toàn tập". |
| **A** | Đối chiếu self-report với telemetry + filesystem thay vì tin agent. |
| **R** | Agent báo "0 tool call, project rỗng, đã ghi FAILURE.md" — thực tế **12 models, 30 tool calls**, file đó chưa từng tồn tại. |

→ Nguyên tắc kiến trúc: **grader deterministic + telemetry là source of truth; self-assessment thì không.**

### d) Kiến trúc đề xuất đầy đủ (nếu được hỏi "cụ thể anh sẽ dựng thế nào")

1. **Control plane bằng code.** Loop, retry, ordering, fan-out ở job runner. Model chỉ nhận 1 step / 1 input / 1 schema output.
2. **State là artifact trên disk, không phải context.** Đọc file → ghi file → checkpoint. Token giảm, và resume từ bước lỗi thay vì chạy lại cả workflow.
3. **Contract mỗi step.** Structured output + validator bằng code. Fail schema thì retry đúng step đó.
4. **Two-tier grading.** Deterministic chạy 100% item (coverage mục lục nguồn, số slide / word-per-slide, entity & số liệu khớp nguồn, SSML hợp lệ, duration); LLM judge chỉ **advisory trên sample 10–20%**, và **không được lật kết quả deterministic**.
5. **Recovery loop có taxonomy.** Lý do fail → nhãn lỗi → prompt vòng 2, **không bao giờ inject đáp án**, tối đa 2 vòng, đo bằng `pass@round2`.

### e) Về ràng buộc "chỉ dùng subscription, không mua API key"

- Token gần như "free" nhưng **quota/throughput mới là tài nguyên khan hiếm**. "Token tăng do chuyển tiếp context" thực chất là đốt quota → mất wall-clock throughput.
- Metric đúng: **cost per accepted artifact** (gồm rework) và **items/hour/seat** — không phải cost per token.
- Rủi ro thật: không pin được version, không SLA, không reproducibility. Đây là lời giải thích khả dĩ nhất cho "tuân thủ ngày càng kém" — và không có regression set thì không chứng minh được.

---

## 5. Đạn cấp 2 — 10 câu interviewer sẽ đào sâu

> Phản hồi thật của một interviewer sau khi nghe bản trả lời ở mục 2.
>
> **Đánh giá tốt ở:** không blame model ngay · nhận ra confounding variables · hiểu regression testing · hiểu deterministic acceptance · hiểu checkpoint/resume · đưa control flow về code · hiểu harness complexity · có production-oriented metric.
>
> **Nhận xét chốt:** *"Điểm mạnh nhất không phải 'biết AI agent', mà là tư duy: **Don't optimize the agent until you can measure the system.**"*
>
> Vế nên thêm để nó có tính hành động: *"— và phép đo đầu tiên phải là phép đo mà chính mình có thể sai trong đó."*

---

### 1. Làm sao chứng minh model vs harness?

**Replay từ trace trước, ablation sau.** Lấy đúng input cuối cùng mà harness gửi cho model (post-assembly prompt), gọi model trực tiếp ngoài harness, cùng params.

- Model trả **đúng** → harness dựng sai context/step.
- Model vẫn **sai** → mới là model.

Đây là phân biệt **input-assembly bug vs capability limit**, và phần lớn là cái đầu.

Cần chắc hơn thì leo **ablation ladder**: L0 model trần một call → L1 + schema/validator → L2 + orchestrator; cùng item, cùng *n*. **Pass rate tăng khi *bỏ* một layer** là bằng chứng cứng nhất.

### 2. Regression set thiết kế thế nào?

**Stratified theo failure mode, không random sample.** Lấy từ trace production thật, không tự bịa.

| Tầng | Tỉ lệ | Nội dung |
|---|---|---|
| Happy path | ~30% | Các ca phổ biến nhất |
| Failure mode đã gặp | ~50% | **Tối thiểu 3 item/mode** — 1 item không phân biệt được fix với may mắn |
| Edge / adversarial | ~20% | Sách quá dài, nhiều bảng, chương không heading, lẫn ngôn ngữ |

Mỗi item mang 3 thứ: **input đóng băng** (hash của source) · **gold hoặc anchor** (không nhất thiết full gold — "phải chứa 5 claim này", "không được chứa X" là đủ) · **lý do item tồn tại** (nó bắt lớp lỗi nào).

Versioned + frozen. Thêm item là bump version, không so điểm cross-version.

> **Quy tắc vàng:** mọi incident production thành 1 item ngay, kể cả trước khi sửa được.

### 3. Validator cho audiobook / slides là gì?

Ba tầng — mấu chốt là **tầng 1–2 bắt ~80% lỗi thật với chi phí gần 0**.

**Structural (deterministic, 100% item)**
- *Slide:* số slide trong khoảng · word-per-slide ≤ N · mọi slide có title · không còn placeholder (`[TODO]`, `{{`)
- *Audio:* SSML parse được · duration khớp ±X% với ước lượng từ char count · không silence > N giây · không markdown leak (`**`, `##`) lọt vào TTS
- *Tóm tắt:* compression ratio trong khoảng · mỗi chương nguồn có ≥1 câu tương ứng

**Fidelity (deterministic — chỗ hay bị bỏ sót)**
Trích mọi **số, ngày, tên riêng** trong output → phải tồn tại trong source. Sai một con số là fail cứng.
→ **Bắt được hallucination mà không cần LLM.**

**Semantic (LLM judge, advisory, sample 10–20%)**
Faithfulness, coherence, tone. Rubric tuyệt đối + anchor example + temp 0 + `rubric_version`. **Không được lật kết quả deterministic.**

### 4. Khi nào agent được phép tự quyết?

**Agency tỉ lệ thuận với khả năng verify.**

- **Cho** tự quyết khi: không gian hành động đóng · hành động reversible · **có oracle rẻ để kiểm**.
- **Không cho** khi: bước đó side-effecting (ghi ra ngoài, gửi, publish) hoặc không verify được.

Ranh giới thực dụng: **agency ở *trong* step, determinism ở *giữa* các step.** Model được tự do chọn cách viết một chương tóm tắt; nó không được tự quyết bỏ chương nào, thứ tự chương, hay khi nào thì xong.

> "Cho agent tự quyết ở chỗ mình có oracle. Chỗ nào không verify được thì đó là chỗ của code."

### 5. Làm sao đo một harness layer tạo lift?

Một biến duy nhất · cùng regression set · cùng model version · workspace sạch mỗi trial. Đo **ba trục**, không phải một: **Δ pass rate · Δ token/quota · Δ wall-time**.

Xác định **noise band** trước: chạy baseline *n* lần với chính nó — độ lệch đó là ngưỡng. Lift nhỏ hơn ngưỡng = không có lift.

**Và phải nói được ceiling effect** (xem cảnh báo ở mục 4a): item phải nằm ở **vùng nhạy, baseline ~40–80%**. Baseline 100% thì mọi layer đều "không lift"; baseline 0% thì mọi layer đều fail. Chọn sai vùng thì phép đo vô nghĩa dù chạy đúng quy trình.

### 6. Làm sao tránh guardrail làm giảm performance?

Ba cơ chế, theo thứ tự hiệu lực:

1. **Guardrail nằm ngoài context, không nằm trong prompt.** Rule nào code kiểm được thì để code kiểm; chỉ cái không kiểm được bằng code mới được chiếm token. Đây là cách gốc để không loãng.
2. **Feedback beats instruction.** Thay vì viết "đừng làm X", để nó làm rồi validator fail và trả lỗi cụ thể. Bằng chứng: pattern đúng xuất hiện **0 lần** dù skill viết đúng.
3. **Budget cứng cho instruction.** Mỗi rule thêm vào phải **đẩy một rule khác ra**, trừ khi chứng minh được lift. Không có budget thì prompt chỉ tăng một chiều.

Bổ sung: đo **adherence riêng cho từng rule**. Rule nào adherence thấp mà vẫn nằm đó chỉ đang tốn token.

### 7. Làm sao handle nondeterminism?

Không khử — **định lượng rồi thiết kế quanh nó.**

- Tách **ba nguồn variance**: LLM (n trial cùng input) · harness (thứ tự chạy, cache, state rò rỉ → workspace sạch mỗi trial) · infra (rate limit, timeout, OOM).
- Báo **pass@1 và pass@k riêng**, kèm khoảng tin cậy. Không bao giờ một con số trần trụi.
- Với batch production, chỉ số vận hành đúng là **pass@1 sau retry có bounded** — vì đó mới là cái khách nhận.
- Ở tầng sản phẩm: nondeterminism **chấp nhận được ở diễn đạt, không chấp nhận được ở cấu trúc và sự kiện**. Cấu trúc ép bằng schema, sự kiện ép bằng entity/number fidelity check, còn lại thả.
- `temp 0` giúp nhưng không đủ và không nên dựa vào.

### 8. Subscription không versioned thì control experiment thế nào?

Thừa nhận thẳng: **không thể có internal validity đầy đủ.** Bốn cách giảm thiểu:

1. **Canary drift** — chạy regression set theo lịch cố định mà **không đổi gì cả**; mọi biến động còn lại là drift của provider. Nó biến "model đổi dưới chân mình" từ vô hình thành một đường trên biểu đồ. Đây là cách duy nhất để "ngày càng kém" thành dữ liệu.
2. **Paired design** — không bao giờ so baseline tuần trước với treatment tuần này. Chạy A/B **xen kẽ trong cùng một cửa sổ thời gian ngắn**, cùng item, so theo cặp; drift ảnh hưởng cả hai như nhau nên bị triệt tiêu.
3. **Fingerprint cái quan sát được** — model string, timestamp, phân phối latency, token accounting. Latency/token nhảy đột ngột thường là dấu provider đã swap build dù tên không đổi.
4. **Công bố giới hạn** — kết quả đúng *tại thời điểm T, trên build không xác định*. Đủ cho quyết định nội bộ, không đủ cho claim đối ngoại.

> "Chi phí để pin version chính là chi phí mua khả năng kết luận. Nếu quyết định đủ quan trọng thì nó đáng tiền — còn nếu không đáng thì mình cũng phải chấp nhận là không kết luận được, chứ không giả vờ là có."

### 9. Khi nào single-agent vs multi-agent?

Mặc định **single-agent + code orchestration**; multi-agent phải tự justify.

**Đáng dùng khi:**
- **Context isolation** — sub-agent làm việc bẩn (đọc 200 trang) rồi chỉ trả về kết quả gọn, giữ context chính sạch. Lý do chính đáng nhất.
- **Đối kháng thật** — một agent viết, một agent phản biện; chỉ hợp lệ khi cái phản biện độc lập (khác prompt/model) và output của nó dùng để **chặn**, không phải để bàn.

**Không phải multi-agent:** "chạy 100 quyển sách song song" là **fan-out nhiều instance của cùng một agent** — đó là parallelism. Đừng nhầm hai cái.

> "Multi-agent giải quyết vấn đề **context** và **tính độc lập**. Nó không giải quyết vấn đề **tuân thủ**. Nếu mình đang dùng multi-agent để ép tuân thủ, thì đó chính là dấu hiệu control flow đang nằm sai chỗ."

*(Câu này nối thẳng về case gốc — orchestrator đang được dùng để ép compliance.)*

### 10. Cost per accepted artifact tính thế nào khi chất lượng chỉ human đánh giá được?

Ba tầng:

**a) Định nghĩa "accepted" bằng quy trình, không bằng metric.**
Accepted = qua deterministic gate **và** qua human review lần đầu mà **không cần sửa**. Cái đo được ngay là **rework rate**: % artifact bị trả về + số vòng trung bình. Không cần chấm điểm chất lượng — chỉ cần đếm việc người phải làm lại.

**b) Đo thời gian người, không chỉ tiền máy.**

```
cost = quota tiêu tốn
     + (phút review × chi phí người)
     + (phút sửa    × chi phí người)
```

Trong workload này chi phí người gần như chắc chắn **lớn hơn** chi phí model — nên **tối ưu token mà làm tăng review time là lỗ**. Đó chính là lý do "cost per token" là chỉ số sai.

**c) Human review là sampling *và* là nguồn nhãn.**
Gate deterministic 100% → human review sample + toàn bộ ca nằm ở **biên gate** → dùng nhãn đó để **calibrate LLM judge** (đo agreement với human). Khi judge đạt agreement đủ cao trên một lớp lỗi, judge được phép thay human ở lớp đó, vẫn audit định kỳ.

> "Human judgment không scale, nhưng human-labeled data thì scale. Nên việc của em là biến mỗi lần review thành một item trong regression set — mỗi giờ người bỏ ra sinh ra tài sản dùng lại được, thay vì tiêu hao một lần."

---

## 6. Ghi chú tự phê

Hai lỗi diễn đạt cần tránh:

- **Đừng nói** "model nhỏ hơn như gpt, llma" → nói **"model rẻ hơn / open-weight cho các bước cơ học"**. (GPT không phải "model nhỏ"; và viết đúng là *Llama*.)
- **Đừng dùng từ "hardness"** để chỉ guardrail. *Hardness* = độ khó của task. Muốn nói rule thì nói **rule / guardrail**.

Và: đừng dừng ở việc liệt kê nghi phạm (data / prompt / context / guardrail). Interviewer muốn thấy **cách mình tìm ra cái nào đúng**, không phải danh sách giả thuyết.

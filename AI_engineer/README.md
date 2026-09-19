# Bộ ôn phỏng vấn — Senior AI/LLM Engineer

Chuẩn bị riêng cho hồ sơ **Nguyen Ngoc Minh Thy** (AI Engineer / Data Engineer — production data platform, eval harness, agent system design), dựa trên CV 2026 và các dự án thật trong `~/Desktop/Fabrion`.

---

## Nội dung

| File | Nội dung | Dùng khi nào |
|---|---|---|
| [`01-mindmap-architecture.md`](01-mindmap-architecture.md) | 5 mind map kiến trúc: RAG · Agent/NL-to-SQL · Eval Harness · LLMOps · Document Intelligence | Vòng system design |
| [`02-theory-questions.md`](02-theory-questions.md) | 5 câu lý thuyết senior (+12 câu hỏi nhanh) | Vòng technical screen |
| [`03-scenario-questions.md`](03-scenario-questions.md) | 5 tình huống production (+6 câu behavioral có sẵn story từ CV) | Vòng hiring manager |
| [`04-coding-challenges.md`](04-coding-challenges.md) | 5 bài code + phân tích "interviewer chấm gì" | Vòng live coding |
| [`code/`](code/) | Lời giải **chạy được**, chỉ dùng stdlib, có self-test | Luyện tay |
| [`06-fabrion-portfolio-map.md`](06-fabrion-portfolio-map.md) | Bản đồ 4 mảng việc ở Fabrion + bản sửa của diagram Harness/Loop/Eval | Câu "kể tôi nghe bạn đã làm gì" |
| [`07-cdc-global-2026-08-25.md`](07-cdc-global-2026-08-25.md) | **12 câu thật CDC Global hỏi (25/08/2026)** + đáp án, follow-up, rút kinh nghiệm | Ôn lại vòng đã đi · chuẩn bị vòng sau |

Chạy toàn bộ lời giải:

```bash
cd ~/Desktop/Interview/code && for f in *.py; do python3 "$f"; done
```

Cả 5 file đều pass, không cần cài gì thêm (Python 3.10+).

---

## Định vị của bạn — nói câu này ở phút đầu tiên

> "Tôi là AI engineer làm ở phần **quyết định xem một AI agent có đáng tin không, trước khi
> có người dựa vào nó**. Tôi xây eval harness, scorer, và nền dữ liệu để chứng minh điều đó —
> trên chính nền tảng dữ liệu production mà tôi cũng là người xây."

Đây là điểm khác biệt thật của bạn. Rất nhiều ứng viên biết build RAG/agent; **rất ít người
biết chứng minh nó đúng**. Mọi câu trả lời nên kéo về trục này.

**Ba con số phải nhớ thuộc lòng:**
- Composite pass rate **0.14 → 0.93** qua **33** vòng diagnose → fix → re-test, trên benchmark **209** câu (BEAVER), với **7** scorer tự động.
- Harness coding agent: **5 task × 3 trial**, grader ẩn, có **null + cheater control** (cả hai phải 0/5), adapter chạy được **pi.dev và OpenAI Codex CLI** trên cùng bộ task.
- Sản phẩm analytics end-to-end tự làm một mình: Airbyte → **65** dbt models → **20+** Cube models → Taipy dashboard + chat agent, orchestrate bằng Dagster.

---

## Lộ trình ôn 7 ngày

| Ngày | Việc | Kết quả cần đạt |
|---|---|---|
| 1 | Đọc `01`, vẽ lại **MAP 1 (RAG)** và **MAP 3 (Eval)** từ trí nhớ | Vẽ được 2 map không nhìn tài liệu |
| 2 | Code bài 1 + bài 2 (không xem lời giải trước 30 phút) | Hiểu RRF, MMR, ngân sách token |
| 3 | Đọc `02` câu 1-3, tự nói to đáp án 30 giây, bấm giờ | Trả lời trôi, không đọc |
| 4 | Code bài 3 + bài 4 | Nói được "retry ≠ repair" và taxonomy lỗi SQL |
| 5 | Đọc `03`, viết **6 story STAR** ra giấy, mỗi story 1 con số | Kể được 90 giây/story |
| 6 | Code bài 5, vẽ lại **MAP 2 + MAP 4** | Liệt kê được đủ `stop_reason` |
| 7 | Mock interview: 1 system design (45') + 1 coding (45') + 3 behavioral | Ghi âm, nghe lại, cắt chỗ lan man |

---

## Ba khung trả lời dùng được cho mọi câu hỏi

**1. System design** — Clarify → **định nghĩa metric TRƯỚC kiến trúc** → happy path →
eval & observability → failure modes & guardrail → trade-off.
*Việc đề xuất metric trước khi vẽ kiến trúc là chữ ký riêng của bạn. Dùng nó.*

**2. Sự cố production** — Đo trước → khoanh vùng theo tầng → sửa nhỏ nhất →
**chặn tái diễn bằng regression gate** → ghi lại.

**3. Behavioral (STAR 90 giây)** — S 10s bối cảnh · T 10s trách nhiệm *của bạn* ·
A 50s quyết định + đánh đổi (nói "tôi", không nói "team") · R 20s **con số** + bài học.

---

## Câu hỏi bạn nên hỏi ngược lại nhà tuyển dụng

Hỏi được những câu này = bạn đang phỏng vấn họ, và nó thể hiện đúng chuyên môn của bạn:

1. "Hiện tại team quyết định một thay đổi về prompt hay model là *cải thiện* dựa vào cái gì?"
2. "Có golden set và regression gate trước khi ship không, hay eval chạy sau khi ship?"
3. "Ai được quyền nói 'không ship'? Grader hay con người?"
4. "Cost per request có được đo như một SLI không, hay chỉ nhìn ở hóa đơn cuối tháng?"
5. "Khi agent trả lời sai cho khách, mất bao lâu để dựng lại đúng cái nó đã thấy lúc đó?"

Nếu họ không trả lời được câu 1 và 2, đó chính là công việc của bạn ở đó — và bạn nên nói thẳng điều đó.

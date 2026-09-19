"""
CHALLENGE 3 — Production LLM client: structured output + retry + repair + circuit breaker.

Đề bài:
  Viết một hàm gọi LLM dùng được trong production:
    - Bắt buộc output đúng JSON schema (validate, không "tin" model)
    - Tự sửa (repair loop): trả lỗi validation NGƯỢC lại cho model để nó sửa
    - Retry lỗi tạm thời với exponential backoff + jitter; KHÔNG retry lỗi vĩnh viễn
    - Circuit breaker: ngừng đấm vào provider đang chết
    - Theo dõi token + cost cho mọi lần thử, kể cả lần thất bại

Vì sao đây là câu hay hỏi:
  Nó phân biệt "người từng gọi API LLM" với "người từng vận hành LLM trong production".
  Điểm mấu chốt: RETRY và REPAIR là hai thứ khác nhau.
    - Retry  = cùng request, lỗi ở hạ tầng (429/5xx/timeout) -> gửi lại y nguyên.
    - Repair = request mới, lỗi ở nội dung (JSON hỏng/sai schema) -> gửi lại KÈM lỗi.
  Gộp hai cái làm một là bug: retry một prompt sinh JSON hỏng thì nó lại hỏng lần nữa.

Chạy: python3 03_llm_client.py
"""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

# --------------------------------------------------------------------------------------
# Lỗi: phân loại retry được / không retry được
# --------------------------------------------------------------------------------------


class TransientError(Exception):
    """429, 5xx, timeout — retry được (gửi lại y nguyên)."""


class PermanentError(Exception):
    """401, 400 bad request, context too long — retry vô nghĩa, fail nhanh."""


class ValidationError(Exception):
    """Model trả về thứ không hợp lệ — sửa bằng REPAIR, không phải retry."""


class CircuitOpenError(Exception):
    """Provider đang được coi là chết; không gửi request nữa."""


# --------------------------------------------------------------------------------------
# Validator schema tối giản (production: dùng Pydantic)
# --------------------------------------------------------------------------------------

Schema = dict[str, Any]


def validate(obj: Any, schema: Schema, path: str = "$") -> list[str]:
    """Trả về danh sách lỗi dạng người-đọc-được. Rỗng = hợp lệ.

    Thông báo lỗi phải NÓI RÕ CÁCH SỬA, vì nó sẽ được đưa lại cho model.
    "invalid input" là thông báo vô dụng; "field 'sentiment' must be one of
    [positive, negative, neutral], got 'happy'" thì model sửa được ngay.
    """
    errs: list[str] = []
    expected = schema.get("type")
    py = {"object": dict, "array": list, "string": str, "number": (int, float), "boolean": bool}
    if expected and not isinstance(obj, py[expected]):
        return [f"{path}: expected {expected}, got {type(obj).__name__}"]

    if expected == "object":
        for key in schema.get("required", []):
            if key not in obj:
                errs.append(f"{path}.{key}: required field is missing")
        for key, sub in schema.get("properties", {}).items():
            if key in obj:
                errs += validate(obj[key], sub, f"{path}.{key}")
        if not schema.get("additionalProperties", True):
            for key in obj:
                if key not in schema.get("properties", {}):
                    errs.append(f"{path}.{key}: unexpected field, remove it")

    elif expected == "array":
        item_schema = schema.get("items")
        if len(obj) < schema.get("minItems", 0):
            errs.append(f"{path}: needs at least {schema['minItems']} items, got {len(obj)}")
        if item_schema:
            for i, item in enumerate(obj):
                errs += validate(item, item_schema, f"{path}[{i}]")

    if "enum" in schema and obj not in schema["enum"]:
        errs.append(f"{path}: must be one of {schema['enum']}, got {obj!r}")
    if "minimum" in schema and isinstance(obj, (int, float)) and obj < schema["minimum"]:
        errs.append(f"{path}: must be >= {schema['minimum']}, got {obj}")
    if "maximum" in schema and isinstance(obj, (int, float)) and obj > schema["maximum"]:
        errs.append(f"{path}: must be <= {schema['maximum']}, got {obj}")
    return errs


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> Any:
    """
    Model hay bọc JSON trong ```json ... ``` hoặc thêm lời dẫn "Here is the result:".
    Bóc theo thứ tự: code fence -> parse thẳng -> quét object cân bằng ngoặc đầu tiên.
    (Constrained decoding / JSON mode ở phía provider tốt hơn, nhưng vẫn phải có lớp này.)
    """
    if m := _FENCE.search(text):
        text = m.group(1)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start < 0:
        raise ValidationError("response chứa JSON object nào cả")
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(text[start:], start):
        if in_str:
            # Phải theo dõi trạng thái chuỗi, nếu không dấu } nằm trong string sẽ đóng sớm.
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError as e:
                    raise ValidationError(f"JSON không parse được: {e}") from e
    raise ValidationError("JSON object bị thiếu dấu đóng ngoặc")


# --------------------------------------------------------------------------------------
# Circuit breaker
# --------------------------------------------------------------------------------------


@dataclass
class CircuitBreaker:
    """
    CLOSED -> (n lỗi liên tiếp) -> OPEN -> (hết cooldown) -> HALF_OPEN
      HALF_OPEN: cho đúng 1 request thử; thành công -> CLOSED, thất bại -> OPEN lại.

    Vì sao cần: khi provider sập, retry của hàng nghìn request đồng thời sẽ kéo dài
    sự cố (retry storm) và đốt tiền vào các request chắc chắn fail. Breaker cho hệ
    thống fail NHANH và chuyển sang fallback.
    """

    threshold: int = 3
    cooldown_s: float = 30.0
    failures: int = 0
    opened_at: float | None = None
    clock: Callable[[], float] = time.monotonic

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "CLOSED"
        return "HALF_OPEN" if self.clock() - self.opened_at >= self.cooldown_s else "OPEN"

    def before_call(self) -> None:
        if self.state == "OPEN":
            raise CircuitOpenError(f"circuit OPEN, thử lại sau {self.cooldown_s}s")

    def on_success(self) -> None:
        self.failures, self.opened_at = 0, None

    def on_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = self.clock()


# --------------------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------------------


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    retries: int = 0
    repairs: int = 0

    def cost(self, in_rate: float, out_rate: float) -> float:
        """rate = USD / 1M token."""
        return (self.input_tokens * in_rate + self.output_tokens * out_rate) / 1_000_000


@dataclass
class LLMClient:
    call_model: Callable[[str], tuple[str, int, int]]  # prompt -> (text, in_tok, out_tok)
    breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    max_retries: int = 3
    max_repairs: int = 2
    base_delay: float = 0.5
    max_delay: float = 8.0
    sleep: Callable[[float], None] = time.sleep
    rng: random.Random = field(default_factory=lambda: random.Random(0))
    usage: Usage = field(default_factory=Usage)

    def _backoff(self, attempt: int) -> float:
        """
        Exponential + full jitter. Jitter là bắt buộc, không phải làm màu:
        không có nó, mọi client bị 429 cùng lúc sẽ retry cùng lúc -> lại 429 (thundering herd).
        """
        return self.rng.uniform(0, min(self.base_delay * 2**attempt, self.max_delay))

    def _call_with_retry(self, prompt: str) -> str:
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self.breaker.before_call()
            try:
                text, in_tok, out_tok = self.call_model(prompt)
            except PermanentError:
                self.breaker.on_failure()
                raise  # fail nhanh: retry không bao giờ cứu được 401/400
            except TransientError as e:
                last = e
                self.breaker.on_failure()
                self.usage.calls += 1
                if attempt < self.max_retries:
                    self.usage.retries += 1
                    self.sleep(self._backoff(attempt))
                    continue
                raise
            self.breaker.on_success()
            self.usage.calls += 1
            self.usage.input_tokens += in_tok
            self.usage.output_tokens += out_tok
            return text
        raise last  # type: ignore[misc]

    def structured(self, prompt: str, schema: Schema) -> Any:
        """
        Vòng lặp REPAIR: mỗi lần output không hợp lệ, gửi lại kèm chính thông báo lỗi.
        Thực nghiệm cho thấy đưa lỗi cụ thể vào lại thường sửa được ngay lần đầu — nhưng
        phải có TRẦN (max_repairs), nếu không một prompt tồi sẽ đốt tiền vô hạn.
        """
        current = prompt
        errors: list[str] = []
        for repair in range(self.max_repairs + 1):
            raw = self._call_with_retry(current)
            try:
                obj = extract_json(raw)
                errors = validate(obj, schema)
                if not errors:
                    return obj
            except ValidationError as e:
                errors = [str(e)]
            if repair < self.max_repairs:
                self.usage.repairs += 1
                current = (
                    f"{prompt}\n\n"
                    f"Lần trước bạn trả về:\n{raw}\n\n"
                    f"Nó KHÔNG hợp lệ:\n- " + "\n- ".join(errors) + "\n\n"
                    "Trả về DUY NHẤT một JSON object hợp lệ đã sửa. Không giải thích, không code fence."
                )
        raise ValidationError(f"vẫn không hợp lệ sau {self.max_repairs} lần repair: {errors}")


# --------------------------------------------------------------------------------------
# Self-test — mock LLM có kịch bản, deterministic
# --------------------------------------------------------------------------------------

SCHEMA: Schema = {
    "type": "object",
    "required": ["sentiment", "confidence", "topics"],
    "additionalProperties": False,
    "properties": {
        "sentiment": {"type": "string", "enum": ["positive", "negative", "neutral"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "topics": {"type": "array", "minItems": 1, "items": {"type": "string"}},
    },
}


def scripted(responses: list[Any]) -> Callable[[str], tuple[str, int, int]]:
    it = iter(responses)

    def _call(prompt: str) -> tuple[str, int, int]:
        r = next(it)
        if isinstance(r, Exception):
            raise r
        return r, len(prompt) // 4, len(r) // 4

    return _call


def _tests() -> None:
    noop = lambda _s: None  # noqa: E731  — không sleep thật khi test

    # (a) Bóc được JSON qua code fence và lời dẫn thừa.
    assert extract_json('Here you go:\n```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('{"a": {"b": "}"}} trailing junk') == {"a": {"b": "}"}}

    # (b) Validator nói rõ cách sửa.
    errs = validate({"sentiment": "happy", "confidence": 1.7}, SCHEMA)
    assert any("must be one of" in e for e in errs)
    assert any("must be <= 1" in e for e in errs)
    assert any("topics: required field is missing" in e for e in errs)

    # (c) Retry lỗi tạm thời rồi thành công; đếm đúng số lần retry.
    c = LLMClient(
        call_model=scripted([
            TransientError("429"),
            TransientError("503"),
            '{"sentiment":"positive","confidence":0.9,"topics":["delivery"]}',
        ]),
        sleep=noop,
    )
    assert c.structured("phân loại review", SCHEMA)["sentiment"] == "positive"
    assert c.usage.retries == 2 and c.usage.repairs == 0

    # (d) Lỗi vĩnh viễn KHÔNG được retry.
    c2 = LLMClient(call_model=scripted([PermanentError("401 unauthorized")]), sleep=noop)
    try:
        c2.structured("x", SCHEMA)
        raise AssertionError("phải ném PermanentError")
    except PermanentError:
        pass
    assert c2.usage.retries == 0, "không được retry lỗi vĩnh viễn"

    # (e) Repair loop: JSON hỏng -> sai schema -> hợp lệ.
    c3 = LLMClient(
        call_model=scripted([
            "Sure! {sentiment: positive,,}",                                     # JSON hỏng
            '{"sentiment":"happy","confidence":0.5,"topics":[]}',                # sai enum + mảng rỗng
            '```json\n{"sentiment":"neutral","confidence":0.5,"topics":["ux"]}\n```',
        ]),
        sleep=noop,
    )
    out = c3.structured("phân loại", SCHEMA)
    assert out == {"sentiment": "neutral", "confidence": 0.5, "topics": ["ux"]}
    assert c3.usage.repairs == 2 and c3.usage.retries == 0

    # (f) Hết lượt repair -> ném lỗi rõ ràng thay vì trả rác cho tầng trên.
    c4 = LLMClient(call_model=scripted(["nope"] * 5), sleep=noop, max_repairs=1)
    try:
        c4.structured("x", SCHEMA)
        raise AssertionError("phải ném ValidationError")
    except ValidationError as e:
        assert "repair" in str(e)

    # (g) Circuit breaker mở sau 3 lỗi liên tiếp, half-open sau cooldown.
    now = [0.0]
    br = CircuitBreaker(threshold=3, cooldown_s=30, clock=lambda: now[0])
    c5 = LLMClient(call_model=scripted([TransientError("503")] * 9), breaker=br, sleep=noop)
    try:
        c5.structured("x", SCHEMA)
    except (TransientError, CircuitOpenError):
        pass
    assert br.state == "OPEN"
    try:
        c5.structured("x", SCHEMA)
        raise AssertionError("circuit đang OPEN thì phải chặn ngay")
    except CircuitOpenError:
        pass
    now[0] = 31.0
    assert br.state == "HALF_OPEN"

    # (h) Backoff có jitter và bị chặn trần.
    c6 = LLMClient(call_model=scripted([]), max_delay=8.0)
    delays = [c6._backoff(i) for i in range(8)]
    assert all(0 <= d <= 8.0 for d in delays)
    assert len(set(delays)) > 1, "phải có jitter, không được là hằng số"

    print("PASS 03_llm_client")
    print(f"  case (c) usage: {c.usage}  cost=${c.usage.cost(0.25, 1.25):.6f}")
    print(f"  case (e) repairs={c3.usage.repairs}, calls={c3.usage.calls}")
    print(f"  breaker state sau cooldown: {br.state}")


if __name__ == "__main__":
    _tests()

"""
CHALLENGE 5 — Agent loop có kiểm soát: tool registry, budget, timeout, loop detection, trace.

Đề bài:
  Viết vòng lặp agent dùng được trong production. Phải có:
    - Tool registry: schema args + validate TRƯỚC khi chạy tool
    - Gọi song song các tool độc lập trong cùng một turn
    - Timeout cho từng tool (một tool treo không được treo cả agent)
    - Lỗi tool trả về dạng OBSERVATION có hướng dẫn sửa (không ném exception ra ngoài)
    - Điều kiện dừng: max_turns, budget USD, và LOOP DETECTION (lặp lại y hệt lời gọi)
    - Trace đầy đủ mỗi turn: tool, args, latency, token, cost
    - Grounding check: câu trả lời cuối phải trích dẫn tool result có thật

Vì sao đây là câu hay hỏi:
  Làm agent CHẠY thì dễ. Làm nó DỪNG ĐÚNG LÚC và SAI MỘT CÁCH AN TOÀN mới là việc của
  senior. Failure mode phổ biến nhất ở production không phải trả lời sai — mà là vòng
  lặp vô hạn đốt tiền.

Chạy: python3 05_agent_loop.py
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

# --------------------------------------------------------------------------------------
# Tool registry
# --------------------------------------------------------------------------------------


@dataclass
class Tool:
    name: str
    description: str          # ĐÂY LÀ PROMPT. Sai tool thường là lỗi mô tả, không phải lỗi model.
    schema: dict[str, Any]    # {"param": {"type": "string", "enum": [...], "required": True}}
    fn: Callable[..., Awaitable[Any]]
    timeout_s: float = 5.0
    mutating: bool = False    # tool có side-effect -> cần xác nhận của người

    def validate(self, args: dict) -> list[str]:
        errs = []
        py = {"string": str, "number": (int, float), "boolean": bool, "array": list}
        for key, spec in self.schema.items():
            if spec.get("required") and key not in args:
                errs.append(f"thiếu tham số bắt buộc '{key}' ({spec.get('type')})")
        for key, val in args.items():
            if key not in self.schema:
                errs.append(f"tham số '{key}' không tồn tại; các tham số hợp lệ: {list(self.schema)}")
                continue
            spec = self.schema[key]
            if "type" in spec and not isinstance(val, py[spec["type"]]):
                errs.append(f"'{key}' phải là {spec['type']}, nhận được {type(val).__name__}")
            if "enum" in spec and val not in spec["enum"]:
                errs.append(f"'{key}' phải thuộc {spec['enum']}, nhận được {val!r}")
        return errs


class ToolRegistry(dict):
    def register(self, tool: Tool) -> None:
        self[tool.name] = tool

    def spec_for_prompt(self) -> str:
        return json.dumps(
            [{"name": t.name, "description": t.description, "params": t.schema} for t in self.values()],
            ensure_ascii=False,
        )


# --------------------------------------------------------------------------------------
# Trace
# --------------------------------------------------------------------------------------


@dataclass
class ToolEvent:
    turn: int
    tool: str
    args: dict
    ok: bool
    latency_ms: float
    result: Any = None
    error: str = ""


@dataclass
class Trace:
    events: list[ToolEvent] = field(default_factory=list)
    turns: int = 0
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ""

    def call_signature(self, tool: str, args: dict) -> str:
        return f"{tool}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"


class AgentError(Exception):
    pass


# --------------------------------------------------------------------------------------
# Agent
# --------------------------------------------------------------------------------------


@dataclass
class Agent:
    """
    LLM ở đây là một callable: (prompt, observations) -> quyết định
      {"tool_calls": [{"name":..., "args": {...}}, ...]}  hoặc  {"final": "...", "cites": [ids]}
    Đổi nó thành lời gọi API thật là xong; toàn bộ phần kiểm soát bên dưới không đổi.
    """

    registry: ToolRegistry
    decide: Callable[[str, list[dict]], Awaitable[tuple[dict, int, int]]]
    max_turns: int = 6
    budget_usd: float = 0.10
    in_rate: float = 0.25   # USD / 1M token
    out_rate: float = 1.25
    max_repeat: int = 2     # cùng một (tool,args) được phép lặp mấy lần trước khi coi là kẹt
    require_approval: Callable[[str, dict], bool] | None = None

    async def _run_tool(self, turn: int, name: str, args: dict) -> ToolEvent:
        """
        Mọi lỗi tool đều trở thành OBSERVATION, không ném ra ngoài — agent chỉ phục hồi
        được nếu nó ĐỌC được lỗi. Và thông báo lỗi phải nói cách sửa.
        """
        t0 = time.perf_counter()
        ms = lambda: (time.perf_counter() - t0) * 1000  # noqa: E731

        tool = self.registry.get(name)
        if tool is None:
            return ToolEvent(turn, name, args, False, ms(),
                             error=f"tool '{name}' không tồn tại. Các tool có sẵn: {list(self.registry)}")
        if errs := tool.validate(args):
            return ToolEvent(turn, name, args, False, ms(), error="tham số không hợp lệ: " + "; ".join(errs))
        if tool.mutating and self.require_approval and not self.require_approval(name, args):
            return ToolEvent(turn, name, args, False, ms(), error="thao tác ghi bị từ chối bởi người duyệt")
        try:
            result = await asyncio.wait_for(tool.fn(**args), timeout=tool.timeout_s)
            return ToolEvent(turn, name, args, True, ms(), result=result)
        except asyncio.TimeoutError:
            return ToolEvent(turn, name, args, False, ms(),
                             error=f"tool quá {tool.timeout_s}s không trả về; thử thu hẹp phạm vi truy vấn")
        except Exception as e:  # tool nghiệp vụ lỗi -> vẫn là observation
            return ToolEvent(turn, name, args, False, ms(), error=f"{type(e).__name__}: {e}")

    async def run(self, task: str) -> tuple[str, Trace]:
        trace = Trace()
        observations: list[dict] = []
        seen: dict[str, int] = {}

        for turn in range(1, self.max_turns + 1):
            trace.turns = turn

            # --- Điều kiện dừng do ngân sách: kiểm TRƯỚC khi gọi, không phải sau ---
            if trace.cost_usd >= self.budget_usd:
                trace.stop_reason = "BUDGET_EXCEEDED"
                return "Đã dừng: vượt ngân sách trước khi hoàn thành nhiệm vụ.", trace

            prompt = f"TASK: {task}\nTOOLS: {self.registry.spec_for_prompt()}"
            decision, in_tok, out_tok = await self.decide(prompt, observations)
            trace.input_tokens += in_tok
            trace.output_tokens += out_tok
            trace.cost_usd += (in_tok * self.in_rate + out_tok * self.out_rate) / 1_000_000

            # --- Agent kết thúc: kiểm grounding trước khi trả về người dùng ---
            if "final" in decision:
                valid_ids = {i for i, e in enumerate(trace.events) if e.ok}
                cites = set(decision.get("cites", []))
                if cites - valid_ids:
                    trace.stop_reason = "UNGROUNDED"
                    return "Không đủ căn cứ để trả lời.", trace
                trace.stop_reason = "COMPLETED"
                return decision["final"], trace

            calls = decision.get("tool_calls", [])
            if not calls:
                trace.stop_reason = "NO_ACTION"
                return "Agent không đề xuất hành động nào.", trace

            # --- Loop detection: cùng tool + cùng args lặp lại = không có tiến triển ---
            for c in calls:
                sig = trace.call_signature(c["name"], c.get("args", {}))
                seen[sig] = seen.get(sig, 0) + 1
                if seen[sig] > self.max_repeat:
                    trace.stop_reason = "LOOP_DETECTED"
                    return f"Đã dừng: lặp lại lời gọi '{c['name']}' không tiến triển.", trace

            # --- Chạy SONG SONG các tool trong cùng một turn ---
            events = await asyncio.gather(
                *(self._run_tool(turn, c["name"], c.get("args", {})) for c in calls)
            )
            base = len(trace.events)
            trace.events.extend(events)
            observations = [
                {
                    "id": base + i,
                    "tool": e.tool,
                    "ok": e.ok,
                    "result" if e.ok else "error": e.result if e.ok else e.error,
                }
                for i, e in enumerate(events)
            ]

        trace.stop_reason = "MAX_TURNS"
        return "Đã dừng: hết số lượt cho phép mà chưa hoàn thành.", trace


# --------------------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------------------

_concurrency = {"now": 0, "max": 0}


async def search_docs(query: str, top_k: float = 3) -> list[str]:
    _concurrency["now"] += 1
    _concurrency["max"] = max(_concurrency["max"], _concurrency["now"])
    await asyncio.sleep(0.05)
    _concurrency["now"] -= 1
    return [f"doc về {query} #{i}" for i in range(int(top_k))]


async def get_metric(metric: str, period: str) -> dict:
    _concurrency["now"] += 1
    _concurrency["max"] = max(_concurrency["max"], _concurrency["now"])
    await asyncio.sleep(0.05)
    _concurrency["now"] -= 1
    return {"metric": metric, "period": period, "value": 42}


async def hangs() -> None:
    await asyncio.sleep(10)


async def boom() -> None:
    raise ValueError("cột 'revenu' không tồn tại; các cột hợp lệ: revenue, cost")


def build_registry() -> ToolRegistry:
    r = ToolRegistry()
    r.register(Tool("search_docs", "Tìm tài liệu nội bộ theo truy vấn ngôn ngữ tự nhiên.",
                    {"query": {"type": "string", "required": True}, "top_k": {"type": "number"}},
                    search_docs))
    r.register(Tool("get_metric", "Lấy giá trị một chỉ số kinh doanh cho một kỳ.",
                    {"metric": {"type": "string", "required": True},
                     "period": {"type": "string", "required": True,
                                "enum": ["daily", "weekly", "monthly"]}},
                    get_metric))
    r.register(Tool("slow_tool", "Tool chậm để test timeout.", {}, hangs, timeout_s=0.1))
    r.register(Tool("bad_tool", "Tool luôn lỗi.", {}, boom))
    return r


def scripted_llm(script: list[dict]):
    """LLM giả lập, deterministic. Ghi lại observations để test có thể kiểm."""
    seen_obs: list[list[dict]] = []
    it = iter(script)

    async def _decide(prompt: str, observations: list[dict]):
        seen_obs.append(observations)
        try:
            return next(it), 500, 60
        except StopIteration:
            return {"final": "hết kịch bản", "cites": []}, 500, 60

    _decide.seen = seen_obs  # type: ignore[attr-defined]
    return _decide


def _tests() -> None:
    async def main() -> None:
        reg = build_registry()

        # (a) Happy path + (b) hai tool độc lập chạy SONG SONG trong cùng một turn.
        _concurrency["max"] = 0
        llm = scripted_llm([
            {"tool_calls": [
                {"name": "search_docs", "args": {"query": "chính sách hoàn tiền"}},
                {"name": "get_metric", "args": {"metric": "refund_rate", "period": "monthly"}},
            ]},
            {"final": "Tỉ lệ hoàn tiền tháng là 42 [1], theo chính sách 30 ngày [0].", "cites": [0, 1]},
        ])
        t0 = time.perf_counter()
        answer, tr = await Agent(reg, llm).run("báo cáo hoàn tiền")
        elapsed = time.perf_counter() - t0
        assert tr.stop_reason == "COMPLETED" and "42" in answer
        assert _concurrency["max"] == 2, "hai tool độc lập phải chạy song song"
        assert elapsed < 0.09, f"chạy tuần tự mất ~0.1s, song song ~0.05s (đo được {elapsed:.3f}s)"
        assert tr.cost_usd > 0 and len(tr.events) == 2

        # (c) Args sai -> observation có hướng dẫn -> agent tự sửa ở turn sau.
        llm = scripted_llm([
            {"tool_calls": [{"name": "get_metric", "args": {"metric": "revenue", "period": "yearly"}}]},
            {"tool_calls": [{"name": "get_metric", "args": {"metric": "revenue", "period": "monthly"}}]},
            {"final": "Doanh thu tháng: 42 [1]", "cites": [1]},
        ])
        answer, tr = await Agent(reg, llm).run("doanh thu")
        assert tr.stop_reason == "COMPLETED"
        assert not tr.events[0].ok and "enum" not in tr.events[0].error
        assert "daily" in tr.events[0].error, "lỗi phải liệt kê giá trị hợp lệ để agent sửa được"
        assert llm.seen[1][0]["error"], "lỗi phải được đưa lại vào context của turn sau"

        # (d) Tool không tồn tại -> observation, không crash.
        llm = scripted_llm([{"tool_calls": [{"name": "run_sql", "args": {}}]},
                            {"final": "xong", "cites": []}])
        _, tr = await Agent(reg, llm).run("x")
        assert "không tồn tại" in tr.events[0].error and "search_docs" in tr.events[0].error

        # (e) Timeout: một tool treo không được treo cả agent.
        llm = scripted_llm([{"tool_calls": [{"name": "slow_tool", "args": {}}]},
                            {"final": "xong", "cites": []}])
        t0 = time.perf_counter()
        _, tr = await Agent(reg, llm).run("x")
        assert time.perf_counter() - t0 < 1.0 and "quá 0.1s" in tr.events[0].error

        # (f) Tool ném exception -> vẫn là observation, kèm gợi ý sửa.
        llm = scripted_llm([{"tool_calls": [{"name": "bad_tool", "args": {}}]},
                            {"final": "xong", "cites": []}])
        _, tr = await Agent(reg, llm).run("x")
        assert not tr.events[0].ok and "revenue" in tr.events[0].error

        # (g) LOOP DETECTION — failure mode đắt tiền nhất ở production.
        same = {"tool_calls": [{"name": "search_docs", "args": {"query": "a"}}]}
        _, tr = await Agent(reg, scripted_llm([same] * 10)).run("x")
        assert tr.stop_reason == "LOOP_DETECTED" and tr.turns <= 4

        # (h) Budget: dừng khi hết tiền, không chạy tiếp.
        varied = [{"tool_calls": [{"name": "search_docs", "args": {"query": f"q{i}"}}]} for i in range(20)]
        _, tr = await Agent(reg, scripted_llm(varied), max_turns=50, budget_usd=0.0005).run("x")
        assert tr.stop_reason == "BUDGET_EXCEEDED" and tr.cost_usd >= 0.0005

        # (i) Max turns.
        varied = [{"tool_calls": [{"name": "search_docs", "args": {"query": f"z{i}"}}]} for i in range(20)]
        _, tr = await Agent(reg, scripted_llm(varied), max_turns=3, budget_usd=99).run("x")
        assert tr.stop_reason == "MAX_TURNS" and tr.turns == 3

        # (j) Grounding: trích dẫn tool result không tồn tại -> từ chối, không trả lời bịa.
        llm = scripted_llm([{"final": "Doanh thu là 1 tỷ [7]", "cites": [7]}])
        answer, tr = await Agent(reg, llm).run("x")
        assert tr.stop_reason == "UNGROUNDED" and "Không đủ căn cứ" in answer

        # (k) Tool có side-effect cần người duyệt.
        reg2 = build_registry()
        reg2.register(Tool("send_email", "Gửi email cho khách.", {}, boom, mutating=True))
        llm = scripted_llm([{"tool_calls": [{"name": "send_email", "args": {}}]},
                            {"final": "xong", "cites": []}])
        _, tr = await Agent(reg2, llm, require_approval=lambda n, a: False).run("x")
        assert "từ chối bởi người duyệt" in tr.events[0].error

        print("PASS 05_agent_loop")
        print(f"  song song: max concurrency = {_concurrency['max']}, turn 1 mất {elapsed*1000:.0f}ms")
     #   print("  các stop_reason đã kiểm: COMPLETED, LOOP_DETECTED, BUDGET_EXCEEDED, MAX_TURNS, UNGROUNDED")

    asyncio.run(main())


if __name__ == "__main__":
    _tests()

"""LLM agent orchestration with an optional LangGraph runtime.

When an LLM API key is configured, the agent runs a tool-calling loop:
``assistant -> tools -> assistant -> ...`` and stops when the model produces a
final answer. When LangGraph is installed, the same loop is expressed as a
StateGraph so runs are inspectable and easy to extend (retries, approvals).

Without a key (or without network), ``AgentService`` falls back to the
deterministic ``RuleRouter`` so the product is always usable.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable

import httpx

from ai.agents.tools import (
    SYSTEM_PROMPT,
    AgentAnswer,
    ToolCall,
    tool_specs,
)

ToolExecutor = Callable[[str, dict[str, Any]], ToolCall]
MAX_STEPS = 6


def _assistant_message(response: dict) -> dict:
    return response["choices"][0]["message"]


class LLMAgent:
    model = "llm"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        execute: ToolExecutor,
        use_langgraph: bool = True,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_name = model
        self.execute = execute
        self.use_langgraph = use_langgraph and self._langgraph_available()
        self.tools = tool_specs()

    @staticmethod
    def _langgraph_available() -> bool:
        try:
            import langgraph  # noqa: F401

            return True
        except ImportError:
            return False

    def _request(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.2,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
            timeout=45,
        )
        response.raise_for_status()
        return response.json()

    def run(self, question: str) -> AgentAnswer:
        started = time.perf_counter()
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
        calls: list[ToolCall] = []
        try:
            if self.use_langgraph:
                answer = self._run_langgraph(messages, calls)
            else:
                answer = self._run_loop(messages, calls)
        except Exception as exc:  # network / provider errors are not fatal
            return AgentAnswer(
                answer=(
                    "Không kết nối được dịch vụ LLM, mình đã chuyển sang chế độ trả lời nội bộ.\n\n"
                    f"Lỗi: {type(exc).__name__}"
                ),
                tool_calls=calls,
                status="error",
                model=self.model,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        return AgentAnswer(
            answer=answer,
            tool_calls=calls,
            status="completed",
            model=f"llm:{self.model_name}",
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    def _run_loop(self, messages: list[dict], calls: list[ToolCall]) -> str:
        for _ in range(MAX_STEPS):
            message = _assistant_message(self._request(messages, self.tools))
            messages.append(message)
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                return message.get("content") or "Mình chưa có câu trả lời phù hợp."
            for tool_call in tool_calls:
                self._execute_tool_call(tool_call, messages, calls)
        return "Mình đã thử nhiều bước nhưng chưa hoàn tất. Bạn vui lòng hỏi cụ thể hơn."

    def _run_langgraph(self, messages: list[dict], calls: list[ToolCall]) -> str:  # pragma: no cover
        from langgraph.graph import END, START, StateGraph

        def assistant(state: dict) -> dict:
            message = _assistant_message(self._request(state["messages"], self.tools))
            return {"messages": [*state["messages"], message]}

        def tools(state: dict) -> dict:
            last = state["messages"][-1]
            messages = list(state["messages"])
            for tool_call in last.get("tool_calls") or []:
                self._execute_tool_call(tool_call, messages, calls)
            return {"messages": messages[1:], "steps": state.get("steps", 0) + 1}

        def route(state: dict) -> str:
            last = state["messages"][-1]
            if last.get("tool_calls") and state.get("steps", 0) < MAX_STEPS:
                return "tools"
            return END

        graph = StateGraph(dict)
        graph.add_node("assistant", assistant)
        graph.add_node("tools", tools)
        graph.add_edge(START, "assistant")
        graph.add_conditional_edges("assistant", route, {"tools": "tools", END: END})
        graph.add_edge("tools", "assistant")
        compiled = graph.compile()
        # langgraph prepends the initial messages we pass in state
        state = compiled.invoke({"messages": messages, "steps": 0})
        last = state["messages"][-1]
        return last.get("content") or "Mình chưa có câu trả lời phù hợp."

    def _execute_tool_call(
        self, tool_call: dict, messages: list[dict], calls: list[ToolCall]
    ) -> None:
        function = tool_call.get("function", {})
        name = function.get("name", "")
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except json.JSONDecodeError:
            arguments = {}
        record = self.execute(name, arguments)
        calls.append(record)
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.get("id", ""),
                "content": json.dumps(
                    {"summary": record.result_summary, "data": record.data},
                    ensure_ascii=False,
                    default=str,
                ),
            }
        )

"""Deterministic, LLM-free intent router.

This is the safety net for demos and for deployments without an LLM key. It
maps a Vietnamese/English question to a small number of allow-listed tool calls
and composes the answer from tool output. The LLM path in ``graph.py`` reuses
the exact same tools and executor, so behaviour stays consistent.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from ai.agents.tools import AgentAnswer, ToolCall

ToolExecutor = Callable[[str, dict[str, Any]], ToolCall]

_SKU_PATTERN = re.compile(r"\b([A-Za-z]{2,6}[-_]?\d{2,6})\b")


def _extract_sku(question: str) -> str | None:
    match = _SKU_PATTERN.search(question)
    return match.group(1).upper() if match else None


def _extract_days(question: str) -> int:
    match = re.search(r"(\d{1,3})\s*(ngày|days?)", question, re.IGNORECASE)
    if match:
        days = int(match.group(1))
        if 1 <= days <= 365:
            return days
    lowered = question.lower()
    if "tuần" in lowered or "week" in lowered:
        return 7
    if "tháng" in lowered or "month" in lowered:
        return 30
    return 30


def _extract_horizon(question: str) -> int:
    for horizon in (7, 14, 30):
        if str(horizon) in question:
            return horizon
    lowered = question.lower()
    if "tuần" in lowered or "week" in lowered:
        return 14
    return 30


class RuleRouter:
    model = "rule_router"

    def run(self, question: str, execute: ToolExecutor) -> AgentAnswer:
        text = question.lower()
        calls: list[ToolCall] = []
        sku = _extract_sku(question)

        wants_write = any(
            keyword in text
            for keyword in ("tạo đơn", "đặt hàng", "nhập hàng", "lên đơn", "order", "purchase")
        )
        if wants_write:
            return self._create_draft(question, sku, execute, calls)

        if any(keyword in text for keyword in ("cảnh báo", "alert", "rủi ro", "bất thường")):
            calls.append(execute("get_alerts", {"limit": 8}))
        elif any(keyword in text for keyword in ("dự báo", "forecast", "nhu cầu", "sắp tới")):
            if sku:
                calls.append(
                    execute("forecast_demand", {"query": sku, "horizon_days": _extract_horizon(question)})
                )
            else:
                calls.append(execute("get_dashboard_overview", {}))
                calls.append(execute("recommend_replenishment", {"limit": 5}))
        elif any(keyword in text for keyword in ("nên nhập", "đề xuất", "replenish", "recommend")):
            calls.append(
                execute(
                    "recommend_replenishment",
                    {"query": sku or "", "limit": 10},
                )
            )
        elif any(keyword in text for keyword in ("doanh thu", "doanh số", "bán", "sales", "revenue")):
            calls.append(execute("get_sales_summary", {"days": _extract_days(question)}))
        elif any(
            keyword in text
            for keyword in ("tồn kho", "còn bao nhiêu", "hết hàng", "sắp hết", "inventory", "stock")
        ):
            calls.append(
                execute(
                    "get_inventory_status",
                    {"query": sku or "", "low_only": "hết hàng" in text or "sắp hết" in text},
                )
            )
        else:
            calls.append(execute("get_dashboard_overview", {}))

        ok_calls = [call for call in calls if call.ok]
        answer = "\n\n".join(call.result_summary for call in ok_calls if call.result_summary)
        if not answer:
            answer = "Mình chưa lấy được dữ liệu phù hợp. Bạn thử hỏi cụ thể hơn, ví dụ: “SKU A001 còn bao nhiêu hàng?”"

        return AgentAnswer(
            answer=answer,
            tool_calls=calls,
            status="completed",
            model=self.model,
        )

    def _create_draft(
        self, question: str, sku: str | None, execute: ToolExecutor, calls: list[ToolCall]
    ) -> AgentAnswer:
        recommendation = execute(
            "recommend_replenishment", {"query": sku or "", "limit": 5}
        )
        calls.append(recommendation)

        items: list[dict[str, Any]] = []
        for row in (recommendation.data or {}).get("items", []):
            if row.get("suggested_qty", 0) > 0 and (sku is None or row.get("sku") == sku):
                items.append({"sku": row["sku"], "quantity": row["suggested_qty"]})

        if not items:
            return AgentAnswer(
                answer=(
                    "Hiện không có SKU nào cần nhập thêm theo đề xuất, nên mình chưa tạo đơn nháp. "
                    "Bạn có thể hỏi “đề xuất nhập hàng” để xem chi tiết."
                ),
                tool_calls=calls,
                status="completed",
                model=self.model,
            )

        draft = execute(
            "create_purchase_order_draft",
            {"items": items[:5], "notes": f"Tạo từ trợ lý AI: {question[:200]}"},
        )
        calls.append(draft)
        pending_id = (draft.data or {}).get("purchase_order_id")
        answer = (
            f"Mình đã tạo **đơn nhập nháp #{pending_id}** với {len(items[:5])} SKU.\n\n"
            f"{recommendation.result_summary}\n\n"
            "Đơn đang ở trạng thái **chờ phê duyệt** — bạn cần vào mục Đơn nhập hàng để kiểm tra và phê duyệt "
            "trước khi gửi nhà cung cấp."
        )
        return AgentAnswer(
            answer=answer,
            tool_calls=calls,
            status="pending_approval",
            pending_purchase_order_id=pending_id,
            model=self.model,
        )

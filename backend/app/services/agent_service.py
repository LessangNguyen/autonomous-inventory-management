"""Agent service: wires the AI agent to tenant-scoped, permission-checked tools."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Alert,
    AgentRun,
    AuditLog,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesItem,
    SalesTransaction,
    Supplier,
)
from app.services.common import (
    daily_sales,
    default_warehouse,
    effective_inventory_map,
    find_product,
    get_or_create_warehouse,
    latest_forecast_map,
)
from app.services.dashboard import (
    RISK_PRIORITY,
    build_summary,
    latest_recommendations,
    overview_text,
)
from app.services.inventory_engine import run_recommendations
from ai.agents.router import RuleRouter
from ai.agents.tools import ALLOWED_TOOLS, AgentAnswer, ToolCall
from ai.forecasting.engine import forecast_series

MAX_ROWS = 20


def _money(value: float) -> str:
    return f"{value:,.0f}"


class AgentToolbox:
    """Executes allow-listed tools with tenant isolation."""

    def __init__(self, db: Session, tenant_id: int, user_id: int | None) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id
        self._products = {
            product.sku.lower(): product
            for product in db.query(Product).filter(Product.tenant_id == tenant_id).all()
        }

    def __call__(self, name: str, arguments: dict[str, Any]) -> ToolCall:
        if name not in ALLOWED_TOOLS:
            return ToolCall(
                tool=name,
                arguments=arguments,
                result_summary=f"Tool '{name}' không nằm trong allowlist nên bị từ chối.",
                ok=False,
            )
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return ToolCall(tool=name, arguments=arguments, result_summary="Tool chưa được triển khai.", ok=False)
        try:
            return handler(arguments or {})
        except Exception as exc:  # tool errors must not break the conversation
            self.db.rollback()
            return ToolCall(
                tool=name,
                arguments=arguments,
                result_summary=f"Không thực hiện được tool: {type(exc).__name__}: {exc}",
                ok=False,
            )

    # ---------- read tools ----------
    def _tool_get_dashboard_overview(self, _: dict) -> ToolCall:
        summary = build_summary(self.db, self.tenant_id)
        return ToolCall(
            tool="get_dashboard_overview",
            arguments={},
            result_summary=overview_text(summary),
            data=summary,
        )

    def _tool_get_inventory_status(self, arguments: dict) -> ToolCall:
        query = (arguments.get("query") or "").strip()
        low_only = bool(arguments.get("low_only"))
        inventory = effective_inventory_map(self.db, self.tenant_id)
        recommendations = {row.product_id: row for row in latest_recommendations(self.db, self.tenant_id)}

        rows: list[dict] = []
        for product in self._products.values():
            if query and query.lower() not in product.sku.lower() and query.lower() not in product.name.lower():
                continue
            snapshots = [
                snapshot
                for (product_id, _), snapshot in inventory.items()
                if product_id == product.id
            ]
            on_hand = sum(snapshot.on_hand for snapshot in snapshots)
            on_order = sum(snapshot.on_order for snapshot in snapshots)
            committed = sum(snapshot.committed for snapshot in snapshots)
            recommendation = recommendations.get(product.id)
            risk = recommendation.stockout_risk if recommendation else "unknown"
            if low_only and risk not in {"critical", "high", "medium", "unknown"}:
                continue
            rows.append(
                {
                    "sku": product.sku,
                    "name": product.name,
                    "on_hand": round(on_hand, 2),
                    "on_order": round(on_order, 2),
                    "committed": round(committed, 2),
                    "inventory_position": round(on_hand + on_order - committed, 2),
                    "days_of_inventory": recommendation.days_of_inventory if recommendation else None,
                    "stockout_risk": risk,
                }
            )

        rows.sort(key=lambda row: RISK_PRIORITY.get(row["stockout_risk"], 0), reverse=True)
        rows = rows[:MAX_ROWS]
        if not rows:
            summary = "Không tìm thấy SKU phù hợp." if query else "Chưa có dữ liệu tồn kho."
        else:
            lines = ["**Tồn kho**" if not query else f"**Tồn kho cho '{query}'**"]
            for row in rows[:10]:
                days = row["days_of_inventory"]
                days_text = f", còn ~{days:.0f} ngày" if days is not None else ""
                lines.append(
                    f"- {row['sku']} · {row['name']}: tồn {row['on_hand']:.0f}, "
                    f"khả dụng {row['inventory_position']:.0f}{days_text} (rủi ro {row['stockout_risk']})"
                )
            summary = "\n".join(lines)
        return ToolCall(
            tool="get_inventory_status",
            arguments=arguments,
            result_summary=summary,
            data={"items": rows},
        )

    def _tool_get_sales_summary(self, arguments: dict) -> ToolCall:
        days = int(arguments.get("days") or 30)
        days = max(1, min(days, 365))
        from datetime import date, datetime, timedelta

        end = datetime.combine(date.today(), datetime.max.time())
        start = end - timedelta(days=days)
        revenue = (
            self.db.query(func.coalesce(func.sum(SalesTransaction.total_amount), 0.0))
            .filter(
                SalesTransaction.tenant_id == self.tenant_id,
                SalesTransaction.occurred_at >= start,
            )
            .scalar()
            or 0.0
        )
        units = (
            self.db.query(func.coalesce(func.sum(SalesItem.quantity), 0.0))
            .join(SalesTransaction, SalesItem.transaction_id == SalesTransaction.id)
            .filter(
                SalesTransaction.tenant_id == self.tenant_id,
                SalesTransaction.occurred_at >= start,
            )
            .scalar()
            or 0.0
        )
        top_rows = (
            self.db.query(
                Product.sku,
                Product.name,
                func.sum(SalesItem.quantity).label("units"),
            )
            .join(SalesItem, SalesItem.product_id == Product.id)
            .join(SalesTransaction, SalesItem.transaction_id == SalesTransaction.id)
            .filter(
                SalesTransaction.tenant_id == self.tenant_id,
                SalesTransaction.occurred_at >= start,
            )
            .group_by(Product.id)
            .order_by(func.sum(SalesItem.quantity).desc())
            .limit(5)
            .all()
        )
        lines = [
            f"**Bán hàng {days} ngày gần nhất**",
            f"- Doanh thu: {_money(float(revenue))} đ",
            f"- Số lượng bán: {float(units):,.0f}",
            f"- Doanh thu/ngày: {_money(float(revenue) / days)} đ",
        ]
        if top_rows:
            lines.append("- Top SKU:")
            lines.extend(
                f"  · {row.sku} · {row.name}: {float(row.units):,.0f}" for row in top_rows
            )
        return ToolCall(
            tool="get_sales_summary",
            arguments=arguments,
            result_summary="\n".join(lines),
            data={
                "days": days,
                "revenue": round(float(revenue), 2),
                "units": round(float(units), 2),
                "top_products": [
                    {"sku": row.sku, "name": row.name, "units": float(row.units)} for row in top_rows
                ],
            },
        )

    def _tool_forecast_demand(self, arguments: dict) -> ToolCall:
        query = arguments.get("query") or ""
        horizon = int(arguments.get("horizon_days") or 30)
        horizon = max(1, min(horizon, 30))
        product = find_product(self.db, self.tenant_id, query)
        if product is None:
            return ToolCall(
                tool="forecast_demand",
                arguments=arguments,
                result_summary=f"Không tìm thấy SKU hoặc sản phẩm khớp với '{query}'.",
                ok=False,
            )
        warehouse = default_warehouse(self.db, self.tenant_id)
        history = daily_sales(
            self.db,
            self.tenant_id,
            product.id,
            warehouse.id if warehouse else None,
            settings.forecast_history_days,
        )
        result = forecast_series(history, horizon=horizon)
        confidence_text = {"high": "cao", "medium": "trung bình", "low": "thấp"}.get(
            result.confidence, result.confidence
        )
        lines = [
            f"**Dự báo {product.sku} · {product.name}**",
            f"- Nhu cầu {horizon} ngày tới: {result.predicted_qty:.0f} đơn vị",
            f"- Trung bình/ngày: {result.predicted_qty / horizon:.1f}",
            f"- Mô hình: {result.model_name} (độ tin cậy {confidence_text})",
        ]
        if result.wape is not None:
            lines.append(f"- Sai số WAPE (backtest): {result.wape * 100:.1f}%")
        return ToolCall(
            tool="forecast_demand",
            arguments=arguments,
            result_summary="\n".join(lines),
            data={
                "sku": product.sku,
                "horizon_days": horizon,
                "predicted_qty": result.predicted_qty,
                "daily_series": result.daily_series,
                "model": result.model_name,
                "confidence": result.confidence,
                "mae": result.mae,
                "wape": result.wape,
            },
        )

    def _tool_recommend_replenishment(self, arguments: dict) -> ToolCall:
        query = (arguments.get("query") or "").strip()
        limit = max(1, min(int(arguments.get("limit") or 10), 20))
        recommendations = latest_recommendations(self.db, self.tenant_id)
        if not recommendations:
            run_recommendations(self.db, self.tenant_id)
            recommendations = latest_recommendations(self.db, self.tenant_id)

        product_filter = find_product(self.db, self.tenant_id, query) if query else None
        inventory = effective_inventory_map(self.db, self.tenant_id)
        items: list[dict] = []
        for row in recommendations:
            if product_filter and row.product_id != product_filter.id:
                continue
            product = self._products_by_id().get(row.product_id)
            if product is None:
                continue
            snapshot = inventory.get((row.product_id, row.warehouse_id))
            items.append(
                {
                    "product_id": product.id,
                    "sku": product.sku,
                    "name": product.name,
                    "suggested_qty": row.suggested_qty,
                    "reorder_point": row.reorder_point,
                    "inventory_position": row.inventory_position,
                    "days_of_inventory": row.days_of_inventory,
                    "stockout_risk": row.stockout_risk,
                    "on_hand": snapshot.on_hand if snapshot else 0,
                    "unit_cost": product.unit_cost,
                }
            )
        items.sort(key=lambda item: (RISK_PRIORITY.get(item["stockout_risk"], 0), item["suggested_qty"]), reverse=True)
        need = [item for item in items if item["suggested_qty"] > 0][:limit]

        if not need:
            summary = "Không có SKU nào cần nhập thêm theo chính sách tồn kho hiện tại."
        else:
            lines = ["**Đề xuất nhập hàng**"]
            for item in need:
                lines.append(
                    f"- {item['sku']} · {item['name']}: nhập {item['suggested_qty']:.0f} "
                    f"(tồn khả dụng {item['inventory_position']:.0f}, ROP {item['reorder_point']:.0f}, "
                    f"rủi ro {item['stockout_risk']})"
                )
            lines.append("\nĐây là đề xuất tham khảo; cần người dùng xác nhận trước khi tạo đơn.")
            summary = "\n".join(lines)
        return ToolCall(
            tool="recommend_replenishment",
            arguments=arguments,
            result_summary=summary,
            data={"items": items[:limit]},
        )

    def _tool_get_alerts(self, arguments: dict) -> ToolCall:
        limit = max(1, min(int(arguments.get("limit") or 8), 20))
        alerts = (
            self.db.query(Alert)
            .filter(Alert.tenant_id == self.tenant_id, Alert.status == "open")
            .order_by(Alert.created_at.desc())
            .limit(limit)
            .all()
        )
        products = self._products_by_id()
        if not alerts:
            summary = "Không có cảnh báo nào đang mở."
        else:
            lines = ["**Cảnh báo đang mở**"]
            for alert in alerts:
                sku = products[alert.product_id].sku if alert.product_id in products else ""
                prefix = f"{sku} · " if sku else ""
                lines.append(f"- [{alert.severity}] {prefix}{alert.message}")
            summary = "\n".join(lines)
        return ToolCall(
            tool="get_alerts",
            arguments=arguments,
            result_summary=summary,
            data={
                "items": [
                    {
                        "id": alert.id,
                        "type": alert.type,
                        "severity": alert.severity,
                        "message": alert.message,
                    }
                    for alert in alerts
                ]
            },
        )

    # ---------- write tool (draft only) ----------
    def _tool_create_purchase_order_draft(self, arguments: dict) -> ToolCall:
        items = arguments.get("items") or []
        if not items:
            return ToolCall(
                tool="create_purchase_order_draft",
                arguments=arguments,
                result_summary="Không có SKU nào để tạo đơn.",
                ok=False,
            )
        warehouse = default_warehouse(self.db, self.tenant_id)
        warehouse = warehouse or get_or_create_warehouse(self.db, self.tenant_id, "MAIN")
        products = self._products_by_id()

        order = PurchaseOrder(
            tenant_id=self.tenant_id,
            warehouse_id=warehouse.id,
            status="pending_approval",
            source="agent",
            notes=(arguments.get("notes") or "")[:500],
            created_by=self.user_id,
        )
        self.db.add(order)
        self.db.flush()
        total = 0.0
        added: list[str] = []
        for item in items:
            sku = str(item.get("sku") or "").strip()
            quantity = float(item.get("quantity") or 0)
            product = next(
                (candidate for candidate in products.values() if candidate.sku.lower() == sku.lower()),
                None,
            )
            if product is None or quantity <= 0:
                continue
            self.db.add(
                PurchaseOrderItem(
                    purchase_order_id=order.id,
                    product_id=product.id,
                    quantity=quantity,
                    unit_cost=product.unit_cost,
                )
            )
            total += quantity * product.unit_cost
            added.append(f"{product.sku} × {quantity:.0f}")
        order.total_amount = total
        order.supplier_id = self._supplier_for_items(items)

        self.db.add(
            AuditLog(
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                action="agent.create_purchase_order_draft",
                entity="purchase_order",
                entity_id=order.id,
                details={"items": added, "total_amount": total},
            )
        )
        self.db.commit()

        return ToolCall(
            tool="create_purchase_order_draft",
            arguments=arguments,
            result_summary=(
                f"Đã tạo đơn nhập nháp #{order.id} gồm: {', '.join(added)}. "
                "Trạng thái chờ phê duyệt."
            ),
            data={"purchase_order_id": order.id, "items": added, "total_amount": total},
        )

    # ---------- helpers ----------
    def _products_by_id(self) -> dict[int, Product]:
        return {product.id: product for product in self._products.values()}

    def _supplier_for_items(self, items: list[dict]) -> int | None:
        product = next(
            (
                candidate
                for candidate in self._products.values()
                if any(
                    str(item.get("sku", "")).lower() == candidate.sku.lower() for item in items
                )
            ),
            None,
        )
        if product and product.supplier_id:
            return product.supplier_id
        supplier = (
            self.db.query(Supplier)
            .filter(Supplier.tenant_id == self.tenant_id)
            .order_by(Supplier.id.asc())
            .first()
        )
        return supplier.id if supplier else None


def run_agent(
    db: Session, tenant_id: int, user_id: int | None, question: str
) -> tuple[AgentAnswer, int]:
    started = time.perf_counter()
    toolbox = AgentToolbox(db, tenant_id, user_id)

    if settings.llm_api_key:
        from ai.agents.graph import LLMAgent

        agent = LLMAgent(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            execute=toolbox,
        )
    else:
        agent = RuleRouter()

    answer = agent.run(question, toolbox) if isinstance(agent, RuleRouter) else agent.run(question)
    latency = answer.latency_ms or int((time.perf_counter() - started) * 1000)

    run = AgentRun(
        tenant_id=tenant_id,
        user_id=user_id,
        question=question,
        answer=answer.answer,
        tool_calls=[
            {
                "tool": call.tool,
                "arguments": call.arguments,
                "result_summary": call.result_summary,
                "ok": call.ok,
            }
            for call in answer.tool_calls
        ],
        status=answer.status,
        model=answer.model,
        latency_ms=latency,
    )
    db.add(run)
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action="agent.run",
            entity="agent_run",
            details={"question": question, "tools": [call.tool for call in answer.tool_calls]},
        )
    )
    db.commit()
    db.refresh(run)
    answer.latency_ms = latency
    return answer, run.id

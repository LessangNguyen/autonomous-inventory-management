"""Unit tests for the inventory decision engine (pure functions)."""

from __future__ import annotations

import math

from app.services.inventory_engine import compute_recommendation, round_up_to_multiple, z_value


def test_round_up_to_multiple():
    assert round_up_to_multiple(0, 6) == 0.0
    assert round_up_to_multiple(7, 6) == 12.0
    assert round_up_to_multiple(12, 6) == 12.0
    assert round_up_to_multiple(12.1, 6) == 18.0
    assert round_up_to_multiple(3.2, 1) == 4.0


def test_z_value_known_service_levels():
    assert z_value(0.90) == 1.2816
    assert z_value(0.95) == 1.6449
    assert z_value(0.99) == 2.3263
    assert 1.6 < z_value(0.949) < 1.7


def test_compute_recommendation_critical_stock():
    result = compute_recommendation(
        avg_daily_demand=10,
        demand_std=3,
        lead_time_days=7,
        on_hand=10,
        on_order=0,
        committed=0,
        service_level=0.95,
        review_period_days=7,
        moq=10,
        order_multiple=5,
    )

    safety_stock = 1.6449 * 3 * math.sqrt(7)
    reorder_point = 10 * 7 + safety_stock
    target_stock = 10 * (7 + 7) + safety_stock

    assert result["safety_stock"] == round(safety_stock, 2)
    assert result["reorder_point"] == round(reorder_point, 2)
    assert result["target_stock"] == round(target_stock, 2)
    assert result["inventory_position"] == 10
    assert result["suggested_qty"] == 145  # 143.06 rounded to ≤ multiple of 5
    assert result["suggested_qty"] % 5 == 0
    assert result["days_of_inventory"] == 1.0
    assert result["stockout_risk"] == "critical"


def test_compute_recommendation_uses_on_order_and_committed():
    result = compute_recommendation(
        avg_daily_demand=5,
        demand_std=1,
        lead_time_days=5,
        on_hand=20,
        on_order=15,
        committed=5,
        service_level=0.95,
        review_period_days=7,
        moq=1,
        order_multiple=1,
    )
    # position = 30, target = 5*12 + safety stock (~5.65) => still needs stock
    assert result["inventory_position"] == 30
    assert result["suggested_qty"] > 0
    assert result["suggested_qty"] == math.ceil(
        result["target_stock"] - result["inventory_position"]
    )


def test_compute_recommendation_healthy_stock_orders_nothing():
    result = compute_recommendation(
        avg_daily_demand=10,
        demand_std=2,
        lead_time_days=3,
        on_hand=200,
        on_order=20,
        committed=10,
        service_level=0.95,
        review_period_days=7,
        moq=10,
        order_multiple=6,
    )
    assert result["suggested_qty"] == 0
    assert result["stockout_risk"] == "low"
    assert result["days_of_inventory"] == 20.0


def test_moq_floor_applies_only_when_reordering():
    result = compute_recommendation(
        avg_daily_demand=10,
        demand_std=0,
        lead_time_days=5,
        on_hand=45,
        on_order=0,
        committed=0,
        service_level=0.95,
        review_period_days=7,
        moq=24,
        order_multiple=6,
    )
    # target = 120, position = 45 -> raw 75 -> rounded to 78, above MOQ
    assert result["suggested_qty"] == 78

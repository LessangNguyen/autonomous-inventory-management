"""Generate synthetic retail data for demos, tests and notebooks.

The dataset mirrors the demo tenant (Vietnamese cosmetics / mini-mart) and is
explicitly synthetic. It must never be presented as real commercial data.

Usage (from the repository root):

    .venv/Scripts/python.exe data/generate_synthetic.py
    .venv/Scripts/python.exe data/generate_synthetic.py --days 200 --seed 42
    .venv/Scripts/python.exe data/generate_synthetic.py --output data/synthetic

Outputs (UTF-8 with BOM so Excel opens Vietnamese correctly):
    suppliers.csv, products.csv, inventory.csv, sales.csv
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import numpy as np  # noqa: E402

from app.services.seed import PRODUCTS, SUPPLIERS, _daily_demand  # noqa: E402

DEFAULT_DAYS = 180
DEFAULT_OUTPUT = ROOT / "data" / "synthetic"


def _write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"  {path.relative_to(ROOT)}  ({len(rows)} dòng)")


def generate(days: int, seed: int, output: Path, end_date: date) -> dict[str, int]:
    rng = np.random.default_rng(seed)
    random.seed(seed)
    start = end_date - timedelta(days=days - 1)

    supplier_rows = [
        [name, f"order{index + 1}@supplier.vn", lead_time, moq, multiple]
        for index, (name, lead_time, moq, multiple) in enumerate(SUPPLIERS)
    ]
    _write_csv(
        output / "suppliers.csv",
        ["name", "email", "lead_time_days", "moq", "order_multiple"],
        supplier_rows,
    )

    product_rows: list[list[object]] = []
    sales_rows: list[list[object]] = []
    inventory_rows: list[list[object]] = []
    daily_totals: dict[str, list[float]] = {}

    for (
        sku, name, category, unit, cost, price, supplier_index, lead_time, moq, multiple,
        base, trend, zero_prob,
    ) in PRODUCTS:
        product_rows.append(
            [
                sku, name, category, unit, cost, price,
                SUPPLIERS[supplier_index][0], lead_time, moq, multiple,
            ]
        )
        totals: list[float] = []
        for offset in range(days):
            day_index = offset
            quantity = _daily_demand(rng, base, trend, zero_prob, day_index)
            if quantity <= 0:
                continue
            day = start + timedelta(days=offset)
            sales_rows.append(
                [sku, day.isoformat(), round(quantity, 2), price, "MAIN", f"HD-{sku}-{offset:04d}"]
            )
            totals.append(quantity)

        average = (sum(totals) / days) if totals else 0.0
        coverage = random.uniform(1.1, 2.4) * (lead_time + 7)
        if len(daily_totals) % 7 == 0:  # a few deliberate stock-out risks
            coverage = random.uniform(0.2, 0.9) * lead_time
        on_hand = max(0.0, round(average * coverage))
        on_order = round(average * random.choice([0, 0, 3, 7]))
        committed = round(average * random.choice([0, 0, 1, 2]))
        inventory_rows.append(
            [sku, "MAIN", on_hand, on_order, committed, end_date.isoformat()]
        )
        daily_totals[sku] = totals

    _write_csv(
        output / "products.csv",
        [
            "sku", "name", "category", "unit", "unit_cost", "price",
            "supplier_name", "lead_time_days", "moq", "order_multiple",
        ],
        product_rows,
    )
    sales_rows.sort(key=lambda row: (row[1], row[0]))
    _write_csv(
        output / "sales.csv",
        ["sku", "date", "quantity", "unit_price", "warehouse_code", "external_id"],
        sales_rows,
    )
    _write_csv(
        output / "inventory.csv",
        ["sku", "warehouse_code", "on_hand", "on_order", "committed", "date"],
        inventory_rows,
    )

    return {
        "suppliers": len(supplier_rows),
        "products": len(product_rows),
        "sales": len(sales_rows),
        "inventory": len(inventory_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sinh dữ liệu bán lẻ synthetic (CSV).")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="Số ngày lịch sử (mặc định 180)")
    parser.add_argument("--seed", type=int, default=42, help="Seed ngẫu nhiên (mặc định 42)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Thư mục đầu ra")
    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        default=date.today(),
        help="Ngày kết thúc chuỗi (YYYY-MM-DD, mặc định hôm nay)",
    )
    args = parser.parse_args()

    if args.days < 60:
        parser.error("--days phải >= 60 để dự báo/backtest có ý nghĩa.")

    print(f"Sinh dữ liệu synthetic: {args.days} ngày, seed={args.seed}, kết thúc {args.end_date}")
    counts = generate(args.days, args.seed, args.output, args.end_date)
    total = sum(counts.values())
    print(f"Hoàn tất {total} dòng tại {args.output}")
    print("Lưu ý: dữ liệu này là synthetic, không dùng để tuyên bố độ chính xác thương mại.")


if __name__ == "__main__":
    main()

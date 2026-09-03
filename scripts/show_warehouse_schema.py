"""Inspect statistical warehouse counts, indexes, and constraints."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import func, inspect, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import models as db
from app.database.session import SessionLocal, engine


WAREHOUSE_MODELS = (
    db.StatDataset,
    db.TradeObservation,
    db.IngestionBatch,
    db.ObservationRejection,
)


def main() -> int:
    print("Warehouse counts")
    with SessionLocal() as session:
        for model in WAREHOUSE_MODELS:
            count = session.scalar(select(func.count()).select_from(model)) or 0
            print(f"{model.__tablename__}: {count}")

    inspector = inspect(engine)
    print("\nWarehouse schema")
    for model in WAREHOUSE_MODELS:
        table_name = model.__tablename__
        print(f"\n{table_name}")
        for constraint in inspector.get_unique_constraints(table_name):
            columns = ", ".join(constraint["column_names"])
            print(f"UNIQUE {constraint['name']}: {columns}")
        for constraint in inspector.get_check_constraints(table_name):
            print(f"CHECK {constraint['name']}: {constraint['sqltext']}")
        for index in inspector.get_indexes(table_name):
            columns = ", ".join(index["column_names"])
            print(f"INDEX {index['name']}: {columns}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

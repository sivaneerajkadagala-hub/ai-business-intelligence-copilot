"""Generate realistic demo datasets (sales, customers, products, orders)
and ingest them through the same physical-table + profiling path used by
real uploads, so dashboards, Copilot, and analytics see identical data."""

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.models.dataset import (
    Dataset,
    DatasetImport,
    DatasetStatus,
    FileType,
    ImportStatus,
    VersionKind,
)
from app.models.user import User, UserRole
from app.services.datasets import profiling
from app.services.datasets.ingest import write_version

REGIONS = ["North", "South", "East", "West"]
CUSTOMER_TYPES = ["standard", "premium", "vip"]

PRODUCTS = [
    # (name, category, price, cost)
    ("Alpha Laptop", "Electronics", 1200, 800),
    ("Vertex Monitor", "Electronics", 350, 210),
    ("Pulse Headphones", "Electronics", 180, 90),
    ("Ergo Chair", "Furniture", 450, 260),
    ("Standing Desk", "Furniture", 700, 420),
    ("Oak Bookshelf", "Furniture", 220, 130),
    ("Trail Sneakers", "Apparel", 95, 45),
    ("Cloud Hoodie", "Apparel", 60, 28),
    ("Denim Jacket", "Apparel", 110, 55),
    ("Arabica Coffee 1kg", "Grocery", 24, 12),
    ("Green Tea Box", "Grocery", 12, 5),
    ("Protein Bars 12pk", "Grocery", 30, 16),
]

FIRST_NAMES = [
    "Aisha", "Rahul", "Maria", "James", "Chen", "Fatima", "Diego", "Emma",
    "Liam", "Priya", "Noah", "Zara", "Omar", "Sofia", "Ethan", "Mei",
]
LAST_NAMES = [
    "Sharma", "Garcia", "Kim", "Johnson", "Ali", "Silva", "Brown", "Patel",
    "Lee", "Khan", "Nguyen", "Smith", "Kaur", "Lopez", "Wong", "Das",
]


def _seed_owner(db: Session) -> User:
    user = db.scalar(sa.select(User).where(User.email == "analyst@bicopilot.dev"))
    if user:
        return user
    user = db.scalar(sa.select(User).where(User.role == UserRole.ADMIN)) or db.scalar(
        sa.select(User)
    )
    if user is None:
        raise RuntimeError("seed: no users exist — run seed_users first")
    return user


def _create_dataset(
    db: Session, engine: Engine, owner: User, *, name: str,
    description: str, df: pd.DataFrame,
) -> Dataset:
    ds = Dataset(
        owner_id=owner.id,
        name=name,
        description=description,
        status=DatasetStatus.READY,
        original_filename=f"{name.lower().replace(' ', '_')}.csv",
        file_type=FileType.CSV,
        file_size_bytes=int(df.memory_usage(deep=True).sum()),
        storage_path="(seeded)",
        row_count=len(df),
        column_count=len(df.columns),
        is_shared=True,
    )
    db.add(ds)
    db.flush()

    df.columns = profiling.normalize_column_names(list(df.columns))
    type_map = profiling.infer_types(df)
    df = profiling.coerce_types(df, type_map)
    version = write_version(
        db, engine, dataset=ds, df=df, type_map=type_map,
        kind=VersionKind.ORIGINAL, parent=None, operations=None, user=owner,
    )
    ds.current_version_id = version.id
    ds.quality_score = profiling.quality_score(df)
    db.add(
        DatasetImport(
            dataset_id=ds.id,
            version_id=version.id,
            imported_by=owner.id,
            status=ImportStatus.SUCCESS,
            rows_imported=len(df),
            rows_rejected=0,
            started_at=utcnow(),
            finished_at=utcnow(),
        )
    )
    return ds


def gen_sales(rng: np.random.Generator, n_days: int = 730) -> pd.DataFrame:
    """~6-7k sales rows over 24 months with seasonality, growth,
    weekend effects — plus injected anomalies for detection demos."""
    end = date.today()
    start = end - timedelta(days=n_days - 1)
    days = [start + timedelta(days=i) for i in range(n_days)]
    price_cost = {p[0]: (p[2], p[3]) for p in PRODUCTS}
    names = list(price_cost)

    rows = []
    for d in days:
        month_phase = math.sin(2 * math.pi * (d.month - 1) / 12)
        weekend_dip = 0.55 if d.weekday() >= 5 else 1.0
        growth = 1 + 0.011 * ((d - start).days / 30)
        base = 9 * (1 + 0.28 * month_phase) * weekend_dip * growth
        n_sales = max(1, int(rng.normal(base, 2)))
        for _ in range(n_sales):
            product = rng.choice(names)
            price, cost = price_cost[product]
            qty = int(rng.integers(1, 9))
            revenue = round(qty * price * rng.uniform(0.92, 1.08), 2)
            c = round(qty * cost, 2)
            category = next(p[1] for p in PRODUCTS if p[0] == product)
            rows.append(
                {
                    "date": d,
                    "product": product,
                    "category": category,
                    "region": rng.choice(REGIONS, p=[0.3, 0.25, 0.25, 0.2]),
                    "quantity": qty,
                    "revenue": revenue,
                    "cost": c,
                    "profit": round(revenue - c, 2),
                }
            )

    df = pd.DataFrame(rows)

    # Injected anomalies: two revenue spikes and one dip — discoverable later.
    for day_idx, factor in [(200, 6.5), (430, 7.5), (600, 0.12)]:
        target = start + timedelta(days=day_idx)
        mask = df["date"] == target
        df.loc[mask, "revenue"] = (df.loc[mask, "revenue"] * factor).round(2)
        df.loc[mask, "profit"] = (df.loc[mask, "revenue"] - df.loc[mask, "cost"]).round(2)

    df.insert(0, "sale_id", range(1, len(df) + 1))
    return df


def gen_customers(rng: np.random.Generator, n: int = 1000) -> pd.DataFrame:
    end = date.today()
    rows = []
    for i in range(1, n + 1):
        signup = end - timedelta(days=int(rng.integers(0, 1095)))
        rows.append(
            {
                "customer_id": i,
                "name": f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
                "region": rng.choice(REGIONS),
                "signup_date": signup,
                "customer_type": rng.choice(CUSTOMER_TYPES, p=[0.7, 0.22, 0.08]),
            }
        )
    return pd.DataFrame(rows)


def gen_products() -> pd.DataFrame:
    rows = [
        {"product_id": i + 1, "product": name, "category": cat,
         "price": price, "cost": cost}
        for i, (name, cat, price, cost) in enumerate(PRODUCTS)
    ]
    return pd.DataFrame(rows)


def gen_orders(rng: np.random.Generator, n_customers: int, n: int = 8000) -> pd.DataFrame:
    end = date.today()
    price = {p[0]: p[2] for p in PRODUCTS}
    names = list(price)
    rows = []
    for i in range(1, n + 1):
        product = rng.choice(names)
        qty = int(rng.integers(1, 6))
        order_date = end - timedelta(days=int(rng.integers(0, 730)))
        rows.append(
            {
                "order_id": i,
                "customer_id": int(rng.integers(1, n_customers + 1)),
                "order_date": order_date,
                "product": product,
                "quantity": qty,
                "amount": round(qty * price[product] * rng.uniform(0.95, 1.05), 2),
            }
        )
    return pd.DataFrame(rows)


def seed_datasets(db: Session, engine: Engine) -> None:
    rng = np.random.default_rng(42)
    owner = _seed_owner(db)

    specs = [
        ("Sales", "24 months of daily sales transactions (seeded demo data)", gen_sales(rng)),
        ("Customers", "Customer directory with signup dates and segments", gen_customers(rng)),
        ("Products", "Product catalog with pricing and cost", gen_products()),
        ("Orders", "Customer orders across the catalog", gen_orders(rng, 1000)),
    ]

    created = 0
    for name, description, df in specs:
        if db.scalar(sa.select(Dataset).where(Dataset.name == name)):
            continue
        _create_dataset(db, engine, owner, name=name, description=description, df=df)
        created += 1
    db.commit()
    print(f"seed: {created} dataset(s) created, {len(specs) - created} already existed")

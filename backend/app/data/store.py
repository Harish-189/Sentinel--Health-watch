"""SQLite storage for aggregate series. One long-format table; no person-level tables exist."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import Boolean, Engine, Float, Integer, String, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.data.privacy import apply_privacy

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "generated" / "sentinel.db"


class Base(DeclarativeBase):
    pass


class Aggregate(Base):
    __tablename__ = "aggregates"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run: Mapped[str] = mapped_column(String(64), index=True)
    day: Mapped[int] = mapped_column(Integer)
    date: Mapped[str] = mapped_column(String(10))
    district: Mapped[str] = mapped_column(String(8), index=True)
    source: Mapped[str] = mapped_column(String(32))
    metric: Mapped[str] = mapped_column(String(48))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False)


_COLUMNS = ["day", "date", "district", "source", "metric", "value", "suppressed"]


def default_engine() -> Engine:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{DB_PATH}")


def ingest(df: pd.DataFrame, run: str, engine: Engine | None = None) -> pd.DataFrame:
    """Guard + suppress, then replace the stored rows for `run`. Returns the stored frame."""
    clean = apply_privacy(df)
    eng = engine or default_engine()
    Base.metadata.create_all(eng)
    with eng.begin() as conn:
        conn.execute(delete(Aggregate).where(Aggregate.run == run))
    clean[_COLUMNS].assign(run=run).to_sql("aggregates", eng, if_exists="append", index=False, chunksize=20_000)
    return clean


def load(run: str, engine: Engine | None = None) -> pd.DataFrame:
    eng = engine or default_engine()
    stmt = select(*(getattr(Aggregate, c) for c in _COLUMNS)).where(Aggregate.run == run).order_by(Aggregate.pk)
    with eng.connect() as conn:
        df = pd.read_sql(stmt, conn)
    df["value"] = df["value"].astype(float)
    df["suppressed"] = df["suppressed"].astype(bool)
    return df

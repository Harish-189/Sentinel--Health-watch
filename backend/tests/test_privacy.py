import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine

from app.data import privacy, store
from app.data.schema import METRICS


def _long(values: list[float], source: str = "clinic", metric: str = "respiratory") -> pd.DataFrame:
    n = len(values)
    return pd.DataFrame(
        {
            "day": range(n),
            "date": pd.date_range("2024-01-01", periods=n).strftime("%Y-%m-%d"),
            "district": ["CBE"] * n,
            "source": [source] * n,
            "metric": [metric] * n,
            "value": values,
        }
    )


def test_small_counts_are_suppressed_and_flagged() -> None:
    out = privacy.suppress_small_cells(_long([0, 3, 4, 5, 12]))
    assert out["value"].isna().tolist() == [True, True, True, False, False]
    assert out["suppressed"].tolist() == [True, True, True, False, False]


def test_non_count_metrics_are_not_suppressed() -> None:
    out = privacy.suppress_small_cells(_long([2.5, 3.1], source="absenteeism", metric="school_rate"))
    assert out["value"].notna().all()
    assert not out["suppressed"].any()


@pytest.mark.parametrize(
    "col", ["patient_name", "name", "dob", "date_of_birth", "home_address", "phone_number", "person_id", "id"]
)
def test_pii_columns_rejected(col: str) -> None:
    df = _long([10, 11]).assign(**{col: ["x", "y"]})
    with pytest.raises(privacy.PIIViolation):
        privacy.guard_columns(df)


def test_allowed_columns_pass() -> None:
    df = _long([10, 11]).assign(district_id=["CBE", "CBE"])
    privacy.guard_columns(df)


def test_pii_like_metric_names_rejected() -> None:
    with pytest.raises(privacy.PIIViolation):
        privacy.guard_columns(_long([10, 11], metric="patient_phone"))


def test_registered_metrics_are_clean() -> None:
    for m in METRICS:
        assert not privacy.is_pii_name(m.metric), m.metric


def test_store_schema_has_no_person_level_columns() -> None:
    for table in store.Base.metadata.tables.values():
        for column in table.columns:
            assert not privacy.is_pii_name(column.name), f"{table.name}.{column.name}"


def test_ingest_rejects_pii_and_suppresses() -> None:
    engine = create_engine("sqlite://")
    with pytest.raises(privacy.PIIViolation):
        store.ingest(_long([10]).assign(patient_name=["a"]), run="t", engine=engine)
    store.ingest(_long([2, 40]), run="t", engine=engine)
    back = store.load("t", engine=engine)
    assert back["suppressed"].tolist() == [True, False]
    assert np.isnan(back["value"].iloc[0])


def test_laplace_noise_is_seeded_and_nonnegative() -> None:
    v = np.array([5.0, 6.0, 100.0])
    a = privacy.laplace_noise(v, epsilon=1.0, seed=1)
    b = privacy.laplace_noise(v, epsilon=1.0, seed=1)
    assert np.array_equal(a, b)
    assert (a >= 0).all()
    assert not np.array_equal(a, v)

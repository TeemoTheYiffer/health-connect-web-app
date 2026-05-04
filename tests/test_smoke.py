"""Lightweight smoke tests: the modules import and the SQLite extractor opens cleanly.

We intentionally don't ship a fixture export (PHI), so end-to-end coverage lives in the
ad-hoc `hcw-sync --local` CLI run. These tests just guard against import-time regressions.
"""

from __future__ import annotations


def test_imports() -> None:
    import health_connect_web  # noqa: F401
    from health_connect_web import config, db, models, units  # noqa: F401
    from health_connect_web.sync import extract, load, runner  # noqa: F401
    from health_connect_web.web import auth, queries  # noqa: F401


def test_units_roundtrip() -> None:
    from health_connect_web.units import grams_to_kg, ms_to_dt

    dt = ms_to_dt(1765699200000)
    assert dt is not None and dt.year == 2025
    assert grams_to_kg(93984) == 93.984


def test_config_email_allowlist(monkeypatch) -> None:
    from health_connect_web.config import Settings

    s = Settings(
        owner_email="owner@example.com",
        allowed_emails="a@example.com, b@example.com",  # comma-separated string
    )
    assert s.is_email_allowed("OWNER@example.com")
    assert s.is_email_allowed("a@example.com")
    assert s.is_email_allowed("b@example.com")
    assert not s.is_email_allowed("nope@example.com")
    assert not s.is_email_allowed("")


def test_models_create_in_memory_sqlite(monkeypatch, tmp_path) -> None:
    """Verify the schema actually creates against SQLite, catches typos/conflicts."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    # Reset cached settings/engine.
    from health_connect_web import config
    from health_connect_web import db as db_mod

    config.get_settings.cache_clear()
    db_mod._engine = None
    db_mod._SessionLocal = None

    from health_connect_web.db import session_scope
    from health_connect_web.models import Base, Vitamin, create_all

    create_all()
    with session_scope() as s:
        s.add(
            Vitamin(
                slug="t-1",
                name="Test",
                kind="vitamin",
                dose="1mg",
                frequency="Daily",
            )
        )
    with session_scope() as s:
        rows = list(s.query(Vitamin).all())
        assert len(rows) == 1
        assert rows[0].slug == "t-1"

    # Also assert Base has all expected tables.
    expected = {
        "blood_pressure",
        "heart_rate",
        "heart_rate_sample",
        "resting_heart_rate",
        "steps",
        "weight",
        "body_fat",
        "height",
        "active_calories",
        "total_calories",
        "distance",
        "floors_climbed",
        "elevation_gained",
        "exercise_session",
        "sleep_session",
        "sleep_stage",
        "nutrition",
        "vitamin",
        "sync_run",
    }
    assert expected.issubset(set(Base.metadata.tables.keys()))

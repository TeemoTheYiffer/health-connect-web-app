"""Upsert extracted rows into our persistent DB.

Idempotent: keyed by Health Connect's uuid. Re-running the sync against an unchanged
export is a no-op (rows are updated to the same values).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from health_connect_web import models as m

log = logging.getLogger(__name__)

# SQLite's default parameter limit is 999; Postgres handles much more, but chunking
# keeps the lookup query small and the hot path uniform across both engines.
_IN_CHUNK = 500


def _fetch_existing_by_uuid(session: Session, model: type[m.Base], uuids: Iterable[str]) -> dict[str, Any]:
    uuids = list(uuids)
    out: dict[str, Any] = {}
    for i in range(0, len(uuids), _IN_CHUNK):
        chunk = uuids[i : i + _IN_CHUNK]
        rows = (
            session.execute(select(model).where(model.uuid.in_(chunk)))  # type: ignore[attr-defined]
            .scalars()
            .all()
        )
        out.update({r.uuid: r for r in rows})  # type: ignore[attr-defined]
    return out


def _upsert_simple(session: Session, model: type[m.Base], rows: Iterable[dict[str, Any]]) -> int:
    """Generic upsert by `uuid`. Returns rows-touched count."""
    n = 0
    by_uuid = {r["uuid"]: r for r in rows if r.get("uuid")}
    if not by_uuid:
        return 0
    existing_by_uuid = _fetch_existing_by_uuid(session, model, by_uuid.keys())

    for uuid_hex, data in by_uuid.items():
        if uuid_hex in existing_by_uuid:
            obj = existing_by_uuid[uuid_hex]
            for k, v in data.items():
                if hasattr(obj, k):
                    setattr(obj, k, v)
        else:
            session.add(model(**{k: v for k, v in data.items() if hasattr(model, k)}))
        n += 1
    session.flush()
    return n


def _upsert_heart_rate(session: Session, rows: Iterable[dict[str, Any]]) -> int:
    """Heart rate has child samples; replace samples on update for simplicity."""
    n = 0
    rows_list = [r for r in rows if r.get("uuid")]
    if not rows_list:
        return 0

    uuids = {r["uuid"] for r in rows_list}
    existing_by_uuid = _fetch_existing_by_uuid(session, m.HeartRate, uuids)

    for r in rows_list:
        samples = r.pop("samples", [])
        if r["uuid"] in existing_by_uuid:
            obj = existing_by_uuid[r["uuid"]]
            for k, v in r.items():
                if hasattr(obj, k):
                    setattr(obj, k, v)
            obj.samples.clear()
            session.flush()
        else:
            obj = m.HeartRate(**{k: v for k, v in r.items() if hasattr(m.HeartRate, k)})
            session.add(obj)
            session.flush()
        for s in samples:
            obj.samples.append(m.HeartRateSample(ts=s["ts"], bpm=s["bpm"]))
        n += 1
    session.flush()
    return n


def _upsert_sleep_session(session: Session, rows: Iterable[dict[str, Any]]) -> int:
    n = 0
    rows_list = [r for r in rows if r.get("uuid")]
    if not rows_list:
        return 0

    uuids = {r["uuid"] for r in rows_list}
    existing_by_uuid = _fetch_existing_by_uuid(session, m.SleepSession, uuids)

    for r in rows_list:
        stages = r.pop("stages", [])
        if r["uuid"] in existing_by_uuid:
            obj = existing_by_uuid[r["uuid"]]
            for k, v in r.items():
                if hasattr(obj, k):
                    setattr(obj, k, v)
            obj.stages.clear()
            session.flush()
        else:
            obj = m.SleepSession(**{k: v for k, v in r.items() if hasattr(m.SleepSession, k)})
            session.add(obj)
            session.flush()
        for s in stages:
            obj.stages.append(
                m.SleepStage(start_time=s["start_time"], end_time=s["end_time"], stage_type=s["stage_type"])
            )
        n += 1
    session.flush()
    return n


# Public dispatch table: model -> upsert function. Wired up in sync.runner.
UPSERTERS = {
    "blood_pressure": (m.BloodPressure, _upsert_simple),
    "resting_heart_rate": (m.RestingHeartRate, _upsert_simple),
    "heart_rate": (None, _upsert_heart_rate),
    "steps": (m.Steps, _upsert_simple),
    "weight": (m.Weight, _upsert_simple),
    "body_fat": (m.BodyFat, _upsert_simple),
    "height": (m.Height, _upsert_simple),
    "active_calories": (m.ActiveCalories, _upsert_simple),
    "total_calories": (m.TotalCalories, _upsert_simple),
    "distance": (m.Distance, _upsert_simple),
    "floors_climbed": (m.FloorsClimbed, _upsert_simple),
    "elevation_gained": (m.ElevationGained, _upsert_simple),
    "exercise_session": (m.ExerciseSession, _upsert_simple),
    "sleep_session": (None, _upsert_sleep_session),
    "nutrition": (m.Nutrition, _upsert_simple),
}


def upsert(session: Session, kind: str, rows: Iterable[dict[str, Any]]) -> int:
    if kind not in UPSERTERS:
        raise KeyError(f"Unknown record kind: {kind}")
    model, fn = UPSERTERS[kind]
    if model is None:  # custom upserter handles its own model
        return fn(session, rows)  # type: ignore[arg-type]
    return fn(session, model, rows)  # type: ignore[arg-type]

"""End-to-end sync orchestration: source -> extract -> load -> audit."""

from __future__ import annotations

import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from health_connect_web import models as m
from health_connect_web.db import session_scope
from health_connect_web.sync import extract, load
from health_connect_web.sync.drive import DriveExport

log = logging.getLogger(__name__)


# Order matters only for foreign-key parents: heart_rate before its samples (handled internally),
# sleep_session before its stages (also internal), and nutrition is independent.
SYNC_ORDER = [
    "blood_pressure",
    "resting_heart_rate",
    "heart_rate",
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
    "nutrition",
]

EXTRACTORS = {
    "blood_pressure": extract.iter_blood_pressure,
    "resting_heart_rate": extract.iter_resting_heart_rate,
    "heart_rate": extract.iter_heart_rate,
    "steps": extract.iter_steps,
    "weight": extract.iter_weight,
    "body_fat": extract.iter_body_fat,
    "height": extract.iter_height,
    "active_calories": extract.iter_active_calories,
    "total_calories": extract.iter_total_calories,
    "distance": extract.iter_distance,
    "floors_climbed": extract.iter_floors_climbed,
    "elevation_gained": extract.iter_elevation_gained,
    "exercise_session": extract.iter_exercise_session,
    "sleep_session": extract.iter_sleep_session,
    "nutrition": extract.iter_nutrition,
}


def _run(
    *,
    session: Session,
    sqlite_path: Path,
    source: str,
    file_id: str | None,
    file_modified_at: datetime | None,
) -> m.SyncRun:
    run = m.SyncRun(
        started_at=datetime.now(UTC),
        source=source,
        file_id=file_id,
        file_modified_at=file_modified_at,
        status="running",
    )
    session.add(run)
    session.flush()

    total = 0
    try:
        with extract.open_export(sqlite_path) as con:
            apps = extract._app_packages(con)
            counts = extract.export_summary(con)
            log.info("Source counts: %s", counts)

            for kind in SYNC_ORDER:
                rows = list(EXTRACTORS[kind](con, apps))
                n = load.upsert(session, kind, rows)
                if n:
                    log.info("Upserted %s: %d", kind, n)
                total += n

        run.finished_at = datetime.now(UTC)
        run.status = "success"
        run.rows_upserted = total
        return run
    except Exception as e:
        run.finished_at = datetime.now(UTC)
        run.status = "error"
        run.notes = f"{type(e).__name__}: {e}"
        log.exception("Sync failed")
        raise


def run_from_local(sqlite_path: Path) -> m.SyncRun:
    with session_scope() as s:
        return _run(
            session=s,
            sqlite_path=sqlite_path,
            source="local",
            file_id=None,
            file_modified_at=None,
        )


def run_from_drive_export(export: DriveExport) -> m.SyncRun:
    try:
        with session_scope() as s:
            return _run(
                session=s,
                sqlite_path=export.sqlite_path,
                source="drive",
                file_id=export.file_id,
                file_modified_at=export.modified_time,
            )
    finally:
        # Clean up the temp dir extract was written to.
        shutil.rmtree(export.sqlite_path.parent, ignore_errors=True)

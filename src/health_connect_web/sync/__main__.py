"""CLI entrypoint for the sync job.

Usage:
    hcw-sync                   # pull latest from Drive
    hcw-sync --local PATH      # read a local Health Connect SQLite (offline iteration)
    hcw-sync --init-db         # create tables and exit (dev/CI)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from health_connect_web.config import get_settings


def _migrate_widen_vitamin_columns(log: logging.Logger) -> None:
    """Idempotent: widen vitamin.{dose,frequency,vendor,url} from VARCHAR to TEXT.

    The first deploy used String(128) for dose/frequency, which can't hold full
    per-cap breakdowns from products like Prostate Essentials. ALTER ... TYPE TEXT
    is a no-op once the column is already TEXT, so this runs safely on every sync.
    SQLite doesn't enforce VARCHAR limits, so we skip it there.
    """
    from sqlalchemy import text

    from health_connect_web.db import engine as get_engine

    eng = get_engine()
    if eng.dialect.name != "postgresql":
        return
    with eng.begin() as conn:
        for col in ("dose", "frequency", "vendor", "url"):
            conn.execute(text(f"ALTER TABLE vitamin ALTER COLUMN {col} TYPE TEXT"))
    log.info("Vitamin column types migrated to TEXT.")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="hcw-sync")
    p.add_argument(
        "--local",
        type=Path,
        nargs="?",
        const=None,
        help="Read from a local Health Connect SQLite file instead of Drive. "
        "If used without a value, falls back to LOCAL_HEALTH_CONNECT_DB env.",
    )
    p.add_argument(
        "--init-db",
        action="store_true",
        help="Create all tables in the configured DATABASE_URL, then exit.",
    )
    args = p.parse_args(argv)

    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("hcw.sync")

    # Avoid importing models at module top so logging is configured first.
    from health_connect_web.models import create_all
    from health_connect_web.sync import drive, runner, supplements

    if args.init_db:
        create_all()
        log.info("Tables created in %s", settings.database_url.split("@")[-1])
        return 0

    # Always ensure tables exist (cheap; create_all is a no-op if already present).
    create_all()
    _migrate_widen_vitamin_columns(log)

    # Idempotently seed supplements from the TOML baked into the image. Keeps prod
    # in sync with the file in git on every sync run. Failures don't block the
    # health-data sync that follows.
    try:
        supplements.seed_supplements_from_toml()
    except Exception as e:
        log.warning("Supplement seed failed (continuing with health sync): %s", e)

    try:
        supplements.seed_herbs_from_toml()
    except Exception as e:
        log.warning("Herb seed failed (continuing with health sync): %s", e)

    if "--local" in (argv or sys.argv[1:]) or args.local is not None:
        path = args.local or settings.local_health_connect_db
        if not path:
            log.error("--local given but no path provided and LOCAL_HEALTH_CONNECT_DB is unset")
            return 2
        path = Path(path)
        if not path.exists():
            log.error("Local export not found: %s", path)
            return 2
        run = runner.run_from_local(path)
        log.info("Local sync done: status=%s rows=%d", run.status, run.rows_upserted)
        return 0 if run.status == "success" else 1

    log.info("Pulling latest export from Drive folder %s", settings.drive_folder_id)
    export = drive.download_latest_export()
    run = runner.run_from_drive_export(export)
    log.info(
        "Drive sync done: file=%s status=%s rows=%d",
        export.file_name,
        run.status,
        run.rows_upserted,
    )
    return 0 if run.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())

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
    from health_connect_web.sync import drive, runner

    if args.init_db:
        create_all()
        log.info("Tables created in %s", settings.database_url.split("@")[-1])
        return 0

    # Always ensure tables exist (cheap; create_all is a no-op if already present).
    create_all()

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

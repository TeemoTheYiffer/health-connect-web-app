"""Load page content from on-disk TOML files at request time.

Used for pages whose content is narrative / structured-but-static, not
record-style data that belongs in the DB. Currently:

- `schedule.toml`  -> /schedule
- `teas.toml`'s [brewing] block -> the brewing-protocols section of /teas

Anyone forking this repo edits the TOML, no template changes required.
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def _candidate_paths(filename: str) -> list[Path]:
    """CWD-relative first (matches the container's /app), then repo-root fallback for dev."""
    return [
        Path(filename),
        Path(__file__).resolve().parents[3] / filename,
    ]


def _load_toml(filename: str) -> dict[str, Any]:
    for p in _candidate_paths(filename):
        if p.exists():
            with p.open("rb") as f:
                return tomllib.load(f)
    log.warning("Content file not found: %s (searched %s)", filename, _candidate_paths(filename))
    return {}


def schedule_data() -> dict[str, Any]:
    """Parsed schedule.toml for /schedule. Returns {} if the file is missing."""
    return _load_toml("schedule.toml")


def tea_brewing() -> dict[str, Any]:
    """Parsed [brewing] block from teas.toml for the /teas page."""
    return _load_toml("teas.toml").get("brewing", {})

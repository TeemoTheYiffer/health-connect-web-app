"""Idempotent seed of the Vitamin/supplement table from a TOML file.

Run automatically as part of the sync job so the prod DB stays in sync with the
`vitamins.toml` baked into the container image. Edits to the TOML land in prod
on the next sync run after the image rebuilds.
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any

from sqlalchemy import select

from health_connect_web import models as m
from health_connect_web.db import session_scope

log = logging.getLogger(__name__)

# Where to look for vitamins.toml. In the container the Dockerfile drops it at
# /app/vitamins.toml (CWD). Locally it's at the repo root. The sync job tries the
# CWD-relative path first, then falls back to the repo root resolved from this file.
_DEFAULT_PATHS: list[Path] = [
    Path("vitamins.toml"),
    Path(__file__).resolve().parents[3] / "vitamins.toml",
]


def _find_toml(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit if explicit.exists() else None
    for p in _DEFAULT_PATHS:
        if p.exists():
            return p
    return None


def seed_supplements_from_toml(path: Path | None = None) -> int:
    """Upsert all `[[items]]` from `vitamins.toml` into the Vitamin table.

    Returns the number of rows touched. Returns 0 (with a warning) if no TOML
    is found, so a missing file doesn't fail the sync run.
    """
    toml_path = _find_toml(path)
    if toml_path is None:
        log.warning("No vitamins.toml found; skipping supplement seed.")
        return 0

    with toml_path.open("rb") as f:
        data = tomllib.load(f)

    items = data.get("items", [])
    if not items:
        log.warning("vitamins.toml has no [[items]]; skipping seed.")
        return 0

    upserted = 0
    with session_scope() as s:
        for i, item in enumerate(items):
            slug = item.get("slug")
            if not slug:
                log.warning("Item #%d missing slug, skipping", i)
                continue

            existing = s.execute(select(m.Vitamin).where(m.Vitamin.slug == slug)).scalar_one_or_none()
            payload: dict[str, Any] = {
                "slug": slug,
                "name": item.get("name", slug),
                "kind": item.get("kind", "supplement"),
                "dose": item.get("dose"),
                "frequency": item.get("frequency"),
                "started_on": item.get("started_on"),
                "positive_effects": item.get("positive_effects"),
                "side_effects": item.get("side_effects"),
                "interactions": item.get("interactions"),
                "stack_interactions": item.get("stack_interactions"),
                "notes": item.get("notes"),
                "vendor": item.get("vendor"),
                "url": item.get("url"),
                "daily_contrib": item.get("contributes") or None,
                "sort_order": int(item.get("sort_order", i)),
            }
            if existing:
                for k, v in payload.items():
                    setattr(existing, k, v)
            else:
                s.add(m.Vitamin(**payload))
            upserted += 1

    log.info("Supplements seeded from %s: %d items", toml_path, upserted)
    return upserted

"""Idempotent seed of the Vitamin and Herb tables from TOML files.

Run automatically as part of the sync job so the prod DB stays in sync with the
`vitamins.toml` and `teas.toml` baked into the container image. Edits to either
TOML land in prod on the next sync run after the image rebuilds.
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

# Where to look for the TOML files. In the container the Dockerfile drops them at
# /app/*.toml (CWD). Locally they're at the repo root. The sync job tries the
# CWD-relative path first, then falls back to the repo root resolved from this file.
_DEFAULT_PATHS: list[Path] = [
    Path("vitamins.toml"),
    Path(__file__).resolve().parents[3] / "vitamins.toml",
]
_TEAS_PATHS: list[Path] = [
    Path("teas.toml"),
    Path(__file__).resolve().parents[3] / "teas.toml",
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

        # Reconcile: drop DB rows whose slug isn't in the TOML anymore. Defensive
        # guard above (return 0 if items is empty) prevents a partial / failed
        # parse from wiping the whole table.
        seen = {item.get("slug") for item in items if item.get("slug")}
        stale = list(s.execute(select(m.Vitamin).where(m.Vitamin.slug.not_in(seen))).scalars())
        if stale:
            log.info(
                "Reconcile: deleting %d stale supplement(s): %s",
                len(stale),
                ", ".join(v.slug for v in stale),
            )
            for v in stale:
                s.delete(v)

    log.info("Supplements seeded from %s: %d items", toml_path, upserted)
    return upserted


def _find_teas_toml(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit if explicit.exists() else None
    for p in _TEAS_PATHS:
        if p.exists():
            return p
    return None


def seed_herbs_from_toml(path: Path | None = None) -> int:
    """Upsert all `[[items]]` from `teas.toml` into the Herb table.

    Returns the number of rows touched. Returns 0 (with a warning) if no TOML
    is found, so a missing file doesn't fail the sync run.
    """
    toml_path = _find_teas_toml(path)
    if toml_path is None:
        log.warning("No teas.toml found; skipping herb seed.")
        return 0

    with toml_path.open("rb") as f:
        data = tomllib.load(f)

    items = data.get("items", [])
    if not items:
        log.warning("teas.toml has no [[items]]; skipping seed.")
        return 0

    upserted = 0
    with session_scope() as s:
        for i, item in enumerate(items):
            slug = item.get("slug")
            if not slug:
                log.warning("Herb item #%d missing slug, skipping", i)
                continue

            existing = s.execute(select(m.Herb).where(m.Herb.slug == slug)).scalar_one_or_none()
            payload: dict[str, Any] = {
                "slug": slug,
                "name": item.get("name", slug),
                "blend": item.get("blend", "both"),
                "amount": item.get("amount"),
                "effects": item.get("effects"),
                "drug_interactions": item.get("drug_interactions"),
                "notes": item.get("notes"),
                "vendor": item.get("vendor"),
                "url": item.get("url"),
                "sort_order": int(item.get("sort_order", i)),
            }
            if existing:
                for k, v in payload.items():
                    setattr(existing, k, v)
            else:
                s.add(m.Herb(**payload))
            upserted += 1

        # Reconcile (same guard as supplements above).
        seen = {item.get("slug") for item in items if item.get("slug")}
        stale = list(s.execute(select(m.Herb).where(m.Herb.slug.not_in(seen))).scalars())
        if stale:
            log.info(
                "Reconcile: deleting %d stale herb(s): %s",
                len(stale),
                ", ".join(h.slug for h in stale),
            )
            for h in stale:
                s.delete(h)

    log.info("Herbs seeded from %s: %d items", toml_path, upserted)
    return upserted

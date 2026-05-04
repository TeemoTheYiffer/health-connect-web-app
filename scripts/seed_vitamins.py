"""Seed the Vitamin table from `vitamins.toml`.

Run after editing the TOML to push changes into the DB. Idempotent on `slug`.
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from sqlalchemy import select

from health_connect_web import models as m
from health_connect_web.db import session_scope
from health_connect_web.models import create_all

ROOT = Path(__file__).resolve().parents[1]
TOML_PATH = ROOT / "vitamins.toml"


def main() -> int:
    if not TOML_PATH.exists():
        print(f"No {TOML_PATH} found. Copy vitamins.toml.example to vitamins.toml and edit.")
        return 2

    with TOML_PATH.open("rb") as f:
        data = tomllib.load(f)

    items = data.get("items", [])
    if not items:
        print("No [[items]] in vitamins.toml.")
        return 1

    create_all()
    upserted = 0
    with session_scope() as s:
        for i, item in enumerate(items):
            slug = item.get("slug")
            if not slug:
                print(f"Skipping item #{i}: missing 'slug'", file=sys.stderr)
                continue
            existing = s.execute(select(m.Vitamin).where(m.Vitamin.slug == slug)).scalar_one_or_none()
            payload = {
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

    print(f"Upserted {upserted} vitamins/medications.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

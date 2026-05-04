"""Unit conversions for Health Connect data.

Health Connect stores everything in SI / coarse units; UI shows human-friendly units.
- Time: ms since epoch (UTC) + zone_offset in seconds.
- Weight: grams.
- Height/distance: meters.
- Energy: calories (not kcal).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone


def ms_to_dt(ms: int | None, zone_offset_s: int | None = None) -> datetime | None:
    if ms is None:
        return None
    base = datetime.fromtimestamp(ms / 1000, tz=UTC)
    if zone_offset_s:
        return base.astimezone(timezone(timedelta(seconds=zone_offset_s)))
    return base


def grams_to_kg(g: float | None) -> float | None:
    return None if g is None else g / 1000.0


def kg_to_lbs(kg: float | None) -> float | None:
    return None if kg is None else kg * 2.2046226218


def meters_to_miles(m: float | None) -> float | None:
    return None if m is None else m * 0.000621371


def meters_to_km(m: float | None) -> float | None:
    return None if m is None else m / 1000.0


def cal_to_kcal(cal: float | None) -> float | None:
    return None if cal is None else cal / 1000.0


def m_to_ft_in(m: float | None) -> tuple[int, float] | None:
    if m is None:
        return None
    total_in = m * 39.3700787
    ft = int(total_in // 12)
    inches = total_in - ft * 12
    return ft, round(inches, 1)

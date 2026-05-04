"""Open a Health Connect SQLite export and yield typed records ready to upsert.

Health Connect's tables share a common shape (uuid BLOB, start/end_time INT ms, app_info_id FK).
We resolve the app FK to a package_name string and emit per-record-type dicts.
"""
from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from health_connect_web.units import ms_to_dt

log = logging.getLogger(__name__)


@contextmanager
def open_export(path: Path) -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()


def _app_packages(con: sqlite3.Connection) -> dict[int, str]:
    return {
        r["row_id"]: r["package_name"]
        for r in con.execute("SELECT row_id, package_name FROM application_info_table")
    }


def _uuid_hex(b: bytes | None) -> str | None:
    return None if b is None else b.hex()


def _common(row: sqlite3.Row, apps: dict[int, str]) -> dict[str, Any]:
    return {
        "uuid": _uuid_hex(row["uuid"]),
        "app_package": apps.get(row["app_info_id"]),
        "last_modified_at": ms_to_dt(row["last_modified_time"]),
    }


# ---- One extractor per table we care about. Each yields plain dicts. ----


def iter_blood_pressure(con: sqlite3.Connection, apps: dict[int, str]) -> Iterator[dict]:
    for r in con.execute(
        "SELECT uuid, last_modified_time, app_info_id, time, zone_offset, "
        "systolic, diastolic, body_position, measurement_location "
        "FROM blood_pressure_record_table"
    ):
        yield {
            **_common(r, apps),
            "time": ms_to_dt(r["time"], r["zone_offset"]),
            "systolic": r["systolic"],
            "diastolic": r["diastolic"],
            "body_position": str(r["body_position"]) if r["body_position"] is not None else None,
            "measurement_location": (
                str(r["measurement_location"]) if r["measurement_location"] is not None else None
            ),
        }


def iter_resting_heart_rate(con: sqlite3.Connection, apps: dict[int, str]) -> Iterator[dict]:
    for r in con.execute(
        "SELECT uuid, last_modified_time, app_info_id, time, zone_offset, beats_per_minute "
        "FROM resting_heart_rate_record_table"
    ):
        yield {
            **_common(r, apps),
            "time": ms_to_dt(r["time"], r["zone_offset"]),
            "bpm": r["beats_per_minute"],
        }


def iter_heart_rate(con: sqlite3.Connection, apps: dict[int, str]) -> Iterator[dict]:
    """Yield heart-rate parents WITH their child series, joined."""
    parents = list(
        con.execute(
            "SELECT row_id, uuid, last_modified_time, app_info_id, "
            "start_time, start_zone_offset, end_time, end_zone_offset "
            "FROM heart_rate_record_table"
        )
    )
    for r in parents:
        # Dedupe by epoch_millis: the source occasionally has duplicate
        # (parent_key, epoch_millis) samples; keep the last reading per timestamp.
        sample_by_ts: dict[int, int] = {}
        for s in con.execute(
            "SELECT epoch_millis, beats_per_minute FROM heart_rate_record_series_table "
            "WHERE parent_key = ? ORDER BY epoch_millis",
            (r["row_id"],),
        ):
            sample_by_ts[s["epoch_millis"]] = s["beats_per_minute"]
        samples = [
            {"ts": ms_to_dt(ts), "bpm": bpm}
            for ts, bpm in sorted(sample_by_ts.items())
        ]
        yield {
            **_common(r, apps),
            "start_time": ms_to_dt(r["start_time"], r["start_zone_offset"]),
            "end_time": ms_to_dt(r["end_time"], r["end_zone_offset"]),
            "samples": samples,
        }


def iter_steps(con: sqlite3.Connection, apps: dict[int, str]) -> Iterator[dict]:
    for r in con.execute(
        "SELECT uuid, last_modified_time, app_info_id, "
        "start_time, start_zone_offset, end_time, end_zone_offset, count "
        "FROM steps_record_table"
    ):
        yield {
            **_common(r, apps),
            "start_time": ms_to_dt(r["start_time"], r["start_zone_offset"]),
            "end_time": ms_to_dt(r["end_time"], r["end_zone_offset"]),
            "count": r["count"],
        }


def iter_weight(con: sqlite3.Connection, apps: dict[int, str]) -> Iterator[dict]:
    for r in con.execute(
        "SELECT uuid, last_modified_time, app_info_id, time, zone_offset, weight "
        "FROM weight_record_table"
    ):
        yield {
            **_common(r, apps),
            "time": ms_to_dt(r["time"], r["zone_offset"]),
            "weight_g": r["weight"],
        }


def iter_body_fat(con: sqlite3.Connection, apps: dict[int, str]) -> Iterator[dict]:
    for r in con.execute(
        "SELECT uuid, last_modified_time, app_info_id, time, zone_offset, percentage "
        "FROM body_fat_record_table"
    ):
        yield {
            **_common(r, apps),
            "time": ms_to_dt(r["time"], r["zone_offset"]),
            "percentage": r["percentage"],
        }


def iter_height(con: sqlite3.Connection, apps: dict[int, str]) -> Iterator[dict]:
    for r in con.execute(
        "SELECT uuid, last_modified_time, app_info_id, time, zone_offset, height "
        "FROM height_record_table"
    ):
        yield {
            **_common(r, apps),
            "time": ms_to_dt(r["time"], r["zone_offset"]),
            "height_m": r["height"],
        }


def _iter_start_end_value(table: str, value_col: str, value_key: str):
    def _impl(con: sqlite3.Connection, apps: dict[int, str]) -> Iterator[dict]:
        for r in con.execute(
            f"SELECT uuid, last_modified_time, app_info_id, "
            f"start_time, start_zone_offset, end_time, end_zone_offset, {value_col} "
            f"FROM {table}"
        ):
            yield {
                **_common(r, apps),
                "start_time": ms_to_dt(r["start_time"], r["start_zone_offset"]),
                "end_time": ms_to_dt(r["end_time"], r["end_zone_offset"]),
                value_key: r[value_col],
            }

    _impl.__name__ = f"iter_{table}"
    return _impl


iter_active_calories = _iter_start_end_value("active_calories_burned_record_table", "energy", "energy_cal")
iter_total_calories = _iter_start_end_value("total_calories_burned_record_table", "energy", "energy_cal")
iter_distance = _iter_start_end_value("distance_record_table", "distance", "distance_m")
iter_floors_climbed = _iter_start_end_value("floors_climbed_record_table", "floors", "floors")
iter_elevation_gained = _iter_start_end_value("elevation_gained_record_table", "elevation", "elevation_m")


def iter_exercise_session(con: sqlite3.Connection, apps: dict[int, str]) -> Iterator[dict]:
    for r in con.execute(
        "SELECT uuid, last_modified_time, app_info_id, "
        "start_time, start_zone_offset, end_time, end_zone_offset, "
        "exercise_type, title, notes "
        "FROM exercise_session_record_table"
    ):
        yield {
            **_common(r, apps),
            "start_time": ms_to_dt(r["start_time"], r["start_zone_offset"]),
            "end_time": ms_to_dt(r["end_time"], r["end_zone_offset"]),
            "exercise_type": r["exercise_type"],
            "title": r["title"],
            "notes": r["notes"],
        }


def iter_sleep_session(con: sqlite3.Connection, apps: dict[int, str]) -> Iterator[dict]:
    parents = list(
        con.execute(
            "SELECT row_id, uuid, last_modified_time, app_info_id, "
            "start_time, start_zone_offset, end_time, end_zone_offset, title, notes "
            "FROM sleep_session_record_table"
        )
    )
    for r in parents:
        # Dedupe stages on start_time (source may double-write).
        stage_by_start: dict[int, sqlite3.Row] = {}
        for s in con.execute(
            "SELECT stage_start_time, stage_end_time, stage_type FROM sleep_stages_table "
            "WHERE parent_key = ? ORDER BY stage_start_time",
            (r["row_id"],),
        ):
            stage_by_start[s["stage_start_time"]] = s
        stages = [
            {
                "start_time": ms_to_dt(s["stage_start_time"]),
                "end_time": ms_to_dt(s["stage_end_time"]),
                "stage_type": s["stage_type"],
            }
            for s in stage_by_start.values()
        ]
        yield {
            **_common(r, apps),
            "start_time": ms_to_dt(r["start_time"], r["start_zone_offset"]),
            "end_time": ms_to_dt(r["end_time"], r["end_zone_offset"]),
            "title": r["title"],
            "notes": r["notes"],
            "stages": stages,
        }


# Mapping from our model field -> (Health Connect column name, conversion factor from
# HC's stored value to our column's unit).
#
# Health Connect stores ALL nutrients in *grams*, including minerals/vitamins that
# anyone reading them expects in mg or μg. The conversion factor here normalizes
# at sync time so the DB column actually contains the unit its name advertises.
#
# Energy is the exception: HC stores it in *calories* (not kcal); we keep it as cal
# in the DB (column suffix `_cal`) and divide by 1000 only when displaying kcal.
_GRAMS_PER_MG = 1000.0
_GRAMS_PER_UG = 1_000_000.0
NUTRITION_FIELDS: dict[str, tuple[str, float]] = {
    # macros stored as grams -> grams (no conversion)
    "energy_cal": ("energy", 1.0),
    "energy_from_fat_cal": ("energy_from_fat", 1.0),
    "total_fat_g": ("total_fat", 1.0),
    "saturated_fat_g": ("saturated_fat", 1.0),
    "trans_fat_g": ("trans_fat", 1.0),
    "monounsaturated_fat_g": ("monounsaturated_fat", 1.0),
    "polyunsaturated_fat_g": ("polyunsaturated_fat", 1.0),
    "unsaturated_fat_g": ("unsaturated_fat", 1.0),
    "total_carbohydrate_g": ("total_carbohydrate", 1.0),
    "sugar_g": ("sugar", 1.0),
    "dietary_fiber_g": ("dietary_fiber", 1.0),
    "protein_g": ("protein", 1.0),
    # mg fields: HC grams -> mg means *1000
    "cholesterol_mg": ("cholesterol", _GRAMS_PER_MG),
    "sodium_mg": ("sodium", _GRAMS_PER_MG),
    "potassium_mg": ("potassium", _GRAMS_PER_MG),
    "caffeine_mg": ("caffeine", _GRAMS_PER_MG),
    "vitamin_c_mg": ("vitamin_c", _GRAMS_PER_MG),
    "vitamin_e_mg": ("vitamin_e", _GRAMS_PER_MG),
    "vitamin_b6_mg": ("vitamin_b6", _GRAMS_PER_MG),
    "thiamin_mg": ("thiamin", _GRAMS_PER_MG),
    "riboflavin_mg": ("riboflavin", _GRAMS_PER_MG),
    "niacin_mg": ("niacin", _GRAMS_PER_MG),
    "pantothenic_acid_mg": ("pantothenic_acid", _GRAMS_PER_MG),
    "calcium_mg": ("calcium", _GRAMS_PER_MG),
    "iron_mg": ("iron", _GRAMS_PER_MG),
    "magnesium_mg": ("magnesium", _GRAMS_PER_MG),
    "phosphorus_mg": ("phosphorus", _GRAMS_PER_MG),
    "zinc_mg": ("zinc", _GRAMS_PER_MG),
    "copper_mg": ("copper", _GRAMS_PER_MG),
    "manganese_mg": ("manganese", _GRAMS_PER_MG),
    "chloride_mg": ("chloride", _GRAMS_PER_MG),
    # μg fields: HC grams -> μg means *1_000_000
    "vitamin_a_ug": ("vitamin_a", _GRAMS_PER_UG),
    "vitamin_d_ug": ("vitamin_d", _GRAMS_PER_UG),
    "vitamin_k_ug": ("vitamin_k", _GRAMS_PER_UG),
    "vitamin_b12_ug": ("vitamin_b12", _GRAMS_PER_UG),
    "folate_ug": ("folate", _GRAMS_PER_UG),
    "folic_acid_ug": ("folic_acid", _GRAMS_PER_UG),
    "biotin_ug": ("biotin", _GRAMS_PER_UG),
    "selenium_ug": ("selenium", _GRAMS_PER_UG),
    "chromium_ug": ("chromium", _GRAMS_PER_UG),
    "iodine_ug": ("iodine", _GRAMS_PER_UG),
    "molybdenum_ug": ("molybdenum", _GRAMS_PER_UG),
}


def _normalize_nutrient(v: float | None) -> float | None:
    """Health Connect emits the float64 sentinel `5e-324` (Double.MIN_VALUE) for unknown values.
    Treat anything <= 1e-300 as missing.
    """
    if v is None:
        return None
    if v <= 1e-300:
        return None
    return v


# Per-record sanity caps in the *destination* unit (after the gram->mg/μg conversion).
# A single meal/supplement should never exceed these; values above are MacroFactor (or
# whichever logger) data-entry mistakes, like an entry that stored grams of thiamin
# where it meant mg. We drop them so the daily averages don't get destroyed by one bad row.
# Caps are roughly 1000x the FDA Daily Value, generous enough for any legitimate megadose.
_NUTRITION_RECORD_CAPS: dict[str, float] = {
    # macros (grams)
    "total_fat_g": 1000.0,
    "saturated_fat_g": 500.0,
    "trans_fat_g": 100.0,
    "monounsaturated_fat_g": 500.0,
    "polyunsaturated_fat_g": 500.0,
    "unsaturated_fat_g": 500.0,
    "total_carbohydrate_g": 2000.0,
    "sugar_g": 1000.0,
    "dietary_fiber_g": 500.0,
    "protein_g": 1000.0,
    # mg
    "cholesterol_mg": 10_000.0,
    "sodium_mg": 30_000.0,
    "potassium_mg": 30_000.0,
    "caffeine_mg": 5_000.0,
    "vitamin_c_mg": 10_000.0,
    "vitamin_e_mg": 1_500.0,
    "vitamin_b6_mg": 1_000.0,
    "thiamin_mg": 1_000.0,
    "riboflavin_mg": 1_000.0,
    "niacin_mg": 5_000.0,
    "pantothenic_acid_mg": 1_000.0,
    "calcium_mg": 5_000.0,
    "iron_mg": 500.0,
    "magnesium_mg": 2_000.0,
    "phosphorus_mg": 5_000.0,
    "zinc_mg": 500.0,
    "copper_mg": 50.0,
    "manganese_mg": 50.0,
    "chloride_mg": 30_000.0,
    # μg
    "vitamin_a_ug": 50_000.0,
    "vitamin_d_ug": 500.0,
    "vitamin_k_ug": 5_000.0,
    "vitamin_b12_ug": 5_000.0,
    "folate_ug": 5_000.0,
    "folic_acid_ug": 5_000.0,
    "biotin_ug": 30_000.0,
    "selenium_ug": 5_000.0,
    "chromium_ug": 5_000.0,
    "iodine_ug": 5_000.0,
    "molybdenum_ug": 5_000.0,
}


def _apply_cap(field: str, value: float | None) -> float | None:
    """Drop values that exceed the per-record sanity cap (return None instead)."""
    if value is None:
        return None
    cap = _NUTRITION_RECORD_CAPS.get(field)
    if cap is not None and value > cap:
        log.warning("Dropping outlier %s = %.2f (cap=%.0f)", field, value, cap)
        return None
    return value


def iter_nutrition(con: sqlite3.Connection, apps: dict[int, str]) -> Iterator[dict]:
    hc_cols = [hc for hc, _ in NUTRITION_FIELDS.values()]
    cols = [
        "uuid", "last_modified_time", "app_info_id",
        "start_time", "start_zone_offset", "end_time", "end_zone_offset",
        "meal_name", "meal_type",
        *hc_cols,
    ]
    sql = f"SELECT {', '.join(cols)} FROM nutrition_record_table"
    for r in con.execute(sql):
        out: dict[str, Any] = {
            **_common(r, apps),
            "start_time": ms_to_dt(r["start_time"], r["start_zone_offset"]),
            "end_time": ms_to_dt(r["end_time"], r["end_zone_offset"]),
            "meal_name": r["meal_name"],
            "meal_type": r["meal_type"],
        }
        for our_name, (hc_name, factor) in NUTRITION_FIELDS.items():
            v = _normalize_nutrient(r[hc_name])
            converted = None if v is None else v * factor
            out[our_name] = _apply_cap(our_name, converted)
        yield out


def export_summary(con: sqlite3.Connection) -> dict[str, int]:
    """Return row counts for every record-type table we touch, useful for sync logs."""
    counts: dict[str, int] = {}
    tables = [
        "blood_pressure_record_table",
        "resting_heart_rate_record_table",
        "heart_rate_record_table",
        "heart_rate_record_series_table",
        "steps_record_table",
        "weight_record_table",
        "body_fat_record_table",
        "height_record_table",
        "active_calories_burned_record_table",
        "total_calories_burned_record_table",
        "distance_record_table",
        "floors_climbed_record_table",
        "elevation_gained_record_table",
        "exercise_session_record_table",
        "sleep_session_record_table",
        "sleep_stages_table",
        "nutrition_record_table",
    ]
    for t in tables:
        try:
            (n,) = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()
            counts[t] = n
        except sqlite3.OperationalError:
            counts[t] = 0
    return counts


def export_modified_at(con: sqlite3.Connection) -> datetime | None:
    """Best-effort: the max(last_modified_time) across record tables.

    Useful for showing 'data current as of ...' on the UI when source file metadata is unavailable.
    """
    candidates = [
        "blood_pressure_record_table",
        "heart_rate_record_table",
        "steps_record_table",
        "nutrition_record_table",
    ]
    best: int | None = None
    for t in candidates:
        try:
            (m,) = con.execute(f'SELECT MAX(last_modified_time) FROM "{t}"').fetchone()
            if m is not None and (best is None or m > best):
                best = m
        except sqlite3.OperationalError:
            continue
    return ms_to_dt(best)

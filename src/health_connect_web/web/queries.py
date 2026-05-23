"""Read-side queries for the page templates.

Kept deliberately simple: each function returns plain dicts/lists ready for Jinja.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from health_connect_web import models as m


def _ago(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


@dataclass
class TimeSeriesPoint:
    t: str  # ISO date or datetime
    v: float | int


# ---------- General Health ----------


def latest_blood_pressure(s: Session) -> m.BloodPressure | None:
    return s.execute(
        select(m.BloodPressure).order_by(desc(m.BloodPressure.time)).limit(1)
    ).scalar_one_or_none()


def recent_blood_pressure(s: Session, days: int = 90) -> list[m.BloodPressure]:
    return list(
        s.execute(
            select(m.BloodPressure).where(m.BloodPressure.time >= _ago(days)).order_by(m.BloodPressure.time)
        ).scalars()
    )


def latest_weight(s: Session) -> m.Weight | None:
    return s.execute(select(m.Weight).order_by(desc(m.Weight.time)).limit(1)).scalar_one_or_none()


def recent_weight(s: Session, days: int = 180) -> list[m.Weight]:
    return list(
        s.execute(select(m.Weight).where(m.Weight.time >= _ago(days)).order_by(m.Weight.time)).scalars()
    )


def latest_body_fat(s: Session) -> m.BodyFat | None:
    return s.execute(select(m.BodyFat).order_by(desc(m.BodyFat.time)).limit(1)).scalar_one_or_none()


def latest_height(s: Session) -> m.Height | None:
    return s.execute(select(m.Height).order_by(desc(m.Height.time)).limit(1)).scalar_one_or_none()


def recent_resting_hr(s: Session, days: int = 60) -> list[m.RestingHeartRate]:
    return list(
        s.execute(
            select(m.RestingHeartRate)
            .where(m.RestingHeartRate.time >= _ago(days))
            .order_by(m.RestingHeartRate.time)
        ).scalars()
    )


def daily_steps(s: Session, days: int = 30) -> list[TimeSeriesPoint]:
    """Aggregate steps by local date (UTC date, Health Connect's local_date varies by app)."""
    cutoff = _ago(days)
    rows = s.execute(
        select(
            func.date(m.Steps.start_time).label("d"),
            func.sum(m.Steps.count).label("n"),
        )
        .where(m.Steps.start_time >= cutoff)
        .group_by(func.date(m.Steps.start_time))
        .order_by(func.date(m.Steps.start_time))
    ).all()
    return [TimeSeriesPoint(t=str(r.d), v=int(r.n or 0)) for r in rows]


def daily_calories_burned(s: Session, days: int = 30) -> list[TimeSeriesPoint]:
    cutoff = _ago(days)
    rows = s.execute(
        select(
            func.date(m.TotalCalories.start_time).label("d"),
            func.sum(m.TotalCalories.energy_cal).label("e"),
        )
        .where(m.TotalCalories.start_time >= cutoff)
        .group_by(func.date(m.TotalCalories.start_time))
        .order_by(func.date(m.TotalCalories.start_time))
    ).all()
    # Convert calories -> kcal for display.
    return [TimeSeriesPoint(t=str(r.d), v=round((r.e or 0) / 1000.0, 0)) for r in rows]


def recent_exercise_sessions(s: Session, limit: int = 12) -> list[m.ExerciseSession]:
    return list(
        s.execute(
            select(m.ExerciseSession).order_by(desc(m.ExerciseSession.start_time)).limit(limit)
        ).scalars()
    )


def recent_sleep_sessions(s: Session, days: int = 30) -> list[dict[str, Any]]:
    cutoff = _ago(days)
    sessions = list(
        s.execute(
            select(m.SleepSession)
            .where(m.SleepSession.start_time >= cutoff)
            .order_by(desc(m.SleepSession.start_time))
        ).scalars()
    )
    out: list[dict[str, Any]] = []
    for ss in sessions:
        duration_h = (ss.end_time - ss.start_time).total_seconds() / 3600.0
        out.append(
            {
                "start": ss.start_time,
                "end": ss.end_time,
                "duration_h": round(duration_h, 2),
                "title": ss.title,
            }
        )
    return out


# ---------- Food ----------


def latest_nutrition_at(s: Session) -> datetime | None:
    """The timestamp of Joe's most recent food log, or None if there's none."""
    return s.execute(select(func.max(m.Nutrition.start_time))).scalar()


def _nutrition_window(s: Session, days: int) -> tuple[datetime, datetime] | None:
    """Window of length `days` ending at the most recent food log.

    Returns None when nothing has been logged. Anchoring to the latest log
    (instead of `now()`) keeps the Food page informative even after stretches
    where Joe didn't log meals.
    """
    end = latest_nutrition_at(s)
    if end is None:
        return None
    return end - timedelta(days=days), end


def daily_nutrition(s: Session, days: int = 14) -> list[dict[str, Any]]:
    """Sum macros and calories by date for the most recent N-day window of logs."""
    win = _nutrition_window(s, days)
    if win is None:
        return []
    start, end = win
    rows = s.execute(
        select(
            func.date(m.Nutrition.start_time).label("d"),
            func.sum(m.Nutrition.energy_cal).label("e"),
            func.sum(m.Nutrition.protein_g).label("p"),
            func.sum(m.Nutrition.total_carbohydrate_g).label("c"),
            func.sum(m.Nutrition.total_fat_g).label("f"),
            func.sum(m.Nutrition.dietary_fiber_g).label("fib"),
            func.sum(m.Nutrition.sugar_g).label("sug"),
            func.sum(m.Nutrition.sodium_mg).label("na"),
        )
        .where(m.Nutrition.start_time >= start, m.Nutrition.start_time <= end)
        .group_by(func.date(m.Nutrition.start_time))
        .order_by(func.date(m.Nutrition.start_time))
    ).all()
    return [
        {
            "date": str(r.d),
            "kcal": round((r.e or 0) / 1000.0, 0),
            "protein_g": round(r.p or 0, 1),
            "carbs_g": round(r.c or 0, 1),
            "fat_g": round(r.f or 0, 1),
            "fiber_g": round(r.fib or 0, 1),
            "sugar_g": round(r.sug or 0, 1),
            "sodium_mg": round(r.na or 0, 0),
        }
        for r in rows
    ]


# FDA Daily Values (2016 update, healthy adults, 2000-kcal reference diet), the values
# printed on US "Nutrition Facts" labels. Keeps %DV familiar to anyone who reads food labels.
# (label, sqlalchemy column, unit, daily_value)
_MICROS: list[tuple[str, Any, str, float]] = [
    ("Vitamin A", m.Nutrition.vitamin_a_ug, "µg", 900.0),
    ("Vitamin C", m.Nutrition.vitamin_c_mg, "mg", 90.0),
    ("Vitamin D", m.Nutrition.vitamin_d_ug, "µg", 20.0),
    ("Vitamin E", m.Nutrition.vitamin_e_mg, "mg", 15.0),
    ("Vitamin K", m.Nutrition.vitamin_k_ug, "µg", 120.0),
    ("Vitamin B6", m.Nutrition.vitamin_b6_mg, "mg", 1.7),
    ("Vitamin B12", m.Nutrition.vitamin_b12_ug, "µg", 2.4),
    ("Thiamin (B1)", m.Nutrition.thiamin_mg, "mg", 1.2),
    ("Riboflavin (B2)", m.Nutrition.riboflavin_mg, "mg", 1.3),
    ("Niacin (B3)", m.Nutrition.niacin_mg, "mg", 16.0),
    ("Folate", m.Nutrition.folate_ug, "µg", 400.0),
    ("Pantothenic acid", m.Nutrition.pantothenic_acid_mg, "mg", 5.0),
    ("Calcium", m.Nutrition.calcium_mg, "mg", 1300.0),
    ("Iron", m.Nutrition.iron_mg, "mg", 18.0),
    ("Magnesium", m.Nutrition.magnesium_mg, "mg", 420.0),
    ("Phosphorus", m.Nutrition.phosphorus_mg, "mg", 1250.0),
    ("Zinc", m.Nutrition.zinc_mg, "mg", 11.0),
    ("Copper", m.Nutrition.copper_mg, "mg", 0.9),
    ("Manganese", m.Nutrition.manganese_mg, "mg", 2.3),
    ("Selenium", m.Nutrition.selenium_ug, "µg", 55.0),
    ("Sodium", m.Nutrition.sodium_mg, "mg", 2300.0),
    ("Potassium", m.Nutrition.potassium_mg, "mg", 4700.0),
]


def micronutrient_averages(s: Session, days: int = 7) -> list[dict[str, Any]]:
    """Average daily intake for selected micros over the most recent N-day window of logs.

    Returns a list of dicts with `name`, `amount`, `unit`, `dv`, `pct_dv` so the template
    can show "176 mg" alongside "196% DV" the way MacroFactor does.

    Daily-day averaging: sum per day first, then average across days with logging, so
    days with zero food logs don't drag the average down.
    """
    win = _nutrition_window(s, days)
    if win is None:
        return []
    start, end = win
    out: list[dict[str, Any]] = []
    for label, col, unit, dv in _MICROS:
        per_day = s.execute(
            select(func.date(m.Nutrition.start_time).label("d"), func.sum(col).label("v"))
            .where(m.Nutrition.start_time >= start, m.Nutrition.start_time <= end)
            .group_by(func.date(m.Nutrition.start_time))
        ).all()
        vals = [(r.v or 0.0) for r in per_day]
        amount = sum(vals) / len(vals) if vals else 0.0
        out.append(
            {
                "name": label,
                "amount": round(amount, 1 if unit == "mg" or unit == "µg" else 2),
                "unit": unit,
                "dv": dv,
                "pct_dv": round(100.0 * amount / dv) if dv else None,
            }
        )
    return out


def top_meals(s: Session, days: int = 30, limit: int = 15) -> list[dict[str, Any]]:
    win = _nutrition_window(s, days)
    if win is None:
        return []
    start, end = win
    rows = s.execute(
        select(
            m.Nutrition.meal_name,
            func.count().label("n"),
            func.sum(m.Nutrition.energy_cal).label("e"),
        )
        .where(
            m.Nutrition.start_time >= start,
            m.Nutrition.start_time <= end,
            m.Nutrition.meal_name.is_not(None),
        )
        .group_by(m.Nutrition.meal_name)
        .order_by(desc("n"))
        .limit(limit)
    ).all()
    return [
        {
            "name": r.meal_name,
            "count": r.n,
            "total_kcal": round((r.e or 0) / 1000.0, 0),
        }
        for r in rows
    ]


# ---------- Vitamins ----------


def vitamins(s: Session) -> list[m.Vitamin]:
    return list(s.execute(select(m.Vitamin).order_by(m.Vitamin.sort_order, m.Vitamin.name)).scalars())


def herbs(s: Session) -> list[m.Herb]:
    return list(s.execute(select(m.Herb).order_by(m.Herb.sort_order, m.Herb.name)).scalars())


# ---------- Allowlist (runtime-managed via /admin) ----------


def list_allowed_emails(s: Session) -> list[m.AllowedEmail]:
    return list(s.execute(select(m.AllowedEmail).order_by(m.AllowedEmail.email)).scalars())


def is_email_in_db_allowlist(s: Session, email: str) -> bool:
    e = email.strip().lower()
    if not e:
        return False
    row = s.execute(select(m.AllowedEmail).where(m.AllowedEmail.email == e)).scalar_one_or_none()
    return row is not None


def add_allowed_email(
    s: Session, email: str, added_by: str | None = None, note: str | None = None
) -> m.AllowedEmail:
    e = email.strip().lower()
    row = m.AllowedEmail(email=e, added_at=datetime.now(UTC), added_by=added_by, note=note)
    s.add(row)
    s.flush()
    return row


def remove_allowed_email(s: Session, allowed_id: int) -> bool:
    row = s.get(m.AllowedEmail, allowed_id)
    if row is None:
        return False
    s.delete(row)
    return True


def seed_allowed_emails_from_env_if_empty(s: Session) -> int:
    """If the allowed_email table is empty, populate from ALLOWED_EMAILS env var.

    Idempotent: subsequent calls (after the table has at least one row) are a no-op.
    Returns the number of inserted rows.
    """
    from health_connect_web.config import get_settings

    existing = s.execute(select(func.count()).select_from(m.AllowedEmail)).scalar() or 0
    if existing:
        return 0
    settings = get_settings()
    emails = [e for e in settings.allowed_emails_list if e]
    if not emails:
        return 0
    now = datetime.now(UTC)
    for e in emails:
        s.add(m.AllowedEmail(email=e, added_at=now, added_by="env-seed"))
    s.flush()
    return len(emails)


# (label, model, primary timestamp column) per Health-Connect-sourced table we surface.
_FRESHNESS_SOURCES: list[tuple[str, Any, Any]] = [
    ("Blood pressure", m.BloodPressure, m.BloodPressure.time),
    ("Weight", m.Weight, m.Weight.time),
    ("Body fat", m.BodyFat, m.BodyFat.time),
    ("Resting HR", m.RestingHeartRate, m.RestingHeartRate.time),
    ("Heart rate", m.HeartRate, m.HeartRate.start_time),
    ("Steps", m.Steps, m.Steps.start_time),
    ("Active calories", m.ActiveCalories, m.ActiveCalories.start_time),
    ("Total calories", m.TotalCalories, m.TotalCalories.start_time),
    ("Distance", m.Distance, m.Distance.start_time),
    ("Exercise session", m.ExerciseSession, m.ExerciseSession.start_time),
    ("Sleep session", m.SleepSession, m.SleepSession.start_time),
    ("Nutrition", m.Nutrition, m.Nutrition.start_time),
]


def recent_sync_runs(s: Session, limit: int = 10) -> list[m.SyncRun]:
    """Audit log of recent sync jobs, newest first. Drives the /data page table."""
    return list(s.execute(select(m.SyncRun).order_by(desc(m.SyncRun.started_at)).limit(limit)).scalars())


def data_freshness(s: Session) -> list[dict[str, Any]]:
    """Latest record timestamp + row count per Health-Connect-sourced table.

    Used on Overview to diagnose 'sync ran but data didn't advance' situations.
    A table whose latest row lags far behind the others points at the upstream
    integration (e.g. MacroFactor -> Health Connect) being the broken link.
    """
    out: list[dict[str, Any]] = []
    for label, _model, time_col in _FRESHNESS_SOURCES:
        row = s.execute(select(func.count(), func.max(time_col))).one()
        count, latest = row[0], row[1]
        out.append({"label": label, "count": count, "latest": latest})
    return out


# FDA Daily Values + IOM Tolerable Upper Intake Levels for nutrients we tally on /supplements.
# (display_name, unit, daily_value, upper_limit_or_None)
_DV_INFO: dict[str, tuple[str, str, float, float | None]] = {
    "vitamin_a_ug": ("Vitamin A", "µg", 900.0, 3000.0),
    "vitamin_c_mg": ("Vitamin C", "mg", 90.0, 2000.0),
    "vitamin_d_ug": ("Vitamin D", "µg", 20.0, 100.0),
    "vitamin_e_mg": ("Vitamin E", "mg", 15.0, 1000.0),
    "vitamin_k_ug": ("Vitamin K", "µg", 120.0, None),
    "vitamin_b6_mg": ("Vitamin B6", "mg", 1.7, 100.0),
    "vitamin_b12_ug": ("Vitamin B12", "µg", 2.4, None),
    "thiamin_mg": ("Thiamin (B1)", "mg", 1.2, None),
    "riboflavin_mg": ("Riboflavin (B2)", "mg", 1.3, None),
    "niacin_mg": ("Niacin (B3)", "mg", 16.0, 35.0),
    "folate_ug": ("Folate", "µg", 400.0, 1000.0),
    "pantothenic_acid_mg": ("Pantothenic acid", "mg", 5.0, None),
    "dietary_fiber_g": ("Fiber", "g", 28.0, None),
    "biotin_ug": ("Biotin", "µg", 30.0, None),
    "calcium_mg": ("Calcium", "mg", 1300.0, 2500.0),
    "iron_mg": ("Iron", "mg", 18.0, 45.0),
    "magnesium_mg": ("Magnesium", "mg", 420.0, 350.0),  # supplemental UL
    "phosphorus_mg": ("Phosphorus", "mg", 1250.0, 4000.0),
    "zinc_mg": ("Zinc", "mg", 11.0, 40.0),
    "copper_mg": ("Copper", "mg", 0.9, 10.0),
    "manganese_mg": ("Manganese", "mg", 2.3, 11.0),
    "selenium_ug": ("Selenium", "µg", 55.0, 400.0),
    "molybdenum_ug": ("Molybdenum", "µg", 45.0, 2000.0),
    "iodine_ug": ("Iodine", "µg", 150.0, 1100.0),
    "chromium_ug": ("Chromium", "µg", 35.0, None),
    "sodium_mg": ("Sodium", "mg", 2300.0, None),
    "potassium_mg": ("Potassium", "mg", 4700.0, None),
}


def _food_avg_by_field(s: Session, days: int = 7) -> dict[str, float]:
    """Per-nutrient average daily intake from food, for any DV-tracked field on Nutrition."""
    win = _nutrition_window(s, days)
    if win is None:
        return {}
    start, end = win
    out: dict[str, float] = {}
    for field in _DV_INFO:
        col = getattr(m.Nutrition, field, None)
        if col is None:
            continue
        per_day = s.execute(
            select(func.date(m.Nutrition.start_time).label("d"), func.sum(col).label("v"))
            .where(m.Nutrition.start_time >= start, m.Nutrition.start_time <= end)
            .group_by(func.date(m.Nutrition.start_time))
        ).all()
        vals = [(r.v or 0.0) for r in per_day]
        out[field] = (sum(vals) / len(vals)) if vals else 0.0
    return out


def _supplement_totals_by_field(s: Session) -> dict[str, list[tuple[str, float]]]:
    """Per-nutrient daily total from supplements, with item-level breakdown."""
    items = list(s.execute(select(m.Vitamin)).scalars())
    by_field: dict[str, list[tuple[str, float]]] = {}
    for it in items:
        contrib = it.daily_contrib or {}
        for field, amount in contrib.items():
            if isinstance(amount, (int, float)):
                by_field.setdefault(field, []).append((it.name, float(amount)))
    return by_field


def combined_daily_intake(s: Session, food_days: int = 7) -> list[dict[str, Any]]:
    """Combined food (avg over the last `food_days` of logs) + supplements daily.

    Skips nutrients where total intake is 0 across both sources.
    """
    food_avg = _food_avg_by_field(s, days=food_days)
    supp_totals = _supplement_totals_by_field(s)

    out: list[dict[str, Any]] = []
    for field, (name, unit, dv, ul) in _DV_INFO.items():
        food_v = food_avg.get(field, 0.0)
        supp_sources = supp_totals.get(field, [])
        supp_total = sum(a for _, a in supp_sources)
        total = food_v + supp_total
        if total <= 0:
            continue
        out.append(
            {
                "name": name,
                "unit": unit,
                "food": round(food_v, 1),
                "supplements": round(supp_total, 1),
                "total": round(total, 1),
                "dv": dv,
                "pct_dv": round(100.0 * total / dv) if dv else None,
                "ul": ul,
                "pct_ul": round(100.0 * total / ul) if ul else None,
                "supp_sources": supp_sources,
            }
        )
    out.sort(key=lambda r: -(r["pct_dv"] or 0))
    return out


def supplement_dv_tally(s: Session) -> list[dict[str, Any]]:
    """Sum each item's `daily_contrib` across the stack and compare to FDA DV + UL.

    Returns rows for nutrients that any item contributes to, sorted by % DV descending.
    Each row carries a list of (item_name, amount) so the template can show the breakdown.
    """
    items = list(s.execute(select(m.Vitamin)).scalars())
    by_field: dict[str, list[tuple[str, float]]] = {}
    for it in items:
        contrib = it.daily_contrib or {}
        for field, amount in contrib.items():
            if not isinstance(amount, (int, float)):
                continue
            by_field.setdefault(field, []).append((it.name, float(amount)))

    out: list[dict[str, Any]] = []
    for field, info in _DV_INFO.items():
        if field not in by_field:
            continue
        sources = by_field[field]
        name, unit, dv, ul = info
        total = sum(a for _, a in sources)
        out.append(
            {
                "name": name,
                "unit": unit,
                "total": round(total, 2),
                "dv": dv,
                "pct_dv": round(100.0 * total / dv) if dv else None,
                "ul": ul,
                "pct_ul": (round(100.0 * total / ul) if ul else None),
                "sources": sources,
            }
        )
    out.sort(key=lambda r: -(r["pct_dv"] or 0))
    return out


# ---------- Misc ----------


def latest_sync(s: Session) -> m.SyncRun | None:
    return s.execute(select(m.SyncRun).order_by(desc(m.SyncRun.started_at)).limit(1)).scalar_one_or_none()


# --- Per-chart payload functions for /health (used by both initial render and the
#     dropdown-driven /api/health/{chart} endpoint).
#
# All windows anchor to the most recent record for that metric so a "7-day" view
# always shows the last 7 days of actual data, even if my latest reading is older
# than that (e.g. I take BP every few days). Same pattern as the Food page.


def _anchored_rows(s: Session, model, time_col, days: int) -> list:
    end = s.execute(select(func.max(time_col))).scalar()
    if end is None:
        return []
    start = end - timedelta(days=days)
    return list(
        s.execute(select(model).where(time_col >= start, time_col <= end).order_by(time_col)).scalars()
    )


def bp_chart_payload(s: Session, days: int = 7) -> dict[str, list]:
    rows = _anchored_rows(s, m.BloodPressure, m.BloodPressure.time, days)
    return {
        "labels": [r.time.strftime("%Y-%m-%d") for r in rows],
        "systolic": [r.systolic for r in rows],
        "diastolic": [r.diastolic for r in rows],
    }


def weight_chart_payload(s: Session, days: int = 7) -> dict[str, list]:
    rows = _anchored_rows(s, m.Weight, m.Weight.time, days)
    return {
        "labels": [r.time.strftime("%Y-%m-%d") for r in rows],
        "kg": [round(r.weight_g / 1000.0, 1) for r in rows],
    }


def steps_chart_payload(s: Session, days: int = 7) -> dict[str, list]:
    end = s.execute(select(func.max(m.Steps.start_time))).scalar()
    if end is None:
        return {"labels": [], "values": []}
    start = end - timedelta(days=days)
    rows = s.execute(
        select(
            func.date(m.Steps.start_time).label("d"),
            func.sum(m.Steps.count).label("n"),
        )
        .where(m.Steps.start_time >= start, m.Steps.start_time <= end)
        .group_by(func.date(m.Steps.start_time))
        .order_by(func.date(m.Steps.start_time))
    ).all()
    return {"labels": [str(r.d) for r in rows], "values": [int(r.n or 0) for r in rows]}


def calories_chart_payload(s: Session, days: int = 7) -> dict[str, list]:
    end = s.execute(select(func.max(m.TotalCalories.start_time))).scalar()
    if end is None:
        return {"labels": [], "values": []}
    start = end - timedelta(days=days)
    rows = s.execute(
        select(
            func.date(m.TotalCalories.start_time).label("d"),
            func.sum(m.TotalCalories.energy_cal).label("e"),
        )
        .where(m.TotalCalories.start_time >= start, m.TotalCalories.start_time <= end)
        .group_by(func.date(m.TotalCalories.start_time))
        .order_by(func.date(m.TotalCalories.start_time))
    ).all()
    return {
        "labels": [str(r.d) for r in rows],
        "values": [round((r.e or 0) / 1000.0, 0) for r in rows],
    }


def rhr_chart_payload(s: Session, days: int = 7) -> dict[str, list]:
    rows = _anchored_rows(s, m.RestingHeartRate, m.RestingHeartRate.time, days)
    return {
        "labels": [r.time.strftime("%Y-%m-%d") for r in rows],
        "values": [r.bpm for r in rows],
    }


HEALTH_CHART_BUILDERS = {
    "bp": bp_chart_payload,
    "weight": weight_chart_payload,
    "steps": steps_chart_payload,
    "calories": calories_chart_payload,
    "rhr": rhr_chart_payload,
}


def health_chart_data(s: Session, default_days: int = 7) -> dict[str, dict[str, list]]:
    """Initial chart payloads for /health. Each chart has its own dropdown that can
    fetch a different window via /api/health/{chart}."""
    return {kind: fn(s, days=default_days) for kind, fn in HEALTH_CHART_BUILDERS.items()}


def food_chart_data(daily: list[dict[str, Any]]) -> dict[str, list]:
    """Pre-shape the macros chart payload."""
    return {
        "labels": [d["date"] for d in daily],
        "kcal": [d["kcal"] for d in daily],
        "protein": [d["protein_g"] for d in daily],
        "carbs": [d["carbs_g"] for d in daily],
        "fat": [d["fat_g"] for d in daily],
    }


def _avg_in_trailing_window(s: Session, model: type, time_col, days: int) -> tuple[list, datetime | None]:
    """Return (rows, anchor_end) for an N-day window ending at the most recent record.

    If there are no records, returns ([], None). Anchoring to the latest reading
    (instead of `now()`) keeps the overview page useful even if data is stale or
    the user logs intermittently (e.g. weekly BP cuffs).
    """
    end = s.execute(select(func.max(time_col))).scalar()
    if end is None:
        return [], None
    start = end - timedelta(days=days)
    rows = list(
        s.execute(select(model).where(time_col >= start, time_col <= end).order_by(time_col)).scalars()
    )
    return rows, end


def landing_summary(s: Session) -> dict[str, Any]:
    """Compact set of headline stats for the index page.

    Cadence per stat: BP 7d, Weight 7d, Resting HR 30d, Steps 30d.
    Each window anchors to the most recent reading for that metric so the page stays
    informative when readings are intermittent.
    """
    bp_rows, bp_end = _avg_in_trailing_window(s, m.BloodPressure, m.BloodPressure.time, days=7)
    bp_avg = (
        {
            "systolic": round(sum(r.systolic for r in bp_rows) / len(bp_rows)),
            "diastolic": round(sum(r.diastolic for r in bp_rows) / len(bp_rows)),
            "n": len(bp_rows),
            "as_of": bp_end,
        }
        if bp_rows
        else None
    )

    w_rows, w_end = _avg_in_trailing_window(s, m.Weight, m.Weight.time, days=7)
    w_avg = (
        {
            "kg": round(sum(r.weight_g for r in w_rows) / len(w_rows) / 1000.0, 1),
            "n": len(w_rows),
            "as_of": w_end,
        }
        if w_rows
        else None
    )

    rhr_rows, rhr_end = _avg_in_trailing_window(s, m.RestingHeartRate, m.RestingHeartRate.time, days=30)
    rhr_avg = (
        {
            "bpm": round(sum(r.bpm for r in rhr_rows) / len(rhr_rows)),
            "n": len(rhr_rows),
            "as_of": rhr_end,
        }
        if rhr_rows
        else None
    )

    steps_rows, steps_end = _avg_in_trailing_window(s, m.Steps, m.Steps.start_time, days=30)
    if steps_rows:
        # Steps come in many small intervals/day; group by date and average daily totals.
        per_day: dict[str, int] = {}
        for r in steps_rows:
            key = r.start_time.date().isoformat()
            per_day[key] = per_day.get(key, 0) + r.count
        steps_avg = {
            "count": round(sum(per_day.values()) / len(per_day)),
            "n": len(per_day),
            "as_of": steps_end,
        }
    else:
        steps_avg = None

    return {
        "bp_avg": bp_avg,
        "weight_avg": w_avg,
        "rhr_avg": rhr_avg,
        "steps_avg": steps_avg,
        "last_sync": latest_sync(s),
    }

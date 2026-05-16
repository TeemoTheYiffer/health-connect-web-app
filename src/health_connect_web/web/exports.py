"""Render a comprehensive Markdown export of the health portfolio.

Designed for two audiences:
- A doctor / nurse who wants a single document covering my stack + recent data.
- An LLM (Claude, etc.) for second-opinion review where context matters.

Pulls live data from the queries layer so the export is always current. No PII
beyond what's already on the site.
"""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from health_connect_web import models as m
from health_connect_web.web import queries


def _h(buf: StringIO, level: int, text: str) -> None:
    buf.write("#" * level + " " + text + "\n\n")


def _line(buf: StringIO, text: str = "") -> None:
    buf.write(text + "\n")


def build_export_markdown(s: Session) -> str:
    buf = StringIO()
    now = datetime.now(UTC)

    _h(buf, 1, "Health Portfolio Export")
    _line(buf, f"Exported: {now.strftime('%Y-%m-%d %H:%M UTC')}")
    _line(
        buf,
        "Source: Samsung Health Connect (synced daily from Drive) plus a curated supplement / tea inventory.",
    )
    _line(buf)

    # ---------- Headline averages ----------
    _h(buf, 2, "Headline Stats")
    summary = queries.landing_summary(s)
    bp = summary.get("bp_avg")
    if bp:
        _line(
            buf,
            f"- **Blood pressure (7d avg)**: {bp['systolic']}/{bp['diastolic']} mmHg "
            f"over {bp['n']} reading(s), as of {bp['as_of'].strftime('%Y-%m-%d')}.",
        )
    w = summary.get("weight_avg")
    if w:
        _line(
            buf,
            f"- **Weight (7d avg)**: {w['kg']} kg ({round(w['kg'] * 2.2046, 1)} lbs) "
            f"over {w['n']} reading(s), as of {w['as_of'].strftime('%Y-%m-%d')}.",
        )
    rhr = summary.get("rhr_avg")
    if rhr:
        _line(
            buf,
            f"- **Resting heart rate (30d avg)**: {rhr['bpm']} bpm over {rhr['n']} reading(s), "
            f"as of {rhr['as_of'].strftime('%Y-%m-%d')}.",
        )
    steps = summary.get("steps_avg")
    if steps:
        _line(
            buf,
            f"- **Steps (30d avg)**: {steps['count']:,}/day across {steps['n']} day(s), "
            f"as of {steps['as_of'].strftime('%Y-%m-%d')}.",
        )
    last_sync = summary.get("last_sync")
    if last_sync:
        _line(
            buf,
            f"- **Last sync**: {last_sync.started_at.strftime('%Y-%m-%d %H:%M UTC')} "
            f"({last_sync.status}, {last_sync.rows_upserted:,} rows touched).",
        )
    _line(buf)

    # ---------- Data freshness ----------
    fresh = queries.data_freshness(s)
    if fresh:
        _h(buf, 2, "Data Freshness")
        _line(buf, "| Source | Records | Latest record |")
        _line(buf, "| --- | ---: | --- |")
        for r in fresh:
            latest = r["latest"].strftime("%Y-%m-%d") if r["latest"] else "n/a"
            _line(buf, f"| {r['label']} | {r['count']:,} | {latest} |")
        _line(buf)

    # ---------- Daily micronutrients (food + supplements) ----------
    micros = queries.combined_daily_intake(s, food_days=7)
    if micros:
        _h(buf, 2, "Daily Micronutrients (food + supplements)")
        _line(buf, "Food = avg over last 7 days of logged meals. Supplements = daily dose from the stack.")
        _line(buf)
        _line(buf, "| Nutrient | Food | Supplements | Total | DV | %DV | UL | %UL |")
        _line(buf, "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        for r in micros:
            ul = f"{r['ul']} {r['unit']}" if r["ul"] else "n/a"
            pct_ul = f"{r['pct_ul']}%" if r["pct_ul"] is not None else "n/a"
            supp = f"{r['supplements']} {r['unit']}" if r["supplements"] > 0 else "-"
            _line(
                buf,
                f"| {r['name']} | {r['food']} {r['unit']} | {supp} | "
                f"**{r['total']} {r['unit']}** | {r['dv']} {r['unit']} | "
                f"{r['pct_dv']}% | {ul} | {pct_ul} |",
            )
        _line(buf)

    # ---------- Recent blood pressure ----------
    bp_recent = queries.recent_blood_pressure(s, days=90)
    if bp_recent:
        _h(buf, 2, "Recent Blood Pressure (last 90 days)")
        _line(buf, "| Date | Systolic | Diastolic |")
        _line(buf, "| --- | ---: | ---: |")
        for r in sorted(bp_recent, key=lambda x: x.time, reverse=True):
            _line(buf, f"| {r.time.strftime('%Y-%m-%d %H:%M')} | {int(r.systolic)} | {int(r.diastolic)} |")
        _line(buf)

    # ---------- Recent weight ----------
    w_recent = queries.recent_weight(s, days=180)
    if w_recent:
        _h(buf, 2, "Weight Trend (last 180 days)")
        _line(buf, "| Date | Weight (kg) | Weight (lbs) |")
        _line(buf, "| --- | ---: | ---: |")
        for r in sorted(w_recent, key=lambda x: x.time, reverse=True):
            kg = round(r.weight_g / 1000, 1)
            _line(buf, f"| {r.time.strftime('%Y-%m-%d')} | {kg} | {round(kg * 2.2046, 1)} |")
        _line(buf)

    # ---------- Recent workouts ----------
    workouts = queries.recent_exercise_sessions(s, limit=20)
    if workouts:
        _h(buf, 2, "Recent Workouts")
        _line(buf, "| Date | Title | Duration |")
        _line(buf, "| --- | --- | ---: |")
        for w_ex in workouts:
            minutes = int((w_ex.end_time - w_ex.start_time).total_seconds() / 60)
            _line(buf, f"| {w_ex.start_time.strftime('%Y-%m-%d')} | {w_ex.title or 'Gym'} | {minutes} min |")
        _line(buf)

    # ---------- Recent sleep ----------
    sleep = queries.recent_sleep_sessions(s, days=30)
    if sleep:
        _h(buf, 2, "Recent Sleep (last 30 days)")
        _line(buf, "| Date | Duration (h) |")
        _line(buf, "| --- | ---: |")
        for sl in sleep:
            _line(buf, f"| {sl['start'].strftime('%Y-%m-%d')} | {sl['duration_h']} |")
        _line(buf)

    # ---------- Daily nutrition (last 14 days) ----------
    daily = queries.daily_nutrition(s, days=14)
    if daily:
        _h(buf, 2, "Daily Macros (last 14 days of logged meals)")
        _line(
            buf,
            "| Date | kcal | Protein (g) | Carbs (g) | Fat (g) | Fiber (g) | Sugar (g) | Sodium (mg) |",
        )
        _line(buf, "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        for d in daily:
            _line(
                buf,
                f"| {d['date']} | {int(d['kcal']):,} | {d['protein_g']} | {d['carbs_g']} | "
                f"{d['fat_g']} | {d['fiber_g']} | {d['sugar_g']} | {int(d['sodium_mg']):,} |",
            )
        _line(buf)

    # ---------- Supplements & drugs ----------
    items = queries.vitamins(s)
    if items:
        _h(buf, 2, f"Supplements & Drugs ({len(items)} items)")
        for v in items:
            _h(buf, 3, f"{v.name} ({v.kind})")
            if v.dose:
                _line(buf, f"- **Dose**: {v.dose}")
            if v.frequency:
                _line(buf, f"- **Frequency**: {v.frequency}")
            if v.positive_effects:
                _line(buf, f"- **Why I take it**: {v.positive_effects}")
            if v.side_effects:
                _line(buf, f"- **Side effects**: {v.side_effects}")
            if v.interactions:
                _line(buf, f"- **Drug interactions**: {v.interactions}")
            if v.stack_interactions:
                _line(buf, f"- **Stack interactions**: {v.stack_interactions}")
            if v.vendor:
                _line(buf, f"- **Vendor**: {v.vendor}")
            _line(buf)

    # ---------- Teas / herbal ingredients ----------
    herbs = queries.herbs(s)
    if herbs:
        _h(buf, 2, f"Herbal Tea Ingredients ({len(herbs)} items)")
        _line(
            buf,
            "Two daily brews (morning + nighttime). Listed at the ingredient level "
            "for herb-drug interaction review.",
        )
        _line(buf)
        for h_item in herbs:
            _h(buf, 3, f"{h_item.name}")
            _line(buf, f"- **Blend**: {h_item.blend}")
            if h_item.amount:
                _line(buf, f"- **Amount**: {h_item.amount}")
            if h_item.effects:
                _line(buf, f"- **Effects**: {h_item.effects}")
            if h_item.drug_interactions:
                _line(buf, f"- **Drug interactions**: {h_item.drug_interactions}")
            if h_item.notes:
                _line(buf, f"- **Notes**: {h_item.notes}")
            if h_item.vendor:
                _line(buf, f"- **Vendor**: {h_item.vendor}")
            _line(buf)

    # ---------- Sync runs (audit) ----------
    runs = list(
        s.execute(select(m.SyncRun).order_by(desc(m.SyncRun.started_at)).limit(10)).scalars()
    )
    if runs:
        _h(buf, 2, "Recent Sync Runs")
        _line(buf, "| Started | Source | Status | Rows | File modified |")
        _line(buf, "| --- | --- | --- | ---: | --- |")
        for r in runs:
            fm = r.file_modified_at.strftime("%Y-%m-%d %H:%M") if r.file_modified_at else "n/a"
            _line(
                buf,
                f"| {r.started_at.strftime('%Y-%m-%d %H:%M UTC')} | {r.source} | "
                f"{r.status} | {r.rows_upserted:,} | {fm} |",
            )
        _line(buf)

    return buf.getvalue()

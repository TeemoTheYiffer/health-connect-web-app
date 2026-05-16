"""SQLAlchemy 2.0 models. Single source of truth for the persistent schema.

Two kinds of tables:
1. Synced from Health Connect, keyed by `uuid` (hex of HC's BLOB uuid). Idempotent upserts.
2. Curated by Joe, Vitamins/medications, plus SyncRun audit log.

Schema is identical across SQLite (dev) and Postgres (prod). Avoid Postgres-only types.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------- Synced records (keyed by Health Connect uuid) ----------


class _HCRecordMixin:
    """Common columns for every Health Connect record we sync."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    app_package: Mapped[str | None] = mapped_column(String(255))
    last_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BloodPressure(_HCRecordMixin, Base):
    __tablename__ = "blood_pressure"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    systolic: Mapped[float] = mapped_column(Float)
    diastolic: Mapped[float] = mapped_column(Float)
    body_position: Mapped[str | None] = mapped_column(String(32))
    measurement_location: Mapped[str | None] = mapped_column(String(32))


class HeartRate(_HCRecordMixin, Base):
    __tablename__ = "heart_rate"

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    samples: Mapped[list[HeartRateSample]] = relationship(
        back_populates="record", cascade="all, delete-orphan", passive_deletes=True
    )


class HeartRateSample(Base):
    __tablename__ = "heart_rate_sample"
    __table_args__ = (
        UniqueConstraint("heart_rate_id", "ts", name="uq_hr_sample_record_ts"),
        Index("ix_hr_sample_ts", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    heart_rate_id: Mapped[int] = mapped_column(
        ForeignKey("heart_rate.id", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bpm: Mapped[int] = mapped_column(Integer, nullable=False)

    record: Mapped[HeartRate] = relationship(back_populates="samples")


class RestingHeartRate(_HCRecordMixin, Base):
    __tablename__ = "resting_heart_rate"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    bpm: Mapped[int] = mapped_column(Integer, nullable=False)


class Steps(_HCRecordMixin, Base):
    __tablename__ = "steps"

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)


class Weight(_HCRecordMixin, Base):
    __tablename__ = "weight"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    weight_g: Mapped[float] = mapped_column(Float, nullable=False)


class BodyFat(_HCRecordMixin, Base):
    __tablename__ = "body_fat"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    percentage: Mapped[float] = mapped_column(Float, nullable=False)


class Height(_HCRecordMixin, Base):
    __tablename__ = "height"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    height_m: Mapped[float] = mapped_column(Float, nullable=False)


class ActiveCalories(_HCRecordMixin, Base):
    __tablename__ = "active_calories"

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    energy_cal: Mapped[float] = mapped_column(Float, nullable=False)


class TotalCalories(_HCRecordMixin, Base):
    __tablename__ = "total_calories"

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    energy_cal: Mapped[float] = mapped_column(Float, nullable=False)


class Distance(_HCRecordMixin, Base):
    __tablename__ = "distance"

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    distance_m: Mapped[float] = mapped_column(Float, nullable=False)


class FloorsClimbed(_HCRecordMixin, Base):
    __tablename__ = "floors_climbed"

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    floors: Mapped[float] = mapped_column(Float, nullable=False)


class ElevationGained(_HCRecordMixin, Base):
    __tablename__ = "elevation_gained"

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    elevation_m: Mapped[float] = mapped_column(Float, nullable=False)


class ExerciseSession(_HCRecordMixin, Base):
    __tablename__ = "exercise_session"

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exercise_type: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)


class SleepSession(_HCRecordMixin, Base):
    __tablename__ = "sleep_session"

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)

    stages: Mapped[list[SleepStage]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )


class SleepStage(Base):
    __tablename__ = "sleep_stage"
    __table_args__ = (UniqueConstraint("session_id", "start_time", name="uq_sleep_stage_session_start"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sleep_session.id", ondelete="CASCADE"), nullable=False
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stage_type: Mapped[int] = mapped_column(Integer, nullable=False)

    session: Mapped[SleepSession] = relationship(back_populates="stages")


class Nutrition(_HCRecordMixin, Base):
    __tablename__ = "nutrition"

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    meal_name: Mapped[str | None] = mapped_column(String(255))
    meal_type: Mapped[int | None] = mapped_column(Integer)

    # Macros (grams) and energy (calories, not kcal, divide by 1000 for display)
    energy_cal: Mapped[float | None] = mapped_column(Float)
    energy_from_fat_cal: Mapped[float | None] = mapped_column(Float)
    total_fat_g: Mapped[float | None] = mapped_column(Float)
    saturated_fat_g: Mapped[float | None] = mapped_column(Float)
    trans_fat_g: Mapped[float | None] = mapped_column(Float)
    monounsaturated_fat_g: Mapped[float | None] = mapped_column(Float)
    polyunsaturated_fat_g: Mapped[float | None] = mapped_column(Float)
    unsaturated_fat_g: Mapped[float | None] = mapped_column(Float)
    cholesterol_mg: Mapped[float | None] = mapped_column(Float)
    total_carbohydrate_g: Mapped[float | None] = mapped_column(Float)
    sugar_g: Mapped[float | None] = mapped_column(Float)
    dietary_fiber_g: Mapped[float | None] = mapped_column(Float)
    protein_g: Mapped[float | None] = mapped_column(Float)
    sodium_mg: Mapped[float | None] = mapped_column(Float)
    potassium_mg: Mapped[float | None] = mapped_column(Float)
    caffeine_mg: Mapped[float | None] = mapped_column(Float)

    # Micros
    vitamin_a_ug: Mapped[float | None] = mapped_column(Float)
    vitamin_c_mg: Mapped[float | None] = mapped_column(Float)
    vitamin_d_ug: Mapped[float | None] = mapped_column(Float)
    vitamin_e_mg: Mapped[float | None] = mapped_column(Float)
    vitamin_k_ug: Mapped[float | None] = mapped_column(Float)
    vitamin_b6_mg: Mapped[float | None] = mapped_column(Float)
    vitamin_b12_ug: Mapped[float | None] = mapped_column(Float)
    thiamin_mg: Mapped[float | None] = mapped_column(Float)
    riboflavin_mg: Mapped[float | None] = mapped_column(Float)
    niacin_mg: Mapped[float | None] = mapped_column(Float)
    folate_ug: Mapped[float | None] = mapped_column(Float)
    folic_acid_ug: Mapped[float | None] = mapped_column(Float)
    pantothenic_acid_mg: Mapped[float | None] = mapped_column(Float)
    biotin_ug: Mapped[float | None] = mapped_column(Float)
    calcium_mg: Mapped[float | None] = mapped_column(Float)
    iron_mg: Mapped[float | None] = mapped_column(Float)
    magnesium_mg: Mapped[float | None] = mapped_column(Float)
    phosphorus_mg: Mapped[float | None] = mapped_column(Float)
    zinc_mg: Mapped[float | None] = mapped_column(Float)
    copper_mg: Mapped[float | None] = mapped_column(Float)
    manganese_mg: Mapped[float | None] = mapped_column(Float)
    selenium_ug: Mapped[float | None] = mapped_column(Float)
    chromium_ug: Mapped[float | None] = mapped_column(Float)
    iodine_ug: Mapped[float | None] = mapped_column(Float)
    molybdenum_ug: Mapped[float | None] = mapped_column(Float)
    chloride_mg: Mapped[float | None] = mapped_column(Float)


# ---------- Curated content (managed by Joe, not synced) ----------


class Herb(Base):
    """A herbal/tea-blend ingredient I consume daily.

    Tracked separately from Vitamin because teas are a different consumption
    pattern (brewed daily, not capsuled) and the audience question is different:
    doctors care about herbal pharmacology / drug interactions, not DV totals.
    Curated by me via `teas.toml`, seeded by the sync job.
    """

    __tablename__ = "herb"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Which brew the herb is in. "morning" | "nighttime" | "both".
    blend: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[str | None] = mapped_column(Text)
    effects: Mapped[str | None] = mapped_column(Text)
    drug_interactions: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    vendor: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Vitamin(Base):
    """A drug, vitamin, or supplement Joe takes routinely.

    Curated by Joe via `scripts/seed_vitamins.py` reading vitamins.toml.
    """

    __tablename__ = "vitamin"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # drug | vitamin | supplement
    # Dose and frequency descriptions can run long for supplement-stack products
    # (e.g. Prostate Essentials' per-cap breakdown is ~220 chars). Text avoids
    # arbitrary VARCHAR caps; Postgres treats VARCHAR vs TEXT identically anyway.
    dose: Mapped[str | None] = mapped_column(Text)
    frequency: Mapped[str | None] = mapped_column(Text)
    started_on: Mapped[str | None] = mapped_column(String(32))  # ISO date string
    positive_effects: Mapped[str | None] = mapped_column(Text)
    side_effects: Mapped[str | None] = mapped_column(Text)
    interactions: Mapped[str | None] = mapped_column(Text)
    stack_interactions: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    vendor: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    # JSON map of {nutrient_field: amount_in_field_unit}, e.g. {"zinc_mg": 30}.
    # Summed across all items to drive the daily-value tally on /supplements.
    daily_contrib: Mapped[dict | None] = mapped_column(JSON)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


# ---------- Sync metadata ----------


class SyncRun(Base):
    """Audit log of every sync attempt."""

    __tablename__ = "sync_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # drive | local | manual
    file_id: Mapped[str | None] = mapped_column(String(255))
    file_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # running | success | error
    rows_upserted: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)


def create_all() -> None:
    """Create all tables. Used in dev/CI; prod should use migrations once schema stabilizes."""
    from health_connect_web.db import engine

    Base.metadata.create_all(engine())

"""Reliability metrics computed with pandas.

The database stores raw stop events. This module turns them into a DataFrame
and computes the numbers a transit operator asks for: on-time performance,
delay by hour of day, the worst stops, and headway regularity (bunching).

Every function takes a DataFrame from ``events_to_frame`` so it can be tested
without a database.
"""

from __future__ import annotations

import pandas as pd
from django.conf import settings

FRAME_COLUMNS = [
    "trip_ref",
    "route",
    "direction",
    "stop_code",
    "stop_name",
    "sequence",
    "scheduled_arrival",
    "actual_arrival",
]

# Headways longer than this are treated as "not a frequent service" and left
# out of the bunching numbers, otherwise the gap between the last trip of one
# day and the first of the next would dominate the average.
MAX_HEADWAY_S = 1800
# A gap under 25% of the scheduled headway counts as bunching.
BUNCHING_RATIO = 0.25


def events_to_frame(queryset) -> pd.DataFrame:
    """Load a StopEvent queryset into a DataFrame with a ``delay_s`` column."""
    rows = queryset.values_list(
        "trip__trip_ref",
        "trip__route__short_name",
        "trip__direction",
        "stop__code",
        "stop__name",
        "sequence",
        "scheduled_arrival",
        "actual_arrival",
    )
    df = pd.DataFrame.from_records(list(rows), columns=FRAME_COLUMNS)
    for col in ("scheduled_arrival", "actual_arrival"):
        df[col] = pd.to_datetime(df[col], utc=True).dt.tz_convert(settings.TIME_ZONE)
    df["delay_s"] = (df["actual_arrival"] - df["scheduled_arrival"]).dt.total_seconds()
    return df


def on_time_performance(
    df: pd.DataFrame, early_s: int | None = None, late_s: int | None = None
) -> dict:
    """Share of stop events that were early, on time or late."""
    early_s = settings.ON_TIME_EARLY_S if early_s is None else early_s
    late_s = settings.ON_TIME_LATE_S if late_s is None else late_s
    total = len(df)
    if total == 0:
        return {
            "events": 0,
            "on_time_pct": None,
            "early_pct": None,
            "late_pct": None,
            "mean_delay_s": None,
            "p90_delay_s": None,
        }
    early = (df["delay_s"] < -early_s).sum()
    late = (df["delay_s"] > late_s).sum()
    on_time = total - early - late
    return {
        "events": int(total),
        "on_time_pct": round(100 * on_time / total, 1),
        "early_pct": round(100 * early / total, 1),
        "late_pct": round(100 * late / total, 1),
        "mean_delay_s": round(float(df["delay_s"].mean()), 1),
        "p90_delay_s": round(float(df["delay_s"].quantile(0.9)), 1),
    }


def delay_by_hour(df: pd.DataFrame) -> list[dict]:
    """Mean delay and on-time share for each scheduled hour of the day."""
    if df.empty:
        return []
    early_s, late_s = settings.ON_TIME_EARLY_S, settings.ON_TIME_LATE_S
    work = df.assign(
        hour=df["scheduled_arrival"].dt.hour,
        is_on_time=df["delay_s"].between(-early_s, late_s),
    )
    grouped = work.groupby("hour").agg(
        events=("delay_s", "size"),
        mean_delay_s=("delay_s", "mean"),
        on_time_pct=("is_on_time", "mean"),
    )
    return [
        {
            "hour": int(hour),
            "events": int(row.events),
            "mean_delay_s": round(float(row.mean_delay_s), 1),
            "on_time_pct": round(100 * float(row.on_time_pct), 1),
        }
        for hour, row in grouped.iterrows()
    ]


def worst_stops(df: pd.DataFrame, n: int = 5, min_events: int = 5) -> list[dict]:
    """Stops with the highest mean delay.

    Stops with fewer than ``min_events`` observations are skipped so one bad
    day at a quiet stop does not top the list.
    """
    if df.empty:
        return []
    grouped = (
        df.groupby(["stop_code", "stop_name"])
        .agg(events=("delay_s", "size"), mean_delay_s=("delay_s", "mean"))
        .reset_index()
    )
    grouped = grouped[grouped["events"] >= min_events]
    grouped = grouped.sort_values("mean_delay_s", ascending=False).head(n)
    return [
        {
            "stop_code": r.stop_code,
            "stop_name": r.stop_name,
            "events": int(r.events),
            "mean_delay_s": round(float(r.mean_delay_s), 1),
        }
        for r in grouped.itertuples()
    ]


def headway_summary(df: pd.DataFrame) -> dict:
    """How evenly spaced vehicles are, compared with the timetable.

    For each stop and direction the events are ordered by scheduled time. The
    scheduled headway is the gap between consecutive scheduled arrivals and
    the actual headway is the gap between the matching actual arrivals.
    """
    empty = {
        "headways_measured": 0,
        "mean_headway_error_s": None,
        "bunching_pct": None,
    }
    if df.empty:
        return empty
    ordered = df.sort_values(["stop_code", "direction", "scheduled_arrival"])
    grouped = ordered.groupby(["stop_code", "direction"])
    ordered = ordered.assign(
        sched_headway_s=grouped["scheduled_arrival"].diff().dt.total_seconds(),
        actual_headway_s=grouped["actual_arrival"].diff().dt.total_seconds(),
    )
    valid = ordered.dropna(subset=["sched_headway_s", "actual_headway_s"])
    valid = valid[
        (valid["sched_headway_s"] > 0) & (valid["sched_headway_s"] <= MAX_HEADWAY_S)
    ]
    if valid.empty:
        return empty
    error = (valid["actual_headway_s"] - valid["sched_headway_s"]).abs()
    bunched = valid["actual_headway_s"] < BUNCHING_RATIO * valid["sched_headway_s"]
    return {
        "headways_measured": int(len(valid)),
        "mean_headway_error_s": round(float(error.mean()), 1),
        "bunching_pct": round(100 * float(bunched.mean()), 1),
    }

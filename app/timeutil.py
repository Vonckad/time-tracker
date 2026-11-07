"""UTC datetime helpers. Durations never go negative."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(value: str) -> datetime:
    """Parse ISO-8601; naive values are treated as UTC."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def duration_seconds(start: datetime, end: datetime) -> int:
    """Non-negative whole seconds between start and end."""
    delta = int((end - start).total_seconds())
    return max(0, delta)


def overlap_seconds(
    entry_start: datetime,
    entry_end: datetime | None,
    period_from: datetime,
    period_to: datetime,
) -> int | None:
    """
    Seconds of [entry_start, entry_end] that fall inside [period_from, period_to]
    (inclusive bounds on the period). Returns None if the entry is still running
    (active timers are excluded from sums).
    """
    if entry_end is None:
        return None
    # Inclusive period: treat period_to as end-of-instant; clip to closed interval.
    clip_start = max(entry_start, period_from)
    clip_end = min(entry_end, period_to)
    if clip_end < clip_start:
        return 0
    return duration_seconds(clip_start, clip_end)

"""
Pure analytics. No I/O, no AWS, no framework imports -- every function here is
callable with plain values or an Equipment and is fully unit-testable.

Status precedence is UNASSIGNED > OVERDUE > IDLE > ACTIVE: an asset nobody owns
is the more urgent problem to surface, and it is also the one that makes an
overdue date meaningless (there is no operator to chase for the return).
"""
from collections import defaultdict
from datetime import date, timedelta

from models import Equipment

UNDER_UTILIZED_THRESHOLD = 0.20
HEALTHY_UTILIZATION_THRESHOLD = 0.80

ACTIVE = "ACTIVE"
IDLE = "IDLE"
UNASSIGNED = "UNASSIGNED"
OVERDUE = "OVERDUE"


def _is_blank(value) -> bool:
    return value is None or str(value).strip() == "" or str(value).strip().upper() == "NULL"


def utilization_rate(engine: float, idle: float) -> float:
    total = engine + idle
    if total == 0:
        return 0.0
    return engine / total


def row_utilization(row: Equipment) -> float:
    return utilization_rate(row.engine_hours_per_day, row.idle_hours_per_day)


def is_unassigned(row: Equipment) -> bool:
    return _is_blank(row.operator_id) or _is_blank(row.check_in_date)


def is_underutilized(row: Equipment) -> bool:
    return row_utilization(row) < UNDER_UTILIZED_THRESHOLD


def expected_return(check_out: date, rental_days: int) -> date:
    return check_out + timedelta(days=rental_days)


def days_until_due(row: Equipment, today: date) -> int | None:
    if row.check_out_date is None:
        return None
    return (expected_return(row.check_out_date, row.rental_days) - today).days


def is_overdue(row: Equipment, today: date) -> bool:
    remaining = days_until_due(row, today)
    return remaining is not None and remaining < 0


def due_soon(row: Equipment, today: date, threshold: int = 2) -> bool:
    remaining = days_until_due(row, today)
    return remaining is not None and 0 <= remaining <= threshold


def status(row: Equipment, today: date) -> str:
    if is_unassigned(row):
        return UNASSIGNED
    if is_overdue(row, today):
        return OVERDUE
    if is_underutilized(row):
        return IDLE
    return ACTIVE


def detect_anomalies(row: Equipment) -> list[str]:
    findings = []

    if _is_blank(row.operator_id):
        findings.append("Checked out but no operator assigned")
    if _is_blank(row.check_in_date):
        findings.append("No check-in record for a checked-out asset")
    if _is_blank(row.site_id):
        findings.append("No site allocated -- equipment location is unaccounted for")

    if row.engine_hours_per_day == 0 and row.idle_hours_per_day > 0:
        findings.append(
            f"0 engine hours over {row.idle_hours_per_day:g} idle hours "
            f"-- rented for {row.rental_days} days and never used"
        )

    util = row_utilization(row)
    if row.engine_hours_per_day > 0 and util < UNDER_UTILIZED_THRESHOLD:
        findings.append(f"Utilization {util * 100:.0f}% is below healthy threshold")

    return findings


def site_summary(rows: list[Equipment]) -> dict[str, dict]:
    """Totals are per-rental (per-day rate x rental days), not per-day snapshots."""
    buckets = defaultdict(lambda: {"total_engine_hours": 0.0, "total_idle_hours": 0.0,
                                   "count": 0, "_util_sum": 0.0})

    for row in rows:
        key = "UNASSIGNED" if _is_blank(row.site_id) else row.site_id
        bucket = buckets[key]
        bucket["total_engine_hours"] += row.engine_hours_per_day * row.rental_days
        bucket["total_idle_hours"] += row.idle_hours_per_day * row.rental_days
        bucket["count"] += 1
        bucket["_util_sum"] += row_utilization(row)

    summary = {}
    for key, bucket in buckets.items():
        summary[key] = {
            "total_engine_hours": round(bucket["total_engine_hours"], 2),
            "total_idle_hours": round(bucket["total_idle_hours"], 2),
            "count": bucket["count"],
            "avg_utilization": round(bucket["_util_sum"] / bucket["count"], 4),
            "downtime_hours": round(bucket["total_idle_hours"], 2),
        }
    return summary

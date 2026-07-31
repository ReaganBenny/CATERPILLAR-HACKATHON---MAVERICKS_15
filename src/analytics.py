"""
Pure analytics. No I/O, no AWS, no framework imports -- every function here is
callable with plain values or an Equipment and is fully unit-testable.

Status precedence is UNASSIGNED > OVERDUE > IDLE > ACTIVE: an asset nobody owns
is the more urgent problem to surface, and it is also the one that makes an
overdue date meaningless (there is no operator to chase for the return).
"""
from collections import defaultdict
from datetime import date, timedelta
from math import asin, cos, radians, sin, sqrt

from models import Equipment

UNDER_UTILIZED_THRESHOLD = 0.20
HEALTHY_UTILIZATION_THRESHOLD = 0.80

# Indicative diesel burn while idling, litres per hour, by machine type.
# Used to convert idle hours into a cost the customer can see on an invoice.
IDLE_FUEL_BURN_RATE = {
    "Excavator": 4.0,
    "Bulldozer": 5.0,
    "Crane": 3.0,
    "Grader": 3.5,
}
DEFAULT_IDLE_FUEL_BURN_RATE = 4.0

# How far an asset may report from its assigned site before it is flagged.
OFF_SITE_THRESHOLD_KM = 5.0

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


def due_date(row: Equipment) -> date | None:
    """
    The date this asset is expected back.

    Closed rental (check-out recorded): the supplied dataset's convention --
    check_out + rental_days, i.e. the scheduled return of the next cycle.

    Open rental (no check-out yet): the rental is still running, so the clock
    started at check-in and the asset is due at check_in + rental_days. Without
    this branch an open rental could never be overdue, which would make live
    ACTIVE / DUE SOON states impossible to demonstrate.
    """
    if row.check_out_date is not None:
        return expected_return(row.check_out_date, row.rental_days)
    if row.check_in_date is not None:
        return row.check_in_date + timedelta(days=row.rental_days)
    return None


def days_until_due(row: Equipment, today: date) -> int | None:
    due = due_date(row)
    if due is None:
        return None
    return (due - today).days


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


def idle_fuel_waste_per_day(row: Equipment) -> float:
    """
    Litres burned per day while the machine idles.

    Idling is not free -- a machine sitting with the engine running still burns
    diesel, which turns idle hours into a number the rental customer can see on
    an invoice. Burn rates are indicative industry figures, not measured.
    """
    rate = IDLE_FUEL_BURN_RATE.get(row.type, DEFAULT_IDLE_FUEL_BURN_RATE)
    return round(row.idle_hours_per_day * rate, 2)


def idle_fuel_waste_total(row: Equipment) -> float:
    """Litres wasted across the whole rental."""
    return round(idle_fuel_waste_per_day(row) * row.rental_days, 2)


def fleet_idle_fuel_waste(rows: list[Equipment]) -> float:
    return round(sum(idle_fuel_waste_total(r) for r in rows), 2)


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two coordinates."""
    radius = 6371.0
    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return round(2 * radius * asin(sqrt(a)), 3)


def distance_from_site(row: Equipment, sites: dict) -> float | None:
    """How far the asset is reporting from the site it is assigned to."""
    if row.latitude is None or row.longitude is None:
        return None
    if _is_blank(row.site_id) or row.site_id not in sites:
        return None
    site = sites[row.site_id]
    return distance_km(row.latitude, row.longitude, site.latitude, site.longitude)


def location_anomalies(row: Equipment, sites: dict) -> list[str]:
    """
    Location findings, kept separate from detect_anomalies() because they need
    the site registry and the core rules stay dependency-free.
    """
    findings = []

    if row.latitude is None or row.longitude is None:
        findings.append("No GPS fix — asset location cannot be confirmed")
        return findings

    if _is_blank(row.site_id):
        findings.append(
            f"Reporting from {row.latitude:.4f}, {row.longitude:.4f} — "
            "not a registered site, and no site is assigned"
        )
        return findings

    distance = distance_from_site(row, sites)
    if distance is not None and distance > OFF_SITE_THRESHOLD_KM:
        findings.append(
            f"{distance} km from assigned site {row.site_id} — "
            f"beyond the {OFF_SITE_THRESHOLD_KM} km geofence"
        )
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

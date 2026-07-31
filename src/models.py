from dataclasses import dataclass
from datetime import date


@dataclass
class Equipment:
    equipment_id: str
    type: str
    site_id: str | None
    check_in_date: date | None
    check_out_date: date | None
    engine_hours_per_day: float
    idle_hours_per_day: float
    rental_days: int
    operator_id: str | None
    # Telemetry, joined from data/telemetry.csv rather than the rental ledger.
    # Optional because the supplied dataset does not carry these fields.
    fuel_usage_per_day: float | None = None
    latitude: float | None = None
    longitude: float | None = None


@dataclass
class Site:
    site_id: str
    site_name: str
    latitude: float
    longitude: float

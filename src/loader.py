"""
CSV -> Equipment / Site objects.

Three separate feeds, joined on equipment_id, mirroring how this works in
production: the rental ledger and the telemetry stream are different systems.

  data/equipment.csv      the supplied dataset, byte-for-byte unmodified
  data/active_rentals.csv SIMULATED currently-open rentals (no check-out yet)
  data/telemetry.csv      SIMULATED fuel + GPS, absent from the supplied schema
  data/sites.csv          SIMULATED site registry with coordinates

Only equipment.csv is real. The rest are labelled simulated everywhere they
surface so nothing invented is ever presented as supplied data.

Deliberately stdlib-only: the Lambda imports this module, and depending on
pandas here would force the AWS-managed pandas layer into the deployment for
the sake of reading a handful of rows.
"""
import csv
from datetime import datetime
from pathlib import Path

from models import Equipment, Site

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_PATH = DATA_DIR / "equipment.csv"
ACTIVE_PATH = DATA_DIR / "active_rentals.csv"
TELEMETRY_PATH = DATA_DIR / "telemetry.csv"
SITES_PATH = DATA_DIR / "sites.csv"

COLUMN_MAP = {
    "Equipment ID": "equipment_id",
    "Type": "type",
    "Site ID": "site_id",
    "Check-In Date": "check_in_date",
    "Check-Out Date": "check_out_date",
    "Engine Hours/Day": "engine_hours_per_day",
    "Idle Hours/Day": "idle_hours_per_day",
    "Rental Days": "rental_days",
    "Last Operator ID": "operator_id",
}


def _clean(value):
    """The source spreadsheet encodes missing values as the literal string NULL."""
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.upper() == "NULL":
        return None
    return text


def _parse_date(value):
    cleaned = _clean(value)
    if cleaned is None:
        return None
    return datetime.strptime(cleaned, "%Y-%m-%d").date()


def _float_or_none(value):
    cleaned = _clean(value)
    return None if cleaned is None else float(cleaned)


def load_telemetry(path: Path = TELEMETRY_PATH) -> dict[str, dict]:
    """SIMULATED fuel + GPS feed, keyed by equipment_id."""
    readings = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            readings[_clean(row["equipment_id"])] = {
                "fuel_usage_per_day": _float_or_none(row["fuel_usage_per_day"]),
                "latitude": _float_or_none(row["latitude"]),
                "longitude": _float_or_none(row["longitude"]),
            }
    return readings


def load_sites(path: Path = SITES_PATH) -> dict[str, Site]:
    """SIMULATED site registry, keyed by site_id."""
    sites = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            site = Site(
                site_id=_clean(row["site_id"]),
                site_name=_clean(row["site_name"]),
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
            )
            sites[site.site_id] = site
    return sites


def _read_rentals(path: Path, telemetry: dict[str, dict]) -> list[Equipment]:
    fleet = []
    with open(path, newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            row = {COLUMN_MAP[k]: v for k, v in raw.items() if k in COLUMN_MAP}
            equipment_id = _clean(row["equipment_id"])
            reading = telemetry.get(equipment_id, {})
            fleet.append(Equipment(
                equipment_id=equipment_id,
                type=_clean(row["type"]),
                site_id=_clean(row["site_id"]),
                check_in_date=_parse_date(row["check_in_date"]),
                check_out_date=_parse_date(row["check_out_date"]),
                engine_hours_per_day=float(_clean(row["engine_hours_per_day"]) or 0),
                idle_hours_per_day=float(_clean(row["idle_hours_per_day"]) or 0),
                rental_days=int(_clean(row["rental_days"]) or 0),
                operator_id=_clean(row["operator_id"]),
                fuel_usage_per_day=reading.get("fuel_usage_per_day"),
                latitude=reading.get("latitude"),
                longitude=reading.get("longitude"),
            ))
    return fleet


def load_equipment(path: Path = DATA_PATH, with_telemetry: bool = True) -> list[Equipment]:
    """The supplied dataset: 7 closed historical rentals."""
    telemetry = load_telemetry() if with_telemetry else {}
    return _read_rentals(path, telemetry)


def load_active_rentals(path: Path = ACTIVE_PATH) -> list[Equipment]:
    """SIMULATED open rentals, so live ACTIVE / DUE SOON states are demonstrable."""
    return _read_rentals(path, load_telemetry())


def load_fleet() -> list[Equipment]:
    """Everything the dashboard shows: supplied history plus simulated open rentals."""
    return load_equipment() + load_active_rentals()

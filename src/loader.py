"""
CSV -> Equipment objects.

Deliberately stdlib-only. The Lambda imports this module, and depending on
pandas here would force the AWS-managed pandas layer into the deployment for
the sake of reading seven rows. Standard-library `csv` removes that dependency
entirely, so the function packages as a few KB with no layers attached.
"""
import csv
from datetime import datetime
from pathlib import Path

from models import Equipment

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "equipment.csv"

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


def load_equipment(path: Path = DATA_PATH) -> list[Equipment]:
    fleet = []
    with open(path, newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            row = {COLUMN_MAP[k]: v for k, v in raw.items() if k in COLUMN_MAP}
            fleet.append(Equipment(
                equipment_id=_clean(row["equipment_id"]),
                type=_clean(row["type"]),
                site_id=_clean(row["site_id"]),
                check_in_date=_parse_date(row["check_in_date"]),
                check_out_date=_parse_date(row["check_out_date"]),
                engine_hours_per_day=float(_clean(row["engine_hours_per_day"]) or 0),
                idle_hours_per_day=float(_clean(row["idle_hours_per_day"]) or 0),
                rental_days=int(_clean(row["rental_days"]) or 0),
                operator_id=_clean(row["operator_id"]),
            ))
    return fleet

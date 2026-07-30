from datetime import datetime
from pathlib import Path

import pandas as pd

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
    if value is None or pd.isna(value):
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
    df = pd.read_csv(path, dtype=str).rename(columns=COLUMN_MAP)

    fleet = []
    for _, row in df.iterrows():
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

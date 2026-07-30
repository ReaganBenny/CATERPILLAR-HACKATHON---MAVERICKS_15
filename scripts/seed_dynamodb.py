#!/usr/bin/env python3
"""
Loads data/equipment.csv into the DynamoDB table created by Terraform.

Closes the gap between "Terraform provisions a table" and "the table actually
holds the fleet" — without this the demo shows an empty table.

Usage:
    python scripts/seed_dynamodb.py --table smart-rental-tracking-dev-assets --region ap-south-1
    python scripts/seed_dynamodb.py --table ... --dry-run     # no AWS calls
"""
import argparse
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import analytics as an  # noqa: E402
from loader import load_equipment  # noqa: E402


def to_item(asset) -> dict:
    """DynamoDB rejects floats, so numerics go in as Decimal."""
    return {
        "equipment_id": asset.equipment_id,
        "type": asset.type,
        # Absent site/operator are stored as the sentinel the dashboard shows,
        # because DynamoDB cannot index a null partition value.
        "site_id": asset.site_id or "UNASSIGNED",
        "operator_id": asset.operator_id or "UNASSIGNED",
        "check_in_date": asset.check_in_date.isoformat() if asset.check_in_date else None,
        "check_out_date": asset.check_out_date.isoformat() if asset.check_out_date else None,
        "engine_hours_per_day": Decimal(str(asset.engine_hours_per_day)),
        "idle_hours_per_day": Decimal(str(asset.idle_hours_per_day)),
        "rental_days": asset.rental_days,
        "utilization_rate": Decimal(str(round(an.row_utilization(asset), 4))),
        "is_unassigned": an.is_unassigned(asset),
        "anomaly_count": len(an.detect_anomalies(asset)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", required=True, help="DynamoDB table name from terraform output")
    parser.add_argument("--region", default="ap-south-1")
    parser.add_argument("--endpoint-url", default=None,
                        help="Override for LocalStack, e.g. http://localhost:4566")
    parser.add_argument("--dry-run", action="store_true", help="Print items without calling AWS")
    args = parser.parse_args()

    fleet = load_equipment()
    items = [to_item(asset) for asset in fleet]

    if args.dry_run:
        for item in items:
            print(item)
        print(f"\n{len(items)} items ready (dry run — nothing written).")
        return 0

    import boto3  # imported here so --dry-run works without the AWS SDK

    table = boto3.resource("dynamodb", region_name=args.region,
                           endpoint_url=args.endpoint_url).Table(args.table)

    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)

    print(f"Wrote {len(items)} assets to {args.table} in {args.region}.")
    print(f"Unassigned: {[a.equipment_id for a in fleet if an.is_unassigned(a)]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

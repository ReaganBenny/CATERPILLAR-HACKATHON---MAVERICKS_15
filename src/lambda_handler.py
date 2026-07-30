"""
AWS Lambda entry point for the scheduled overdue/anomaly sweep.

Split deliberately in two:

  build_payload()  -- pure, no boto3, no network. Unit-tested locally.
  handler()        -- the AWS shim. Imports boto3 lazily and publishes to SNS.

That split means the whole decision path is covered by tests that run in CI
without AWS credentials, and only the delivery mechanism is untested until the
stack is actually deployed.
"""
import json
import os
from datetime import date

import analytics as an
from loader import load_equipment


def build_payload(fleet, today: date) -> dict:
    """Everything the notification needs, computed from the analytics layer."""
    overdue, due_soon, unassigned, anomalies = [], [], [], []

    for asset in fleet:
        reasons = an.detect_anomalies(asset)
        if reasons:
            anomalies.append({"equipment_id": asset.equipment_id, "reasons": reasons})

        if an.is_unassigned(asset):
            unassigned.append(asset.equipment_id)
            continue

        if an.is_overdue(asset, today):
            overdue.append({
                "equipment_id": asset.equipment_id,
                "days_late": abs(an.days_until_due(asset, today)),
            })
        elif an.due_soon(asset, today):
            due_soon.append({
                "equipment_id": asset.equipment_id,
                "days_until_due": an.days_until_due(asset, today),
            })

    return {
        "as_of": today.isoformat(),
        "fleet_size": len(fleet),
        "overdue": overdue,
        "due_soon": due_soon,
        "unassigned": unassigned,
        "anomalies": anomalies,
        "requires_notification": bool(overdue or due_soon or unassigned),
    }


def format_message(payload: dict) -> str:
    """Human-readable body for the SNS email."""
    lines = [f"Smart Rental Tracking — fleet sweep {payload['as_of']}",
             f"{payload['fleet_size']} assets checked.", ""]

    if payload["unassigned"]:
        lines.append(f"UNASSIGNED ({len(payload['unassigned'])}): "
                     f"{', '.join(payload['unassigned'])} — billed with no operator or site.")
    for item in payload["overdue"]:
        lines.append(f"OVERDUE: {item['equipment_id']} is {item['days_late']} day(s) past return.")
    for item in payload["due_soon"]:
        lines.append(f"DUE SOON: {item['equipment_id']} due in {item['days_until_due']} day(s).")
    if payload["anomalies"]:
        lines.append("")
        lines.append("Anomalies:")
        for item in payload["anomalies"]:
            lines.append(f"  {item['equipment_id']}: {'; '.join(item['reasons'])}")

    if not payload["requires_notification"]:
        lines.append("No action required.")
    return "\n".join(lines)


def handler(event, context):  # pragma: no cover - requires AWS runtime
    """Triggered by EventBridge on a schedule. Publishes to SNS when action is needed."""
    today = date.fromisoformat(event["today"]) if event and "today" in event else date.today()
    payload = build_payload(load_equipment(), today)

    topic_arn = os.environ.get("SNS_TOPIC_ARN")
    if payload["requires_notification"] and topic_arn:
        import boto3  # imported here so local tests need no AWS SDK

        boto3.client("sns").publish(
            TopicArn=topic_arn,
            Subject=f"[Rental Alert] {len(payload['overdue'])} overdue, "
                    f"{len(payload['unassigned'])} unassigned",
            Message=format_message(payload),
        )
        payload["notification_sent"] = True
    else:
        payload["notification_sent"] = False

    return {"statusCode": 200, "body": json.dumps(payload)}

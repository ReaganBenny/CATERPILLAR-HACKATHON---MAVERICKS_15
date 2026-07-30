from datetime import date

import pytest

import lambda_handler as lh
from loader import load_equipment

TODAY = date(2025, 6, 1)


@pytest.fixture(scope="module")
def fleet():
    return load_equipment()


def test_payload_shape(fleet):
    payload = lh.build_payload(fleet, TODAY)
    assert payload["as_of"] == "2025-06-01"
    assert payload["fleet_size"] == 7
    assert set(payload) >= {"overdue", "due_soon", "unassigned", "anomalies",
                            "requires_notification"}


def test_payload_separates_unassigned_from_overdue(fleet):
    payload = lh.build_payload(fleet, TODAY)
    assert sorted(payload["unassigned"]) == ["EQX1002", "EQX1007"]
    overdue_ids = {item["equipment_id"] for item in payload["overdue"]}
    # Unassigned assets are reported as unassigned, not double-counted as overdue.
    assert overdue_ids.isdisjoint({"EQX1002", "EQX1007"})
    assert len(overdue_ids) == 5


def test_payload_days_late_is_positive(fleet):
    payload = lh.build_payload(fleet, TODAY)
    eqx1004 = next(i for i in payload["overdue"] if i["equipment_id"] == "EQX1004")
    assert eqx1004["days_late"] == 7


def test_payload_due_soon_populated_at_the_right_date(fleet):
    payload = lh.build_payload(fleet, date(2025, 5, 24))
    due_ids = {item["equipment_id"] for item in payload["due_soon"]}
    assert "EQX1004" in due_ids


def test_payload_flags_notification_required(fleet):
    assert lh.build_payload(fleet, TODAY)["requires_notification"] is True


def test_payload_includes_anomaly_reasons(fleet):
    payload = lh.build_payload(fleet, TODAY)
    ghost = next(i for i in payload["anomalies"] if i["equipment_id"] == "EQX1002")
    assert any("no operator assigned" in r for r in ghost["reasons"])


def test_message_mentions_unassigned_and_overdue(fleet):
    message = lh.format_message(lh.build_payload(fleet, TODAY))
    assert "UNASSIGNED" in message
    assert "OVERDUE" in message
    assert "EQX1002" in message


def test_message_is_plain_text_and_non_empty(fleet):
    message = lh.format_message(lh.build_payload(fleet, TODAY))
    assert isinstance(message, str) and len(message) > 50


def test_handler_does_not_require_boto3_at_import_time():
    """boto3 is imported inside handler(), so CI needs no AWS SDK."""
    import inspect
    source = inspect.getsource(lh)
    assert "import boto3" in source
    top_level = source.split("def handler")[0]
    assert "import boto3" not in top_level

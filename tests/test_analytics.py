from datetime import date

import pytest

import analytics as an
from loader import load_equipment
from models import Equipment

TODAY = date(2025, 6, 1)


@pytest.fixture(scope="module")
def fleet():
    return load_equipment()


@pytest.fixture(scope="module")
def by_id(fleet):
    return {e.equipment_id: e for e in fleet}


# --- loader ---

def test_loader_reads_all_seven_rows(fleet):
    assert len(fleet) == 7
    assert [e.equipment_id for e in fleet] == [
        "EQX1001", "EQX1002", "EQX1003", "EQX1004", "EQX1005", "EQX1006", "EQX1007",
    ]


def test_loader_converts_null_strings_to_none(by_id):
    assert by_id["EQX1002"].site_id is None
    assert by_id["EQX1002"].operator_id is None
    assert by_id["EQX1007"].site_id is None
    assert by_id["EQX1007"].operator_id is None
    assert by_id["EQX1001"].site_id == "S003"


def test_loader_parses_types(by_id):
    eqx = by_id["EQX1003"]
    assert eqx.check_in_date == date(2025, 2, 15)
    assert eqx.check_out_date == date(2025, 3, 11)
    assert eqx.engine_hours_per_day == 7.5
    assert eqx.idle_hours_per_day == 0.5
    assert eqx.rental_days == 25


# --- utilization_rate ---

def test_utilization_rate_basic():
    assert an.utilization_rate(8, 2) == 0.8


def test_utilization_rate_handles_zero_over_zero():
    assert an.utilization_rate(0, 0) == 0.0


def test_utilization_rate_zero_engine():
    assert an.utilization_rate(0, 11) == 0.0


def test_utilization_rate_no_idle():
    assert an.utilization_rate(8, 0) == 1.0


@pytest.mark.parametrize("equipment_id,expected", [
    ("EQX1001", 1.5 / 11.5),
    ("EQX1002", 0.0),
    ("EQX1003", 7.5 / 8.0),
    ("EQX1004", 2 / 11),
    ("EQX1005", 1.0),
    ("EQX1006", 3 / 9),
    ("EQX1007", 0.0),
])
def test_row_utilization_against_dataset(by_id, equipment_id, expected):
    assert an.row_utilization(by_id[equipment_id]) == pytest.approx(expected)


# --- is_unassigned ---

def test_eqx1002_and_eqx1007_are_unassigned(by_id):
    assert an.is_unassigned(by_id["EQX1002"]) is True
    assert an.is_unassigned(by_id["EQX1007"]) is True


def test_assigned_assets_are_not_unassigned(by_id):
    for equipment_id in ["EQX1001", "EQX1003", "EQX1004", "EQX1005", "EQX1006"]:
        assert an.is_unassigned(by_id[equipment_id]) is False


def test_is_unassigned_when_check_in_missing():
    row = Equipment("EQX9999", "Crane", "S001", None, date(2025, 5, 1), 4, 4, 10, "OP999")
    assert an.is_unassigned(row) is True


# --- is_underutilized ---

def test_eqx1004_is_underutilized(by_id):
    assert an.is_underutilized(by_id["EQX1004"]) is True
    assert an.row_utilization(by_id["EQX1004"]) == pytest.approx(0.1818, abs=1e-4)


def test_eqx1005_is_the_healthy_baseline(by_id):
    healthy = by_id["EQX1005"]
    assert an.is_underutilized(healthy) is False
    assert an.row_utilization(healthy) == 1.0
    assert an.row_utilization(healthy) >= an.HEALTHY_UTILIZATION_THRESHOLD
    assert an.detect_anomalies(healthy) == []


def test_underutilized_set_across_dataset(by_id):
    flagged = {eid for eid, row in by_id.items() if an.is_underutilized(row)}
    assert flagged == {"EQX1001", "EQX1002", "EQX1004", "EQX1007"}


# --- expected_return / days_until_due ---

def test_expected_return():
    assert an.expected_return(date(2025, 5, 15), 10) == date(2025, 5, 25)


def test_expected_return_crosses_month_boundary():
    assert an.expected_return(date(2025, 1, 31), 30) == date(2025, 3, 2)


def test_days_until_due_negative_when_past(by_id):
    assert an.days_until_due(by_id["EQX1004"], TODAY) == -7


def test_days_until_due_positive_when_future(by_id):
    assert an.days_until_due(by_id["EQX1004"], date(2025, 5, 20)) == 5


def test_open_rental_is_due_from_check_in():
    """
    An open rental has no check-out, so the clock runs from check-in. Without
    this an in-progress rental could never be overdue.
    """
    row = Equipment("EQX9998", "Grader", "S001", date(2025, 5, 1), None, 5, 1, 10, "OP998")
    assert an.due_date(row) == date(2025, 5, 11)
    assert an.days_until_due(row, TODAY) == -21
    assert an.is_overdue(row, TODAY) is True


def test_days_until_due_none_without_any_date():
    row = Equipment("EQX9996", "Crane", "S001", None, None, 5, 1, 10, "OP996")
    assert an.due_date(row) is None
    assert an.days_until_due(row, TODAY) is None
    assert an.is_overdue(row, TODAY) is False


def test_closed_rental_still_uses_check_out_anchor():
    """Regression guard: the supplied dataset's convention must not shift."""
    row = Equipment("EQX9995", "Grader", "S001", date(2025, 5, 1),
                    date(2025, 5, 11), 5, 1, 10, "OP995")
    assert an.due_date(row) == date(2025, 5, 21)


# --- is_overdue / due_soon ---

def test_is_overdue_at_default_today(by_id):
    assert an.is_overdue(by_id["EQX1004"], TODAY) is True


def test_not_overdue_before_due_date(by_id):
    assert an.is_overdue(by_id["EQX1004"], date(2025, 5, 20)) is False


def test_not_overdue_on_exact_due_date(by_id):
    assert an.is_overdue(by_id["EQX1004"], date(2025, 5, 25)) is False


def test_due_soon_within_threshold(by_id):
    assert an.due_soon(by_id["EQX1004"], date(2025, 5, 24)) is True


def test_due_soon_excludes_far_future(by_id):
    assert an.due_soon(by_id["EQX1004"], date(2025, 5, 1)) is False


def test_due_soon_excludes_already_overdue(by_id):
    assert an.due_soon(by_id["EQX1004"], TODAY) is False


def test_due_soon_custom_threshold(by_id):
    assert an.due_soon(by_id["EQX1004"], date(2025, 5, 20), threshold=5) is True


def test_due_soon_none_without_check_out():
    row = Equipment("EQX9997", "Crane", "S002", date(2025, 5, 1), None, 3, 3, 7, "OP997")
    assert an.due_soon(row, TODAY) is False


# --- status ---

def test_unassigned_takes_precedence_over_overdue(by_id):
    assert an.status(by_id["EQX1002"], TODAY) == an.UNASSIGNED
    assert an.status(by_id["EQX1007"], TODAY) == an.UNASSIGNED
    assert an.is_overdue(by_id["EQX1002"], TODAY) is True


def test_status_overdue(by_id):
    assert an.status(by_id["EQX1004"], TODAY) == an.OVERDUE


def test_status_idle_when_underutilized_and_not_overdue(by_id):
    assert an.status(by_id["EQX1001"], date(2025, 4, 20)) == an.IDLE


def test_status_active_for_healthy_in_window(by_id):
    assert an.status(by_id["EQX1005"], date(2025, 2, 10)) == an.ACTIVE


def test_every_status_is_a_known_value(by_id):
    valid = {an.ACTIVE, an.IDLE, an.UNASSIGNED, an.OVERDUE}
    for row in by_id.values():
        assert an.status(row, TODAY) in valid


# --- detect_anomalies ---

def test_eqx1002_ghost_asset_anomalies(by_id):
    findings = an.detect_anomalies(by_id["EQX1002"])
    assert "Checked out but no operator assigned" in findings
    assert any("0 engine hours over 11 idle hours" in f for f in findings)
    assert any("no site allocated" in f.lower() for f in findings)


def test_eqx1007_ghost_asset_anomalies(by_id):
    findings = an.detect_anomalies(by_id["EQX1007"])
    assert "Checked out but no operator assigned" in findings
    assert any("0 engine hours over 12 idle hours" in f for f in findings)


def test_eqx1004_reports_utilization_anomaly(by_id):
    findings = an.detect_anomalies(by_id["EQX1004"])
    assert findings == ["Utilization 18% is below healthy threshold"]


def test_eqx1001_reports_utilization_anomaly(by_id):
    findings = an.detect_anomalies(by_id["EQX1001"])
    assert findings == ["Utilization 13% is below healthy threshold"]


def test_healthy_assets_report_no_anomalies(by_id):
    assert an.detect_anomalies(by_id["EQX1003"]) == []
    assert an.detect_anomalies(by_id["EQX1005"]) == []
    assert an.detect_anomalies(by_id["EQX1006"]) == []


# --- site_summary ---

def test_site_summary_groups_every_site(fleet):
    summary = an.site_summary(fleet)
    assert set(summary) == {"S001", "S002", "S003", "S004", "S006", "UNASSIGNED"}


def test_site_summary_unassigned_bucket_holds_both_ghosts(fleet):
    summary = an.site_summary(fleet)
    assert summary["UNASSIGNED"]["count"] == 2
    assert summary["UNASSIGNED"]["total_engine_hours"] == 0.0
    assert summary["UNASSIGNED"]["total_idle_hours"] == 20 * 11 + 12 * 12
    assert summary["UNASSIGNED"]["avg_utilization"] == 0.0


def test_site_summary_totals_use_rental_days(fleet):
    summary = an.site_summary(fleet)
    assert summary["S004"]["total_engine_hours"] == 20.0
    assert summary["S004"]["total_idle_hours"] == 90.0
    assert summary["S004"]["downtime_hours"] == 90.0
    assert summary["S004"]["avg_utilization"] == pytest.approx(0.1818, abs=1e-4)


def test_site_summary_healthy_site_has_no_downtime(fleet):
    summary = an.site_summary(fleet)
    assert summary["S006"]["total_engine_hours"] == 240.0
    assert summary["S006"]["downtime_hours"] == 0.0
    assert summary["S006"]["avg_utilization"] == 1.0

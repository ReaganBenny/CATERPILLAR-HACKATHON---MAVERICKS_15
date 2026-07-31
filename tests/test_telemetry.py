"""
Covers the simulated telemetry feeds: fuel, GPS, site registry and open rentals.

These feeds are invented -- the supplied dataset carries none of them. The tests
assert that they stay clearly separated from the real data, and that the real
data is never modified by loading them.
"""
from datetime import date

import pytest

import analytics as an
from loader import load_active_rentals, load_equipment, load_fleet, load_sites
from models import Equipment

TODAY = date(2025, 6, 1)


@pytest.fixture(scope="module")
def fleet():
    return load_fleet()


@pytest.fixture(scope="module")
def sites():
    return load_sites()


@pytest.fixture(scope="module")
def by_id(fleet):
    return {e.equipment_id: e for e in fleet}


# --- the supplied dataset must stay untouched ---

def test_supplied_dataset_is_still_exactly_seven_rows():
    assert len(load_equipment()) == 7


def test_supplied_dataset_loads_without_telemetry_too():
    """The real data stands alone; telemetry is an optional join."""
    bare = load_equipment(with_telemetry=False)
    assert len(bare) == 7
    assert all(a.fuel_usage_per_day is None for a in bare)
    assert all(a.latitude is None for a in bare)


def test_fleet_is_supplied_plus_simulated(fleet):
    assert len(fleet) == 11
    assert len(load_active_rentals()) == 4


# --- open rentals ---

def test_active_rentals_have_no_check_out():
    assert all(a.check_out_date is None for a in load_active_rentals())


def test_open_rentals_produce_live_statuses(by_id):
    """The point of the simulated rentals: ACTIVE and OVERDUE both appear live."""
    assert an.status(by_id["EQX1008"], TODAY) == an.ACTIVE
    assert an.status(by_id["EQX1009"], TODAY) == an.ACTIVE
    assert an.status(by_id["EQX1010"], TODAY) == an.OVERDUE


def test_due_soon_fires_on_an_open_rental(by_id):
    assert an.due_soon(by_id["EQX1009"], TODAY) is True
    assert an.days_until_due(by_id["EQX1009"], TODAY) == 1


def test_open_rental_overdue_is_computed_from_check_in(by_id):
    assert an.days_until_due(by_id["EQX1010"], TODAY) == -11


def test_all_four_statuses_present_at_default_date(fleet):
    """
    The demo shows every status without touching the date picker. EQX1011 is
    the IDLE case: open, assigned, on schedule, but barely used.
    """
    seen = {an.status(a, TODAY) for a in fleet}
    assert seen == {an.ACTIVE, an.IDLE, an.OVERDUE, an.UNASSIGNED}


def test_idle_open_rental_is_not_overdue(by_id):
    idle = by_id["EQX1011"]
    assert an.status(idle, TODAY) == an.IDLE
    assert an.is_overdue(idle, TODAY) is False
    assert an.is_underutilized(idle) is True


# --- fuel ---

def test_every_asset_has_a_fuel_reading(fleet):
    assert all(a.fuel_usage_per_day is not None for a in fleet)


def test_idle_fuel_waste_uses_type_specific_burn_rate(by_id):
    crane = by_id["EQX1002"]           # 11 idle h/day, Crane burns 3.0 L/h
    assert an.idle_fuel_waste_per_day(crane) == 33.0
    assert an.idle_fuel_waste_total(crane) == 33.0 * 20


def test_healthy_asset_wastes_no_fuel_idling(by_id):
    assert an.idle_fuel_waste_per_day(by_id["EQX1005"]) == 0.0
    assert an.idle_fuel_waste_total(by_id["EQX1005"]) == 0.0


def test_unknown_type_falls_back_to_default_rate():
    row = Equipment("EQX9994", "Telehandler", "S001", date(2025, 5, 1),
                    None, 1, 10, 5, "OP994")
    assert an.idle_fuel_waste_per_day(row) == 10 * an.DEFAULT_IDLE_FUEL_BURN_RATE


def test_ghost_assets_dominate_wasted_fuel(by_id):
    ghosts = an.fleet_idle_fuel_waste([by_id["EQX1002"], by_id["EQX1007"]])
    assert ghosts == pytest.approx(1236.0)


# --- location ---

def test_site_registry_loads(sites):
    assert set(sites) == {"S001", "S002", "S003", "S004", "S006"}
    assert sites["S001"].site_name == "Poonamallee Yard"


def test_every_asset_reports_gps(fleet):
    assert all(a.latitude is not None and a.longitude is not None for a in fleet)


def test_distance_km_is_zero_for_identical_points():
    assert an.distance_km(13.0, 80.0, 13.0, 80.0) == 0.0


def test_distance_km_matches_known_separation():
    # ~1 degree of latitude is ~111 km.
    assert an.distance_km(13.0, 80.0, 14.0, 80.0) == pytest.approx(111.2, abs=1.0)


def test_assigned_assets_are_within_the_geofence(by_id, sites):
    for equipment_id in ["EQX1001", "EQX1003", "EQX1004", "EQX1005", "EQX1006"]:
        distance = an.distance_from_site(by_id[equipment_id], sites)
        assert distance is not None and distance <= an.OFF_SITE_THRESHOLD_KM


def test_assigned_assets_report_no_location_anomaly(by_id, sites):
    for equipment_id in ["EQX1001", "EQX1003", "EQX1005"]:
        assert an.location_anomalies(by_id[equipment_id], sites) == []


def test_ghost_assets_are_located_off_any_registered_site(by_id, sites):
    """
    The GPS works -- that is the point. The crane is findable, it is just
    parked somewhere that is not a site anyone assigned it to.
    """
    for equipment_id in ["EQX1002", "EQX1007"]:
        findings = an.location_anomalies(by_id[equipment_id], sites)
        assert len(findings) == 1
        assert "not a registered site" in findings[0]


def test_distance_from_site_is_none_without_assignment(by_id, sites):
    assert an.distance_from_site(by_id["EQX1002"], sites) is None


def test_missing_gps_is_reported(sites):
    row = Equipment("EQX9993", "Crane", "S001", date(2025, 5, 1), None, 5, 1, 10, "OP993")
    assert an.location_anomalies(row, sites) == ["No GPS fix — asset location cannot be confirmed"]


def test_asset_far_from_its_site_is_flagged(sites):
    row = Equipment("EQX9992", "Crane", "S001", date(2025, 5, 1), None, 5, 1, 10, "OP992",
                    latitude=13.5000, longitude=80.5000)
    findings = an.location_anomalies(row, sites)
    assert len(findings) == 1
    assert "geofence" in findings[0]

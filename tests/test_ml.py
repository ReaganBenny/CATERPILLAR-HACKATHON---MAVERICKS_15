import pytest

import ml
from loader import load_equipment


@pytest.fixture(scope="module")
def fleet():
    return load_equipment()


# --- leakage guards: these are the tests that matter most ---

def test_target_is_not_in_the_feature_set():
    """Regression guard. Putting rental_days back in DEMAND_FEATURES leaks the label."""
    assert ml.DEMAND_TARGET == "rental_days"
    assert ml.DEMAND_TARGET not in ml.DEMAND_FEATURES


def test_target_is_not_in_the_anomaly_feature_set():
    assert ml.DEMAND_TARGET not in ml.ANOMALY_FEATURES


def test_metrics_are_cross_validated_not_in_sample(fleet):
    metrics = ml.predict_demand(fleet).metrics
    assert metrics["cv"] == "leave-one-out"
    # In-sample R2 is always the flattering number; LOO must be reported alongside
    # it and must be strictly lower on a dataset this small.
    assert metrics["loo_r2"] < metrics["in_sample_r2"]


def test_honest_r2_is_modest_not_suspiciously_high(fleet):
    """A leak-free model on 7 rows cannot legitimately score above ~0.8."""
    assert ml.predict_demand(fleet).metrics["loo_r2"] < 0.8


# --- demand model ---

def test_demand_model_reports_sample_size(fleet):
    assert ml.predict_demand(fleet).metrics["n_samples"] == 7


def test_demand_model_beats_the_naive_baseline(fleet):
    metrics = ml.predict_demand(fleet).metrics
    assert metrics["loo_mae_days"] < metrics["baseline_mae_days"]
    assert metrics["beats_baseline"] is True


def test_demand_predictions_cover_every_asset(fleet):
    preds = ml.predict_demand(fleet).predictions
    assert len(preds) == 7
    assert set(preds.columns) >= {"equipment_id", "predicted_rental_days",
                                 "loo_predicted_rental_days", "abs_error_days"}


def test_feature_importances_sum_to_one(fleet):
    importances = ml.predict_demand(fleet).feature_importances
    assert set(importances) == set(ml.DEMAND_FEATURES)
    assert sum(importances.values()) == pytest.approx(1.0, abs=0.01)


def test_demand_by_type_site_aggregates(fleet):
    agg = ml.demand_by_type_site(fleet)
    assert agg["assets"].sum() == 7
    # Lowest-utilization group sorts first -- that's the reallocation candidate.
    assert agg.iloc[0]["mean_utilization"] == 0.0


# --- dataframe conversion ---

def test_to_dataframe_maps_null_site_to_unassigned(fleet):
    df = ml.to_dataframe(fleet)
    unassigned = df[df["site_id"] == "UNASSIGNED"]["equipment_id"].tolist()
    assert sorted(unassigned) == ["EQX1002", "EQX1007"]


def test_to_dataframe_utilization_matches_analytics(fleet):
    df = ml.to_dataframe(fleet)
    row = df[df["equipment_id"] == "EQX1005"].iloc[0]
    assert row["utilization_rate"] == 1.0


# --- isolation forest cross-check: asserts the documented inversion ---

def test_crosscheck_returns_a_row_per_asset(fleet):
    assert len(ml.isolation_forest_crosscheck(fleet)) == 7


def test_isolation_forest_flags_the_healthiest_assets(fleet):
    """
    Documents the finding rather than hiding it: the unsupervised model treats
    high utilization as the outlier, because under-utilization is the majority.
    """
    df = ml.isolation_forest_crosscheck(fleet)
    ml_flagged = set(df[df["ml_anomaly"]]["equipment_id"])
    assert "EQX1005" in ml_flagged   # 100% utilization -- the healthy baseline
    assert "EQX1003" in ml_flagged   # 94% utilization


def test_isolation_forest_misses_both_ghost_assets(fleet):
    df = ml.isolation_forest_crosscheck(fleet)
    ml_flagged = set(df[df["ml_anomaly"]]["equipment_id"])
    assert "EQX1002" not in ml_flagged
    assert "EQX1007" not in ml_flagged


def test_rules_catch_what_the_model_misses(fleet):
    df = ml.isolation_forest_crosscheck(fleet)
    rule_flagged = set(df[df["rule_anomaly"]]["equipment_id"])
    assert {"EQX1002", "EQX1007"} <= rule_flagged


def test_disagreement_summary_is_total_on_this_dataset(fleet):
    result = ml.crosscheck_disagreement(fleet)
    assert result["agreement_rate"] == 0.0
    assert {"EQX1002", "EQX1007"} <= set(result["flagged_by_rules_only"])
    assert {"EQX1003", "EQX1005"} <= set(result["flagged_by_ml_only"])

import numpy as np
import pandas as pd
import pytest

from credit_risk_desk.ingest import demo_frames, parse_dates, validate
from credit_risk_desk.ml import FEATURES, choose_threshold, make_pipeline


def test_demo_reproducible_and_valid():
    a, b = demo_frames(), demo_frames()
    validate(a)
    for key in a:
        pd.testing.assert_frame_equal(a[key], b[key])


@pytest.mark.parametrize("problem", ["duplicate", "orphan", "future_opening", "bad_status", "missing"])
def test_import_rejects_broken_data(problem):
    frames = demo_frames()
    if problem == "duplicate": frames["clients"].loc[1, "client_id"] = 1
    if problem == "orphan": frames["loans"].loc[0, "account_id"] = 999999
    if problem == "future_opening": frames["accounts"].loc[0, "opened_at"] = pd.Timestamp("2030-01-01").date()
    if problem == "bad_status": frames["loans"].loc[0, "status"] = "Z"
    if problem == "missing": frames["transactions"].loc[0, "balance"] = np.nan
    with pytest.raises(ValueError): validate(frames)


def test_date_century_and_invalid_date():
    assert str(parse_dates(pd.Series([930101, 981231])).iloc[0]) == "1993-01-01"
    with pytest.raises(ValueError): parse_dates(pd.Series([931332]))


def test_imputer_fit_only_on_train_and_serialization(tmp_path):
    import joblib
    x = pd.DataFrame(np.arange(200, dtype=float).reshape(20, 10), columns=FEATURES)
    x.loc[0, FEATURES[0]] = np.nan
    model = make_pipeline().fit(x, np.arange(20) % 2)
    expected = np.nanmedian(x.to_numpy(), axis=0)
    np.testing.assert_allclose(model["imputer"].statistics_, expected)
    future = pd.DataFrame(np.full((1, 10), 999999.), columns=FEATURES)
    before = model["imputer"].statistics_.copy()
    p = model.predict_proba(future)
    np.testing.assert_array_equal(model["imputer"].statistics_, before)
    path = tmp_path / "model.joblib"
    joblib.dump(model, path)
    np.testing.assert_allclose(joblib.load(path).predict_proba(future), p)


def test_cost_threshold_uses_validation_costs():
    y = np.array([0, 0, 1, 1])
    p = np.array([.1, .4, .3, .8])
    threshold, cost = choose_threshold(y, p, fn_cost=5, fp_cost=1)
    assert threshold == .3
    assert cost == 1

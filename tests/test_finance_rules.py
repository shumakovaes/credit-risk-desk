from datetime import date
import math

import pytest

from credit_risk_desk.finance import payment
from credit_risk_desk.rules import evaluate_rules
from credit_risk_desk.schemas import ApplicationRequest


def request(**updates):
    data = dict(account_id=1, as_of=date(2024, 12, 16), amount=120000, months=24,
                annual_rate_pct=12, declared_monthly_income=30000,
                existing_monthly_payments=2000, available_limit=200000)
    return ApplicationRequest(**(data | updates))


def test_zero_rate():
    result = payment(120000, 0, 24)
    assert result["monthly_payment"] == 5000
    assert result["interest"] == 0


def test_annuity_independent_present_value():
    result = payment(120000, 12, 24)
    pv = sum(result["monthly_payment"] / 1.01 ** k for k in range(1, 25))
    assert abs(pv - 120000) < .15


@pytest.mark.parametrize("amount,rate,months", [(0, 12, 24), (100, -1, 12), (100, 12, 0), (math.inf, 12, 12), (100, math.nan, 12), (100, 1, True), (100, 1, 1.5)])
def test_invalid_financial_inputs(amount, rate, months):
    with pytest.raises(ValueError):
        payment(amount, rate, months)


def test_tiny_rate_stable():
    assert payment(120000, 1e-12, 24)["monthly_payment"] == 5000


def test_missing_fields_are_unknown_not_passed():
    result = evaluate_rules(request(available_limit=None, declared_monthly_income=None), 5000,
                            {"account_age_days": 100, "tx_count_90d": 10})
    by_code = {x["code"]: x["status"] for x in result["checks"]}
    assert by_code["available_limit"] == by_code["payment_to_income"] == "unknown"


def test_limit_and_burden_boundary():
    result = evaluate_rules(request(amount=1000, available_limit=1000, declared_monthly_income=10000, existing_monthly_payments=0),
                            4500, {"account_age_days": 90, "tx_count_90d": 1})
    assert all(x["status"] == "passed" for x in result["checks"])
    bad = evaluate_rules(request(available_limit=0), 20000, {"account_age_days": 20, "tx_count_90d": 0})
    by_code = {x["code"]: x["status"] for x in bad["checks"]}
    assert by_code["available_limit"] == by_code["payment_to_income"] == "failed"
    assert by_code["history"] == "unknown"

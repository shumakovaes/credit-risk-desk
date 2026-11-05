from datetime import date

import pytest
from sqlalchemy import text

from credit_risk_desk.ingest import demo_frames, load_dataset
from credit_risk_desk.ml import train
from credit_risk_desk.service import features_for

pytestmark = pytest.mark.integration


def payload(**updates):
    return {"account_id": 1, "as_of": "2024-12-16", "amount": 120000, "months": 24,
            "annual_rate_pct": 12, "declared_monthly_income": 30000,
            "existing_monthly_payments": 2000, "available_limit": 200000} | updates


def test_future_transactions_do_not_change_features(pg):
    with pg.connect() as conn:
        tx = conn.begin()
        try:
            old = features_for(conn, 1, date(2024, 1, 1), 100000, 24, 5000)
            for i, d in enumerate(["2024-01-01", "2024-01-02"]):
                conn.execute(text("""INSERT INTO clean.transactions VALUES (:id, 1, CAST(:day AS date), 'credit', 99999999, -99999999, '')"""), {"id": 90000000 + i, "day": d})
            new = features_for(conn, 1, date(2024, 1, 1), 100000, 24, 5000)
            assert new == old
        finally:
            tx.rollback()


def test_mart_only_closed_and_same_pipeline(pg):
    with pg.connect() as conn:
        row = conn.execute(text("SELECT * FROM analytics.training_mart ORDER BY loan_id LIMIT 1")).mappings().one()
        live = features_for(conn, row["account_id"], row["issued_at"], row["amount"], int(row["months"]), row["payment"])
        assert live == {k: row[k] for k in live}
        n = conn.execute(text("SELECT count(*) FROM analytics.training_mart")).scalar_one()
        assert n == 24


def test_import_does_not_overwrite(pg):
    with pytest.raises(ValueError, match="already contains"):
        load_dataset(pg, demo_frames(), "demo", {})


def test_no_training_metrics_on_synthetic_data(pg, tmp_path):
    with pytest.raises(ValueError, match="real Berka"):
        train(pg, tmp_path)


def test_end_to_end_application_and_export(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/metadata").json()["mode"] == "demo"
    assert client.get("/portfolio").json()["loans"] == 48
    assert client.get("/portfolio?status=B").json()["loans"] == 12
    assert len(client.get("/loans?status=B").json()) == 12
    assert client.get("/clients/1").json()["client"]["client_id"] == 1
    response = client.post("/applications/evaluate", json=payload())
    assert response.status_code == 201, response.text
    report = response.json()
    assert report["status"] == "manual_review"
    assert report["model"]["available"] is False
    assert all(r["status"] == "passed" for r in report["rules"]["checks"])
    saved = client.get(f"/applications/{report['application_id']}").json()
    assert saved["result"] == report
    csv = client.get("/portfolio/export?status=B").text
    assert "dataset_mode,currency" in csv and "demo,CZK" in csv
    assert len(csv.splitlines()) == 13


def test_rule_violation_and_validation(client):
    result = client.post("/applications/evaluate", json=payload(available_limit=0)).json()
    assert result["status"] == "rule_violation"
    assert client.post("/applications/evaluate", json=payload(as_of="2100-01-01")).status_code == 422
    assert client.post("/applications/evaluate", json=payload(account_id=999999)).status_code == 422
    assert client.post("/applications/evaluate", json=payload(as_of="1900-01-01")).status_code == 422
    assert client.post("/calculator/payment", json={"amount": 100, "months": 0, "annual_rate_pct": 1}).status_code == 422
    assert client.post("/calculator/payment", json={"amount": 1200, "months": 12, "annual_rate_pct": 0}).json()["monthly_payment"] == 100
    assert client.get("/clients/999999").status_code == 404
    assert client.get("/portfolio?status=Z").status_code == 422
    assert client.get("/clients?q=%27%20OR%201%3D1--").json() == []

import json
import os
import uuid
from datetime import date

from fastapi.encoders import jsonable_encoder
from sqlalchemy import text

from .finance import payment
from .ml import score
from .rules import evaluate_rules


def dataset(conn):
    row = conn.execute(text("SELECT mode, reference_date, imported_at FROM raw.dataset WHERE id=1")).mappings().first()
    if row is None:
        raise ValueError("База пуста. Загрузите демонстрационные данные или Berka.")
    return dict(row)


def features_for(conn, account_id, as_of, amount, months, monthly):
    row = conn.execute(text("SELECT * FROM analytics.account_features(:id, CAST(:as_of AS date), :amount, :months, :payment)"),
                       {"id": account_id, "as_of": as_of, "amount": amount, "months": months, "payment": monthly}).mappings().first()
    if row is None:
        raise ValueError("Счёт не найден или дата оценки раньше открытия счёта.")
    return dict(row)


def evaluate(conn, request):
    source = dataset(conn)
    if request.as_of > source["reference_date"]:
        raise ValueError(f"Дата оценки не должна быть позже даты доступных данных {source['reference_date']}.")
    calculation = payment(request.amount, request.annual_rate_pct, request.months)
    features = features_for(conn, request.account_id, request.as_of, request.amount, request.months, calculation["monthly_payment"])
    rules = evaluate_rules(request, calculation["monthly_payment"], features)
    model = score(features, os.getenv("MODEL_DIR", "artifacts"), source["mode"])
    statuses = [r["status"] for r in rules["checks"]]
    if "failed" in statuses:
        status = "rule_violation"
    elif "unknown" in statuses or not model["available"] or model.get("requires_review"):
        status = "manual_review"
    else:
        status = "checks_passed"
    result = jsonable_encoder({"application_id": str(uuid.uuid4()), "dataset": source, "as_of": request.as_of,
                              "currency": "CZK", "status": status, "calculation": calculation,
                              "rules": rules, "model": model, "features": features,
                              "notice": "Учебная проверка. checks_passed не является одобрением кредита. Лимит и доход введены пользователем."})
    conn.execute(text("""INSERT INTO clean.applications(application_id, account_id, dataset_mode, request, result)
                      VALUES (CAST(:id AS uuid), :account, :mode, CAST(:request AS jsonb), CAST(:result AS jsonb))"""),
                 {"id": result["application_id"], "account": request.account_id, "mode": source["mode"],
                  "request": request.model_dump_json(), "result": json.dumps(result, ensure_ascii=False)})
    return result


def portfolio(conn, district=None, status=None):
    params = {"district": district, "status": status}
    where = "WHERE (CAST(:district AS integer) IS NULL OR a.district_id=:district) AND (CAST(:status AS text) IS NULL OR l.status=:status)"
    rows = conn.execute(text(f"""SELECT l.*, a.client_id, a.district_id FROM clean.loans l
                               JOIN clean.accounts a USING(account_id) {where} ORDER BY l.loan_id"""), params).mappings().all()
    items = [dict(r) for r in rows]
    return {"dataset": dataset(conn), "currency": "CZK", "loans": len(items),
            "original_amount_total": sum(float(r["amount"]) for r in items),
            "status_counts": {s: sum(r["status"] == s for r in items) for s in "ABCD"},
            "items": items, "amount_label": "Сумма при выдаче, не текущая задолженность"}

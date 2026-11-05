import csv
import io
import json
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .db import get_engine
from .finance import payment
from .schemas import ApplicationRequest, PaymentRequest
from .service import dataset, evaluate, portfolio

app = FastAPI(title="Credit Risk Desk", version="0.1.0", description="Учебная аналитика розничных кредитов. Валюта: CZK.")


@app.get("/health")
def health():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except SQLAlchemyError:
        raise HTTPException(503, "База данных недоступна") from None


@app.get("/metadata")
def metadata():
    with get_engine().connect() as conn:
        try:
            info = dataset(conn)
        except ValueError as exc:
            raise HTTPException(503, str(exc)) from exc
        info["districts"] = list(conn.execute(text("SELECT DISTINCT district_id FROM clean.accounts ORDER BY district_id")).scalars())
        return info


@app.get("/clients")
def clients(q: str = Query("", max_length=30), limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    with get_engine().connect() as conn:
        rows = conn.execute(text("""SELECT a.client_id, a.account_id, a.district_id, a.opened_at
            FROM clean.accounts a WHERE CAST(a.client_id AS text) LIKE :q OR CAST(a.account_id AS text) LIKE :q
            ORDER BY a.client_id, a.account_id LIMIT :limit OFFSET :offset"""),
            {"q": "%" + q + "%", "limit": limit, "offset": offset}).mappings().all()
        return [dict(r) for r in rows]


@app.get("/clients/{client_id}")
def client_card(client_id: int):
    with get_engine().connect() as conn:
        client = conn.execute(text("SELECT * FROM clean.clients WHERE client_id=:id"), {"id": client_id}).mappings().first()
        if client is None:
            raise HTTPException(404, "Клиент не найден")
        accounts = conn.execute(text("SELECT * FROM clean.accounts WHERE client_id=:id ORDER BY account_id"), {"id": client_id}).mappings().all()
        loans = conn.execute(text("SELECT l.* FROM clean.loans l JOIN clean.accounts a USING(account_id) WHERE a.client_id=:id"), {"id": client_id}).mappings().all()
        transactions = conn.execute(text("""SELECT t.* FROM clean.transactions t JOIN clean.accounts a USING(account_id)
           WHERE a.client_id=:id ORDER BY booked_at DESC, trans_id DESC LIMIT 100"""), {"id": client_id}).mappings().all()
        return {"client": dict(client), "dataset": dataset(conn), "accounts": [dict(r) for r in accounts],
                "loans": [dict(r) for r in loans], "recent_transactions": [dict(r) for r in transactions]}


@app.get("/loans")
def loans(status: str | None = Query(None, pattern="^[ABCD]$"), limit: int = Query(100, ge=1, le=1000)):
    with get_engine().connect() as conn:
        return [dict(r) for r in conn.execute(text("SELECT * FROM clean.loans WHERE CAST(:status AS text) IS NULL OR status=:status ORDER BY loan_id LIMIT :limit"), {"status": status, "limit": limit}).mappings()]


@app.get("/portfolio")
def get_portfolio(district: int | None = None, status: str | None = Query(None, pattern="^[ABCD]$")):
    with get_engine().connect() as conn:
        return portfolio(conn, district, status)


@app.get("/portfolio/export")
def export_portfolio(district: int | None = None, status: str | None = Query(None, pattern="^[ABCD]$")):
    with get_engine().connect() as conn:
        data = portfolio(conn, district, status)
    fields = ["dataset_mode", "currency", "loan_id", "account_id", "client_id", "district_id", "issued_at", "amount", "months", "payment", "status"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for row in data["items"]:
        writer.writerow({"dataset_mode": data["dataset"]["mode"], "currency": "CZK", **row})
    return Response(content="\ufeff" + buffer.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=credit-portfolio.csv"})


@app.post("/calculator/payment")
def calculate(request: PaymentRequest):
    return payment(request.amount, request.annual_rate_pct, request.months)


@app.post("/applications/evaluate", status_code=201)
def evaluate_application(request: ApplicationRequest):
    with get_engine().begin() as conn:
        try:
            return evaluate(conn, request)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc


@app.get("/applications")
def applications(limit: int = Query(30, ge=1, le=100)):
    with get_engine().connect() as conn:
        rows = conn.execute(text("""SELECT application_id, account_id, created_at, dataset_mode, result->>'status' AS status
                                   FROM clean.applications ORDER BY created_at DESC LIMIT :limit"""), {"limit": limit}).mappings()
        return [dict(r) for r in rows]


@app.get("/applications/{application_id}")
def application(application_id: UUID):
    with get_engine().connect() as conn:
        row = conn.execute(text("SELECT request, result FROM clean.applications WHERE application_id=:id"), {"id": application_id}).mappings().first()
        if row is None:
            raise HTTPException(404, "Заявка не найдена")
        return dict(row)

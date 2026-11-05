import json
import os
from pathlib import Path


def load_rules():
    return json.loads(Path(os.getenv("RULES_PATH", "config/rules.json")).read_text(encoding="utf-8"))


def evaluate_rules(request, monthly_payment, features, config=None):
    c = config or load_rules()
    checks = []

    def add(code, passed, reason):
        checks.append({"code": code, "status": "unknown" if passed is None else "passed" if passed else "failed", "reason": reason})

    add("amount", c["min_amount"] <= request.amount <= c["max_amount"],
        f"Сумма: {request.amount:,.0f} CZK; допустимо {c['min_amount']:,.0f}–{c['max_amount']:,.0f}.")
    add("term", c["min_months"] <= request.months <= c["max_months"],
        f"Срок: {request.months} мес.; допустимо {c['min_months']}–{c['max_months']}.")
    add("available_limit", None if request.available_limit is None else request.amount <= request.available_limit,
        "Лимит не предоставлен." if request.available_limit is None else f"Заявленный доступный лимит: {request.available_limit:,.0f} CZK; внешняя проверка не выполнялась.")
    burden = None
    if request.declared_monthly_income is not None and request.existing_monthly_payments is not None:
        burden = (monthly_payment + request.existing_monthly_payments) / request.declared_monthly_income
    add("payment_to_income", None if burden is None else burden <= c["max_payment_to_income"],
        "Нужны заявленные доход и действующие платежи." if burden is None else f"Нагрузка по заявленным данным: {burden:.1%}; максимум {c['max_payment_to_income']:.0%}.")
    history_ok = features["account_age_days"] >= c["minimum_history_days"] and features["tx_count_90d"] > 0
    add("history", True if history_ok else None,
        "Есть история операций за расчётное окно." if history_ok else "Недостаточно истории: требуется ручная проверка.")
    return {"version": c["version"], "checks": checks, "payment_to_income": burden}

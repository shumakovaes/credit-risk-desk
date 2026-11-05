import math


def payment(amount: float, annual_rate_pct: float, months: int) -> dict:
    """Monthly annuity, nominal annual rate in percent, no fees/insurance."""
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError("Сумма должна быть положительным конечным числом")
    if isinstance(months, bool) or not isinstance(months, int) or not 1 <= months <= 600:
        raise ValueError("Срок должен быть целым числом от 1 до 600 месяцев")
    if not math.isfinite(annual_rate_pct) or not 0 <= annual_rate_pct <= 100:
        raise ValueError("Ставка должна быть от 0 до 100 процентов годовых")
    rate = annual_rate_pct / 1200
    monthly = amount / months if rate == 0 else amount * rate / (-math.expm1(-months * math.log1p(rate)))
    total = monthly * months
    return {"monthly_payment": round(monthly, 2), "total_payment": round(total, 2),
            "interest": round(total - amount, 2), "currency": "CZK",
            "annual_rate_pct": annual_rate_pct, "months": months,
            "assumption": "Номинальная ставка, ежемесячные платежи, без комиссий; последний платёж может отличаться из-за округления."}

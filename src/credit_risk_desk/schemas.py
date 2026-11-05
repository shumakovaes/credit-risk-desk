from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Money = Annotated[float, Field(gt=0, le=100_000_000, allow_inf_nan=False)]
NonNegative = Annotated[float, Field(ge=0, le=100_000_000, allow_inf_nan=False)]


class PaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Money
    annual_rate_pct: float = Field(ge=0, le=100, allow_inf_nan=False)
    months: int = Field(ge=1, le=600, strict=True)


class ApplicationRequest(PaymentRequest):
    account_id: int = Field(gt=0, strict=True)
    as_of: date
    declared_monthly_income: Money | None = None
    existing_monthly_payments: NonNegative | None = None
    available_limit: NonNegative | None = None

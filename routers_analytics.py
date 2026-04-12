from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import Category, Transaction, User

router = APIRouter(prefix="/analytics", tags=["analytics"])


# --- Response schemas ---

class CategoryBudgetPlan(BaseModel):
    category_id: int
    category_name: str
    monthly_totals: list[Decimal]  # oldest -> newest
    average: Decimal
    trend: str  # "rising" | "falling" | "stable"
    trend_pct: float
    suggested_budget: Decimal


class BudgetPlanResponse(BaseModel):
    months_analyzed: int
    period_start: date
    period_end: date
    transaction_type: str
    total_suggested_budget: Decimal
    categories: list[CategoryBudgetPlan]


# --- Helpers ---

def _shift_months(year: int, month: int, delta: int) -> tuple[int, int]:
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


# --- Endpoint ---

@router.get("/budget-plan", response_model=BudgetPlanResponse)
def budget_plan(
    months: int = Query(3, ge=2, le=12, description="Number of past months to analyze"),
    transaction_type: str = Query("expense", pattern="^(expense|income)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BudgetPlanResponse:
    # 1. Build the month window [oldest -> current], inclusive
    today = datetime.now()
    start_year, start_month = _shift_months(today.year, today.month, -(months - 1))
    period_start = date(start_year, start_month, 1)
    period_end = today.date()

    month_indices: list[tuple[int, int]] = []
    y, m = start_year, start_month
    for _ in range(months):
        month_indices.append((y, m))
        y, m = _shift_months(y, m, 1)
    month_pos = {key: i for i, key in enumerate(month_indices)}

    # 2. Fetch user's transactions in the window, joined with category names
    stmt = (
        select(Transaction, Category.name)
        .join(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.user_id == current_user.id,
            Transaction.type == transaction_type,
            Transaction.created_at >= datetime(start_year, start_month, 1),
        )
    )
    rows = db.execute(stmt).all()

    # 3. Aggregate: category_id -> [total per month], oldest -> newest
    buckets: dict[int, list[Decimal]] = defaultdict(
        lambda: [Decimal("0")] * months
    )
    names: dict[int, str] = {}
    for tx, cat_name in rows:
        key = (tx.created_at.year, tx.created_at.month)
        idx = month_pos.get(key)
        if idx is None:
            continue
        buckets[tx.category_id][idx] += tx.amount
        names[tx.category_id] = cat_name

    # 4. Linear weights favoring recent months: oldest=1, newest=N
    weights = [Decimal(i + 1) for i in range(months)]
    weight_sum = sum(weights)

    categories_out: list[CategoryBudgetPlan] = []
    total_budget = Decimal("0")

    for cat_id, totals in buckets.items():
        # Simple average
        average = sum(totals) / Decimal(months)

        # Weighted moving average -> suggested next-month budget
        weighted = sum(t * w for t, w in zip(totals, weights)) / weight_sum

        # Trend: compare newer half vs older half of the window
        half = months // 2
        older_avg = (
            sum(totals[:half]) / Decimal(half) if half else Decimal("0")
        )
        newer_avg = sum(totals[half:]) / Decimal(months - half)

        if older_avg == 0 and newer_avg == 0:
            trend, trend_pct = "stable", 0.0
        elif older_avg == 0:
            trend, trend_pct = "rising", 100.0
        else:
            diff_pct = float((newer_avg - older_avg) / older_avg * 100)
            trend_pct = round(diff_pct, 2)
            if abs(diff_pct) < 5:
                trend = "stable"
            elif diff_pct > 0:
                trend = "rising"
            else:
                trend = "falling"

        suggested = _q(weighted)
        total_budget += suggested
        categories_out.append(
            CategoryBudgetPlan(
                category_id=cat_id,
                category_name=names[cat_id],
                monthly_totals=[_q(t) for t in totals],
                average=_q(average),
                trend=trend,
                trend_pct=trend_pct,
                suggested_budget=suggested,
            )
        )

    categories_out.sort(key=lambda c: c.suggested_budget, reverse=True)

    return BudgetPlanResponse(
        months_analyzed=months,
        period_start=period_start,
        period_end=period_end,
        transaction_type=transaction_type,
        total_suggested_budget=_q(total_budget),
        categories=categories_out,
    )

"""Analytics router.

Endpoints:

* ``GET /analytics/budget-plan`` — weighted-moving-average budget suggestion.
* ``GET /analytics/transactions`` — filtered & sorted transaction listing.
* ``GET /analytics/anomalies`` — categories whose monthly spending exceeds
  their historical mean by more than two standard deviations.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from statistics import pstdev

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import Category, Transaction, User
from schemas import TransactionResponse

router = APIRouter(prefix="/analytics", tags=["analytics"])


# --- Response schemas ---

class CategoryBudgetPlan(BaseModel):
    """Per-category analytics summary and suggested next-month budget."""

    category_id: int
    category_name: str
    monthly_totals: list[Decimal]  # oldest -> newest
    average: Decimal
    trend: str  # "rising" | "falling" | "stable"
    trend_pct: float
    suggested_budget: Decimal


class BudgetPlanResponse(BaseModel):
    """Aggregated budget-plan response covering all active categories."""

    months_analyzed: int
    period_start: date
    period_end: date
    transaction_type: str
    total_suggested_budget: Decimal
    categories: list[CategoryBudgetPlan]


class AnomalousMonth(BaseModel):
    """A single month whose total exceeds the category's mean + 2·σ threshold."""

    month: str  # "YYYY-MM"
    total: Decimal
    deviation_sigmas: float


class CategoryAnomaly(BaseModel):
    """Category whose spending shows at least one anomalous month."""

    category_id: int
    category_name: str
    mean_monthly: Decimal
    stdev_monthly: Decimal
    threshold: Decimal
    anomalous_months: list[AnomalousMonth]


class AnomaliesResponse(BaseModel):
    """Wrapper around the list of categories with anomalous spending."""

    months_analyzed: int
    transaction_type: str
    anomalies: list[CategoryAnomaly]


# --- Helpers ---

def _shift_months(year: int, month: int, delta: int) -> tuple[int, int]:
    """Return ``(year, month)`` shifted by ``delta`` whole months."""
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


def _q(value: Decimal) -> Decimal:
    """Quantize a Decimal to two fractional digits for monetary output."""
    return value.quantize(Decimal("0.01"))


# --- Endpoint ---

@router.get("/budget-plan", response_model=BudgetPlanResponse)
# pylint: disable=too-many-locals
def budget_plan(
    months: int = Query(3, ge=2, le=12, description="Number of past months to analyze"),
    transaction_type: str = Query("expense", pattern="^(expense|income)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BudgetPlanResponse:
    """Compute per-category averages, trend and suggested next-month budget.

    Fetches the authenticated user's transactions of the requested type
    over the last ``months`` months, groups them by ``(category, month)``,
    and returns a weighted-moving-average budget recommendation together
    with a rising/falling/stable trend marker per category.
    """
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


# --- Filtered transaction listing ------------------------------------------


@router.get("/transactions", response_model=list[TransactionResponse])
# pylint: disable=too-many-arguments
def list_transactions(
    date_from: date | None = Query(
        None, description="Include transactions on/after this date (inclusive)"
    ),
    date_to: date | None = Query(
        None, description="Include transactions on/before this date (inclusive)"
    ),
    category_id: int | None = Query(None, ge=1),
    transaction_type: str | None = Query(
        None, pattern="^(expense|income)$"
    ),
    sort_by: str = Query("date", pattern="^(date|amount)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TransactionResponse]:
    """Return the current user's transactions filtered by date/category/type.

    Supports sorting by either ``date`` (``created_at``) or ``amount``,
    ascending or descending.
    """
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="date_from must be on or before date_to",
        )

    if category_id is not None:
        category = db.get(Category, category_id)
        if category is None or category.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found or does not belong to the current user",
            )

    stmt = select(Transaction).where(Transaction.user_id == current_user.id)

    if date_from is not None:
        stmt = stmt.where(
            Transaction.created_at >= datetime.combine(date_from, datetime.min.time())
        )
    if date_to is not None:
        # date_to is inclusive → use strict "<" against the next day at 00:00
        stmt = stmt.where(
            Transaction.created_at
            < datetime.combine(date_to + timedelta(days=1), datetime.min.time())
        )
    if category_id is not None:
        stmt = stmt.where(Transaction.category_id == category_id)
    if transaction_type is not None:
        stmt = stmt.where(Transaction.type == transaction_type)

    sort_col = Transaction.amount if sort_by == "amount" else Transaction.created_at
    stmt = stmt.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

    return list(db.scalars(stmt).all())


# --- Anomaly detection ------------------------------------------------------


@router.get("/anomalies", response_model=AnomaliesResponse)
# pylint: disable=too-many-locals
def anomalies(
    months: int = Query(
        6,
        ge=3,
        le=24,
        description="Historical window in months (at least 3 for meaningful σ)",
    ),
    transaction_type: str = Query("expense", pattern="^(expense|income)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnomaliesResponse:
    """Detect categories with months whose total exceeds mean + 2·σ.

    For each category with activity in the window, computes the mean and
    population standard deviation of per-month totals (zero-filled for
    months with no activity) and flags any month whose total rises above
    ``mean + 2 * σ``. Categories with at least one flagged month appear in
    the response.
    """
    # 1. Build the month window
    today = datetime.now()
    start_year, start_month = _shift_months(today.year, today.month, -(months - 1))

    month_indices: list[tuple[int, int]] = []
    y, m = start_year, start_month
    for _ in range(months):
        month_indices.append((y, m))
        y, m = _shift_months(y, m, 1)
    month_pos = {key: i for i, key in enumerate(month_indices)}
    month_labels = [f"{yy:04d}-{mm:02d}" for yy, mm in month_indices]

    # 2. Aggregate monthly totals per category
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

    buckets: dict[int, list[Decimal]] = defaultdict(
        lambda: [Decimal("0")] * months
    )
    names: dict[int, str] = {}
    for tx, cat_name in rows:
        idx = month_pos.get((tx.created_at.year, tx.created_at.month))
        if idx is None:
            continue
        buckets[tx.category_id][idx] += tx.amount
        names[tx.category_id] = cat_name

    # 3. For each category, compute mean/σ and find anomalous months
    result: list[CategoryAnomaly] = []
    for cat_id, totals in buckets.items():
        floats = [float(t) for t in totals]
        mean_val = sum(floats) / len(floats)
        sigma = pstdev(floats)  # pstdev works for n>=1; 0 for constant data
        if sigma == 0:
            continue  # no variation -> no anomalies possible

        threshold = mean_val + 2 * sigma
        flagged: list[AnomalousMonth] = []
        for idx, total in enumerate(floats):
            if total > threshold:
                deviation = (total - mean_val) / sigma
                flagged.append(
                    AnomalousMonth(
                        month=month_labels[idx],
                        total=_q(Decimal(str(total))),
                        deviation_sigmas=round(deviation, 2),
                    )
                )
        if flagged:
            result.append(
                CategoryAnomaly(
                    category_id=cat_id,
                    category_name=names[cat_id],
                    mean_monthly=_q(Decimal(str(mean_val))),
                    stdev_monthly=_q(Decimal(str(sigma))),
                    threshold=_q(Decimal(str(threshold))),
                    anomalous_months=flagged,
                )
            )

    # Sort categories by largest deviation first
    result.sort(
        key=lambda c: max(m.deviation_sigmas for m in c.anomalous_months),
        reverse=True,
    )

    return AnomaliesResponse(
        months_analyzed=months,
        transaction_type=transaction_type,
        anomalies=result,
    )

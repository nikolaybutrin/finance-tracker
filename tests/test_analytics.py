from datetime import datetime
from decimal import Decimal

from models import Transaction, User


def _shift_months(year: int, month: int, delta: int) -> tuple[int, int]:
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


def _insert_tx(db, user_id, category_id, amount, year, month, tx_type="expense"):
    tx = Transaction(
        amount=Decimal(amount),
        description=None,
        type=tx_type,
        user_id=user_id,
        category_id=category_id,
        created_at=datetime(year, month, 15, 12, 0, 0),
    )
    db.add(tx)


def test_budget_plan_requires_auth(client):
    resp = client.get("/analytics/budget-plan")
    assert resp.status_code == 401


def test_budget_plan_empty(client, auth_headers):
    resp = client.get(
        "/analytics/budget-plan?months=3", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["months_analyzed"] == 3
    assert body["transaction_type"] == "expense"
    assert body["categories"] == []
    assert Decimal(body["total_suggested_budget"]) == Decimal("0.00")


def test_budget_plan_rising_trend_and_weighted_budget(
    client, auth_headers, db_session, registered_user
):
    # Set up a category via API
    cat = client.post(
        "/categories", json={"name": "Food"}, headers=auth_headers
    ).json()
    user_id = db_session.query(User).filter_by(username="alice").one().id

    # Insert monthly totals 100 / 200 / 300 across the 3-month window
    now = datetime.now()
    m0 = _shift_months(now.year, now.month, -2)  # oldest
    m1 = _shift_months(now.year, now.month, -1)
    m2 = (now.year, now.month)  # newest

    _insert_tx(db_session, user_id, cat["id"], "100.00", *m0)
    _insert_tx(db_session, user_id, cat["id"], "200.00", *m1)
    _insert_tx(db_session, user_id, cat["id"], "300.00", *m2)
    db_session.commit()

    resp = client.get(
        "/analytics/budget-plan?months=3", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()

    assert len(body["categories"]) == 1
    plan = body["categories"][0]
    assert plan["category_name"] == "Food"
    assert [Decimal(x) for x in plan["monthly_totals"]] == [
        Decimal("100.00"),
        Decimal("200.00"),
        Decimal("300.00"),
    ]
    # Simple average: (100+200+300)/3 = 200
    assert Decimal(plan["average"]) == Decimal("200.00")
    # Weighted: (100*1 + 200*2 + 300*3) / 6 = 1400/6 ≈ 233.33
    assert Decimal(plan["suggested_budget"]) == Decimal("233.33")
    assert plan["trend"] == "rising"
    assert plan["trend_pct"] > 0
    # Total = sum of per-category suggested
    assert Decimal(body["total_suggested_budget"]) == Decimal("233.33")


def test_budget_plan_falling_trend(
    client, auth_headers, db_session
):
    cat = client.post(
        "/categories", json={"name": "Entertainment"}, headers=auth_headers
    ).json()
    user_id = db_session.query(User).filter_by(username="alice").one().id

    now = datetime.now()
    m0 = _shift_months(now.year, now.month, -2)
    m1 = _shift_months(now.year, now.month, -1)
    m2 = (now.year, now.month)

    _insert_tx(db_session, user_id, cat["id"], "500.00", *m0)
    _insert_tx(db_session, user_id, cat["id"], "400.00", *m1)
    _insert_tx(db_session, user_id, cat["id"], "100.00", *m2)
    db_session.commit()

    resp = client.get(
        "/analytics/budget-plan?months=3", headers=auth_headers
    )
    plan = resp.json()["categories"][0]
    assert plan["trend"] == "falling"
    assert plan["trend_pct"] < 0


def test_budget_plan_income_filter(client, auth_headers, db_session):
    cat = client.post(
        "/categories", json={"name": "Salary"}, headers=auth_headers
    ).json()
    user_id = db_session.query(User).filter_by(username="alice").one().id

    now = datetime.now()
    m = (now.year, now.month)
    _insert_tx(db_session, user_id, cat["id"], "1000.00", *m, tx_type="income")
    _insert_tx(db_session, user_id, cat["id"], "50.00", *m, tx_type="expense")
    db_session.commit()

    resp = client.get(
        "/analytics/budget-plan?months=3&transaction_type=income",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    cats = resp.json()["categories"]
    assert len(cats) == 1
    assert cats[0]["category_name"] == "Salary"
    # Only the income row should be counted; it's in the newest month slot
    assert Decimal(cats[0]["monthly_totals"][-1]) == Decimal("1000.00")

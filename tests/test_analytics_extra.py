"""Tests for analytics filter/sort listing and anomaly detection endpoints."""

from datetime import datetime, timedelta
from decimal import Decimal

from models import Transaction, User


def _insert_tx(
    db, user_id, category_id, amount, when: datetime, tx_type="expense"
):
    tx = Transaction(
        amount=Decimal(amount),
        description=None,
        type=tx_type,
        user_id=user_id,
        category_id=category_id,
        created_at=when,
    )
    db.add(tx)
    return tx


# --- /analytics/transactions ------------------------------------------------


def test_filter_requires_auth(client):
    assert client.get("/analytics/transactions").status_code == 401


def test_filter_empty(client, auth_headers):
    resp = client.get("/analytics/transactions", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_filter_sort_by_amount_desc(client, auth_headers):
    cat = client.post(
        "/categories", json={"name": "Food"}, headers=auth_headers
    ).json()
    for amt in ("5.00", "20.00", "15.00"):
        client.post(
            "/transactions",
            json={
                "amount": amt,
                "description": None,
                "type": "expense",
                "category_id": cat["id"],
            },
            headers=auth_headers,
        )

    resp = client.get(
        "/analytics/transactions?sort_by=amount&order=desc",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    amounts = [Decimal(t["amount"]) for t in resp.json()]
    assert amounts == [Decimal("20.00"), Decimal("15.00"), Decimal("5.00")]


def test_filter_sort_by_amount_asc(client, auth_headers):
    cat = client.post(
        "/categories", json={"name": "Food"}, headers=auth_headers
    ).json()
    for amt in ("5.00", "20.00", "15.00"):
        client.post(
            "/transactions",
            json={
                "amount": amt,
                "description": None,
                "type": "expense",
                "category_id": cat["id"],
            },
            headers=auth_headers,
        )

    resp = client.get(
        "/analytics/transactions?sort_by=amount&order=asc",
        headers=auth_headers,
    )
    amounts = [Decimal(t["amount"]) for t in resp.json()]
    assert amounts == [Decimal("5.00"), Decimal("15.00"), Decimal("20.00")]


def test_filter_by_category(client, auth_headers):
    food = client.post(
        "/categories", json={"name": "Food"}, headers=auth_headers
    ).json()
    rent = client.post(
        "/categories", json={"name": "Rent"}, headers=auth_headers
    ).json()

    for cat_id in (food["id"], food["id"], rent["id"]):
        client.post(
            "/transactions",
            json={
                "amount": "10.00",
                "description": None,
                "type": "expense",
                "category_id": cat_id,
            },
            headers=auth_headers,
        )

    resp = client.get(
        f"/analytics/transactions?category_id={food['id']}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert all(t["category_id"] == food["id"] for t in body)


def test_filter_by_category_not_found(client, auth_headers):
    resp = client.get(
        "/analytics/transactions?category_id=9999", headers=auth_headers
    )
    assert resp.status_code == 404


def test_filter_by_type(client, auth_headers):
    cat = client.post(
        "/categories", json={"name": "Salary"}, headers=auth_headers
    ).json()
    client.post(
        "/transactions",
        json={
            "amount": "1000.00",
            "description": None,
            "type": "income",
            "category_id": cat["id"],
        },
        headers=auth_headers,
    )
    client.post(
        "/transactions",
        json={
            "amount": "50.00",
            "description": None,
            "type": "expense",
            "category_id": cat["id"],
        },
        headers=auth_headers,
    )

    resp = client.get(
        "/analytics/transactions?transaction_type=income", headers=auth_headers
    )
    body = resp.json()
    assert len(body) == 1
    assert body[0]["type"] == "income"


def test_filter_by_date_range(client, auth_headers, db_session):
    cat = client.post(
        "/categories", json={"name": "Food"}, headers=auth_headers
    ).json()
    user_id = db_session.query(User).filter_by(username="alice").one().id

    # Insert explicit historical dates
    _insert_tx(db_session, user_id, cat["id"], "10.00", datetime(2026, 1, 10))
    _insert_tx(db_session, user_id, cat["id"], "20.00", datetime(2026, 2, 15))
    _insert_tx(db_session, user_id, cat["id"], "30.00", datetime(2026, 3, 20))
    db_session.commit()

    resp = client.get(
        "/analytics/transactions?date_from=2026-02-01&date_to=2026-02-28",
        headers=auth_headers,
    )
    body = resp.json()
    assert len(body) == 1
    assert Decimal(body[0]["amount"]) == Decimal("20.00")


def test_filter_invalid_date_range(client, auth_headers):
    resp = client.get(
        "/analytics/transactions?date_from=2026-03-01&date_to=2026-02-01",
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_filter_invalid_sort_by(client, auth_headers):
    resp = client.get(
        "/analytics/transactions?sort_by=foo", headers=auth_headers
    )
    assert resp.status_code == 422


# --- /analytics/anomalies ---------------------------------------------------


def test_anomalies_requires_auth(client):
    assert client.get("/analytics/anomalies").status_code == 401


def test_anomalies_empty(client, auth_headers):
    resp = client.get("/analytics/anomalies?months=3", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["months_analyzed"] == 3
    assert body["anomalies"] == []


def test_anomalies_detects_spike(client, auth_headers, db_session):
    cat = client.post(
        "/categories", json={"name": "Food"}, headers=auth_headers
    ).json()
    user_id = db_session.query(User).filter_by(username="alice").one().id

    # Build 6 monthly totals where one month is a massive outlier.
    # Values: [100, 100, 100, 100, 100, 1000]  -> mean ≈ 250, σ ≈ 335,
    # threshold ≈ 920, so 1000 is flagged.
    now = datetime.now()

    def month_start(delta):
        y = now.year
        m = now.month + delta
        while m <= 0:
            m += 12
            y -= 1
        while m > 12:
            m -= 12
            y += 1
        return datetime(y, m, 15)

    amounts = ["100", "100", "100", "100", "100", "1000"]
    for delta, amt in zip(range(-5, 1), amounts):
        _insert_tx(db_session, user_id, cat["id"], amt, month_start(delta))
    db_session.commit()

    resp = client.get("/analytics/anomalies?months=6", headers=auth_headers)
    assert resp.status_code == 200
    anomalies = resp.json()["anomalies"]
    assert len(anomalies) == 1
    an = anomalies[0]
    assert an["category_name"] == "Food"
    assert len(an["anomalous_months"]) == 1
    flagged = an["anomalous_months"][0]
    assert Decimal(flagged["total"]) == Decimal("1000.00")
    assert flagged["deviation_sigmas"] > 2.0


def test_anomalies_skipped_when_constant(client, auth_headers, db_session):
    cat = client.post(
        "/categories", json={"name": "Rent"}, headers=auth_headers
    ).json()
    user_id = db_session.query(User).filter_by(username="alice").one().id

    now = datetime.now()
    for delta in range(-5, 1):
        when = datetime(now.year, ((now.month - 1 + delta) % 12) + 1, 15)
        _insert_tx(db_session, user_id, cat["id"], "500.00", when)
    db_session.commit()

    resp = client.get("/analytics/anomalies?months=6", headers=auth_headers)
    # Constant spending -> σ=0 -> no anomalies
    assert resp.json()["anomalies"] == []


def test_anomalies_invalid_months(client, auth_headers):
    resp = client.get("/analytics/anomalies?months=2", headers=auth_headers)
    assert resp.status_code == 422  # below ge=3

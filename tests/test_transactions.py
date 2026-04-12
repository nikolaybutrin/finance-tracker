def test_create_transaction_requires_auth(client):
    resp = client.post(
        "/transactions",
        json={
            "amount": "100.00",
            "description": "lunch",
            "type": "expense",
            "category_id": 1,
        },
    )
    assert resp.status_code == 401


def test_create_transaction(client, auth_headers):
    category = client.post(
        "/categories", json={"name": "Food"}, headers=auth_headers
    ).json()

    resp = client.post(
        "/transactions",
        json={
            "amount": "42.50",
            "description": "lunch",
            "type": "expense",
            "category_id": category["id"],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["amount"] == "42.50"
    assert data["type"] == "expense"
    assert data["category_id"] == category["id"]
    assert data["description"] == "lunch"


def test_create_transaction_unknown_category(client, auth_headers):
    resp = client.post(
        "/transactions",
        json={
            "amount": "10.00",
            "description": None,
            "type": "expense",
            "category_id": 9999,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_create_transaction_rejects_foreign_category(client):
    # User 1 creates a category
    client.post(
        "/register",
        json={"username": "u1", "email": "u1@e.com", "password": "password1"},
    )
    t1 = client.post(
        "/login", data={"username": "u1", "password": "password1"}
    ).json()["access_token"]
    cat = client.post(
        "/categories",
        json={"name": "Food"},
        headers={"Authorization": f"Bearer {t1}"},
    ).json()

    # User 2 tries to use it
    client.post(
        "/register",
        json={"username": "u2", "email": "u2@e.com", "password": "password2"},
    )
    t2 = client.post(
        "/login", data={"username": "u2", "password": "password2"}
    ).json()["access_token"]
    resp = client.post(
        "/transactions",
        json={
            "amount": "10.00",
            "description": None,
            "type": "expense",
            "category_id": cat["id"],
        },
        headers={"Authorization": f"Bearer {t2}"},
    )
    assert resp.status_code == 400


def test_list_transactions(client, auth_headers):
    category = client.post(
        "/categories", json={"name": "Food"}, headers=auth_headers
    ).json()
    for amount in ("10.00", "20.00", "30.00"):
        client.post(
            "/transactions",
            json={
                "amount": amount,
                "description": None,
                "type": "expense",
                "category_id": category["id"],
            },
            headers=auth_headers,
        )

    resp = client.get("/transactions", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def _make_tx(client, auth_headers, category_id, amount="10.00", tx_type="expense"):
    return client.post(
        "/transactions",
        json={
            "amount": amount,
            "description": "test",
            "type": tx_type,
            "category_id": category_id,
        },
        headers=auth_headers,
    ).json()


def test_get_transaction(client, auth_headers):
    cat = client.post(
        "/categories", json={"name": "Food"}, headers=auth_headers
    ).json()
    tx = _make_tx(client, auth_headers, cat["id"])
    resp = client.get(f"/transactions/{tx['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == tx["id"]


def test_get_missing_transaction(client, auth_headers):
    resp = client.get("/transactions/9999", headers=auth_headers)
    assert resp.status_code == 404


def test_update_transaction(client, auth_headers):
    cat = client.post(
        "/categories", json={"name": "Food"}, headers=auth_headers
    ).json()
    tx = _make_tx(client, auth_headers, cat["id"], amount="10.00")

    resp = client.patch(
        f"/transactions/{tx['id']}",
        json={"amount": "99.99", "description": "updated"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["amount"] == "99.99"
    assert body["description"] == "updated"


def test_update_transaction_with_foreign_category(client, auth_headers):
    cat = client.post(
        "/categories", json={"name": "Food"}, headers=auth_headers
    ).json()
    tx = _make_tx(client, auth_headers, cat["id"])

    # A second user creates their own category
    client.post(
        "/register",
        json={"username": "intruder", "email": "int@e.com", "password": "password2"},
    )
    t2 = client.post(
        "/login", data={"username": "intruder", "password": "password2"}
    ).json()["access_token"]
    foreign_cat = client.post(
        "/categories",
        json={"name": "Other"},
        headers={"Authorization": f"Bearer {t2}"},
    ).json()

    resp = client.patch(
        f"/transactions/{tx['id']}",
        json={"category_id": foreign_cat["id"]},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_update_missing_transaction(client, auth_headers):
    resp = client.patch(
        "/transactions/9999",
        json={"amount": "5.00"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_delete_transaction(client, auth_headers):
    cat = client.post(
        "/categories", json={"name": "Food"}, headers=auth_headers
    ).json()
    tx = _make_tx(client, auth_headers, cat["id"])

    resp = client.delete(f"/transactions/{tx['id']}", headers=auth_headers)
    assert resp.status_code == 204

    resp = client.get(f"/transactions/{tx['id']}", headers=auth_headers)
    assert resp.status_code == 404


def test_delete_missing_transaction(client, auth_headers):
    resp = client.delete("/transactions/9999", headers=auth_headers)
    assert resp.status_code == 404


def test_create_transaction_invalid_amount(client, auth_headers):
    cat = client.post(
        "/categories", json={"name": "Food"}, headers=auth_headers
    ).json()
    resp = client.post(
        "/transactions",
        json={
            "amount": "-10.00",  # must be > 0
            "description": None,
            "type": "expense",
            "category_id": cat["id"],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_create_transaction_invalid_type(client, auth_headers):
    cat = client.post(
        "/categories", json={"name": "Food"}, headers=auth_headers
    ).json()
    resp = client.post(
        "/transactions",
        json={
            "amount": "10.00",
            "description": None,
            "type": "gift",  # not in enum
            "category_id": cat["id"],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_transaction_isolation_between_users(client, auth_headers):
    cat = client.post(
        "/categories", json={"name": "Food"}, headers=auth_headers
    ).json()
    tx = _make_tx(client, auth_headers, cat["id"])

    client.post(
        "/register",
        json={"username": "u2", "email": "u2@e.com", "password": "password2"},
    )
    t2 = client.post(
        "/login", data={"username": "u2", "password": "password2"}
    ).json()["access_token"]
    h2 = {"Authorization": f"Bearer {t2}"}

    # u2 cannot see or touch alice's transaction
    assert client.get(f"/transactions/{tx['id']}", headers=h2).status_code == 404
    assert client.delete(f"/transactions/{tx['id']}", headers=h2).status_code == 404

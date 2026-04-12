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

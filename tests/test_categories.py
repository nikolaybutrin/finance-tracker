def test_categories_require_auth(client):
    resp = client.get("/categories")
    assert resp.status_code == 401


def test_create_category(client, auth_headers):
    resp = client.post("/categories", json={"name": "Food"}, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Food"
    assert "id" in data
    assert "user_id" in data


def test_list_categories(client, auth_headers):
    for name in ("Food", "Transport", "Rent"):
        client.post("/categories", json={"name": name}, headers=auth_headers)

    resp = client.get("/categories", headers=auth_headers)
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()}
    assert names == {"Food", "Transport", "Rent"}


def test_get_category(client, auth_headers):
    created = client.post(
        "/categories", json={"name": "Food"}, headers=auth_headers
    ).json()
    resp = client.get(f"/categories/{created['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Food"


def test_get_missing_category(client, auth_headers):
    resp = client.get("/categories/9999", headers=auth_headers)
    assert resp.status_code == 404


def test_update_category(client, auth_headers):
    created = client.post(
        "/categories", json={"name": "Food"}, headers=auth_headers
    ).json()
    resp = client.patch(
        f"/categories/{created['id']}",
        json={"name": "Groceries"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Groceries"


def test_delete_category(client, auth_headers):
    created = client.post(
        "/categories", json={"name": "Food"}, headers=auth_headers
    ).json()
    resp = client.delete(f"/categories/{created['id']}", headers=auth_headers)
    assert resp.status_code == 204

    resp = client.get(f"/categories/{created['id']}", headers=auth_headers)
    assert resp.status_code == 404


def test_category_isolation_between_users(client):
    # User 1
    client.post(
        "/register",
        json={"username": "u1", "email": "u1@e.com", "password": "password1"},
    )
    t1 = client.post(
        "/login", data={"username": "u1", "password": "password1"}
    ).json()["access_token"]
    h1 = {"Authorization": f"Bearer {t1}"}
    client.post("/categories", json={"name": "U1-Cat"}, headers=h1)

    # User 2
    client.post(
        "/register",
        json={"username": "u2", "email": "u2@e.com", "password": "password2"},
    )
    t2 = client.post(
        "/login", data={"username": "u2", "password": "password2"}
    ).json()["access_token"]
    h2 = {"Authorization": f"Bearer {t2}"}

    resp = client.get("/categories", headers=h2)
    assert resp.status_code == 200
    assert resp.json() == []

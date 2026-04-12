def test_register_creates_user(client):
    resp = client.post(
        "/register",
        json={
            "username": "bob",
            "email": "bob@example.com",
            "password": "secret123",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "bob"
    assert data["email"] == "bob@example.com"
    assert "id" in data
    assert "password" not in data and "password_hash" not in data


def test_register_duplicate_username(client, registered_user):
    resp = client.post(
        "/register",
        json={
            "username": "alice",
            "email": "other@example.com",
            "password": "password123",
        },
    )
    assert resp.status_code == 400


def test_register_duplicate_email(client, registered_user):
    resp = client.post(
        "/register",
        json={
            "username": "alice2",
            "email": "alice@example.com",
            "password": "password123",
        },
    )
    assert resp.status_code == 400


def test_login_success(client, registered_user):
    resp = client.post(
        "/login",
        data={"username": "alice", "password": "password123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_wrong_password(client, registered_user):
    resp = client.post(
        "/login",
        data={"username": "alice", "password": "wrong-password"},
    )
    assert resp.status_code == 401


def test_login_unknown_user(client):
    resp = client.post(
        "/login",
        data={"username": "ghost", "password": "whatever1"},
    )
    assert resp.status_code == 401

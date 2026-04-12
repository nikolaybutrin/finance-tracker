"""Tests for the uniform error payload produced by global exception handlers."""


def test_404_payload_shape(client, auth_headers):
    resp = client.get("/categories/9999", headers=auth_headers)
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "not_found"
    assert body["status_code"] == 404
    assert "does not belong" in body["detail"]


def test_401_payload_shape(client):
    resp = client.get("/categories")
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"] == "unauthorized"
    assert body["status_code"] == 401


def test_422_payload_shape_on_register(client):
    resp = client.post(
        "/register",
        json={
            "username": "",  # violates min_length=1
            "email": "not-an-email",  # violates EmailStr
            "password": "short",  # violates min_length=8
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "validation_error"
    assert body["status_code"] == 422
    assert body["detail"] == "Request validation failed"
    fields = {e["field"] for e in body["errors"]}
    # At least email and password should show up as invalid
    assert "email" in fields
    assert "password" in fields


def test_422_on_invalid_query_param(client, auth_headers):
    resp = client.get(
        "/analytics/budget-plan?months=99", headers=auth_headers
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "validation_error"
    assert any(e["field"] == "months" for e in body["errors"])

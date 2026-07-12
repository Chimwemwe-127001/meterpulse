"""
Authentication and registration tests.
"""
from tests.conftest import register_and_login


def test_register_and_login(client):
    headers = register_and_login(client, "operator@example.com")
    resp = client.get("/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "operator@example.com"


def test_register_ignores_client_supplied_role(client):
    """Regression: role in the payload must not grant admin (CWE-915)."""
    resp = client.post("/auth/register", json={
        "email": "wannabe-admin@example.com",
        "password": "password123",
        "full_name": "Sneaky User",
        "role": "admin",
    })
    assert resp.status_code == 201
    assert resp.json()["role"] == "operator"


def test_duplicate_email_conflict(client):
    payload = {
        "email": "dup@example.com",
        "password": "password123",
        "full_name": "First User",
    }
    assert client.post("/auth/register", json=payload).status_code == 201
    assert client.post("/auth/register", json=payload).status_code == 409


def test_wrong_password_rejected(client):
    register_and_login(client, "user@example.com")
    resp = client.post("/auth/login", data={
        "username": "user@example.com",
        "password": "wrong-password",
    })
    assert resp.status_code == 401


def test_unknown_email_rejected(client):
    resp = client.post("/auth/login", data={
        "username": "ghost@example.com",
        "password": "password123",
    })
    assert resp.status_code == 401


def test_password_over_72_bytes_rejected(client):
    """bcrypt truncates at 72 bytes; longer passwords must be rejected."""
    resp = client.post("/auth/register", json={
        "email": "longpass@example.com",
        "password": "x" * 73,
        "full_name": "Long Password",
    })
    assert resp.status_code == 422


def test_protected_endpoint_requires_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/meters").status_code == 401

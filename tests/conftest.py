"""
Test configuration.

Environment must be set before importing the app: settings are read
(and cached) at import time.
"""
import os

os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["DATABASE_URL"] = "sqlite:///./test_meterpulse.db"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["DEBUG"] = "false"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine, SessionLocal
from app.main import app
from app.models.user import User


@pytest.fixture(autouse=True)
def fresh_schema():
    """Empty database for every test."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


def register_and_login(client: TestClient, email: str, role: str | None = None) -> dict:
    """
    Register a user and return Authorization headers.

    role='admin' promotes the account directly in the DB, since the API
    (correctly) refuses to accept a client-supplied role.
    """
    resp = client.post("/auth/register", json={
        "email": email,
        "password": "password123",
        "full_name": "Test User",
    })
    assert resp.status_code == 201, resp.text

    if role == "admin":
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == email).first()
            user.role = "admin"
            db.commit()
        finally:
            db.close()

    resp = client.post("/auth/login", data={"username": email, "password": "password123"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_meter(client: TestClient, headers: dict, code: str = "ZM-001") -> dict:
    resp = client.post("/meters", headers=headers, json={
        "meter_code": code,
        "location": "Cairo Road, Lusaka",
        "utility_type": "electricity",
        "unit": "kWh",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()

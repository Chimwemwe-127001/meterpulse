"""
Object-level authorization tests (OWASP API1:2023 - BOLA regressions).
"""
from tests.conftest import register_and_login, create_meter


def test_user_cannot_read_another_users_meter(client):
    headers_a = register_and_login(client, "alice@example.com")
    headers_b = register_and_login(client, "bob@example.com")
    meter = create_meter(client, headers_a)

    # Bob gets 404, not the meter (and not 403: existence isn't confirmed)
    resp = client.get(f"/meters/{meter['id']}", headers=headers_b)
    assert resp.status_code == 404


def test_user_cannot_update_another_users_meter(client):
    headers_a = register_and_login(client, "alice@example.com")
    headers_b = register_and_login(client, "bob@example.com")
    meter = create_meter(client, headers_a)

    resp = client.put(
        f"/meters/{meter['id']}",
        headers=headers_b,
        json={"status": "inactive"},
    )
    assert resp.status_code == 404


def test_user_cannot_submit_reading_to_another_users_meter(client):
    headers_a = register_and_login(client, "alice@example.com")
    headers_b = register_and_login(client, "bob@example.com")
    meter = create_meter(client, headers_a)

    resp = client.post(
        f"/meters/{meter['id']}/readings",
        headers=headers_b,
        json={"value": "100.0", "recorded_at": "2026-07-01T08:00:00Z"},
    )
    assert resp.status_code == 404


def test_meter_listing_is_scoped_to_owner(client):
    headers_a = register_and_login(client, "alice@example.com")
    headers_b = register_and_login(client, "bob@example.com")
    create_meter(client, headers_a, code="ZM-A")
    create_meter(client, headers_b, code="ZM-B")

    codes = [m["meter_code"] for m in client.get("/meters", headers=headers_b).json()["items"]]
    assert codes == ["ZM-B"]


def test_alerts_are_scoped_through_meter_ownership(client):
    headers_a = register_and_login(client, "alice@example.com")
    headers_b = register_and_login(client, "bob@example.com")
    meter = create_meter(client, headers_a)

    # Generate a NEGATIVE_DELTA alert on Alice's meter
    client.post(f"/meters/{meter['id']}/readings", headers=headers_a,
                json={"value": "100.0", "recorded_at": "2026-07-01T08:00:00Z"})
    resp = client.post(f"/meters/{meter['id']}/readings", headers=headers_a,
                       json={"value": "90.0", "recorded_at": "2026-07-02T08:00:00Z"})
    assert resp.status_code == 201
    assert any(a["alert_type"] == "NEGATIVE_DELTA" for a in resp.json()["alerts_generated"])

    # Alice sees the alert; Bob sees nothing and cannot resolve it
    alerts_a = client.get("/alerts", headers=headers_a).json()
    assert alerts_a["total"] == 1
    alert_id = alerts_a["items"][0]["id"]

    assert client.get("/alerts", headers=headers_b).json()["total"] == 0
    assert client.get(f"/alerts/{alert_id}", headers=headers_b).status_code == 404
    assert client.patch(f"/alerts/{alert_id}/resolve", headers=headers_b).status_code == 404


def test_admin_sees_all_meters(client):
    headers_a = register_and_login(client, "alice@example.com")
    admin = register_and_login(client, "admin@example.com", role="admin")
    meter = create_meter(client, headers_a)

    assert client.get(f"/meters/{meter['id']}", headers=admin).status_code == 200
    assert client.get("/meters", headers=admin).json()["total"] == 1


def test_delete_requires_admin(client):
    headers_a = register_and_login(client, "alice@example.com")
    admin = register_and_login(client, "admin@example.com", role="admin")
    meter = create_meter(client, headers_a)

    assert client.delete(f"/meters/{meter['id']}", headers=headers_a).status_code == 403
    assert client.delete(f"/meters/{meter['id']}", headers=admin).status_code == 204


def test_alert_resolution_is_audited(client):
    headers = register_and_login(client, "alice@example.com")
    meter = create_meter(client, headers)
    client.post(f"/meters/{meter['id']}/readings", headers=headers,
                json={"value": "100.0", "recorded_at": "2026-07-01T08:00:00Z"})
    client.post(f"/meters/{meter['id']}/readings", headers=headers,
                json={"value": "90.0", "recorded_at": "2026-07-02T08:00:00Z"})

    alert_id = client.get("/alerts", headers=headers).json()["items"][0]["id"]
    me = client.get("/auth/me", headers=headers).json()

    resolved = client.patch(f"/alerts/{alert_id}/resolve", headers=headers).json()
    assert resolved["resolved"] is True
    assert resolved["resolved_by"] == me["id"]
    assert resolved["resolved_at"] is not None

    unresolved = client.patch(f"/alerts/{alert_id}/resolve", headers=headers,
                              json={"resolved": False}).json()
    assert unresolved["resolved"] is False
    assert unresolved["resolved_by"] is None

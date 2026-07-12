"""
Reading submission, consumption calculation, and end-to-end anomaly tests.
"""
from datetime import datetime, timedelta, timezone

from tests.conftest import register_and_login, create_meter

BASE_TIME = datetime(2026, 6, 1, 8, 0, 0, tzinfo=timezone.utc)


def submit(client, headers, meter_id, value, at):
    return client.post(
        f"/meters/{meter_id}/readings",
        headers=headers,
        json={"value": str(value), "recorded_at": at.isoformat()},
    )


def test_first_reading_has_no_consumption(client):
    headers = register_and_login(client, "op@example.com")
    meter = create_meter(client, headers)

    resp = submit(client, headers, meter["id"], 100, BASE_TIME)
    assert resp.status_code == 201
    assert resp.json()["consumption"] is None


def test_consumption_is_delta_from_previous(client):
    headers = register_and_login(client, "op@example.com")
    meter = create_meter(client, headers)

    submit(client, headers, meter["id"], 100, BASE_TIME)
    resp = submit(client, headers, meter["id"], 112.5, BASE_TIME + timedelta(days=1))
    assert resp.status_code == 201
    assert float(resp.json()["consumption"]) == 12.5


def test_backdated_reading_rejected(client):
    """Regression: a backfilled recorded_at would corrupt deltas and
    raise a false tampering alert."""
    headers = register_and_login(client, "op@example.com")
    meter = create_meter(client, headers)

    submit(client, headers, meter["id"], 100, BASE_TIME)
    resp = submit(client, headers, meter["id"], 105, BASE_TIME - timedelta(days=1))
    assert resp.status_code == 409


def test_inactive_meter_rejects_readings(client):
    headers = register_and_login(client, "op@example.com")
    meter = create_meter(client, headers)
    client.put(f"/meters/{meter['id']}", headers=headers, json={"status": "inactive"})

    resp = submit(client, headers, meter["id"], 100, BASE_TIME)
    assert resp.status_code == 409


def test_negative_delta_alert(client):
    headers = register_and_login(client, "op@example.com")
    meter = create_meter(client, headers)

    submit(client, headers, meter["id"], 100, BASE_TIME)
    resp = submit(client, headers, meter["id"], 95, BASE_TIME + timedelta(days=1))
    types = [a["alert_type"] for a in resp.json()["alerts_generated"]]
    assert "NEGATIVE_DELTA" in types


def test_zero_reading_alert(client):
    headers = register_and_login(client, "op@example.com")
    meter = create_meter(client, headers)

    submit(client, headers, meter["id"], 100, BASE_TIME)
    submit(client, headers, meter["id"], 110, BASE_TIME + timedelta(days=1))
    resp = submit(client, headers, meter["id"], 110, BASE_TIME + timedelta(days=2))
    types = [a["alert_type"] for a in resp.json()["alerts_generated"]]
    assert "ZERO_READING" in types


def test_spike_alert_after_sufficient_history(client):
    headers = register_and_login(client, "op@example.com")
    meter = create_meter(client, headers)

    # 6 readings, 10 units/day steady -> 5 historical rates
    for i in range(6):
        resp = submit(client, headers, meter["id"], 100 + i * 10, BASE_TIME + timedelta(days=i))
        assert resp.json()["alerts_generated"] == []

    # 100 units in one day: 10x the median rate
    resp = submit(client, headers, meter["id"], 250, BASE_TIME + timedelta(days=6))
    types = [a["alert_type"] for a in resp.json()["alerts_generated"]]
    assert "SPIKE" in types


def test_no_spike_alert_with_insufficient_history(client):
    """A huge second reading must not alert: one delta is not a baseline."""
    headers = register_and_login(client, "op@example.com")
    meter = create_meter(client, headers)

    submit(client, headers, meter["id"], 100, BASE_TIME)
    submit(client, headers, meter["id"], 110, BASE_TIME + timedelta(days=1))
    resp = submit(client, headers, meter["id"], 500, BASE_TIME + timedelta(days=2))
    types = [a["alert_type"] for a in resp.json()["alerts_generated"]]
    assert "SPIKE" not in types


def test_irregular_interval_is_not_a_spike(client):
    """Regression: a two-week gap at normal daily usage is not a spike
    once consumption is normalized to a rate."""
    headers = register_and_login(client, "op@example.com")
    meter = create_meter(client, headers)

    for i in range(6):
        submit(client, headers, meter["id"], 100 + i * 10, BASE_TIME + timedelta(days=i))

    # 14 days later at the same 10/day usage: delta 140, rate 10/day
    resp = submit(client, headers, meter["id"], 290, BASE_TIME + timedelta(days=19))
    assert resp.json()["alerts_generated"] == []


def test_reading_list_and_summary(client):
    headers = register_and_login(client, "op@example.com")
    meter = create_meter(client, headers)

    now = datetime.now(timezone.utc)
    submit(client, headers, meter["id"], 100, now - timedelta(days=2))
    submit(client, headers, meter["id"], 110, now - timedelta(days=1))

    listing = client.get(f"/meters/{meter['id']}/readings", headers=headers).json()
    assert listing["total"] == 2

    summary = client.get(f"/meters/{meter['id']}/readings/summary", headers=headers).json()
    assert summary["reading_count"] == 2
    assert float(summary["total_consumption"]) == 10.0


def test_health_check_probes_database(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["database"] == "connected"


import sqlite3

import pytest
from fastapi.testclient import TestClient

import api.main as api_module
from detection.alert_store import initialize_alert_table, save_alert


@pytest.fixture
def client_with_alert(tmp_path, monkeypatch):
    database_path = tmp_path / "test_energy_data.db"

    connection = sqlite3.connect(database_path)
    connection.execute("""
        CREATE TABLE machine_telemetry (
            id INTEGER PRIMARY KEY
        )
    """)
    connection.execute(
        "INSERT INTO machine_telemetry (id) VALUES (1)"
    )
    connection.commit()
    connection.close()

    initialize_alert_table(database_path)

    detection_result = {
        "is_anomaly": True,
        "event_id": "TEST-EVENT-001",
        "machine_id": "MOTOR-01",
        "timestamp": "2026-10-12T10:00:00",
        "actual_power_kw": 65.0,
        "expected_power_kw": 55.0,
        "excess_power_kw": 10.0,
        "excess_percentage": 18.18,
        "residual_threshold_kw": 5.0,
        "severity": "HIGH",
        "detection_method": "TEST",
        "explanation": "Test alert for API validation.",
    }

    assert save_alert(1, detection_result, database_path) is True

    monkeypatch.setattr(
        api_module,
        "DATABASE_PATH",
        database_path,
    )

    with TestClient(api_module.app) as client:
        yield client


def test_open_to_acknowledged(client_with_alert):
    response = client_with_alert.patch(
        "/api/v1/alerts/1/status",
        json={"status": "ACKNOWLEDGED"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACKNOWLEDGED"


def test_acknowledged_to_resolved(client_with_alert):
    client_with_alert.patch(
        "/api/v1/alerts/1/status",
        json={"status": "ACKNOWLEDGED"},
    )

    response = client_with_alert.patch(
        "/api/v1/alerts/1/status",
        json={"status": "RESOLVED"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "RESOLVED"


def test_open_cannot_skip_to_resolved(client_with_alert):
    response = client_with_alert.patch(
        "/api/v1/alerts/1/status",
        json={"status": "RESOLVED"},
    )

    assert response.status_code == 409

    alert = client_with_alert.get("/api/v1/alerts/1")
    assert alert.json()["status"] == "OPEN"


def test_cannot_acknowledge_twice(client_with_alert):
    client_with_alert.patch(
        "/api/v1/alerts/1/status",
        json={"status": "ACKNOWLEDGED"},
    )

    response = client_with_alert.patch(
        "/api/v1/alerts/1/status",
        json={"status": "ACKNOWLEDGED"},
    )

    assert response.status_code == 409


def test_resolved_alert_cannot_be_reopened(client_with_alert):
    client_with_alert.patch(
        "/api/v1/alerts/1/status",
        json={"status": "ACKNOWLEDGED"},
    )
    client_with_alert.patch(
        "/api/v1/alerts/1/status",
        json={"status": "RESOLVED"},
    )

    response = client_with_alert.patch(
        "/api/v1/alerts/1/status",
        json={"status": "ACKNOWLEDGED"},
    )

    assert response.status_code == 409


def test_nonexistent_alert_returns_404(client_with_alert):
    response = client_with_alert.patch(
        "/api/v1/alerts/999/status",
        json={"status": "ACKNOWLEDGED"},
    )

    assert response.status_code == 404


def test_invalid_status_returns_422(client_with_alert):
    response = client_with_alert.patch(
        "/api/v1/alerts/1/status",
        json={"status": "CLOSED"},
    )

    assert response.status_code == 422

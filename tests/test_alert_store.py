import json
import sqlite3

import pytest

from detection.alert_store import initialize_alert_table, save_alert


@pytest.fixture
def test_database(tmp_path):
    db_path = tmp_path / "alert_test.db"

    connection = sqlite3.connect(db_path)
    connection.execute("""
        CREATE TABLE machine_telemetry (
            id INTEGER PRIMARY KEY,
            event_id TEXT
        )
    """)
    connection.execute(
        "INSERT INTO machine_telemetry (id, event_id) VALUES (?, ?)",
        (1, "event-001")
    )
    connection.commit()
    connection.close()

    initialize_alert_table(db_path)
    return db_path


@pytest.fixture
def anomaly():
    return {
        "is_anomaly": True,
        "event_id": "event-001",
        "machine_id": "MOTOR-01",
        "timestamp": "2026-10-31T10:00:00",
        "actual_power_kw": 65.0,
        "expected_power_kw": 60.0,
        "excess_power_kw": 5.0,
        "excess_percentage": 8.33,
        "residual_threshold_kw": 1.8,
        "severity": "HIGH",
        "detection_method": "CONDITION_AWARE_REGRESSION",
        "explanation": "Test anomaly."
    }


def test_insert_anomaly(test_database, anomaly):
    assert save_alert(1, anomaly, test_database) is True


def test_prevent_duplicate_alert(test_database, anomaly):
    assert save_alert(1, anomaly, test_database) is True
    assert save_alert(1, anomaly, test_database) is False


def test_ignore_normal_reading(test_database, anomaly):
    anomaly["is_anomaly"] = False
    assert save_alert(1, anomaly, test_database) is False


def test_reject_invalid_telemetry_reference(test_database, anomaly):
    with pytest.raises(sqlite3.IntegrityError):
        save_alert(999, anomaly, test_database)


def test_reject_non_dictionary_result(test_database):
    with pytest.raises(TypeError):
        save_alert(1, "invalid", test_database)


def test_save_and_retrieve_combined_diagnosis_explanation(
    test_database,
    anomaly,
):
    combined_explanation = {
        "detection_explanation": "Excess power detected by regression.",
        "diagnosis": {
            "diagnosis_status": "ANOMALY_REQUIRES_INVESTIGATION",
            "summary": "CRITICAL excess-power anomaly detected.",
            "possible_contributors": [
                "Sensor error may contribute."
            ],
            "recommended_actions": [
                "Inspect the power meter."
            ],
            "limitations": "Advisory assessment, not a confirmed fault.",
        },
    }

    anomaly["explanation"] = json.dumps(combined_explanation)

    saved = save_alert(1, anomaly, test_database)

    assert saved is True

    connection = sqlite3.connect(test_database)

    try:
        row = connection.execute(
            """
            SELECT explanation, severity, machine_id
            FROM energy_alerts
            WHERE telemetry_id = ?
            """,
            (1,),
        ).fetchone()
    finally:
        connection.close()

    assert row is not None

    stored_explanation = json.loads(row[0])

    assert (
        stored_explanation["detection_explanation"]
        == "Excess power detected by regression."
    )

    assert (
        stored_explanation["diagnosis"]["diagnosis_status"]
        == "ANOMALY_REQUIRES_INVESTIGATION"
    )

    assert row[1] == "HIGH"
    assert row[2] == "MOTOR-01"
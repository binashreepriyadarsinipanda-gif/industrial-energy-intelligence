
import json
import sqlite3

import pytest

from ingestion import mqtt_consumer
from ingestion.telemetry_validator import validate_telemetry


def test_save_new_telemetry(monkeypatch, tmp_path):
    """A new telemetry event should be saved successfully."""

    db_path = tmp_path / "test_energy_data.db"

    with sqlite3.connect(db_path) as connection:
        connection.execute("""
            CREATE TABLE machine_telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                machine_id TEXT NOT NULL,
                state TEXT NOT NULL,
                load_percent REAL,
                rpm REAL,
                temperature_c REAL,
                power_kw REAL,
                expected_power_kw REAL,
                production_units_per_min REAL,
                energy_kwh REAL,
                degradation_factor REAL,
                event_id TEXT
            )
        """)

        connection.execute("""
            CREATE UNIQUE INDEX ux_machine_telemetry_event_id
            ON machine_telemetry(event_id)
            WHERE event_id IS NOT NULL
        """)

    monkeypatch.setattr(mqtt_consumer, "DATABASE_PATH", db_path)

    telemetry = {
        "event_id": "test-event-001",
        "timestamp": "2026-10-29T10:00:00",
        "machine_id": "MOTOR-01",
        "state": "RUNNING",
        "load_percent": 70.0,
        "rpm": 1500.0,
        "temperature_c": 55.0,
        "power_kw": 60.0,
        "expected_power_kw": 58.0,
        "production_units_per_min": 80.0,
        "energy_kwh": 0.0333,
        "degradation_factor": 1.001,
    }

    assert mqtt_consumer.save_telemetry(telemetry) is True

    with sqlite3.connect(db_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM machine_telemetry"
        ).fetchone()[0]

    assert count == 1


def test_duplicate_telemetry_is_ignored(monkeypatch, tmp_path):
    """A repeated event ID should not create a second record."""

    db_path = tmp_path / "test_duplicate_energy_data.db"

    with sqlite3.connect(db_path) as connection:
        connection.execute("""
            CREATE TABLE machine_telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                machine_id TEXT NOT NULL,
                state TEXT NOT NULL,
                load_percent REAL,
                rpm REAL,
                temperature_c REAL,
                power_kw REAL,
                expected_power_kw REAL,
                production_units_per_min REAL,
                energy_kwh REAL,
                degradation_factor REAL,
                event_id TEXT
            )
        """)

        connection.execute("""
            CREATE UNIQUE INDEX ux_machine_telemetry_event_id
            ON machine_telemetry(event_id)
            WHERE event_id IS NOT NULL
        """)

    monkeypatch.setattr(mqtt_consumer, "DATABASE_PATH", db_path)

    telemetry = {
        "event_id": "duplicate-test-001",
        "timestamp": "2026-10-29T10:00:00",
        "machine_id": "MOTOR-01",
        "state": "RUNNING",
        "load_percent": 70.0,
        "rpm": 1500.0,
        "temperature_c": 55.0,
        "power_kw": 60.0,
        "expected_power_kw": 58.0,
        "production_units_per_min": 80.0,
        "energy_kwh": 0.0333,
        "degradation_factor": 1.001,
    }

    first_result = mqtt_consumer.save_telemetry(telemetry)
    second_result = mqtt_consumer.save_telemetry(telemetry)

    assert first_result is True
    assert second_result is False

    with sqlite3.connect(db_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM machine_telemetry"
        ).fetchone()[0]

    assert count == 1


def test_database_error_is_raised(monkeypatch, tmp_path):
    """A missing table should raise a SQLite database error."""

    db_path = tmp_path / "test_database_error.db"

    with sqlite3.connect(db_path):
        pass

    monkeypatch.setattr(mqtt_consumer, "DATABASE_PATH", db_path)

    telemetry = {
        "event_id": "database-error-test-001",
        "timestamp": "2026-10-29T10:00:00",
        "machine_id": "MOTOR-01",
        "state": "RUNNING",
        "load_percent": 70.0,
        "rpm": 1500.0,
        "temperature_c": 55.0,
        "power_kw": 60.0,
        "expected_power_kw": 58.0,
        "production_units_per_min": 80.0,
        "energy_kwh": 0.0333,
        "degradation_factor": 1.001,
    }

    with pytest.raises(sqlite3.OperationalError):
        mqtt_consumer.save_telemetry(telemetry)


def test_invalid_telemetry_is_rejected(monkeypatch, capsys):
    """Invalid telemetry should be rejected without saving it."""

    save_called = False

    def fake_save_telemetry(data):
        nonlocal save_called
        save_called = True

    monkeypatch.setattr(
        mqtt_consumer,
        "save_telemetry",
        fake_save_telemetry,
    )

    class FakeMessage:
        payload = b'{"machine_id": "MOTOR-01", "state": "BROKEN"}'

    mqtt_consumer.on_message(
        client=None,
        userdata=None,
        msg=FakeMessage(),
    )

    captured = capsys.readouterr()

    assert "Telemetry rejected:" in captured.out
    assert save_called is False


def test_malformed_json_is_rejected(monkeypatch, capsys):
    """Malformed JSON should be rejected without saving."""

    save_called = False

    def fake_save_telemetry(data):
        nonlocal save_called
        save_called = True

    monkeypatch.setattr(
        mqtt_consumer,
        "save_telemetry",
        fake_save_telemetry,
    )

    class FakeMessage:
        payload = b'{"machine_id": "MOTOR-01", "state":'

    mqtt_consumer.on_message(
        client=None,
        userdata=None,
        msg=FakeMessage(),
    )

    captured = capsys.readouterr()

    assert "Invalid message payload:" in captured.out
    assert save_called is False


def test_valid_telemetry_reaches_save_function(monkeypatch, capsys):
    """Valid telemetry should be passed to the saving function."""

    saved_data = []

    def fake_save_telemetry(data):
        saved_data.append(data)
        return True

    monkeypatch.setattr(
        mqtt_consumer,
        "save_telemetry",
        fake_save_telemetry,
    )

    telemetry = {
        "event_id": "550e8400-e29b-41d4-a716-446655440000",
        "timestamp": "2026-10-29T10:00:00",
        "machine_id": "MOTOR-01",
        "state": "RUNNING",
        "load_percent": 70.0,
        "rpm": 1500.0,
        "temperature_c": 55.0,
        "power_kw": 60.0,
        "expected_power_kw": 58.0,
        "production_units_per_min": 80.0,
        "energy_kwh": 0.0333,
        "degradation_factor": 1.001,
    }

    class FakeMessage:
        payload = json.dumps(telemetry).encode("utf-8")

    mqtt_consumer.on_message(
        client=None,
        userdata=None,
        msg=FakeMessage(),
    )

    captured = capsys.readouterr()

    assert len(saved_data) == 1
    assert saved_data[0] == telemetry
    assert "Telemetry saved:" in captured.out


def test_invalid_utf8_payload_is_rejected(monkeypatch, capsys):
    """Invalid UTF-8 payloads should be rejected without saving."""

    save_called = False

    def fake_save_telemetry(data):
        nonlocal save_called
        save_called = True

    monkeypatch.setattr(
        mqtt_consumer,
        "save_telemetry",
        fake_save_telemetry,
    )

    class FakeMessage:
        payload = b"\xff\xfe\xfa"

    mqtt_consumer.on_message(
        client=None,
        userdata=None,
        msg=FakeMessage(),
    )

    captured = capsys.readouterr()

    assert "Invalid message payload:" in captured.out
    assert save_called is False


def test_validator_rejects_load_above_100():
    """The validator should reject load percentages above 100."""

    telemetry = {
        "event_id": "550e8400-e29b-41d4-a716-446655440001",
        "timestamp": "2026-10-29T10:00:00",
        "machine_id": "MOTOR-01",
        "state": "RUNNING",
        "load_percent": 150.0,
        "rpm": 1500.0,
        "temperature_c": 55.0,
        "power_kw": 60.0,
        "expected_power_kw": 58.0,
        "production_units_per_min": 80.0,
        "energy_kwh": 0.0333,
        "degradation_factor": 1.001,
    }

    is_valid, errors = validate_telemetry(telemetry)

    assert is_valid is False
    assert any("load_percent" in error for error in errors)


def test_validator_rejects_negative_power():
    """The validator should reject negative power consumption."""

    telemetry = {
        "event_id": "550e8400-e29b-41d4-a716-446655440002",
        "timestamp": "2026-10-29T10:00:00",
        "machine_id": "MOTOR-01",
        "state": "RUNNING",
        "load_percent": 70.0,
        "rpm": 1500.0,
        "temperature_c": 55.0,
        "power_kw": -10.0,
        "expected_power_kw": 58.0,
        "production_units_per_min": 80.0,
        "energy_kwh": 0.0333,
        "degradation_factor": 1.001,
    }

    is_valid, errors = validate_telemetry(telemetry)

    assert is_valid is False
    assert any("power_kw" in error for error in errors)


def test_validator_rejects_invalid_timestamp():
    """The validator should reject an invalid timestamp."""

    telemetry = {
        "event_id": "550e8400-e29b-41d4-a716-446655440004",
        "timestamp": "not-a-timestamp",
        "machine_id": "MOTOR-01",
        "state": "RUNNING",
        "load_percent": 70.0,
        "rpm": 1500.0,
        "temperature_c": 55.0,
        "power_kw": 60.0,
        "expected_power_kw": 58.0,
        "production_units_per_min": 80.0,
        "energy_kwh": 0.0333,
        "degradation_factor": 1.001,
    }

    is_valid, errors = validate_telemetry(telemetry)

    assert is_valid is False
    assert any("timestamp" in error for error in errors)


def test_validator_rejects_infinite_power():
    """The validator should reject infinite power measurements."""

    telemetry = {
        "event_id": "550e8400-e29b-41d4-a716-446655440005",
        "timestamp": "2026-10-29T10:00:00",
        "machine_id": "MOTOR-01",
        "state": "RUNNING",
        "load_percent": 70.0,
        "rpm": 1500.0,
        "temperature_c": 55.0,
        "power_kw": float("inf"),
        "expected_power_kw": 58.0,
        "production_units_per_min": 80.0,
        "energy_kwh": 0.0333,
        "degradation_factor": 1.001,
    }

    is_valid, errors = validate_telemetry(telemetry)

    assert is_valid is False
    assert any("power_kw" in error for error in errors)


def test_validator_rejects_nan_temperature():
    """The validator should reject NaN temperature measurements."""

    telemetry = {
        "event_id": "550e8400-e29b-41d4-a716-446655440006",
        "timestamp": "2026-10-29T10:00:00",
        "machine_id": "MOTOR-01",
        "state": "RUNNING",
        "load_percent": 70.0,
        "rpm": 1500.0,
        "temperature_c": float("nan"),
        "power_kw": 60.0,
        "expected_power_kw": 58.0,
        "production_units_per_min": 80.0,
        "energy_kwh": 0.0333,
        "degradation_factor": 1.001,
    }

    is_valid, errors = validate_telemetry(telemetry)

    assert is_valid is False
    assert any("temperature_c" in error for error in errors)


def test_validator_rejects_boolean_power():
    """Boolean values must not be accepted as power measurements."""

    telemetry = {
        "event_id": "550e8400-e29b-41d4-a716-446655440007",
        "timestamp": "2026-10-29T10:00:00",
        "machine_id": "MOTOR-01",
        "state": "RUNNING",
        "load_percent": 70.0,
        "rpm": 1500.0,
        "temperature_c": 55.0,
        "power_kw": True,
        "expected_power_kw": 58.0,
        "production_units_per_min": 80.0,
        "energy_kwh": 0.0333,
        "degradation_factor": 1.001,
    }

    is_valid, errors = validate_telemetry(telemetry)

    assert is_valid is False
    assert any("power_kw" in error for error in errors)


def test_validator_rejects_invalid_machine_state():
    """The validator should reject unknown machine states."""

    telemetry = {
        "event_id": "550e8400-e29b-41d4-a716-446655440008",
        "timestamp": "2026-10-29T10:00:00",
        "machine_id": "MOTOR-01",
        "state": "BROKEN",
        "load_percent": 70.0,
        "rpm": 1500.0,
        "temperature_c": 55.0,
        "power_kw": 60.0,
        "expected_power_kw": 58.0,
        "production_units_per_min": 80.0,
        "energy_kwh": 0.0333,
        "degradation_factor": 1.001,
    }

    is_valid, errors = validate_telemetry(telemetry)

    assert is_valid is False
    assert any("state" in error.lower() for error in errors)


def test_validator_rejects_non_dictionary_payload():
    """Telemetry must be represented as a dictionary."""

    is_valid, errors = validate_telemetry(["MOTOR-01", "RUNNING"])

    assert is_valid is False
    assert any("JSON object" in error for error in errors)


def test_validator_rejects_missing_machine_id():
    """Telemetry without a machine ID must be rejected."""

    telemetry = {
        "event_id": "550e8400-e29b-41d4-a716-446655440009",
        "timestamp": "2026-10-29T10:00:00",
        "state": "RUNNING",
        "load_percent": 70.0,
        "rpm": 1500.0,
        "temperature_c": 55.0,
        "power_kw": 60.0,
        "expected_power_kw": 58.0,
        "production_units_per_min": 80.0,
        "energy_kwh": 0.0333,
        "degradation_factor": 1.001,
    }

    is_valid, errors = validate_telemetry(telemetry)

    assert is_valid is False
    assert any("machine_id" in error for error in errors)


def test_validator_rejects_production_during_shutdown():
    """A shutdown machine should not report active production."""

    telemetry = {
        "event_id": "550e8400-e29b-41d4-a716-446655440010",
        "timestamp": "2026-10-29T10:00:00",
        "machine_id": "MOTOR-01",
        "state": "SHUTDOWN",
        "load_percent": 0.0,
        "rpm": 0.0,
        "temperature_c": 40.0,
        "power_kw": 0.0,
        "expected_power_kw": 58.0,
        "production_units_per_min": 80.0,
        "energy_kwh": 0.0,
        "degradation_factor": 1.001,
    }

    is_valid, errors = validate_telemetry(telemetry)

    assert is_valid is False
    assert any("production" in error.lower() for error in errors)


def test_validator_accepts_production_during_running():
    """A running machine may report positive production."""

    telemetry = {
        "event_id": "550e8400-e29b-41d4-a716-446655440011",
        "timestamp": "2026-10-29T10:00:00",
        "machine_id": "MOTOR-01",
        "state": "RUNNING",
        "load_percent": 70.0,
        "rpm": 1500.0,
        "temperature_c": 55.0,
        "power_kw": 60.0,
        "expected_power_kw": 58.0,
        "production_units_per_min": 80.0,
        "energy_kwh": 0.0333,
        "degradation_factor": 1.001,
    }

    is_valid, errors = validate_telemetry(telemetry)

    assert is_valid is True, errors


def test_new_telemetry_runs_energy_detection(monkeypatch, capsys):
    """New telemetry should be passed to the energy detector."""

    saved_data = []
    detected_data = []

    def fake_save_telemetry(data):
        saved_data.append(data)
        return True

    def fake_get_telemetry_id(event_id):
        return 101

    def fake_detect_energy_waste(data):
        detected_data.append(data)
        return {
            "is_anomaly": False,
            "actual_power_kw": 60.0,
            "expected_power_kw": 58.0,
            "excess_power_kw": 2.0,
            "severity": "NORMAL",
        }

    monkeypatch.setattr(
        mqtt_consumer, "save_telemetry", fake_save_telemetry
    )
    monkeypatch.setattr(
        mqtt_consumer, "get_telemetry_id", fake_get_telemetry_id
    )
    monkeypatch.setattr(
        mqtt_consumer, "detect_energy_waste", fake_detect_energy_waste
    )

    telemetry = {
        "event_id": "550e8400-e29b-41d4-a716-446655440000",
        "timestamp": "2026-10-29T10:00:00",
        "machine_id": "MOTOR-01",
        "state": "RUNNING",
        "load_percent": 70.0,
        "rpm": 1500.0,
        "temperature_c": 55.0,
        "power_kw": 60.0,
        "expected_power_kw": 58.0,
        "production_units_per_min": 80.0,
        "energy_kwh": 0.0333,
        "degradation_factor": 1.001,
    }

    class FakeMessage:
        payload = json.dumps(telemetry).encode("utf-8")

    mqtt_consumer.on_message(
        client=None,
        userdata=None,
        msg=FakeMessage(),
    )

    assert len(saved_data) == 1
    assert len(detected_data) == 1
    assert detected_data[0] == telemetry

    captured = capsys.readouterr()
    assert "Normal energy consumption:" in captured.out



def test_anomaly_runs_diagnosis_and_saves_combined_explanation(
    monkeypatch,
    capsys,
):
    """An anomaly should be diagnosed and saved with its explanation."""

    saved_alerts = []
    diagnosed_inputs = []

    telemetry = {
        "event_id": "11111111-1111-4111-8111-111111111111",
        "timestamp": "2026-10-31T10:00:00",
        "machine_id": "MOTOR-01",
        "state": "RUNNING",
        "load_percent": 75.0,
        "rpm": 1500.0,
        "temperature_c": 57.0,
        "power_kw": 72.0,
        "expected_power_kw": 58.0,
        "production_units_per_min": 85.0,
        "energy_kwh": 0.04,
        "degradation_factor": 1.133,
    }

    detection = {
        "is_anomaly": True,
        "event_id": telemetry["event_id"],
        "machine_id": telemetry["machine_id"],
        "timestamp": telemetry["timestamp"],
        "actual_power_kw": 72.0,
        "expected_power_kw": 58.0,
        "excess_power_kw": 14.0,
        "excess_percentage": 24.14,
        "residual_threshold_kw": 2.5,
        "severity": "CRITICAL",
        "detection_method": "CONDITION_AWARE_REGRESSION",
        "explanation": "Test ML anomaly explanation.",
    }

    diagnosis = {
        "machine_id": "MOTOR-01",
        "severity": "CRITICAL",
        "diagnosis_status": "ANOMALY_REQUIRES_INVESTIGATION",
        "summary": "CRITICAL excess-power anomaly detected.",
        "evidence": [],
        "possible_contributors": ["Sensor error may contribute."],
        "recommended_actions": ["Inspect the power meter."],
        "limitations": "This is advisory, not a confirmed fault.",
    }

    def fake_save_telemetry(data):
        return True

    def fake_get_telemetry_id(event_id):
        return 501

    def fake_detect_energy_waste(data):
        return detection

    def fake_diagnose_energy_anomaly(data, result):
        diagnosed_inputs.append((data, result))
        return diagnosis

    def fake_save_alert(telemetry_id, result, database_path):
        saved_alerts.append((telemetry_id, result, database_path))
        return True

    monkeypatch.setattr(
        mqtt_consumer,
        "save_telemetry",
        fake_save_telemetry,
    )
    monkeypatch.setattr(
        mqtt_consumer,
        "get_telemetry_id",
        fake_get_telemetry_id,
    )
    monkeypatch.setattr(
        mqtt_consumer,
        "detect_energy_waste",
        fake_detect_energy_waste,
    )
    monkeypatch.setattr(
        mqtt_consumer,
        "diagnose_energy_anomaly",
        fake_diagnose_energy_anomaly,
    )
    monkeypatch.setattr(
        mqtt_consumer,
        "save_alert",
        fake_save_alert,
    )

    class FakeMessage:
        payload = json.dumps(telemetry).encode("utf-8")

    mqtt_consumer.on_message(
        client=None,
        userdata=None,
        msg=FakeMessage(),
    )

    assert len(diagnosed_inputs) == 1
    assert diagnosed_inputs[0][0] == telemetry
    assert diagnosed_inputs[0][1] is detection

    assert len(saved_alerts) == 1

    telemetry_id, saved_result, _ = saved_alerts[0]

    assert telemetry_id == 501

    combined_explanation = json.loads(
        saved_result["explanation"]
    )

    assert (
        combined_explanation["detection_explanation"]
        == "Test ML anomaly explanation."
    )

    assert (
        combined_explanation["diagnosis"]["diagnosis_status"]
        == "ANOMALY_REQUIRES_INVESTIGATION"
    )

    # The original detector result must remain unchanged.
    assert detection["explanation"] == "Test ML anomaly explanation."

    captured = capsys.readouterr()

    assert "Diagnostic assessment:" in captured.out
    assert "ENERGY WASTE ALERT CREATED:" in captured.out

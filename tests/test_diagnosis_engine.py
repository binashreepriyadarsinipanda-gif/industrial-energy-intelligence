
import pytest

from diagnosis.diagnosis_engine import diagnose_energy_anomaly


@pytest.fixture
def valid_telemetry():
    return {
        "machine_id": "MOTOR-01",
        "state": "RUNNING",
        "load_percent": 75.0,
        "rpm": 1500.0,
        "temperature_c": 57.0,
        "production_units_per_min": 85.0,
        "degradation_factor": 1.133,
        "power_kw": 72.0,
    }


@pytest.fixture
def valid_detection():
    return {
        "is_anomaly": True,
        "severity": "CRITICAL",
        "actual_power_kw": 72.0,
        "expected_power_kw": 63.5499,
        "excess_power_kw": 8.4501,
        "excess_percentage": 13.3,
        "residual_threshold_kw": 2.5,
        "detection_method": "CONDITION_AWARE_REGRESSION",
    }


def test_valid_anomaly_returns_diagnosis(
    valid_telemetry, valid_detection
):
    result = diagnose_energy_anomaly(
        valid_telemetry, valid_detection
    )

    assert result["machine_id"] == "MOTOR-01"
    assert result["severity"] == "CRITICAL"
    assert result["diagnosis_status"] == (
        "ANOMALY_REQUIRES_INVESTIGATION"
    )
    assert len(result["evidence"]) > 0
    assert len(result["recommended_actions"]) > 0


def test_normal_detection_returns_no_anomaly(
    valid_telemetry, valid_detection
):
    # Keep telemetry and detection actual power consistent.
    valid_telemetry["power_kw"] = 64.5499

    valid_detection.update({
        "is_anomaly": False,
        "severity": "NORMAL",
        "actual_power_kw": 64.5499,
        "excess_power_kw": 1.0,
        "excess_percentage": 1.57,
    })

    result = diagnose_energy_anomaly(
        valid_telemetry, valid_detection
    )

    assert result["machine_id"] == "MOTOR-01"
    assert result["severity"] == "NORMAL"
    assert result["diagnosis_status"] == "NO_ANOMALY"
    assert result["evidence"] == []
    assert result["recommended_actions"] == []


def test_missing_telemetry_field_is_rejected(
    valid_telemetry, valid_detection
):
    del valid_telemetry["temperature_c"]

    with pytest.raises(ValueError, match="Missing telemetry fields"):
        diagnose_energy_anomaly(
            valid_telemetry, valid_detection
        )


def test_missing_detection_field_is_rejected(
    valid_telemetry, valid_detection
):
    del valid_detection["severity"]

    with pytest.raises(ValueError, match="Missing detection fields"):
        diagnose_energy_anomaly(
            valid_telemetry, valid_detection
        )


def test_inconsistent_actual_power_is_rejected(
    valid_telemetry, valid_detection
):
    valid_detection["actual_power_kw"] = 70.0

    with pytest.raises(
        ValueError,
        match="Actual power"
    ):
        diagnose_energy_anomaly(
            valid_telemetry, valid_detection
        )


def test_inconsistent_excess_power_is_rejected(
    valid_telemetry, valid_detection
):
    valid_detection["excess_power_kw"] = 5.0

    with pytest.raises(
        ValueError,
        match="Excess power"
    ):
        diagnose_energy_anomaly(
            valid_telemetry, valid_detection
        )


def test_inconsistent_percentage_is_rejected(
    valid_telemetry, valid_detection
):
    valid_detection["excess_percentage"] = 50.0

    with pytest.raises(
        ValueError,
        match="Excess percentage"
    ):
        diagnose_energy_anomaly(
            valid_telemetry, valid_detection
        )


def test_inconsistent_severity_is_rejected(
    valid_telemetry, valid_detection
):
    valid_detection["severity"] = "WARNING"

    with pytest.raises(
        ValueError,
        match="Severity"
    ):
        diagnose_energy_anomaly(
            valid_telemetry, valid_detection
        )


def test_invalid_operating_state_is_rejected(
    valid_telemetry, valid_detection
):
    valid_telemetry["state"] = "BROKEN"

    with pytest.raises(
        ValueError,
        match="operating state"
    ):
        diagnose_energy_anomaly(
            valid_telemetry, valid_detection
        )

import pytest

from detection.energy_detector import EnergyWasteDetector


@pytest.fixture(scope="module")
def detector():
    return EnergyWasteDetector()


@pytest.fixture
def normal_telemetry():
    return {
        "machine_id": "MOTOR-TEST",
        "event_id": "test-event-001",
        "timestamp": "2026-10-30T10:00:00",
        "state": "RUNNING",
        "load_percent": 70.0,
        "rpm": 1460.0,
        "temperature_c": 55.0,
        "production_units_per_min": 82.0,
        "power_kw": 60.0,
    }


def test_normal_power_is_not_anomaly(detector, normal_telemetry):
    result = detector.detect(normal_telemetry)

    assert result["is_anomaly"] is False
    assert result["severity"] == "NORMAL"


def test_power_below_threshold_is_not_anomaly(detector, normal_telemetry):
    expected = detector.detect(normal_telemetry)["expected_power_kw"]
    normal_telemetry["power_kw"] = expected + detector.threshold * 0.99

    result = detector.detect(normal_telemetry)

    assert result["is_anomaly"] is False
    assert result["severity"] == "NORMAL"


def test_power_above_threshold_is_anomaly(detector, normal_telemetry):
    expected = detector.detect(normal_telemetry)["expected_power_kw"]
    normal_telemetry["power_kw"] = expected + detector.threshold * 1.5

    result = detector.detect(normal_telemetry)

    assert result["is_anomaly"] is True
    assert result["severity"] == "WARNING"


@pytest.mark.parametrize(
    ("threshold_multiplier", "expected_severity"),
    [
        (2.0, "HIGH"),
        (2.5, "HIGH"),
        (3.0, "CRITICAL"),
        (3.5, "CRITICAL"),
    ],
)
def test_anomaly_severity_levels(
    detector, normal_telemetry, threshold_multiplier, expected_severity
):
    expected = detector.detect(normal_telemetry)["expected_power_kw"]
    normal_telemetry["power_kw"] = (
        expected + detector.threshold * threshold_multiplier
    )

    result = detector.detect(normal_telemetry)

    assert result["is_anomaly"] is True
    assert result["severity"] == expected_severity


def test_missing_fields_are_rejected(detector):
    with pytest.raises(ValueError, match="Missing telemetry fields"):
        detector.detect({"power_kw": 50})


def test_non_dictionary_input_is_rejected(detector):
    with pytest.raises(TypeError):
        detector.detect("invalid telemetry")


@pytest.mark.parametrize("invalid_value", ["abc", None, True, float("nan"), float("inf")])
def test_invalid_numeric_values_are_rejected(
    detector, normal_telemetry, invalid_value
):
    normal_telemetry["load_percent"] = invalid_value

    with pytest.raises(ValueError):
        detector.detect(normal_telemetry)


def test_negative_power_is_rejected(detector, normal_telemetry):
    normal_telemetry["power_kw"] = -10

    with pytest.raises(ValueError, match="Actual power cannot be negative"):
        detector.detect(normal_telemetry)


def test_result_contains_required_fields(detector, normal_telemetry):
    result = detector.detect(normal_telemetry)

    required = {
        "machine_id",
        "event_id",
        "timestamp",
        "machine_state",
        "actual_power_kw",
        "expected_power_kw",
        "excess_power_kw",
        "residual_threshold_kw",
        "is_anomaly",
        "severity",
        "detection_method",
        "explanation",
    }

    assert required.issubset(result.keys())

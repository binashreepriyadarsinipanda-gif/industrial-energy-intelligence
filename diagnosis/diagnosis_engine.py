
"""
Rule-based diagnostic explanation for industrial energy anomalies.

This module describes observed telemetry and suggests inspection actions.
It does not claim to identify a confirmed physical root cause.
"""

import math


REQUIRED_TELEMETRY_FIELDS = (
    "machine_id",
    "state",
    "load_percent",
    "rpm",
    "temperature_c",
    "production_units_per_min",
    "degradation_factor",
    "power_kw",
)

REQUIRED_DETECTION_FIELDS = (
    "is_anomaly",
    "severity",
    "actual_power_kw",
    "expected_power_kw",
    "excess_power_kw",
    "excess_percentage",
    "residual_threshold_kw",
    "detection_method",
)

VALID_SEVERITIES = {"NORMAL", "WARNING", "HIGH", "CRITICAL"}

VALID_STATES = {
    "STARTUP",
    "RUNNING",
    "HIGH_LOAD",
    "LOW_LOAD",
    "IDLE",
    "SHUTDOWN",
}

# Detector values are rounded before being returned.
# These tolerances account for that rounding.
POWER_TOLERANCE = 0.001
PERCENTAGE_TOLERANCE = 0.05


def _finite_number(data, field):
    """Read and validate one finite numeric value."""

    value = data[field]

    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric.")

    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be numeric.")

    if not math.isfinite(value):
        raise ValueError(f"{field} must be finite.")

    return value


def _validate_detection_consistency(
    telemetry,
    measurements,
    detection_result,
    detection_values,
):
    """Verify that detector output agrees with telemetry and its rules."""

    actual = detection_values["actual_power_kw"]
    expected = detection_values["expected_power_kw"]
    excess = detection_values["excess_power_kw"]
    threshold = detection_values["residual_threshold_kw"]

    # Actual power must agree with the telemetry record.
    if abs(actual - measurements["power_kw"]) > POWER_TOLERANCE:
        raise ValueError(
            "Actual power in detection result does not match telemetry."
        )

    # Excess must equal actual power minus expected power.
    calculated_excess = actual - expected

    if abs(calculated_excess - excess) > POWER_TOLERANCE:
        raise ValueError(
            "Excess power is inconsistent with actual and expected power."
        )

    # Validate the reported excess percentage.
    reported_percentage = detection_result["excess_percentage"]

    if expected > 0:
        calculated_percentage = calculated_excess / expected * 100

        if reported_percentage is None:
            raise ValueError(
                "Excess percentage cannot be None when expected power is positive."
            )

        reported_percentage = _finite_number(
            detection_result, "excess_percentage"
        )

        if abs(reported_percentage - calculated_percentage) > PERCENTAGE_TOLERANCE:
            raise ValueError(
                "Excess percentage is inconsistent with actual and expected power."
            )

    else:
        calculated_percentage = None

        if reported_percentage is not None:
            raise ValueError(
                "Excess percentage must be None when expected power is zero or negative."
            )

    # Reproduce the detector's exact severity rules.
    if calculated_excess > threshold:
        expected_severity = "WARNING"

        if calculated_excess >= 3 * threshold:
            expected_severity = "CRITICAL"
        elif calculated_excess >= 2 * threshold:
            expected_severity = "HIGH"

        expected_anomaly_status = True

    else:
        expected_severity = "NORMAL"
        expected_anomaly_status = False

    if detection_result["severity"] != expected_severity:
        raise ValueError(
            "Severity is inconsistent with excess power and threshold."
        )

    if detection_result["is_anomaly"] != expected_anomaly_status:
        raise ValueError(
            "Anomaly status is inconsistent with excess power and threshold."
        )

    return calculated_excess, calculated_percentage


def diagnose_energy_anomaly(telemetry, detection_result):
    """
    Generate an evidence-based explanation and inspection guidance.

    The output is advisory. It does not establish a physical fault.
    """

    if not isinstance(telemetry, dict):
        raise TypeError("Telemetry must be a dictionary.")

    if not isinstance(detection_result, dict):
        raise TypeError("Detection result must be a dictionary.")

    # Check required telemetry fields.
    missing_telemetry = [
        field for field in REQUIRED_TELEMETRY_FIELDS
        if field not in telemetry
    ]

    if missing_telemetry:
        raise ValueError(
            f"Missing telemetry fields: {missing_telemetry}"
        )

    # Check required detection fields.
    missing_detection = [
        field for field in REQUIRED_DETECTION_FIELDS
        if field not in detection_result
    ]

    if missing_detection:
        raise ValueError(
            f"Missing detection fields: {missing_detection}"
        )

    # Validate machine identity.
    machine_id = telemetry["machine_id"]

    if not isinstance(machine_id, str) or not machine_id.strip():
        raise ValueError("machine_id must be a non-empty string.")

    # Validate telemetry measurements.
    numeric_fields = (
        "load_percent",
        "rpm",
        "temperature_c",
        "production_units_per_min",
        "degradation_factor",
        "power_kw",
    )

    measurements = {
        field: _finite_number(telemetry, field)
        for field in numeric_fields
    }

    # Validate detection measurements.
    detection_values = {
        field: _finite_number(detection_result, field)
        for field in (
            "actual_power_kw",
            "expected_power_kw",
            "excess_power_kw",
            "residual_threshold_kw",
        )
    }

    # Validate severity.
    severity = detection_result["severity"]

    if not isinstance(severity, str) or severity not in VALID_SEVERITIES:
        raise ValueError("Invalid detection severity.")

    # Validate anomaly flag.
    is_anomaly = detection_result["is_anomaly"]

    if not isinstance(is_anomaly, bool):
        raise ValueError("is_anomaly must be boolean.")

    # Validate operating state.
    state = telemetry["state"]

    if not isinstance(state, str) or state not in VALID_STATES:
        raise ValueError("Invalid machine operating state.")

    # Validate detection method.
    detection_method = detection_result["detection_method"]

    if not isinstance(detection_method, str) or not detection_method.strip():
        raise ValueError("Detection method must be a non-empty string.")

    # Validate physical measurement ranges.
    if not 0 <= measurements["load_percent"] <= 100:
        raise ValueError("load_percent must be between 0 and 100.")

    if any(
        measurements[field] < 0
        for field in (
            "rpm",
            "production_units_per_min",
            "power_kw",
        )
    ):
        raise ValueError(
            "RPM, production and power cannot be negative."
        )

    if measurements["degradation_factor"] <= 0:
        raise ValueError("degradation_factor must be positive.")

    if detection_values["actual_power_kw"] < 0:
        raise ValueError("Actual power cannot be negative.")

    if detection_values["expected_power_kw"] < 0:
        raise ValueError("Expected power cannot be negative.")

    if detection_values["residual_threshold_kw"] <= 0:
        raise ValueError("Residual threshold must be positive.")

    # Cross-check all detector outputs, including NORMAL results.
    excess, calculated_percentage = _validate_detection_consistency(
        telemetry,
        measurements,
        detection_result,
        detection_values,
    )

    # Return a normal result only after all validation succeeds.
    if not is_anomaly:
        return {
            "machine_id": machine_id,
            "severity": "NORMAL",
            "diagnosis_status": "NO_ANOMALY",
            "summary": "No excess-power anomaly was detected.",
            "evidence": [],
            "possible_contributors": [],
            "recommended_actions": [],
            "limitations": (
                "A normal detection does not establish that the "
                "machine is free from every possible fault."
            ),
        }

    expected = detection_values["expected_power_kw"]

    evidence = [
        {
            "observation": "Actual power exceeds expected power.",
            "actual": detection_values["actual_power_kw"],
            "expected": expected,
            "excess_kw": excess,
            "excess_percentage": (
                round(calculated_percentage, 2)
                if calculated_percentage is not None
                else None
            ),
        },
        {
            "observation": "Machine operating state.",
            "value": state,
        },
        {
            "observation": "Machine load.",
            "value": measurements["load_percent"],
            "unit": "%",
        },
        {
            "observation": "Machine rotational speed.",
            "value": measurements["rpm"],
            "unit": "RPM",
        },
        {
            "observation": "Machine temperature.",
            "value": measurements["temperature_c"],
            "unit": "°C",
        },
        {
            "observation": "Production rate.",
            "value": measurements["production_units_per_min"],
            "unit": "units/min",
        },
    ]

    possible_contributors = [
        (
            "Operating conditions may influence energy consumption. "
            "Compare the reading with historical readings from the "
            "same machine state and similar load."
        ),
        (
            "The excess-power reading may also be affected by sensor "
            "measurement error or model estimation error."
        ),
    ]

    recommended_actions = [
        (
            "Compare actual and expected power across repeated "
            "readings under similar operating conditions."
        ),
        (
            "Check power-meter calibration and telemetry sensor quality."
        ),
        (
            "Inspect the motor, drive and connected load if excess "
            "consumption persists."
        ),
        (
            "Review temperature and vibration measurements using "
            "appropriate equipment and manufacturer limits."
        ),
    ]

    if state in {"IDLE", "SHUTDOWN"}:
        recommended_actions.insert(
            0,
            (
                "Verify whether the measured power is appropriate "
                "for the current idle or shutdown operating condition."
            ),
        )

    return {
        "machine_id": machine_id,
        "severity": severity,
        "diagnosis_status": "ANOMALY_REQUIRES_INVESTIGATION",
        "summary": (
            f"{severity} excess-power anomaly detected for "
            f"{machine_id} during {state} operation."
        ),
        "evidence": evidence,
        "possible_contributors": possible_contributors,
        "recommended_actions": recommended_actions,
        "limitations": (
            "This is a rule-based advisory explanation, not a "
            "confirmed physical root-cause diagnosis. The available "
            "telemetry and synthetic benchmark do not establish "
            "mechanical failure or verified energy savings."
        ),
    }


from datetime import datetime
from uuid import UUID


REQUIRED_FIELDS = [
    "event_id",
    "timestamp",
    "machine_id",
    "state",
    "load_percent",
    "rpm",
    "temperature_c",
    "power_kw",
    "expected_power_kw",
    "production_units_per_min",
    "energy_kwh",
    "degradation_factor",
]

VALID_STATES = {
    "STARTUP",
    "RUNNING",
    "HIGH_LOAD",
    "LOW_LOAD",
    "IDLE",
    "SHUTDOWN",
}

PRODUCTION_STATES = {
    "RUNNING",
    "HIGH_LOAD",
}

NUMERIC_FIELDS = [
    "load_percent",
    "rpm",
    "temperature_c",
    "power_kw",
    "expected_power_kw",
    "production_units_per_min",
    "energy_kwh",
    "degradation_factor",
]


def validate_telemetry(data):
    """Validate telemetry and return (is_valid, errors).

    The input dictionary is not modified.
    """

    errors = []

    # 1. The payload must be a dictionary.
    if not isinstance(data, dict):
        return False, ["Telemetry must be a JSON object."]

    # 2. Check required fields.
    missing = [
        field
        for field in REQUIRED_FIELDS
        if field not in data
    ]

    if missing:
        errors.append(
            f"Missing fields: {', '.join(missing)}"
        )
        return False, errors

    # 3. Validate event ID.
    if (
        not isinstance(data["event_id"], str)
        or not data["event_id"].strip()
    ):
        errors.append("event_id must be a non-empty string.")
    else:
        try:
            UUID(data["event_id"])
        except (ValueError, AttributeError, TypeError):
            errors.append("event_id must be a valid UUID.")

    # 4. Validate timestamp.
    if not isinstance(data["timestamp"], str):
        errors.append("timestamp must be a string.")
    else:
        try:
            datetime.fromisoformat(data["timestamp"])
        except ValueError:
            errors.append(
                "timestamp must be a valid ISO 8601 datetime."
            )

    # 5. Validate machine ID.
    if (
        not isinstance(data["machine_id"], str)
        or not data["machine_id"].strip()
    ):
        errors.append(
            "machine_id must be a non-empty string."
        )

    # 6. Validate machine state.
    if (
        not isinstance(data["state"], str)
        or data["state"] not in VALID_STATES
    ):
        errors.append(
            f"Invalid machine state: {data['state']!r}"
        )

    # 7. Validate numeric measurements.
    values = {}

    for field in NUMERIC_FIELDS:
        value = data[field]

        # Booleans are subclasses of int in Python,
        # so reject them explicitly.
        if isinstance(value, bool) or not isinstance(
            value, (int, float)
        ):
            errors.append(f"{field} must be a number.")
            continue

        # Reject NaN and positive/negative infinity.
        if value != value or value in (
            float("inf"),
            float("-inf"),
        ):
            errors.append(f"{field} must be finite.")
            continue

        values[field] = value

    # 8. Load must be between 0 and 100 percent.
    if (
        "load_percent" in values
        and not 0 <= values["load_percent"] <= 100
    ):
        errors.append(
            "load_percent must be between 0 and 100."
        )

    # 9. These quantities cannot be negative.
    for field in (
        "rpm",
        "power_kw",
        "expected_power_kw",
        "production_units_per_min",
        "energy_kwh",
    ):
        if field in values and values[field] < 0:
            errors.append(f"{field} cannot be negative.")

    # 10. Degradation factor must be positive.
    if (
        "degradation_factor" in values
        and values["degradation_factor"] <= 0
    ):
        errors.append(
            "degradation_factor must be greater than zero."
        )

    # 11. Cross-field consistency:
    # The simulator produces output only in RUNNING
    # and HIGH_LOAD states.
    if (
        isinstance(data["state"], str)
        and data["state"] in VALID_STATES
        and data["state"] not in PRODUCTION_STATES
        and "production_units_per_min" in values
        and values["production_units_per_min"] > 0
    ):
        errors.append(
            "production_units_per_min must be zero "
            "when the machine is not RUNNING or HIGH_LOAD."
        )

    return len(errors) == 0, errors

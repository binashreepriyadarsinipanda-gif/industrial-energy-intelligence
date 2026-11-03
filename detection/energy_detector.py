
from pathlib import Path
import math

import joblib
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "saved_v2"
    / "regression_baseline_v2.joblib"
)

REQUIRED_FIELDS = [
    "load_percent",
    "rpm",
    "temperature_c",
    "production_units_per_min",
    "power_kw",
]

MODEL_FEATURES = [
    "load_percent",
    "rpm",
    "temperature_c",
    "production_units_per_min",
]


# ============================================================
# ENERGY DETECTION ENGINE
# ============================================================

class EnergyWasteDetector:
    """
    Detect unusually high power consumption using a
    condition-aware regression model.

    Positive residuals above the calibrated threshold
    are flagged for investigation.

    An anomaly indicates potential energy waste and does
    not independently confirm a physical machine fault.
    """

    def __init__(self, model_path=MODEL_PATH):

        self.model_path = Path(model_path)

        if not self.model_path.is_absolute():
            self.model_path = PROJECT_ROOT / self.model_path

        if not self.model_path.is_file():
            raise FileNotFoundError(
                f"Regression model not found: {self.model_path}"
            )

        try:
            artifact = joblib.load(self.model_path)
        except Exception as exc:
            raise RuntimeError(
                f"Could not load regression model: {exc}"
            ) from exc

        if not isinstance(artifact, dict):
            raise ValueError(
                "Invalid model artifact: expected a dictionary."
            )

        required_keys = {
            "model",
            "feature_columns",
            "residual_threshold",
        }

        missing_keys = required_keys - set(artifact.keys())

        if missing_keys:
            raise ValueError(
                f"Model artifact is missing keys: "
                f"{sorted(missing_keys)}"
            )

        self.model = artifact["model"]
        self.feature_columns = artifact["feature_columns"]

        if not isinstance(self.feature_columns, list):
            raise ValueError(
                "feature_columns must be a list."
            )

        if not self.feature_columns:
            raise ValueError(
                "feature_columns cannot be empty."
            )

        if len(set(self.feature_columns)) != len(
            self.feature_columns
        ):
            raise ValueError(
                "Duplicate feature columns found in model artifact."
            )

        if set(self.feature_columns) != set(MODEL_FEATURES):
            raise ValueError(
                "Model features do not match expected v2 features. "
                f"Found: {self.feature_columns}"
            )

        if not callable(getattr(self.model, "predict", None)):
            raise ValueError(
                "Loaded model does not provide a predict method."
            )

        threshold = self._validate_numeric(
            artifact["residual_threshold"],
            "residual_threshold",
        )

        if threshold <= 0:
            raise ValueError(
                "Residual threshold must be positive."
            )

        self.threshold = threshold

        model_feature_count = getattr(
            self.model,
            "n_features_in_",
            None,
        )

        if (
            model_feature_count is not None
            and model_feature_count != len(self.feature_columns)
        ):
            raise ValueError(
                "Model input dimension does not match "
                "artifact feature columns."
            )

        print("Energy Waste Detector initialized.")
        print(f"Model: {self.model_path}")
        print(f"Features: {self.feature_columns}")
        print(
            f"Residual threshold: {self.threshold:.6f} kW"
        )

    # ========================================================
    # NUMERIC VALIDATION
    # ========================================================

    @staticmethod
    def _validate_numeric(value, field_name):

        if isinstance(value, bool):
            raise ValueError(
                f"{field_name} must be numeric, not boolean."
            )

        try:
            numeric_value = float(value)

        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{field_name} must be numeric."
            ) from exc

        if not math.isfinite(numeric_value):
            raise ValueError(
                f"{field_name} must be finite."
            )

        return numeric_value

    # ========================================================
    # TELEMETRY VALIDATION
    # ========================================================

    def _validate_telemetry(self, telemetry):

        if not isinstance(telemetry, dict):
            raise TypeError(
                "Telemetry must be a dictionary."
            )

        missing_fields = [
            field
            for field in REQUIRED_FIELDS
            if field not in telemetry
        ]

        if missing_fields:
            raise ValueError(
                f"Missing telemetry fields: {missing_fields}"
            )

        features = {}

        for field in MODEL_FEATURES:
            features[field] = self._validate_numeric(
                telemetry[field],
                field,
            )

        actual_power = self._validate_numeric(
            telemetry["power_kw"],
            "power_kw",
        )

        if not 0 <= features["load_percent"] <= 100:
            raise ValueError(
                "load_percent must be between 0 and 100."
            )

        if features["rpm"] < 0:
            raise ValueError("rpm cannot be negative.")

        if features["temperature_c"] < 0:
            raise ValueError(
                "temperature_c cannot be negative."
            )

        if features["production_units_per_min"] < 0:
            raise ValueError(
                "production_units_per_min cannot be negative."
            )

        if actual_power < 0:
            raise ValueError(
                "Actual power cannot be negative."
            )

        return features, actual_power

    # ========================================================
    # ANOMALY DETECTION
    # ========================================================

    def detect(self, telemetry):

        features, actual_power = self._validate_telemetry(
            telemetry
        )

        input_df = pd.DataFrame(
            [
                [
                    features[column]
                    for column in self.feature_columns
                ]
            ],
            columns=self.feature_columns,
        )

        try:
            prediction = self.model.predict(input_df)

        except Exception as exc:
            raise RuntimeError(
                f"Regression prediction failed: {exc}"
            ) from exc

        if len(prediction) != 1:
            raise RuntimeError(
                "Unexpected number of predictions returned."
            )

        expected_power = self._validate_numeric(
            prediction[0],
            "predicted_expected_power",
        )

        if expected_power <= 0:
            raise ValueError(
                "Predicted expected power must be positive."
            )

        # Calculate residual using full-precision model prediction.
        excess_power = actual_power - expected_power

        excess_percentage = (
            excess_power / expected_power
        ) * 100

        # Preserve the calibrated anomaly threshold.
        is_anomaly = excess_power > self.threshold

        # The public expected_power_kw result is rounded to
        # four decimal places. This tolerance accounts for
        # the maximum rounding difference (0.00005 kW)
        # when testing exact severity boundaries.
        tolerance = max(
            0.000051,
            abs(self.threshold) * 1e-9,
        )

        if not is_anomaly:
            severity = "NORMAL"

        elif excess_power >= (
            3.0 * self.threshold - tolerance
        ):
            severity = "CRITICAL"

        elif excess_power >= (
            2.0 * self.threshold - tolerance
        ):
            severity = "HIGH"

        else:
            severity = "WARNING"

        explanation = (
            f"Actual power consumption is {actual_power:.2f} kW, "
            f"while expected power is {expected_power:.2f} kW. "
            f"Excess consumption is {excess_power:.2f} kW "
            f"({excess_percentage:.2f}%). "
            f"The calibrated residual threshold is "
            f"{self.threshold:.2f} kW."
        )

        return {
            "event_id": telemetry.get("event_id"),
            "machine_id": telemetry.get("machine_id"),
            "timestamp": telemetry.get("timestamp"),
            "machine_state": telemetry.get("state"),

            "actual_power_kw": round(actual_power, 4),
            "expected_power_kw": round(expected_power, 4),
            "excess_power_kw": round(excess_power, 4),
            "excess_percentage": round(excess_percentage, 2),

            "residual_threshold_kw": round(
                self.threshold,
                6,
            ),

            "is_anomaly": bool(is_anomaly),
            "severity": severity,

            "detection_method": (
                "CONDITION_AWARE_REGRESSION"
            ),

            "explanation": explanation,
        }


# ============================================================
# BACKWARD-COMPATIBLE DETECTION FUNCTION
# ============================================================

_default_detector = None


def detect_energy_waste(telemetry):
    """
    Module-level interface used by the MQTT consumer.

    Loads the model once and reuses the detector for
    subsequent telemetry messages.
    """

    global _default_detector

    if _default_detector is None:
        _default_detector = EnergyWasteDetector()

    return _default_detector.detect(telemetry)

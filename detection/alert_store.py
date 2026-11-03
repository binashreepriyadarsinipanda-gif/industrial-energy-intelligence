import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "database" / "energy_data.db"


def initialize_alert_table(database_path=DEFAULT_DATABASE_PATH):
    """Create the alert table if it does not already exist."""

    connection = sqlite3.connect(database_path)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        connection.execute("""
            CREATE TABLE IF NOT EXISTS energy_alerts (
                alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
                telemetry_id INTEGER NOT NULL UNIQUE,
                event_id TEXT,
                machine_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                actual_power_kw REAL NOT NULL,
                expected_power_kw REAL NOT NULL,
                excess_power_kw REAL NOT NULL,
                excess_percentage REAL,
                threshold_kw REAL NOT NULL,
                severity TEXT NOT NULL
                    CHECK (severity IN ('WARNING', 'HIGH', 'CRITICAL')),
                detection_method TEXT NOT NULL,
                explanation TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN'
                    CHECK (status IN ('OPEN', 'ACKNOWLEDGED', 'RESOLVED')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (telemetry_id)
                    REFERENCES machine_telemetry(id)
            )
        """)

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def save_alert(
    telemetry_id,
    detection_result,
    database_path=DEFAULT_DATABASE_PATH,
):
    """
    Persist an anomaly result.

    Returns True if a new alert was inserted.
    Returns False if the reading is normal or already has an alert.
    """

    if not isinstance(detection_result, dict):
        raise TypeError("Detection result must be a dictionary.")

    if not detection_result.get("is_anomaly", False):
        return False

    required_fields = [
        "event_id",
        "machine_id",
        "timestamp",
        "actual_power_kw",
        "expected_power_kw",
        "excess_power_kw",
        "residual_threshold_kw",
        "severity",
        "detection_method",
        "explanation",
    ]

    missing = [
        field for field in required_fields
        if field not in detection_result
    ]

    if missing:
        raise ValueError(f"Missing detection result fields: {missing}")

    connection = sqlite3.connect(database_path, timeout=10)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        cursor = connection.execute("""
            INSERT INTO energy_alerts (
                telemetry_id,
                event_id,
                machine_id,
                timestamp,
                actual_power_kw,
                expected_power_kw,
                excess_power_kw,
                excess_percentage,
                threshold_kw,
                severity,
                detection_method,
                explanation
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(telemetry_id) DO NOTHING
        """, (
            telemetry_id,
            detection_result["event_id"],
            detection_result["machine_id"],
            detection_result["timestamp"],
            detection_result["actual_power_kw"],
            detection_result["expected_power_kw"],
            detection_result["excess_power_kw"],
            detection_result.get("excess_percentage"),
            detection_result["residual_threshold_kw"],
            detection_result["severity"],
            detection_result["detection_method"],
            detection_result["explanation"],
        ))

        connection.commit()
        return cursor.rowcount == 1

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

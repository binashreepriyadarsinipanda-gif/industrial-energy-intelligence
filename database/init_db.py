import sqlite3
from pathlib import Path
from datetime import datetime, timezone


DATABASE_PATH = Path(__file__).resolve().parent / "energy_data.db"


def create_database():
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        cursor = connection.cursor()
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS plants (
                plant_id INTEGER PRIMARY KEY AUTOINCREMENT,
                plant_code TEXT NOT NULL UNIQUE,
                plant_name TEXT NOT NULL,
                location TEXT,
                industry_type TEXT,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS production_lines (
                line_id INTEGER PRIMARY KEY AUTOINCREMENT,
                plant_id INTEGER NOT NULL,
                line_code TEXT NOT NULL,
                line_name TEXT NOT NULL,
                process_type TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (plant_id, line_code),
                FOREIGN KEY (plant_id) REFERENCES plants (plant_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS machines (
                machine_id INTEGER PRIMARY KEY AUTOINCREMENT,
                line_id INTEGER NOT NULL,
                machine_code TEXT NOT NULL,
                machine_name TEXT NOT NULL,
                machine_type TEXT,
                status TEXT NOT NULL,
                rated_power_kw REAL,
                created_at TEXT NOT NULL,
                UNIQUE (line_id, machine_code),
                FOREIGN KEY (line_id) REFERENCES production_lines (line_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS machine_telemetry (
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

        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
                ux_machine_telemetry_event_id
            ON machine_telemetry(event_id)
            WHERE event_id IS NOT NULL
        """)

        cursor.execute("""
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
                FOREIGN KEY (telemetry_id) REFERENCES machine_telemetry(id)
            )
        """)

        cursor.execute("""
            INSERT OR IGNORE INTO plants (
                plant_code, plant_name, location, industry_type, created_at
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            "PLANT-01",
            "Industrial Energy Intelligence Plant",
            "Bhubaneswar, Odisha, India",
            "Industrial Manufacturing",
            now,
        ))

        cursor.execute("""
            INSERT OR IGNORE INTO production_lines (
                plant_id, line_code, line_name, process_type, status, created_at
            )
            SELECT plant_id, ?, ?, ?, ?, ?
            FROM plants WHERE plant_code = ?
        """, (
            "LINE-01",
            "Primary Production Line",
            "Industrial Manufacturing",
            "ACTIVE",
            now,
            "PLANT-01",
        ))

        cursor.execute("""
            INSERT OR IGNORE INTO machines (
                line_id, machine_code, machine_name, machine_type,
                status, rated_power_kw, created_at
            )
            SELECT line_id, ?, ?, ?, ?, ?, ?
            FROM production_lines WHERE line_code = ?
        """, (
            "MOTOR-01",
            "Industrial Motor 01",
            "Electric Motor",
            "ACTIVE",
            75.0,
            now,
            "LINE-01",
        ))

        connection.commit()

        print("Database initialized successfully.")
        print("Tables: plants, production_lines, machines,")
        print("        machine_telemetry, energy_alerts")
        print("Demo plant and machine records verified.")
        print("Database:", DATABASE_PATH)

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    create_database()
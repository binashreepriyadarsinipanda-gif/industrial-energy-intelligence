import sqlite3
from pathlib import Path


DATABASE_PATH = Path(__file__).resolve().parent / "energy_data.db"


def migrate():
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)

    try:
        cursor = connection.cursor()
        cursor.execute("PRAGMA busy_timeout = 10000")

        columns = {
            row[1]
            for row in cursor.execute(
                "PRAGMA table_info(machine_telemetry)"
            ).fetchall()
        }

        if "event_id" not in columns:
            cursor.execute(
                "ALTER TABLE machine_telemetry ADD COLUMN event_id TEXT"
            )

        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
                ux_machine_telemetry_event_id
            ON machine_telemetry(event_id)
            WHERE event_id IS NOT NULL
        """)

        connection.commit()
        print("Migration completed successfully.")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    migrate()

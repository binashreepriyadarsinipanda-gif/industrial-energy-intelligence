import sqlite3
from pathlib import Path
from datetime import datetime


DATABASE_PATH = (
    Path(__file__).resolve().parent / "energy_data.db"
)


def create_database():
    connection = sqlite3.connect(DATABASE_PATH)
    cursor = connection.cursor()

    # Plants table
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

    # Production lines table
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
            FOREIGN KEY (plant_id)
                REFERENCES plants (plant_id)
        )
    """)

    # Machines table
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
            FOREIGN KEY (line_id)
                REFERENCES production_lines (line_id)
        )
    """)

    connection.commit()
    connection.close()

    print("Database initialized successfully.")
    print("Table verified: plants")
    print("Table verified: production_lines")
    print("Table created/verified: machines")
    print("Database:", DATABASE_PATH)


if __name__ == "__main__":
    create_database()
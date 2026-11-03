
import sqlite3

connection = sqlite3.connect("database/energy_data.db")

checks = [
    (
        "Negative power readings",
        """
        SELECT COUNT(*)
        FROM machine_telemetry
        WHERE power_kw < 0
        """
    ),
    (
        "Duplicate event IDs",
        """
        SELECT COUNT(*)
        FROM (
            SELECT event_id
            FROM machine_telemetry
            WHERE event_id IS NOT NULL
            GROUP BY event_id
            HAVING COUNT(*) > 1
        )
        """
    ),
]

for name, query in checks:
    result = connection.execute(query).fetchone()[0]
    print(f"{name}: {result}")

connection.close()

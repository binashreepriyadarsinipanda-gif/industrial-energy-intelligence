import csv
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database" / "energy_data.db"
OUTPUT_PATH = ROOT / "data" / "historical_telemetry.csv"
AUDIT_PATH = ROOT / "data" / "historical_exclusion_audit.csv"

INCLUDED_DATES = {"2026-10-12", "2026-10-25"}
SESSION_GAP_SECONDS = 10


def main():
    connection = sqlite3.connect(
        f"{DB_PATH.as_uri()}?mode=ro",
        uri=True
    )
    connection.row_factory = sqlite3.Row

    try:
        rows = connection.execute("""
            SELECT *
            FROM machine_telemetry
            ORDER BY timestamp, id
        """).fetchall()
    finally:
        connection.close()

    duplicate_counts = Counter(
        (row["machine_id"], row["timestamp"])
        for row in rows
    )

    included = []
    audit = []

    for row in rows:
        record = dict(row)
        date = record["timestamp"][:10]

        if date not in INCLUDED_DATES:
            audit.append({
                "record_id": record["id"],
                "timestamp": record["timestamp"],
                "machine_id": record["machine_id"],
                "reason": "Excluded date: ambiguous historical provenance"
            })
            continue

        key = (record["machine_id"], record["timestamp"])

        if duplicate_counts[key] > 1:
            audit.append({
                "record_id": record["id"],
                "timestamp": record["timestamp"],
                "machine_id": record["machine_id"],
                "reason": "Conflicting duplicate machine-timestamp"
            })
            continue

        included.append(record)

    previous_by_date = {}
    session_number_by_date = Counter()

    for record in included:
        timestamp = datetime.fromisoformat(record["timestamp"])
        date = timestamp.date().isoformat()
        previous = previous_by_date.get(date)

        if previous is None:
            session_number_by_date[date] = 1
        elif (timestamp - previous).total_seconds() > SESSION_GAP_SECONDS:
            session_number_by_date[date] += 1

        record["session_id"] = (
            f"{date}_session_{session_number_by_date[date]}"
        )
        record["source_type"] = "synthetic_historical_telemetry"

        previous_by_date[date] = timestamp

    if included:
        fieldnames = list(included[0].keys())
        with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(included)

    with AUDIT_PATH.open("w", newline="", encoding="utf-8") as file:
        fields = ["record_id", "timestamp", "machine_id", "reason"]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(audit)

    print("Historical dataset preparation completed.")
    print("Source records:", len(rows))
    print("Exported records:", len(included))
    print("Excluded records:", len(audit))
    print("Dataset:", OUTPUT_PATH)
    print("Exclusion audit:", AUDIT_PATH)

    print("\nSession summary:")
    for session_id, count in sorted(
        Counter(row["session_id"] for row in included).items()
    ):
        print(session_id, count)


if __name__ == "__main__":
    main()

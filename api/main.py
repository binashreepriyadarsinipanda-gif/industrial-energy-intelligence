
import json
import os
import secrets
import sqlite3
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query, Header
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / "database" / "energy_data.db"


app = FastAPI(
    title="Industrial Energy Intelligence API",
    description=(
        "REST API for industrial machine telemetry, "
        "energy-waste detection, alert management and analytics."
    ),
    version="1.0.0",
)


# --------------------------------------------------
# DATABASE CONNECTIONS
# --------------------------------------------------

def get_connection():
    """Create a read-only database connection."""

    if not DATABASE_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Database not found: {DATABASE_PATH}",
        )

    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")

    return connection


def get_write_connection():
    """Create a database connection for controlled write operations."""

    if not DATABASE_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Database not found: {DATABASE_PATH}",
        )

    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def fetch_all(query: str, parameters: tuple = ()):
    connection = get_connection()

    try:
        rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    finally:
        connection.close()


def fetch_one(query: str, parameters: tuple = ()):
    connection = get_connection()

    try:
        row = connection.execute(query, parameters).fetchone()
        return dict(row) if row else None

    finally:
        connection.close()


# --------------------------------------------------
# REQUEST MODELS
# --------------------------------------------------

class AlertStatusUpdate(BaseModel):
    status: Literal["ACKNOWLEDGED", "RESOLVED"]


class TelemetryIngest(BaseModel):
    """Telemetry received from the local MQTT consumer."""

    event_id: str = Field(min_length=1, max_length=200)
    timestamp: str = Field(min_length=1, max_length=100)
    machine_id: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=50)

    load_percent: float
    rpm: float
    temperature_c: float
    power_kw: float
    expected_power_kw: float
    production_units_per_min: float
    energy_kwh: float
    degradation_factor: float


class AlertIngest(BaseModel):
    """An ML-generated energy-waste alert from the local consumer."""

    event_id: str = Field(min_length=1, max_length=200)
    machine_id: str = Field(min_length=1, max_length=100)
    timestamp: str = Field(min_length=1, max_length=100)
    actual_power_kw: float
    expected_power_kw: float
    excess_power_kw: float
    excess_percentage: Optional[float] = None
    threshold_kw: float
    severity: Literal["WARNING", "HIGH", "CRITICAL"]
    detection_method: str = Field(min_length=1, max_length=200)
    explanation: str = Field(min_length=1, max_length=10000)


# --------------------------------------------------
# ALERT EXPLANATION PARSER
# --------------------------------------------------

def parse_alert_explanation(alert: dict) -> dict:
    raw_explanation = alert.get("explanation")

    if not raw_explanation:
        alert["explanation_details"] = None
        return alert

    try:
        parsed = json.loads(raw_explanation)
        alert["explanation_details"] = parsed

    except (json.JSONDecodeError, TypeError):
        alert["explanation_details"] = {
            "detection_explanation": raw_explanation
        }

    return alert


# --------------------------------------------------
# GENERAL ENDPOINTS
# --------------------------------------------------

@app.get("/", tags=["General"])
def root():
    return {
        "message": "Industrial Energy Intelligence API is running.",
        "version": app.version,
        "documentation": "/docs",
        "database": str(DATABASE_PATH),
    }


@app.get("/health", tags=["General"])
def health_check():
    connection = get_connection()

    try:
        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        telemetry_count = connection.execute(
            "SELECT COUNT(*) FROM machine_telemetry"
        ).fetchone()[0]

        alert_count = connection.execute(
            "SELECT COUNT(*) FROM energy_alerts"
        ).fetchone()[0]

        return {
            "status": "healthy" if integrity == "ok" else "unhealthy",
            "database_integrity": integrity,
            "telemetry_records": telemetry_count,
            "total_alerts": alert_count,
            "database_path": str(DATABASE_PATH),
        }

    finally:
        connection.close()


# --------------------------------------------------
# OVERVIEW
# --------------------------------------------------

@app.get("/api/v1/overview", tags=["Analytics"])
def get_overview():
    telemetry = fetch_one(
        """
        SELECT
            COUNT(*) AS total_readings,
            COUNT(DISTINCT machine_id) AS monitored_machines,
            ROUND(AVG(power_kw), 3) AS average_power_kw,
            ROUND(MAX(power_kw), 3) AS maximum_power_kw,
            ROUND(SUM(energy_kwh), 3) AS total_energy_kwh,
            MAX(timestamp) AS latest_reading
        FROM machine_telemetry
        """
    )

    alerts = fetch_one(
        """
        SELECT
            COUNT(*) AS total_alerts,
            SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END)
                AS open_alerts,
            SUM(CASE WHEN severity = 'CRITICAL' THEN 1 ELSE 0 END)
                AS critical_alerts,
            SUM(CASE WHEN severity = 'HIGH' THEN 1 ELSE 0 END)
                AS high_alerts,
            SUM(CASE WHEN severity = 'WARNING' THEN 1 ELSE 0 END)
                AS warning_alerts
        FROM energy_alerts
        """
    )

    return {
        "telemetry": telemetry,
        "alerts": alerts,
    }


# --------------------------------------------------
# PLANT MANAGEMENT
# --------------------------------------------------

@app.get("/api/v1/plants", tags=["Plant Management"])
def get_plants():
    return fetch_all(
        """
        SELECT
            p.*,
            COUNT(DISTINCT pl.line_id) AS production_line_count,
            COUNT(DISTINCT m.machine_id) AS machine_count
        FROM plants p
        LEFT JOIN production_lines pl ON pl.plant_id = p.plant_id
        LEFT JOIN machines m ON m.line_id = pl.line_id
        GROUP BY p.plant_id
        ORDER BY p.plant_id
        """
    )


# --------------------------------------------------
# MACHINE MANAGEMENT
# --------------------------------------------------

@app.get("/api/v1/machines", tags=["Machine Management"])
def get_machines():
    return fetch_all(
        """
        SELECT
            m.machine_id,
            m.machine_code,
            m.machine_name,
            m.machine_type,
            m.status,
            m.rated_power_kw,
            pl.line_code,
            pl.line_name,
            p.plant_code,
            p.plant_name,
            (
                SELECT mt.timestamp
                FROM machine_telemetry mt
                WHERE mt.machine_id = m.machine_code
                ORDER BY mt.id DESC
                LIMIT 1
            ) AS latest_reading
        FROM machines m
        LEFT JOIN production_lines pl ON pl.line_id = m.line_id
        LEFT JOIN plants p ON p.plant_id = pl.plant_id
        ORDER BY m.machine_id
        """
    )


# --------------------------------------------------
# TELEMETRY INGESTION - AUTHENTICATED CLOUD UPLOAD
# --------------------------------------------------

@app.post(
    "/api/v1/telemetry/ingest",
    tags=["Telemetry"],
)
def ingest_telemetry(
    request: TelemetryIngest,
    x_api_token: Optional[str] = Header(
        default=None,
        alias="X-API-Token",
    ),
):
    """
    Receive telemetry from the local MQTT consumer.

    Authentication is performed using the TELEMETRY_API_TOKEN
    environment variable configured on Render.
    """

    configured_token = os.getenv("TELEMETRY_API_TOKEN")

    if not configured_token:
        raise HTTPException(
            status_code=503,
            detail="Telemetry ingestion is not configured.",
        )

    if (
        not x_api_token
        or not secrets.compare_digest(
            x_api_token,
            configured_token,
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API token.",
        )

    connection = get_write_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        # Prevent the same event from being inserted twice.
        existing = connection.execute(
            """
            SELECT id
            FROM machine_telemetry
            WHERE event_id = ?
            LIMIT 1
            """,
            (request.event_id,),
        ).fetchone()

        if existing:
            connection.commit()

            return {
                "status": "duplicate",
                "message": "This telemetry event already exists.",
                "event_id": request.event_id,
            }

        connection.execute(
            """
            INSERT INTO machine_telemetry (
                event_id,
                timestamp,
                machine_id,
                state,
                load_percent,
                rpm,
                temperature_c,
                power_kw,
                expected_power_kw,
                production_units_per_min,
                energy_kwh,
                degradation_factor
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.event_id,
                request.timestamp,
                request.machine_id,
                request.state,
                request.load_percent,
                request.rpm,
                request.temperature_c,
                request.power_kw,
                request.expected_power_kw,
                request.production_units_per_min,
                request.energy_kwh,
                request.degradation_factor,
            ),
        )

        connection.commit()

        return {
            "status": "inserted",
            "message": "Telemetry successfully received.",
            "event_id": request.event_id,
        }

    except sqlite3.Error:
        connection.rollback()

        raise HTTPException(
            status_code=500,
            detail="Could not save telemetry to the database.",
        )

    finally:
        connection.close()


# --------------------------------------------------
# ALERT INGESTION - AUTHENTICATED CLOUD UPLOAD
# --------------------------------------------------

@app.post("/api/v1/alerts/ingest", tags=["Alerts"])
def ingest_alert(
    request: AlertIngest,
    x_api_token: Optional[str] = Header(
        default=None,
        alias="X-API-Token",
    ),
):
    """Receive an ML-generated alert and link it to cloud telemetry."""

    configured_token = os.getenv("TELEMETRY_API_TOKEN")

    if not configured_token:
        raise HTTPException(
            status_code=503,
            detail="Alert ingestion is not configured.",
        )

    if (
        not x_api_token
        or not secrets.compare_digest(x_api_token, configured_token)
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API token.",
        )

    connection = get_write_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        telemetry = connection.execute(
            """
            SELECT id, machine_id
            FROM machine_telemetry
            WHERE event_id = ?
            LIMIT 1
            """,
            (request.event_id,),
        ).fetchone()

        if not telemetry:
            raise HTTPException(
                status_code=409,
                detail="Matching cloud telemetry has not been received.",
            )

        if telemetry["machine_id"] != request.machine_id:
            raise HTTPException(
                status_code=409,
                detail="Alert machine does not match cloud telemetry.",
            )

        existing = connection.execute(
            """
            SELECT alert_id
            FROM energy_alerts
            WHERE telemetry_id = ?
            LIMIT 1
            """,
            (telemetry["id"],),
        ).fetchone()

        if existing:
            connection.commit()
            return {
                "status": "duplicate",
                "event_id": request.event_id,
                "alert_id": existing["alert_id"],
            }

        cursor = connection.execute(
            """
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
            """,
            (
                telemetry["id"],
                request.event_id,
                request.machine_id,
                request.timestamp,
                request.actual_power_kw,
                request.expected_power_kw,
                request.excess_power_kw,
                request.excess_percentage,
                request.threshold_kw,
                request.severity,
                request.detection_method,
                request.explanation,
            ),
        )

        connection.commit()

        return {
            "status": "inserted",
            "event_id": request.event_id,
            "alert_id": cursor.lastrowid,
        }

    except HTTPException:
        connection.rollback()
        raise

    except sqlite3.Error:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not save alert to the database.",
        )

    finally:
        connection.close()


# --------------------------------------------------
# TELEMETRY - RETRIEVAL
# --------------------------------------------------

@app.get("/api/v1/telemetry/latest", tags=["Telemetry"])
def get_latest_telemetry():
    return fetch_all(
        """
        SELECT mt.*
        FROM machine_telemetry mt
        INNER JOIN (
            SELECT machine_id, MAX(id) AS latest_id
            FROM machine_telemetry
            GROUP BY machine_id
        ) latest ON latest.latest_id = mt.id
        ORDER BY mt.machine_id
        """
    )


@app.get("/api/v1/telemetry", tags=["Telemetry"])
def get_telemetry(
    machine_id: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    conditions = []
    parameters = []

    if machine_id:
        conditions.append("machine_id = ?")
        parameters.append(machine_id)

    if state:
        conditions.append("state = ?")
        parameters.append(state.upper())

    where_clause = (
        "WHERE " + " AND ".join(conditions)
        if conditions else ""
    )

    total = fetch_one(
        f"""
        SELECT COUNT(*) AS total
        FROM machine_telemetry
        {where_clause}
        """,
        tuple(parameters),
    )["total"]

    records = fetch_all(
        f"""
        SELECT *
        FROM machine_telemetry
        {where_clause}
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        tuple(parameters) + (limit, offset),
    )

    return {
        "total_records": total,
        "limit": limit,
        "offset": offset,
        "records": records,
    }


# --------------------------------------------------
# ENERGY ALERTS - RETRIEVAL
# --------------------------------------------------

@app.get("/api/v1/alerts", tags=["Energy Alerts"])
def get_alerts(
    machine_id: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    conditions = []
    parameters = []

    if machine_id:
        conditions.append("machine_id = ?")
        parameters.append(machine_id)

    if severity:
        conditions.append("severity = ?")
        parameters.append(severity.upper())

    if status:
        conditions.append("status = ?")
        parameters.append(status.upper())

    where_clause = (
        "WHERE " + " AND ".join(conditions)
        if conditions else ""
    )

    total = fetch_one(
        f"""
        SELECT COUNT(*) AS total
        FROM energy_alerts
        {where_clause}
        """,
        tuple(parameters),
    )["total"]

    records = fetch_all(
        f"""
        SELECT *
        FROM energy_alerts
        {where_clause}
        ORDER BY alert_id DESC
        LIMIT ? OFFSET ?
        """,
        tuple(parameters) + (limit, offset),
    )

    records = [parse_alert_explanation(row) for row in records]

    return {
        "total_alerts": total,
        "limit": limit,
        "offset": offset,
        "alerts": records,
    }


# --------------------------------------------------
# ENERGY ALERTS - STATUS MANAGEMENT
# --------------------------------------------------

@app.patch(
    "/api/v1/alerts/{alert_id}/status",
    tags=["Energy Alerts"],
)
def update_alert_status(
    alert_id: int,
    request: AlertStatusUpdate,
):
    """
    Update an alert through the permitted lifecycle:

    OPEN -> ACKNOWLEDGED -> RESOLVED
    """

    target_status = request.status

    connection = get_write_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        alert = connection.execute(
            """
            SELECT *
            FROM energy_alerts
            WHERE alert_id = ?
            """,
            (alert_id,),
        ).fetchone()

        if alert is None:
            raise HTTPException(
                status_code=404,
                detail="Energy alert not found.",
            )

        current_status = alert["status"]

        allowed_transitions = {
            "OPEN": "ACKNOWLEDGED",
            "ACKNOWLEDGED": "RESOLVED",
        }

        expected_status = allowed_transitions.get(current_status)

        if expected_status != target_status:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Invalid alert status transition: "
                    f"{current_status} -> {target_status}. "
                    f"Expected next status: {expected_status or 'None'}."
                ),
            )

        cursor = connection.execute(
            """
            UPDATE energy_alerts
            SET status = ?
            WHERE alert_id = ?
              AND status = ?
            """,
            (
                target_status,
                alert_id,
                current_status,
            ),
        )

        if cursor.rowcount != 1:
            raise HTTPException(
                status_code=409,
                detail="Alert status changed before the update completed.",
            )

        updated_alert = connection.execute(
            """
            SELECT *
            FROM energy_alerts
            WHERE alert_id = ?
            """,
            (alert_id,),
        ).fetchone()

        connection.commit()

        result = dict(updated_alert)
        return parse_alert_explanation(result)

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


# --------------------------------------------------
# ENERGY ALERTS - DETAILS
# --------------------------------------------------

@app.get("/api/v1/alerts/{alert_id}", tags=["Energy Alerts"])
def get_alert_details(alert_id: int):
    alert = fetch_one(
        """
        SELECT *
        FROM energy_alerts
        WHERE alert_id = ?
        """,
        (alert_id,),
    )

    if alert is None:
        raise HTTPException(
            status_code=404,
            detail="Energy alert not found.",
        )

    alert = parse_alert_explanation(alert)

    telemetry = fetch_one(
        """
        SELECT *
        FROM machine_telemetry
        WHERE id = ?
        """,
        (alert["telemetry_id"],),
    )

    alert["telemetry"] = telemetry

    return alert


# --------------------------------------------------
# ENERGY ANALYTICS
# --------------------------------------------------

@app.get("/api/v1/analytics/energy", tags=["Analytics"])
def get_energy_analytics(
    machine_id: Optional[str] = None,
):
    conditions = []
    parameters = []

    if machine_id:
        conditions.append("machine_id = ?")
        parameters.append(machine_id)

    where_clause = (
        "WHERE " + " AND ".join(conditions)
        if conditions else ""
    )

    return {
        "by_operating_state": fetch_all(
            f"""
            SELECT
                state,
                COUNT(*) AS reading_count,
                ROUND(AVG(power_kw), 3) AS average_power_kw,
                ROUND(MAX(power_kw), 3) AS maximum_power_kw,
                ROUND(SUM(energy_kwh), 3) AS total_energy_kwh
            FROM machine_telemetry
            {where_clause}
            GROUP BY state
            ORDER BY reading_count DESC
            """,
            tuple(parameters),
        ),
        "by_machine": fetch_all(
            f"""
            SELECT
                machine_id,
                COUNT(*) AS reading_count,
                ROUND(AVG(power_kw), 3) AS average_power_kw,
                ROUND(SUM(energy_kwh), 3) AS total_energy_kwh,
                ROUND(AVG(expected_power_kw), 3)
                    AS average_expected_power_kw
            FROM machine_telemetry
            {where_clause}
            GROUP BY machine_id
            ORDER BY machine_id
            """,
            tuple(parameters),
        ),
    }


# --------------------------------------------------
# ALERT ANALYTICS
# --------------------------------------------------

@app.get("/api/v1/analytics/alerts", tags=["Analytics"])
def get_alert_analytics():
    return {
        "by_severity": fetch_all(
            """
            SELECT
                severity,
                COUNT(*) AS alert_count
            FROM energy_alerts
            GROUP BY severity
            ORDER BY
                CASE severity
                    WHEN 'CRITICAL' THEN 1
                    WHEN 'HIGH' THEN 2
                    WHEN 'WARNING' THEN 3
                    ELSE 4
                END
            """
        ),
        "by_status": fetch_all(
            """
            SELECT
                status,
                COUNT(*) AS alert_count
            FROM energy_alerts
            GROUP BY status
            ORDER BY status
            """
        ),
        "by_machine": fetch_all(
            """
            SELECT
                machine_id,
                COUNT(*) AS alert_count,
                ROUND(AVG(excess_power_kw), 3)
                    AS average_excess_power_kw,
                ROUND(MAX(excess_power_kw), 3)
                    AS maximum_excess_power_kw
            FROM energy_alerts
            GROUP BY machine_id
            ORDER BY alert_count DESC
            """
        ),
    }


import json
import sqlite3
from pathlib import Path

import paho.mqtt.client as mqtt

from ingestion.telemetry_validator import validate_telemetry
from detection.energy_detector import detect_energy_waste
from detection.alert_store import initialize_alert_table, save_alert
from diagnosis.diagnosis_engine import diagnose_energy_anomaly


# ============================================================
# CONFIGURATION
# ============================================================

BROKER = "localhost"
PORT = 1883
TOPIC = "industrial/plant1/motor01/telemetry"

DATABASE_PATH = (
    Path(__file__).resolve().parent.parent
    / "database"
    / "energy_data.db"
)


# ============================================================
# DATABASE FUNCTION: SAVE TELEMETRY
# ============================================================

def save_telemetry(data):
    """Save validated telemetry; ignore duplicate event IDs."""

    connection = None

    try:
        connection = sqlite3.connect(
            DATABASE_PATH,
            timeout=10,
        )

        cursor = connection.cursor()

        cursor.execute(
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
            ON CONFLICT DO NOTHING
            """,
            (
                data["event_id"],
                data["timestamp"],
                data["machine_id"],
                data["state"],
                data["load_percent"],
                data["rpm"],
                data["temperature_c"],
                data["power_kw"],
                data["expected_power_kw"],
                data["production_units_per_min"],
                data["energy_kwh"],
                data["degradation_factor"],
            ),
        )

        inserted = cursor.rowcount == 1
        connection.commit()

        return inserted

    except Exception:
        if connection is not None:
            connection.rollback()
        raise

    finally:
        if connection is not None:
            connection.close()


# ============================================================
# DATABASE FUNCTION: RETRIEVE TELEMETRY ID
# ============================================================

def get_telemetry_id(event_id):
    """Retrieve the database ID for a saved telemetry event."""

    connection = None

    try:
        connection = sqlite3.connect(
            DATABASE_PATH,
            timeout=10,
        )

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT id
            FROM machine_telemetry
            WHERE event_id = ?
            """,
            (event_id,),
        )

        result = cursor.fetchone()

        if result is None:
            raise LookupError(
                f"Telemetry record not found for event_id: {event_id}"
            )

        return result[0]

    finally:
        if connection is not None:
            connection.close()


# ============================================================
# ALERT EXPLANATION BUILDER
# ============================================================

def build_alert_explanation(detection_result, diagnosis_result):
    """
    Preserve the original ML explanation and attach structured
    advisory diagnosis information.
    """

    combined_explanation = {
        "detection_explanation": detection_result["explanation"],
        "diagnosis": diagnosis_result,
    }

    return json.dumps(
        combined_explanation,
        ensure_ascii=False,
        allow_nan=False,
    )


# ============================================================
# MQTT CALLBACKS
# ============================================================

def on_connect(client, userdata, flags, reason_code, properties):
    """Subscribe to telemetry after a successful connection."""

    if reason_code == 0:
        print("Connected to MQTT broker.")
        print("Subscribing to:", TOPIC)

        result, _ = client.subscribe(TOPIC)

        if result != mqtt.MQTT_ERR_SUCCESS:
            print("Warning: MQTT subscription request failed.")

    else:
        print("MQTT connection failed:", reason_code)


def on_message(client, userdata, msg):
    """Validate, store, detect and diagnose energy anomalies."""

    # --------------------------------------------------------
    # STEP 1: DECODE MESSAGE
    # --------------------------------------------------------

    try:
        payload = msg.payload.decode("utf-8")
        data = json.loads(payload)

    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        print("Invalid message payload:", error)
        return

    # --------------------------------------------------------
    # STEP 2: VALIDATE TELEMETRY
    # --------------------------------------------------------

    try:
        is_valid, errors = validate_telemetry(data)

        if not is_valid:
            print("Telemetry rejected:", errors)
            return

        # ----------------------------------------------------
        # STEP 3: SAVE TELEMETRY
        # ----------------------------------------------------

        inserted = save_telemetry(data)

        if not inserted:
            print(
                "Duplicate event ignored:",
                data["event_id"],
            )
            return

        print(
            "Telemetry saved:",
            "event_id =", data["event_id"],
            "| machine =", data["machine_id"],
            "| state =", data["state"],
        )

        # ----------------------------------------------------
        # STEP 4: RETRIEVE TELEMETRY DATABASE ID
        # ----------------------------------------------------

        telemetry_id = get_telemetry_id(data["event_id"])

        # ----------------------------------------------------
        # STEP 5: RUN ML ENERGY-WASTE DETECTOR
        # ----------------------------------------------------

        detection_result = detect_energy_waste(data)

        print(
            "Energy detection:",
            "machine =", data["machine_id"],
            "| actual =", detection_result["actual_power_kw"],
            "kW | expected =",
            detection_result["expected_power_kw"],
            "kW | excess =",
            detection_result["excess_power_kw"],
            "kW | severity =",
            detection_result["severity"],
        )

        # ----------------------------------------------------
        # STEP 6: DIAGNOSE AND SAVE ANOMALY
        # ----------------------------------------------------

        if detection_result["is_anomaly"]:

            diagnosis_result = diagnose_energy_anomaly(
                data,
                detection_result,
            )

            print(
                "Diagnostic assessment:",
                diagnosis_result["diagnosis_status"],
            )

            print(
                "Diagnostic summary:",
                diagnosis_result["summary"],
            )

            # Preserve the original detector result.
            # Only its explanation field is replaced in a copy.
            alert_result = detection_result.copy()

            alert_result["explanation"] = build_alert_explanation(
                detection_result,
                diagnosis_result,
            )

            alert_saved = save_alert(
                telemetry_id,
                alert_result,
                DATABASE_PATH,
            )

            if alert_saved:
                print(
                    "ENERGY WASTE ALERT CREATED:",
                    "| machine =", data["machine_id"],
                    "| severity =", detection_result["severity"],
                    "| excess power =",
                    detection_result["excess_power_kw"],
                    "kW",
                )

            else:
                print(
                    "Alert already exists for telemetry ID:",
                    telemetry_id,
                )

        else:
            print(
                "Normal energy consumption:",
                data["machine_id"],
            )

    # --------------------------------------------------------
    # ERROR HANDLING
    # --------------------------------------------------------

    except sqlite3.Error as error:
        print("Database error:", error)

    except Exception as error:
        print("Error processing telemetry:", error)


# ============================================================
# MAIN FUNCTION
# ============================================================

def main():
    """Initialize alert storage and start the MQTT consumer."""

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="industrial_energy_consumer",
    )

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        print("Starting industrial energy telemetry consumer...")
        print("Broker:", BROKER)
        print("Port:", PORT)
        print("Topic:", TOPIC)
        print("Database:", DATABASE_PATH)

        initialize_alert_table(DATABASE_PATH)

        print("Alert storage initialized successfully.")

        client.connect(BROKER, PORT, keepalive=60)
        client.loop_forever()

    except KeyboardInterrupt:
        print("\nConsumer stopped by user.")

    except (OSError, sqlite3.Error, mqtt.MqttError) as error:
        print("MQTT or database runtime error:", error)

    finally:
        client.disconnect()
        client.loop_stop()
        print("Consumer shut down.")


if __name__ == "__main__":
    main()

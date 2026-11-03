
import argparse
import json
import math
import random
import time
from datetime import datetime

import paho.mqtt.client as mqtt

from ingestion.event_identity import create_event_id


# ============================================================
# MQTT CONFIGURATION
# ============================================================

BROKER = "localhost"
PORT = 1883
TOPIC = "industrial/plant1/motor01/telemetry"
MACHINE_ID = "MOTOR-01"
PUBLISH_INTERVAL_SECONDS = 2

# Controlled anomaly-test settings.
# This adds 12% excess power during eligible operating states.
TEST_DEGRADATION_FACTOR = 1.12


# ============================================================
# MACHINE SIMULATION
# ============================================================

cycle = 0


def generate_machine_data(anomaly_test=False):
    """Generate one simulated industrial machine telemetry event."""

    global cycle

    cycle += 1
    phase = cycle % 120

    # --------------------------------------------------------
    # MACHINE OPERATING STATES
    # --------------------------------------------------------

    if phase < 10:
        state = "STARTUP"
        load = random.uniform(18, 30)
        rpm = random.uniform(350, 850)

    elif phase < 70:
        state = "RUNNING"
        load = random.uniform(58, 82)
        rpm = 900 + load * 8 + random.gauss(0, 20)

    elif phase < 90:
        state = "HIGH_LOAD"
        load = random.uniform(82, 96)
        rpm = 900 + load * 8 + random.gauss(0, 20)

    elif phase < 105:
        state = "LOW_LOAD"
        load = random.uniform(25, 45)
        rpm = 900 + load * 8 + random.gauss(0, 20)

    elif phase < 115:
        state = "IDLE"
        load = random.uniform(5, 12)
        rpm = random.uniform(350, 550)

    else:
        state = "SHUTDOWN"
        load = 0.0
        rpm = 0.0

    load = max(0.0, min(load, 100.0))

    # --------------------------------------------------------
    # NORMAL TEMPERATURE
    # Matches benchmark generation logic.
    # --------------------------------------------------------

    temperature = (
        30
        + load * 0.32
        + random.gauss(0, 1.5)
    )

    # --------------------------------------------------------
    # EXPECTED POWER
    # Matches the benchmark baseline formula.
    # --------------------------------------------------------

    expected_power = (
        8
        + load * 0.55
        + rpm * 0.008
        + temperature * 0.04
    )

    # --------------------------------------------------------
    # HEALTHY OPERATION / CONTROLLED ANOMALY
    # --------------------------------------------------------

    degradation = 1.0

    if anomaly_test and state in ("RUNNING", "HIGH_LOAD"):
        degradation = TEST_DEGRADATION_FACTOR

    power = (
        expected_power * degradation
        + random.gauss(0, 0.8)
    )

    # --------------------------------------------------------
    # PRODUCTION
    # --------------------------------------------------------

    if state in ("RUNNING", "HIGH_LOAD"):
        production = max(
            0,
            load * 1.15 + random.gauss(0, 2)
        )
    else:
        production = 0.0

    # Energy consumed during one publishing interval.
    energy_kwh = power * (
        PUBLISH_INTERVAL_SECONDS / 3600
    )

    return {
        "event_id": create_event_id(),
        "timestamp": datetime.now().isoformat(),
        "machine_id": MACHINE_ID,
        "state": state,
        "load_percent": round(load, 2),
        "rpm": round(rpm, 2),
        "temperature_c": round(temperature, 2),
        "power_kw": round(power, 2),
        "expected_power_kw": round(expected_power, 2),
        "production_units_per_min": round(production, 2),
        "energy_kwh": round(energy_kwh, 5),
        "degradation_factor": round(degradation, 5),
    }


# ============================================================
# MQTT PUBLISHER
# ============================================================

def main():
    """Connect to MQTT and publish simulated telemetry."""

    parser = argparse.ArgumentParser(
        description="Industrial Energy Intelligence MQTT Simulator"
    )

    parser.add_argument(
        "--anomaly-test",
        action="store_true",
        help="Inject controlled excess power during RUNNING and HIGH_LOAD.",
    )

    args = parser.parse_args()

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="industrial_energy_simulator",
    )

    connected = False

    try:
        print("=" * 45)
        print("Industrial Energy Intelligence Platform")
        print("Live MQTT Machine Simulator")
        print("=" * 45)
        print(f"Machine: {MACHINE_ID}")
        print(f"Broker: {BROKER}:{PORT}")
        print(f"Topic: {TOPIC}")

        if args.anomaly_test:
            print("Mode: CONTROLLED ANOMALY TEST")
            print(f"Test degradation: {TEST_DEGRADATION_FACTOR}")
        else:
            print("Mode: HEALTHY NORMAL OPERATION")
            print("Degradation: 1.0")

        print("Press CTRL+C to stop.\n")

        client.connect(BROKER, PORT, keepalive=60)
        client.loop_start()
        connected = True

        while True:
            machine_data = generate_machine_data(
                anomaly_test=args.anomaly_test
            )

            message = json.dumps(machine_data)

            info = client.publish(
                TOPIC,
                message,
                qos=1,
            )

            info.wait_for_publish(timeout=5)

            if not info.is_published():
                print(
                    "Publish timed out; event:",
                    machine_data["event_id"],
                )
                continue

            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                print(
                    "Publish failed; result code:",
                    info.rc,
                )
                continue

            print(
                f"[{machine_data['timestamp']}] "
                f"Event={machine_data['event_id']} | "
                f"State={machine_data['state']} | "
                f"Load={machine_data['load_percent']}% | "
                f"RPM={machine_data['rpm']} | "
                f"Temp={machine_data['temperature_c']} C | "
                f"Power={machine_data['power_kw']} kW | "
                f"Expected={machine_data['expected_power_kw']} kW | "
                f"Degradation={machine_data['degradation_factor']} | "
                f"Production={machine_data['production_units_per_min']} units/min"
            )

            time.sleep(PUBLISH_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\nSimulator stopped by user.")

    except (OSError, RuntimeError) as error:
        print("MQTT simulator error:", error)

    finally:
        if connected:
            client.disconnect()
            client.loop_stop()

        print("Simulator shut down.")


if __name__ == "__main__":
    main()

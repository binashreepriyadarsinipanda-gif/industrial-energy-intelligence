
import numpy as np
import pandas as pd
from pathlib import Path

# ============================================================
# REPRODUCIBILITY AND CONFIGURATION
# ============================================================

RANDOM_SEED = 42
SAMPLE_INTERVAL_SECONDS = 2
NUMBER_OF_SESSIONS = 10
OBSERVATIONS_PER_SESSION = 1200

OUTPUT_PATH = (
    Path(__file__).resolve().parent
    / "controlled_energy_benchmark.csv"
)

# Only inject anomalies during productive operating states.
ELIGIBLE_STATES = ("RUNNING", "HIGH_LOAD")

# Anomaly windows are defined using observation indices.
ANOMALY_REGIONS = {
    "SUDDEN_EXCESS": (200, 260),
    "GRADUAL_EXCESS": (400, 520),
    "SUSTAINED_EXCESS": (650, 800),
    "INTERMITTENT_EXCESS": (950, 1100),
}


def generate_benchmark():
    rng = np.random.default_rng(RANDOM_SEED)
    records = []

    for session in range(NUMBER_OF_SESSIONS):
        session_id = f"BENCH_SESSION_{session + 1:02d}"

        for step in range(OBSERVATIONS_PER_SESSION):

            # ------------------------------------------------
            # OPERATING STATE
            # ------------------------------------------------

            phase = step % 120

            if phase < 10:
                state = "STARTUP"
                load = rng.uniform(22, 28)

            elif phase < 70:
                state = "RUNNING"
                load = 65 + 10 * np.sin(step / 8)
                load += rng.normal(0, 2)

            elif phase < 90:
                state = "HIGH_LOAD"
                load = rng.normal(88, 2)

            elif phase < 105:
                state = "LOW_LOAD"
                load = rng.normal(35, 2)

            elif phase < 115:
                state = "IDLE"
                load = rng.uniform(7, 9)

            else:
                state = "SHUTDOWN"
                load = 0

            load = float(np.clip(load, 0, 100))

            # ------------------------------------------------
            # MACHINE VARIABLES
            # ------------------------------------------------

            if state == "SHUTDOWN":
                rpm = 0

            elif state == "IDLE":
                rpm = rng.normal(500, 20)

            else:
                rpm = 900 + load * 8 + rng.normal(0, 15)

            temperature = (
                30
                + load * 0.32
                + rng.normal(0, 1.2)
            )

            # ------------------------------------------------
            # NORMAL POWER BASELINE
            # ------------------------------------------------

            baseline_power = (
                8
                + load * 0.55
                + rpm * 0.008
                + temperature * 0.04
            )

            power = baseline_power + rng.normal(0, 0.8)

            # ------------------------------------------------
            # CONTROLLED ANOMALY INJECTION
            # ------------------------------------------------

            anomaly_label = 0
            anomaly_type = "NORMAL"

            for scenario, (start, end) in ANOMALY_REGIONS.items():

                if start <= step < end:

                    # Only compare productive operating states.
                    if state in ELIGIBLE_STATES:

                        injection_applied = False

                        if scenario == "SUDDEN_EXCESS":
                            power += baseline_power * 0.25
                            injection_applied = True

                        elif scenario == "GRADUAL_EXCESS":
                            progress = (step - start) / (end - start)

                            power += baseline_power * (
                                0.05 + 0.20 * progress
                            )

                            injection_applied = True

                        elif scenario == "SUSTAINED_EXCESS":
                            power += baseline_power * 0.18
                            injection_applied = True

                        elif scenario == "INTERMITTENT_EXCESS":

                            # Ten injected observations followed by
                            # ten normal observations.
                            if (step - start) % 20 < 10:
                                power += baseline_power * 0.30
                                injection_applied = True

                        if injection_applied:
                            anomaly_label = 1
                            anomaly_type = scenario

                    # Each observation belongs to at most one region.
                    break

            # ------------------------------------------------
            # PRODUCTION AND ENERGY
            # ------------------------------------------------

            if state in ("RUNNING", "HIGH_LOAD"):
                production = max(
                    0,
                    load * 1.15 + rng.normal(0, 2)
                )
            else:
                production = 0

            energy_kwh = (
                power * SAMPLE_INTERVAL_SECONDS / 3600
            )

            # ------------------------------------------------
            # RECORD
            # ------------------------------------------------

            records.append({
                "session_id": session_id,
                "timestamp_seconds": (
                    step * SAMPLE_INTERVAL_SECONDS
                ),
                "machine_id": "BENCH_MOTOR_01",
                "state": state,
                "load_percent": round(load, 2),
                "rpm": round(rpm, 2),
                "temperature_c": round(temperature, 2),
                "power_kw": round(power, 2),
                "production_units_per_min": round(
                    production, 2
                ),
                "energy_kwh": round(energy_kwh, 7),
                "anomaly_label": anomaly_label,
                "anomaly_type": anomaly_type,
            })

    df = pd.DataFrame(records)

    # --------------------------------------------------------
    # BASIC INTEGRITY CHECKS BEFORE SAVING
    # --------------------------------------------------------

    expected_rows = NUMBER_OF_SESSIONS * OBSERVATIONS_PER_SESSION

    assert len(df) == expected_rows, (
        f"Expected {expected_rows} rows, got {len(df)}"
    )

    assert not df.isnull().any().any(), (
        "Benchmark contains missing values."
    )

    assert set(df["anomaly_label"].unique()).issubset({0, 1}), (
        "Unexpected anomaly label values."
    )

    assert (
        (df["anomaly_label"] == 1)
        == (df["anomaly_type"] != "NORMAL")
    ).all(), "Anomaly labels and anomaly types are inconsistent."

    assert (
        df.loc[df["anomaly_label"] == 1, "state"]
        .isin(ELIGIBLE_STATES)
    ).all(), "Anomaly injected outside eligible operating states."

    # Check timestamp continuity within every session.
    for session_id, group in df.groupby("session_id"):
        timestamps = group["timestamp_seconds"].to_numpy()
        differences = np.diff(timestamps)

        assert np.all(differences == SAMPLE_INTERVAL_SECONDS), (
            f"Timestamp gap found in {session_id}"
        )

    # --------------------------------------------------------
    # SAVE BENCHMARK
    # --------------------------------------------------------

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)

    return df


if __name__ == "__main__":

    benchmark = generate_benchmark()

    print("Controlled benchmark generated successfully.")

    print("\nDataset integrity:")
    print("Total observations:", len(benchmark))
    print("Sessions:", benchmark["session_id"].nunique())
    print("Observations per session:")
    print(benchmark.groupby("session_id").size().to_string())

    print("\nAnomaly distribution:")
    print(benchmark["anomaly_type"].value_counts().to_string())

    print("\nLabel distribution:")
    print(benchmark["anomaly_label"].value_counts().to_string())

    print("\nOperating-state distribution:")
    print(benchmark["state"].value_counts().to_string())

    print("\nSaved to:", OUTPUT_PATH)

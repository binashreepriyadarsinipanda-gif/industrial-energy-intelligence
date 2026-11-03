import numpy as np
import pandas as pd
from pathlib import Path

# ============================================================
# CONFIGURATION
# ============================================================

RANDOM_SEED = 2027
SAMPLE_INTERVAL_SECONDS = 2
NUMBER_OF_SESSIONS = 10
OBSERVATIONS_PER_SESSION = 1200

OUTPUT_PATH = (
    Path(__file__).resolve().parent
    / "controlled_energy_benchmark_v2.csv"
)

ELIGIBLE_STATES = ("RUNNING", "HIGH_LOAD")

ANOMALY_TYPES = (
    "SUDDEN_EXCESS",
    "GRADUAL_EXCESS",
    "SUSTAINED_EXCESS",
    "INTERMITTENT_EXCESS",
)

VALID_STATES = {
    "STARTUP",
    "RUNNING",
    "HIGH_LOAD",
    "LOW_LOAD",
    "IDLE",
    "SHUTDOWN",
}

REQUIRED_COLUMNS = [
    "session_id",
    "timestamp_seconds",
    "machine_id",
    "state",
    "load_percent",
    "rpm",
    "temperature_c",
    "power_kw",
    "production_units_per_min",
    "energy_kwh",
    "anomaly_label",
    "anomaly_type",
]


# ============================================================
# OPERATING STATE GENERATION
# ============================================================

def generate_operating_states(rng):
    """Generate a variable operating schedule for one session."""

    states = []

    startup_length = int(rng.integers(8, 21))
    states.extend(["STARTUP"] * startup_length)

    operating_cycle = [
        ("RUNNING", 45, 85),
        ("HIGH_LOAD", 10, 25),
        ("LOW_LOAD", 10, 25),
        ("IDLE", 5, 15),
        ("SHUTDOWN", 5, 12),
    ]

    while len(states) < OBSERVATIONS_PER_SESSION:

        cycle = list(operating_cycle)
        rng.shuffle(cycle)

        for state, minimum, maximum in cycle:

            duration = int(
                rng.integers(minimum, maximum + 1)
            )

            states.extend([state] * duration)

            if len(states) >= OBSERVATIONS_PER_SESSION:
                break

    return states[:OBSERVATIONS_PER_SESSION]


# ============================================================
# MACHINE MEASUREMENTS
# ============================================================

def generate_measurements(state, rng):
    """Generate synthetic operating measurements."""

    if state == "STARTUP":

        load = rng.uniform(18, 30)
        rpm = rng.uniform(350, 850)

    elif state == "RUNNING":

        load = rng.uniform(58, 82)
        rpm = 900 + load * 8 + rng.normal(0, 20)

    elif state == "HIGH_LOAD":

        load = rng.uniform(82, 96)
        rpm = 900 + load * 8 + rng.normal(0, 20)

    elif state == "LOW_LOAD":

        load = rng.uniform(25, 45)
        rpm = 900 + load * 8 + rng.normal(0, 20)

    elif state == "IDLE":

        load = rng.uniform(5, 12)
        rpm = rng.uniform(350, 550)

    else:

        load = 0.0
        rpm = 0.0

    load = float(np.clip(load, 0, 100))

    temperature = (
        30
        + load * 0.32
        + rng.normal(0, 1.5)
    )

    baseline_power = (
        8
        + load * 0.55
        + rpm * 0.008
        + temperature * 0.04
    )

    power = baseline_power + rng.normal(0, 0.8)

    if state in ELIGIBLE_STATES:

        production = max(
            0,
            load * 1.15 + rng.normal(0, 2)
        )

    else:

        production = 0.0

    return {
        "load_percent": float(load),
        "rpm": float(max(0, rpm)),
        "temperature_c": float(temperature),
        "baseline_power_kw": float(baseline_power),
        "power_kw": float(power),
        "production_units_per_min": float(production),
    }


# ============================================================
# RANDOMIZED ANOMALY SCENARIOS
# ============================================================

def choose_anomaly_windows(states, rng):
    """
    Select four non-overlapping anomaly windows.

    Windows remain entirely inside RUNNING or HIGH_LOAD states.
    """

    eligible = np.array(
        [
            state in ELIGIBLE_STATES
            for state in states
        ],
        dtype=bool,
    )

    selected_windows = []

    occupied = np.zeros(
        OBSERVATIONS_PER_SESSION,
        dtype=bool,
    )

    duration_ranges = {
        "SUDDEN_EXCESS": (8, 25),
        "GRADUAL_EXCESS": (45, 100),
        "SUSTAINED_EXCESS": (45, 100),
        "INTERMITTENT_EXCESS": (40, 100),
    }

    for anomaly_type in rng.permutation(ANOMALY_TYPES):

        minimum, maximum = duration_ranges[str(anomaly_type)]

        selected = None

        for _ in range(5000):

            duration = int(
                rng.integers(minimum, maximum + 1)
            )

            latest_start = (
                OBSERVATIONS_PER_SESSION - duration
            )

            start = int(
                rng.integers(0, latest_start + 1)
            )

            end = start + duration

            if not eligible[start:end].all():
                continue

            if occupied[start:end].any():
                continue

            selected = (
                str(anomaly_type),
                start,
                end,
            )

            occupied[start:end] = True

            break

        if selected is None:

            raise RuntimeError(
                f"Could not place {anomaly_type} in this session. "
                "No benchmark was saved."
            )

        selected_windows.append(selected)

    return selected_windows


# ============================================================
# ANOMALY INJECTION
# ============================================================

def apply_anomaly(
    anomaly_type,
    position,
    duration,
    baseline_power,
    rng,
):
    """Calculate injected excess power for one observation."""

    if anomaly_type == "SUDDEN_EXCESS":

        return (
            baseline_power
            * rng.uniform(0.18, 0.32)
        )

    if anomaly_type == "GRADUAL_EXCESS":

        progress = position / max(duration - 1, 1)

        starting_level = rng.uniform(0.03, 0.08)
        ending_level = rng.uniform(0.18, 0.30)

        magnitude = (
            starting_level
            + (ending_level - starting_level) * progress
        )

        return baseline_power * magnitude

    if anomaly_type == "SUSTAINED_EXCESS":

        return (
            baseline_power
            * rng.uniform(0.12, 0.24)
        )

    if anomaly_type == "INTERMITTENT_EXCESS":

        pulse_length = int(rng.integers(5, 13))

        cycle_length = pulse_length * 2

        if position % cycle_length < pulse_length:

            return (
                baseline_power
                * rng.uniform(0.20, 0.35)
            )

        return 0.0

    raise ValueError(
        f"Unknown anomaly type: {anomaly_type}"
    )


# ============================================================
# GENERATE ONE SESSION
# ============================================================

def generate_session(session_number, rng):
    """Generate one complete synthetic machine session."""

    session_id = (
        f"BENCH_SESSION_{session_number:02d}"
    )

    states = generate_operating_states(rng)

    windows = choose_anomaly_windows(states, rng)

    anomaly_lookup = {}

    for anomaly_type, start, end in windows:

        for index in range(start, end):

            anomaly_lookup[index] = (
                anomaly_type,
                index - start,
                end - start,
            )

    records = []

    for step, state in enumerate(states):

        measurements = generate_measurements(
            state,
            rng,
        )

        power = measurements["power_kw"]

        anomaly_label = 0
        anomaly_type = "NORMAL"

        if step in anomaly_lookup:

            scenario, position, duration = (
                anomaly_lookup[step]
            )

            excess = apply_anomaly(
                scenario,
                position,
                duration,
                measurements["baseline_power_kw"],
                rng,
            )

            if excess > 0:

                power += excess

                anomaly_label = 1

                anomaly_type = scenario

        # Round power first so stored energy is consistent
        # with the exact power value written to the CSV.

        power = round(float(power), 2)

        energy_kwh = round(
            power * SAMPLE_INTERVAL_SECONDS / 3600,
            7,
        )

        records.append({

            "session_id": session_id,

            "timestamp_seconds": (
                step * SAMPLE_INTERVAL_SECONDS
            ),

            "machine_id": "BENCH_MOTOR_01",

            "state": state,

            "load_percent": round(
                measurements["load_percent"],
                2,
            ),

            "rpm": round(
                measurements["rpm"],
                2,
            ),

            "temperature_c": round(
                measurements["temperature_c"],
                2,
            ),

            "power_kw": power,

            "production_units_per_min": round(
                measurements["production_units_per_min"],
                2,
            ),

            "energy_kwh": energy_kwh,

            "anomaly_label": anomaly_label,

            "anomaly_type": anomaly_type,
        })

    return records


# ============================================================
# DATASET VALIDATION
# ============================================================

def validate_benchmark(df):
    """
    Validate schema, numeric integrity, labels, operating
    constraints, energy calculations, session structure
    and anomaly coverage.
    """

    expected_rows = (
        NUMBER_OF_SESSIONS
        * OBSERVATIONS_PER_SESSION
    )

    assert isinstance(df, pd.DataFrame), (
        "Input must be a pandas DataFrame."
    )

    assert len(df) == expected_rows, (
        f"Expected {expected_rows} rows, got {len(df)}."
    )

    assert list(df.columns) == REQUIRED_COLUMNS, (
        "Dataset columns do not match the required schema."
    )

    assert not df.isnull().any().any(), (
        "Dataset contains missing values."
    )

    numeric_columns = [
        "timestamp_seconds",
        "load_percent",
        "rpm",
        "temperature_c",
        "power_kw",
        "production_units_per_min",
        "energy_kwh",
        "anomaly_label",
    ]

    for column in numeric_columns:

        values = pd.to_numeric(
            df[column],
            errors="coerce",
        ).to_numpy(dtype=float)

        assert np.isfinite(values).all(), (
            f"Non-numeric or non-finite values in {column}."
        )

    assert set(df["state"].unique()).issubset(
        VALID_STATES
    ), "Unexpected operating state found."

    valid_anomaly_types = (
        set(ANOMALY_TYPES) | {"NORMAL"}
    )

    assert set(
        df["anomaly_type"].unique()
    ).issubset(valid_anomaly_types), (
        "Unexpected anomaly type found."
    )

    assert df["anomaly_label"].isin([0, 1]).all(), (
        "Anomaly labels must be binary 0 or 1."
    )

    assert (
        (df["anomaly_label"] == 1)
        == (df["anomaly_type"] != "NORMAL")
    ).all(), (
        "Anomaly labels and anomaly types are inconsistent."
    )

    assert df["load_percent"].between(0, 100).all(), (
        "Load percentage must be between 0 and 100."
    )

    for column in [
        "rpm",
        "power_kw",
        "energy_kwh",
        "production_units_per_min",
    ]:

        assert (df[column] >= 0).all(), (
            f"Negative values found in {column}."
        )

    nonproductive = ~df["state"].isin(
        ELIGIBLE_STATES
    )

    assert (
        df.loc[
            nonproductive,
            "production_units_per_min",
        ] == 0
    ).all(), (
        "Nonproductive states must have zero production."
    )

    assert (
        df.loc[
            df["anomaly_label"] == 1,
            "state",
        ].isin(ELIGIBLE_STATES)
    ).all(), (
        "Anomalies must occur only in productive states."
    )

    # Validate energy calculation.

    expected_energy = (
        df["power_kw"]
        * SAMPLE_INTERVAL_SECONDS
        / 3600
    )

    assert np.allclose(
        df["energy_kwh"].to_numpy(dtype=float),
        expected_energy.to_numpy(dtype=float),
        rtol=0,
        atol=5.1e-8,
    ), (
        "Energy values do not match power and sampling interval."
    )

    # Validate session IDs.

    expected_session_ids = {
        f"BENCH_SESSION_{i:02d}"
        for i in range(
            1,
            NUMBER_OF_SESSIONS + 1,
        )
    }

    assert set(
        df["session_id"].unique()
    ) == expected_session_ids, (
        "Session IDs are missing or unexpected."
    )

    # Validate machine ID.

    assert df["machine_id"].nunique() == 1, (
        "This benchmark is expected to contain one machine ID."
    )

    assert df["machine_id"].iloc[0] == (
        "BENCH_MOTOR_01"
    ), "Unexpected machine ID."

    # Validate each session separately.

    for session_id, group in df.groupby(
        "session_id",
        sort=True,
    ):

        assert len(group) == OBSERVATIONS_PER_SESSION, (
            f"Incorrect row count in {session_id}."
        )

        assert not group[
            "timestamp_seconds"
        ].duplicated().any(), (
            f"Duplicate timestamps in {session_id}."
        )

        timestamps = group[
            "timestamp_seconds"
        ].to_numpy(dtype=float)

        assert timestamps[0] == 0, (
            f"Session {session_id} does not start at timestamp zero."
        )

        assert np.all(
            np.diff(timestamps) == SAMPLE_INTERVAL_SECONDS
        ), (
            f"Timestamp discontinuity in {session_id}."
        )

        observed_anomalies = set(
            group.loc[
                group["anomaly_label"] == 1,
                "anomaly_type",
            ]
        )

        assert set(ANOMALY_TYPES).issubset(
            observed_anomalies
        ), (
            f"Missing anomaly type in {session_id}."
        )

    return True


# ============================================================
# MAIN GENERATION
# ============================================================

def generate_benchmark():
    """Generate, validate and save benchmark v2."""

    # Do not accidentally overwrite an existing dataset.

    if OUTPUT_PATH.exists():

        raise FileExistsError(
            f"{OUTPUT_PATH} already exists. "
            "Move or rename it before generating a replacement."
        )

    rng = np.random.default_rng(
        RANDOM_SEED
    )

    records = []

    for session_number in range(
        1,
        NUMBER_OF_SESSIONS + 1,
    ):

        records.extend(
            generate_session(
                session_number,
                rng,
            )
        )

    df = pd.DataFrame(
        records,
        columns=REQUIRED_COLUMNS,
    )

    # Validate before saving.

    validate_benchmark(df)

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        OUTPUT_PATH,
        index=False,
    )

    return df


# ============================================================
# EXECUTION
# ============================================================

if __name__ == "__main__":

    benchmark = generate_benchmark()

    print(
        "Benchmark v2 generated successfully."
    )

    print(
        "\nDataset shape:",
        benchmark.shape,
    )

    print("\nSession sizes:")

    print(
        benchmark.groupby(
            "session_id"
        ).size().to_string()
    )

    print("\nAnomaly distribution:")

    print(
        benchmark["anomaly_type"]
        .value_counts()
        .to_string()
    )

    print("\nLabel distribution:")

    print(
        benchmark["anomaly_label"]
        .value_counts()
        .to_string()
    )

    print("\nOperating-state distribution:")

    print(
        benchmark["state"]
        .value_counts()
        .to_string()
    )

    print("\nAnomaly distribution by session:")

    print(
        pd.crosstab(
            benchmark["session_id"],
            benchmark["anomaly_type"],
        ).to_string()
    )

    print(
        "\nSaved to:",
        OUTPUT_PATH,
    )
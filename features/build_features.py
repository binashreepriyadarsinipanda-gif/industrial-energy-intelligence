from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# PATHS AND CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Use the newly audited benchmark v2.
INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "controlled_energy_benchmark_v2.csv"
)

# Preserve the original feature dataset.
OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "benchmark_features_v2.csv"
)


# ============================================================
# DATASET SCHEMA
# ============================================================

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


# These are the only numerical model predictors.
NUMERIC_FEATURES = [
    "load_percent",
    "rpm",
    "temperature_c",
    "power_kw",
    "production_units_per_min",
]


# Operating state will be one-hot encoded.
CATEGORICAL_FEATURES = [
    "state",
]


# Metadata is retained for auditing and session-based splitting.
METADATA_COLUMNS = [
    "session_id",
    "timestamp_seconds",
    "machine_id",
    "anomaly_type",
    "energy_kwh",
]


TARGET_COLUMN = "anomaly_label"


# ============================================================
# LOAD AND VALIDATE BENCHMARK
# ============================================================

def load_benchmark():
    """Load and validate benchmark v2."""

    if not INPUT_PATH.exists():

        raise FileNotFoundError(
            f"Benchmark v2 not found: {INPUT_PATH}"
        )

    df = pd.read_csv(INPUT_PATH)

    if df.empty:

        raise ValueError(
            "Benchmark dataset is empty."
        )

    missing_columns = (
        set(REQUIRED_COLUMNS) - set(df.columns)
    )

    if missing_columns:

        raise ValueError(
            f"Missing required columns: "
            f"{sorted(missing_columns)}"
        )

    # Check missing values.

    if df[REQUIRED_COLUMNS].isnull().any().any():

        raise ValueError(
            "Benchmark contains missing values."
        )

    # Check numeric columns.

    numeric_columns = [
        "timestamp_seconds",
        "load_percent",
        "rpm",
        "temperature_c",
        "power_kw",
        "production_units_per_min",
        "energy_kwh",
        TARGET_COLUMN,
    ]

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

        values = df[column].to_numpy(
            dtype=float
        )

        if not np.isfinite(values).all():

            raise ValueError(
                f"Invalid numeric values in {column}."
            )

    # Check binary target.

    if not set(
        df[TARGET_COLUMN].unique()
    ).issubset({0, 1}):

        raise ValueError(
            "Anomaly labels must contain only 0 and 1."
        )

    # Check label and anomaly type consistency.

    expected_labels = (
        df["anomaly_type"] != "NORMAL"
    ).astype(int)

    if not (
        df[TARGET_COLUMN].astype(int)
        == expected_labels
    ).all():

        raise ValueError(
            "Anomaly labels and anomaly types are inconsistent."
        )

    # Check operating states.

    valid_states = {
        "STARTUP",
        "RUNNING",
        "HIGH_LOAD",
        "LOW_LOAD",
        "IDLE",
        "SHUTDOWN",
    }

    if not set(df["state"].unique()).issubset(
        valid_states
    ):

        raise ValueError(
            "Unexpected operating state found."
        )

    # Check duplicate session timestamps.

    if df.duplicated(
        subset=[
            "session_id",
            "timestamp_seconds",
        ]
    ).any():

        raise ValueError(
            "Duplicate session timestamps detected."
        )

    # Check non-negative physical measurements.

    nonnegative_columns = [
        "rpm",
        "power_kw",
        "energy_kwh",
        "production_units_per_min",
    ]

    for column in nonnegative_columns:

        if (df[column] < 0).any():

            raise ValueError(
                f"Negative values found in {column}."
            )

    if not df["load_percent"].between(
        0,
        100,
    ).all():

        raise ValueError(
            "Load percentage must be between 0 and 100."
        )

    # Confirm expected session count.

    if df["session_id"].nunique() != 10:

        raise ValueError(
            "Expected exactly 10 benchmark sessions."
        )

    # Confirm each session has 1200 observations.

    session_sizes = df.groupby(
        "session_id"
    ).size()

    if not (session_sizes == 1200).all():

        raise ValueError(
            "Every session must contain 1200 observations."
        )

    # Ensure all anomaly types are represented.

    required_anomaly_types = {
        "NORMAL",
        "SUDDEN_EXCESS",
        "GRADUAL_EXCESS",
        "SUSTAINED_EXCESS",
        "INTERMITTENT_EXCESS",
    }

    if set(
        df["anomaly_type"].unique()
    ) != required_anomaly_types:

        raise ValueError(
            "Unexpected or missing anomaly types."
        )

    return df


# ============================================================
# FEATURE ENGINEERING
# ============================================================

def build_features(df):
    """
    Build model predictors and retain metadata separately.

    Metadata and target columns are not included in X.
    """

    # Select numerical predictors.

    X_numeric = df[
        NUMERIC_FEATURES
    ].copy()

    # Select categorical predictors.

    X_categorical = df[
        CATEGORICAL_FEATURES
    ].copy()

    # One-hot encode machine operating state.

    X_categorical = pd.get_dummies(
        X_categorical,
        columns=CATEGORICAL_FEATURES,
        dtype=int,
    )

    # Combine numerical and categorical features.

    X = pd.concat(
        [
            X_numeric,
            X_categorical,
        ],
        axis=1,
    )

    # Maintain deterministic feature order.

    X = X.reindex(
        sorted(X.columns),
        axis=1,
    )

    # Confirm all model features are numeric.

    if not all(
        pd.api.types.is_numeric_dtype(dtype)
        for dtype in X.dtypes
    ):

        raise TypeError(
            "Non-numeric model features detected."
        )

    # Check finite feature values.

    if not np.isfinite(
        X.to_numpy(dtype=float)
    ).all():

        raise ValueError(
            "Non-finite feature values detected."
        )

    # Extract target separately.

    y = df[
        TARGET_COLUMN
    ].astype(int).copy()

    # Preserve metadata outside model predictors.

    metadata = df[
        METADATA_COLUMNS
    ].copy()

    # Explicit leakage protection.

    forbidden_predictors = {
        "session_id",
        "timestamp_seconds",
        "machine_id",
        "anomaly_type",
        "anomaly_label",
        "energy_kwh",
    }

    leakage_columns = (
        set(X.columns) & forbidden_predictors
    )

    if leakage_columns:

        raise ValueError(
            f"Potential target leakage: {leakage_columns}"
        )

    return X, y, metadata


# ============================================================
# SAVE FEATURE DATASET
# ============================================================

def save_features(X, y, metadata):
    """Save metadata, model features and target separately."""

    if OUTPUT_PATH.exists():

        raise FileExistsError(
            f"Output already exists: {OUTPUT_PATH}. "
            "The existing file will not be overwritten."
        )

    # Metadata is retained for session-based splitting.
    # It must not be passed directly into model.fit().

    output = pd.concat(
        [
            metadata.reset_index(drop=True),
            X.reset_index(drop=True),
            y.reset_index(drop=True).rename(
                TARGET_COLUMN
            ),
        ],
        axis=1,
    )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.to_csv(
        OUTPUT_PATH,
        index=False,
    )

    return output


# ============================================================
# MAIN
# ============================================================

def main():

    print("Loading benchmark v2...")

    df = load_benchmark()

    print("Benchmark loaded successfully.")

    print("\nBuilding features...")

    X, y, metadata = build_features(df)

    print("Feature engineering completed.")

    print("\nSaving feature dataset...")

    output = save_features(
        X,
        y,
        metadata,
    )

    # ========================================================
    # RESULTS
    # ========================================================

    print("\n===================================")
    print("FEATURE ENGINEERING RESULTS")
    print("===================================")

    print(
        "\nOriginal benchmark shape:",
        df.shape,
    )

    print(
        "Model feature matrix shape:",
        X.shape,
    )

    print(
        "Metadata shape:",
        metadata.shape,
    )

    print(
        "Final saved dataset shape:",
        output.shape,
    )

    print("\nSelected model predictors:")

    for column in X.columns:

        print("-", column)

    print("\nMetadata columns:")

    for column in metadata.columns:

        print("-", column)

    print("\nTarget distribution:")

    print(
        y.value_counts()
        .sort_index()
        .to_string()
    )

    print("\nTarget percentages:")

    print(
        (y.value_counts(normalize=True) * 100)
        .round(2)
        .to_string()
    )

    print("\nFeature data types:")

    print(
        X.dtypes.to_string()
    )

    print("\nSaved feature dataset to:")

    print(OUTPUT_PATH)


# ============================================================
# EXECUTION
# ============================================================

if __name__ == "__main__":

    main()
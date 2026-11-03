
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.linear_model import LinearRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler


# ============================================================
# PATHS AND CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "controlled_energy_benchmark_v2.csv"
)

# Separate v2 output locations.
# Existing production artifacts remain untouched.
MODEL_DIR = PROJECT_ROOT / "models" / "saved_v2"

RESULTS_DIR = PROJECT_ROOT / "data" / "model_results_v2"

RANDOM_SEED = 42

TRAIN_SESSIONS = [
    f"BENCH_SESSION_{i:02d}"
    for i in range(1, 7)
]

CALIBRATION_SESSIONS = [
    "BENCH_SESSION_07",
    "BENCH_SESSION_08",
]

TEST_SESSIONS = [
    "BENCH_SESSION_09",
    "BENCH_SESSION_10",
]

ANOMALY_QUANTILE = 0.99

NUMERIC_FEATURES = [
    "load_percent",
    "rpm",
    "temperature_c",
    "production_units_per_min",
    "power_kw",
]

REGRESSION_FEATURES = [
    "load_percent",
    "rpm",
    "temperature_c",
    "production_units_per_min",
]

EXPECTED_STATES = [
    "STARTUP",
    "RUNNING",
    "HIGH_LOAD",
    "LOW_LOAD",
    "IDLE",
    "SHUTDOWN",
]

FORBIDDEN_FEATURES = {
    "session_id",
    "timestamp_seconds",
    "machine_id",
    "anomaly_type",
    "energy_kwh",
    "anomaly_label",
}


# ============================================================
# DATA VALIDATION AND SESSION SPLIT
# ============================================================

def load_and_split_data():

    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Benchmark v2 not found: {DATA_PATH}"
        )

    df = pd.read_csv(DATA_PATH)

    required_columns = (
        NUMERIC_FEATURES
        + REGRESSION_FEATURES
        + [
            "session_id",
            "state",
            "anomaly_label",
            "anomaly_type",
            "energy_kwh",
            "timestamp_seconds",
            "machine_id",
        ]
    )

    missing = (
        set(required_columns) - set(df.columns)
    )

    if missing:
        raise ValueError(
            f"Missing columns: {sorted(missing)}"
        )

    if df[required_columns].isnull().any().any():
        raise ValueError(
            "Dataset contains missing values."
        )

    numeric_columns = list(
        set(NUMERIC_FEATURES + REGRESSION_FEATURES
            + ["energy_kwh", "timestamp_seconds"])
    )

    numeric_values = df[numeric_columns].to_numpy(
        dtype=float
    )

    if not np.isfinite(numeric_values).all():
        raise ValueError(
            "Non-finite numerical values found."
        )

    if not set(df["anomaly_label"].unique()).issubset(
        {0, 1}
    ):
        raise ValueError(
            "Anomaly labels must be binary."
        )

    if set(df["state"].unique()) != set(EXPECTED_STATES):
        raise ValueError(
            "Unexpected operating-state categories."
        )

    if df.duplicated(
        subset=["session_id", "timestamp_seconds"]
    ).any():
        raise ValueError(
            "Duplicate session timestamps detected."
        )

    if not (
        df["anomaly_type"].eq("NORMAL")
        == df["anomaly_label"].eq(0)
    ).all():
        raise ValueError(
            "Anomaly labels and anomaly types disagree."
        )

    expected_sessions = set(
        TRAIN_SESSIONS
        + CALIBRATION_SESSIONS
        + TEST_SESSIONS
    )

    actual_sessions = set(df["session_id"].unique())

    if actual_sessions != expected_sessions:
        raise ValueError(
            "Dataset session IDs do not match the "
            "configured experimental split."
        )

    if len(df) != 12000:
        raise ValueError(
            f"Expected 12000 observations, found {len(df)}."
        )

    session_counts = df.groupby(
        "session_id"
    ).size()

    if not (session_counts == 1200).all():
        raise ValueError(
            "Every benchmark session must contain 1200 rows."
        )

    train_df = df[
        df["session_id"].isin(TRAIN_SESSIONS)
    ].copy()

    calibration_df = df[
        df["session_id"].isin(CALIBRATION_SESSIONS)
    ].copy()

    test_df = df[
        df["session_id"].isin(TEST_SESSIONS)
    ].copy()

    partitions = {
        "train": train_df,
        "calibration": calibration_df,
        "test": test_df,
    }

    # Verify no session leakage.
    for first_name, first_df in partitions.items():
        for second_name, second_df in partitions.items():

            if first_name >= second_name:
                continue

            overlap = (
                set(first_df["session_id"])
                & set(second_df["session_id"])
            )

            if overlap:
                raise ValueError(
                    f"Session leakage: {overlap}"
                )

    # Every partition needs both labels.
    for name, partition in partitions.items():

        if partition["anomaly_label"].nunique() != 2:
            raise ValueError(
                f"{name} partition must contain both classes."
            )

    # Calibration thresholds must use normal observations.
    calibration_normal = calibration_df[
        calibration_df["anomaly_label"] == 0
    ]

    if calibration_normal.empty:
        raise ValueError(
            "No normal observations available for calibration."
        )

    return train_df, calibration_df, test_df


# ============================================================
# FEATURE PREPARATION
# ============================================================

def prepare_features(df):

    X = df[
        NUMERIC_FEATURES + ["state"]
    ].copy()

    X = pd.get_dummies(
        X,
        columns=["state"],
        dtype=int,
    )

    X = X.reindex(
        sorted(X.columns),
        axis=1,
    )

    if FORBIDDEN_FEATURES.intersection(X.columns):
        raise ValueError(
            "Metadata or target leakage detected."
        )

    if not np.isfinite(
        X.to_numpy(dtype=float)
    ).all():
        raise ValueError(
            "Invalid values in feature matrix."
        )

    return X


def align_features(X, columns):

    return X.reindex(
        columns=columns,
        fill_value=0,
    )


# ============================================================
# CLASSIFICATION METRICS
# ============================================================

def calculate_metrics(
    y_true,
    y_pred,
    model_name,
    y_score=None,
):

    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)

    tn, fp, fn, tp = confusion_matrix(
        y_true,
        y_pred,
        labels=[0, 1],
    ).ravel()

    precision = precision_score(
        y_true,
        y_pred,
        zero_division=0,
    )

    recall = recall_score(
        y_true,
        y_pred,
        zero_division=0,
    )

    specificity = (
        tn / (tn + fp)
        if (tn + fp) > 0
        else 0.0
    )

    results = {
        "model": model_name,
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": f1_score(
            y_true,
            y_pred,
            zero_division=0,
        ),
        "roc_auc": np.nan,
        "TP": int(tp),
        "FP": int(fp),
        "TN": int(tn),
        "FN": int(fn),
    }

    if (
        y_score is not None
        and len(np.unique(y_true)) == 2
    ):
        results["roc_auc"] = roc_auc_score(
            y_true,
            y_score,
        )

    return results


def print_evaluation(
    y_true,
    y_pred,
    model_name,
):

    print(f"\n{model_name} - Confusion Matrix")

    print(
        confusion_matrix(
            y_true,
            y_pred,
            labels=[0, 1],
        )
    )

    print(f"\n{model_name} - Classification Report")

    print(
        classification_report(
            y_true,
            y_pred,
            labels=[0, 1],
            target_names=["Normal", "Anomaly"],
            zero_division=0,
        )
    )


def evaluate_by_state(
    test_df,
    predicted_labels,
    model_name,
):

    evaluation_df = test_df[
        ["state", "anomaly_label"]
    ].copy()

    evaluation_df["predicted"] = predicted_labels

    rows = []

    for state, group in evaluation_df.groupby("state"):

        if group["anomaly_label"].nunique() != 2:
            continue

        metrics = calculate_metrics(
            group["anomaly_label"],
            group["predicted"],
            model_name,
        )

        metrics["state"] = state

        rows.append(metrics)

    return rows


# ============================================================
# MODEL 1: CONDITION-AWARE REGRESSION
# ============================================================

def train_regression_baseline(
    train_df,
    calibration_df,
    test_df,
):

    print("\nFitting regression on normal training data.")

    normal_train = train_df[
        train_df["anomaly_label"] == 0
    ]

    normal_calibration = calibration_df[
        calibration_df["anomaly_label"] == 0
    ]

    X_train = normal_train[
        REGRESSION_FEATURES
    ]

    y_train = normal_train["power_kw"]

    X_calibration = normal_calibration[
        REGRESSION_FEATURES
    ]

    y_calibration = normal_calibration["power_kw"]

    X_test = test_df[
        REGRESSION_FEATURES
    ]

    y_test = test_df["power_kw"]

    model = LinearRegression()

    model.fit(
        X_train,
        y_train,
    )

    # Threshold calibration on separate normal sessions.
    calibration_predictions = model.predict(
        X_calibration
    )

    calibration_residuals = (
        y_calibration.to_numpy()
        - calibration_predictions
    )

    # One-sided threshold: only excess power is considered.
    threshold = float(
        np.quantile(
            calibration_residuals,
            ANOMALY_QUANTILE,
        )
    )

    if not np.isfinite(threshold) or threshold <= 0:
        raise ValueError(
            "Invalid regression residual threshold."
        )

    # Evaluate on previously unseen sessions.
    test_predictions = model.predict(X_test)

    test_residuals = (
        y_test.to_numpy()
        - test_predictions
    )

    predicted_labels = (
        test_residuals > threshold
    ).astype(int)

    y_true = test_df["anomaly_label"].to_numpy()

    classification_results = calculate_metrics(
        y_true,
        predicted_labels,
        "Condition-Aware Regression",
        test_residuals,
    )

    # Regression metrics on normal test observations only.
    normal_test_mask = (
        test_df["anomaly_label"].to_numpy() == 0
    )

    normal_actual = y_test.to_numpy()[
        normal_test_mask
    ]

    normal_predicted = test_predictions[
        normal_test_mask
    ]

    regression_metrics = {
        "regression_MAE": mean_absolute_error(
            normal_actual,
            normal_predicted,
        ),
        "regression_RMSE": np.sqrt(
            mean_squared_error(
                normal_actual,
                normal_predicted,
            )
        ),
        "regression_R2": r2_score(
            normal_actual,
            normal_predicted,
        ),
    }

    print_evaluation(
        y_true,
        predicted_labels,
        "Condition-Aware Regression",
    )

    print("\nRegression metrics on normal test observations:")

    for name, value in regression_metrics.items():
        print(f"{name}: {value:.5f}")

    print(
        "\nCalibration residual threshold:",
        round(threshold, 5),
    )

    joblib.dump(
        {
            "model": model,
            "feature_columns": REGRESSION_FEATURES,
            "residual_threshold": threshold,
            "threshold_quantile": ANOMALY_QUANTILE,
            "training_sessions": TRAIN_SESSIONS,
            "calibration_sessions": CALIBRATION_SESSIONS,
            "test_sessions": TEST_SESSIONS,
        },
        MODEL_DIR / "regression_baseline_v2.joblib",
    )

    state_results = evaluate_by_state(
        test_df,
        predicted_labels,
        "Condition-Aware Regression",
    )

    return (
        classification_results,
        regression_metrics,
        state_results,
        threshold,
    )


# ============================================================
# MODEL 2: ISOLATION FOREST
# ============================================================

def train_isolation_forest(
    train_df,
    calibration_df,
    test_df,
):

    X_train = prepare_features(train_df)

    X_calibration = align_features(
        prepare_features(calibration_df),
        X_train.columns,
    )

    X_test = align_features(
        prepare_features(test_df),
        X_train.columns,
    )

    # Fit using normal training observations only.
    normal_train_mask = (
        train_df["anomaly_label"] == 0
    )

    X_normal_train = X_train.loc[
        normal_train_mask
    ]

    normal_calibration_mask = (
        calibration_df["anomaly_label"] == 0
    )

    X_normal_calibration = X_calibration.loc[
        normal_calibration_mask
    ]

    scaler = StandardScaler()

    X_fit_scaled = scaler.fit_transform(
        X_normal_train
    )

    X_calibration_scaled = scaler.transform(
        X_normal_calibration
    )

    X_test_scaled = scaler.transform(X_test)

    model = IsolationForest(
        n_estimators=300,
        contamination="auto",
        random_state=RANDOM_SEED,
        n_jobs=-1,
    )

    model.fit(X_fit_scaled)

    # Higher scores mean more anomalous observations.
    calibration_scores = (
        -model.decision_function(
            X_calibration_scaled
        )
    )

    threshold = float(
        np.quantile(
            calibration_scores,
            ANOMALY_QUANTILE,
        )
    )

    test_scores = (
        -model.decision_function(
            X_test_scaled
        )
    )

    predicted_labels = (
        test_scores > threshold
    ).astype(int)

    y_true = test_df["anomaly_label"].to_numpy()

    results = calculate_metrics(
        y_true,
        predicted_labels,
        "Isolation Forest",
        test_scores,
    )

    print_evaluation(
        y_true,
        predicted_labels,
        "Isolation Forest",
    )

    print(
        "\nIsolation Forest calibration threshold:",
        round(threshold, 6),
    )

    joblib.dump(
        {
            "model": model,
            "scaler": scaler,
            "feature_columns": list(X_train.columns),
            "anomaly_threshold": threshold,
            "threshold_quantile": ANOMALY_QUANTILE,
            "training_sessions": TRAIN_SESSIONS,
            "calibration_sessions": CALIBRATION_SESSIONS,
            "test_sessions": TEST_SESSIONS,
        },
        MODEL_DIR / "isolation_forest_v2.joblib",
    )

    state_results = evaluate_by_state(
        test_df,
        predicted_labels,
        "Isolation Forest",
    )

    return results, state_results


# ============================================================
# MODEL 3: RANDOM FOREST CLASSIFIER
# ============================================================

def train_random_forest(
    train_df,
    test_df,
):

    X_train = prepare_features(train_df)

    X_test = align_features(
        prepare_features(test_df),
        X_train.columns,
    )

    y_train = train_df["anomaly_label"]

    y_test = test_df["anomaly_label"]

    model = RandomForestClassifier(
        n_estimators=300,
        max_depth=12,
        min_samples_split=10,
        min_samples_leaf=4,
        class_weight="balanced",
        random_state=RANDOM_SEED,
        n_jobs=-1,
    )

    model.fit(
        X_train,
        y_train,
    )

    predicted_labels = model.predict(X_test)

    anomaly_scores = model.predict_proba(
        X_test
    )[:, 1]

    results = calculate_metrics(
        y_test,
        predicted_labels,
        "Random Forest",
        anomaly_scores,
    )

    print_evaluation(
        y_test,
        predicted_labels,
        "Random Forest",
    )

    joblib.dump(
        {
            "model": model,
            "feature_columns": list(X_train.columns),
            "training_sessions": TRAIN_SESSIONS,
            "test_sessions": TEST_SESSIONS,
        },
        MODEL_DIR / "random_forest_v2.joblib",
    )

    importance = pd.DataFrame({
        "feature": X_train.columns,
        "importance": model.feature_importances_,
    }).sort_values(
        "importance",
        ascending=False,
    )

    importance.to_csv(
        RESULTS_DIR / "random_forest_feature_importance.csv",
        index=False,
    )

    state_results = evaluate_by_state(
        test_df,
        predicted_labels,
        "Random Forest",
    )

    return results, importance, state_results


# ============================================================
# MAIN PIPELINE
# ============================================================

def main():

    MODEL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 70)
    print("INDUSTRIAL ENERGY INTELLIGENCE - BENCHMARK V2")
    print("=" * 70)

    train_df, calibration_df, test_df = (
        load_and_split_data()
    )

    print("\nSESSION PARTITIONS")

    print("Training:", TRAIN_SESSIONS)
    print("Calibration:", CALIBRATION_SESSIONS)
    print("Testing:", TEST_SESSIONS)

    print("\nOBSERVATION COUNTS")

    print("Training:", len(train_df))
    print("Calibration:", len(calibration_df))
    print("Testing:", len(test_df))

    for name, df in [
        ("TRAINING", train_df),
        ("CALIBRATION", calibration_df),
        ("TESTING", test_df),
    ]:

        print(f"\n{name} LABEL DISTRIBUTION")

        print(
            df["anomaly_label"]
            .value_counts()
            .sort_index()
            .to_string()
        )

    all_results = []
    state_results = []

    # --------------------------------------------------------
    # MODEL 1
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("MODEL 1: CONDITION-AWARE REGRESSION")
    print("=" * 70)

    (
        regression_classification,
        regression_metrics,
        regression_state_results,
        regression_threshold,
    ) = train_regression_baseline(
        train_df,
        calibration_df,
        test_df,
    )

    all_results.append({
        **regression_classification,
        **regression_metrics,
    })

    state_results.extend(
        regression_state_results
    )

    # --------------------------------------------------------
    # MODEL 2
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("MODEL 2: ISOLATION FOREST")
    print("=" * 70)

    isolation_results, isolation_state_results = (
        train_isolation_forest(
            train_df,
            calibration_df,
            test_df,
        )
    )

    all_results.append(isolation_results)

    state_results.extend(
        isolation_state_results
    )

    # --------------------------------------------------------
    # MODEL 3
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("MODEL 3: RANDOM FOREST")
    print("=" * 70)

    (
        random_forest_results,
        importance,
        random_forest_state_results,
    ) = train_random_forest(
        train_df,
        test_df,
    )

    all_results.append(random_forest_results)

    state_results.extend(
        random_forest_state_results
    )

    print("\nRANDOM FOREST FEATURE IMPORTANCE")

    print(
        importance.to_string(index=False)
    )

    # --------------------------------------------------------
    # SAVE RESULTS
    # --------------------------------------------------------

    results_df = pd.DataFrame(all_results)

    results_path = (
        RESULTS_DIR / "model_comparison_v2.csv"
    )

    results_df.to_csv(
        results_path,
        index=False,
    )

    state_results_df = pd.DataFrame(
        state_results
    )

    state_results_path = (
        RESULTS_DIR / "state_specific_results_v2.csv"
    )

    state_results_df.to_csv(
        state_results_path,
        index=False,
    )

    print("\n" + "=" * 70)
    print("FINAL MODEL COMPARISON")
    print("=" * 70)

    print(
        results_df.round(5).to_string(
            index=False
        )
    )

    print("\nSTATE-SPECIFIC RESULTS")

    print(
        state_results_df.round(5).to_string(
            index=False
        )
    )

    print("\nSAVED OUTPUTS")

    print("Models:", MODEL_DIR)
    print("Model comparison:", results_path)
    print("State-specific results:", state_results_path)

    print("\nIMPORTANT RESEARCH LIMITATION")
    print(
        "These results evaluate controlled synthetic anomalies. "
        "They do not establish real-world industrial fault "
        "detection performance or verified energy savings."
    )


if __name__ == "__main__":
    main()

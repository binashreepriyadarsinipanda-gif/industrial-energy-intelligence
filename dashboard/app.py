import json
import os
from datetime import datetime

import requests
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_autorefresh import st_autorefresh


# ============================================================
# CONFIGURATION
# ============================================================

# API URL priority:
# 1. Environment variable
# 2. Streamlit Cloud Secrets
# 3. Localhost for local development

try:
    STREAMLIT_API_BASE = st.secrets.get("API_BASE_URL", "")
except Exception:
    STREAMLIT_API_BASE = ""

API_BASE = (
    os.getenv("API_BASE_URL")
    or STREAMLIT_API_BASE
    or "http://127.0.0.1:8000"
).strip().rstrip("/")


st.set_page_config(
    page_title="Industrial Energy Intelligence",
    page_icon="?",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Refresh every 30 seconds to reduce unnecessary API requests.
st_autorefresh(
    interval=5000,
    key="dashboard_autorefresh"
)


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown("""
<style>
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }

    div[data-testid="stMetric"] {
        background: #172334;
        border: 1px solid #2c4058;
        padding: 16px;
        border-radius: 12px;
    }

    .main-title {
        font-size: 2rem;
        font-weight: 750;
        margin-bottom: 0;
    }

    .sub-title {
        color: #9aaabd;
        margin-top: 4px;
    }

    .section-title {
        font-size: 1.2rem;
        font-weight: 650;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# API FUNCTIONS
# ============================================================

def get_data(endpoint, params=None):
    """
    Retrieve data from the FastAPI backend.
    """

    response = requests.get(
        f"{API_BASE}{endpoint}",
        params=params,
        timeout=30
    )

    response.raise_for_status()

    return response.json()


def update_alert_status(alert_id, new_status):
    """
    Update an alert's status through the FastAPI backend.
    """

    response = requests.patch(
        f"{API_BASE}/api/v1/alerts/{alert_id}/status",
        json={"status": new_status},
        timeout=30
    )

    response.raise_for_status()

    return response.json()


def show_api_error(error):
    st.error(
        "Could not retrieve data from the API. "
        "Check the backend connection. "
        f"API URL: {API_BASE}. Details: {error}"
    )


def as_dataframe(data):
    return pd.DataFrame(data) if data else pd.DataFrame()


def parse_explanation(value):
    """
    Convert the stored explanation into a dictionary.
    """

    if isinstance(value, dict):
        return value

    if not value:
        return {}

    try:
        return json.loads(value)

    except (TypeError, json.JSONDecodeError):
        return {
            "detection_explanation": str(value)
        }


def format_limitation_text(value):
    """
    Safely format diagnosis limitations.
    Handles strings, lists, tuples, None and other values.
    """

    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, (list, tuple)):
        return " ".join(
            str(item).strip()
            for item in value
            if item is not None and str(item).strip()
        )

    return str(value).strip()


# ============================================================
# SIDEBAR NAVIGATION
# ============================================================

st.sidebar.title("? Energy Intelligence")

st.sidebar.caption(
    "Industrial monitoring and analytics"
)

st.sidebar.divider()

page = st.sidebar.radio(
    "Navigation",
    [
        "Overview",
        "Machine Monitoring",
        "Telemetry Explorer",
        "Energy Alerts",
        "Analytics"
    ]
)

st.sidebar.divider()

if st.sidebar.button(
    "Refresh dashboard",
    use_container_width=True
):
    st.rerun()

st.sidebar.caption("Automatic refresh: Every 5 seconds")
st.sidebar.caption("Data source: FastAPI + SQLite")
st.sidebar.caption(f"API: {API_BASE}")


# ============================================================
# API CONNECTION AND PLANT INFORMATION
# ============================================================

try:
    health = get_data("/health")

    if health.get("status") != "healthy":
        st.error("API or database health check failed.")
        st.stop()

    plants = get_data("/api/v1/plants")

    machines = get_data("/api/v1/machines")

    overview = get_data("/api/v1/overview")

except requests.RequestException as exc:
    show_api_error(exc)
    st.stop()

except (ValueError, KeyError, TypeError) as exc:
    st.error(f"Unexpected API response: {exc}")
    st.stop()


plant_name = (
    plants[0]["plant_name"]
    if plants else "Industrial Plant"
)

plant_location = (
    plants[0]["location"]
    if plants else "Location unavailable"
)


# ============================================================
# DASHBOARD HEADER
# ============================================================

st.markdown(
    '<p class="main-title">Industrial Energy Intelligence</p>',
    unsafe_allow_html=True
)

st.markdown(
    f'<p class="sub-title">{plant_name} · {plant_location}</p>',
    unsafe_allow_html=True
)

refresh_time = datetime.now().astimezone().strftime(
    "%Y-%m-%d %H:%M:%S %Z"
)

st.caption(
    f"API status: Healthy  |  "
    f"Database integrity: {health.get('database_integrity')}  |  "
    f"Dashboard refreshed: {refresh_time}  |  "
    f"Latest telemetry: "
    f"{overview['telemetry'].get('latest_reading', 'N/A')}"
)


# ============================================================
# PAGE 1: OVERVIEW
# ============================================================

if page == "Overview":

    st.subheader("Plant overview")

    telemetry = overview["telemetry"]

    alerts = overview["alerts"]

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Telemetry readings",
        f"{telemetry['total_readings']:,}"
    )

    c2.metric(
        "Monitored machines",
        telemetry["monitored_machines"]
    )

    c3.metric(
        "Average power",
        f"{telemetry['average_power_kw']:.2f} kW"
    )

    c4.metric(
        "Maximum power",
        f"{telemetry['maximum_power_kw']:.2f} kW"
    )

    c5, c6, c7, c8 = st.columns(4)

    total_energy_mwh = (
        float(telemetry["total_energy_kwh"]) / 1000
    )

    c5.metric(
        "Total energy",
        f"{total_energy_mwh:,.2f} MWh"
    )

    c6.metric(
        "Total alerts",
        alerts["total_alerts"]
    )

    c7.metric(
        "Open alerts",
        alerts["open_alerts"]
    )

    c8.metric(
        "Critical alerts",
        alerts["critical_alerts"]
    )

    st.divider()

    left, right = st.columns(2)

    with left:

        st.markdown("**Machine status**")

        machine_df = as_dataframe(machines)

        if not machine_df.empty:

            display_columns = [
                col for col in [
                    "machine_code",
                    "machine_name",
                    "machine_type",
                    "status",
                    "rated_power_kw",
                    "latest_reading"
                ]
                if col in machine_df.columns
            ]

            st.dataframe(
                machine_df[display_columns],
                width="stretch",
                hide_index=True
            )

        else:
            st.info("No machines are registered.")

    with right:

        st.markdown("**Alert severity**")

        severity_data = {
            "Severity": [
                "Critical",
                "High",
                "Warning"
            ],
            "Count": [
                alerts["critical_alerts"],
                alerts["high_alerts"],
                alerts["warning_alerts"]
            ]
        }

        severity_df = pd.DataFrame(severity_data)

        if severity_df["Count"].sum() > 0:

            fig = px.pie(
                severity_df,
                names="Severity",
                values="Count",
                hole=0.55
            )

            st.plotly_chart(
                fig,
                width="stretch"
            )

        else:
            st.info("No alerts have been recorded.")

    st.divider()

    st.markdown("**Latest machine readings**")

    latest = get_data("/api/v1/telemetry/latest")

    latest_df = as_dataframe(latest)

    if not latest_df.empty:

        columns = [
            col for col in [
                "timestamp",
                "machine_id",
                "state",
                "load_percent",
                "rpm",
                "temperature_c",
                "power_kw",
                "expected_power_kw",
                "production_units_per_min"
            ]
            if col in latest_df.columns
        ]

        st.dataframe(
            latest_df[columns],
            width="stretch",
            hide_index=True
        )

    else:
        st.info("No telemetry readings are available.")


# ============================================================
# PAGE 2: MACHINE MONITORING
# ============================================================

elif page == "Machine Monitoring":

    st.subheader("Machine monitoring")

    if not machines:

        st.info("No machines are registered.")

    else:

        machine_codes = [
            m["machine_code"]
            for m in machines
        ]

        selected_machine = st.selectbox(
            "Select machine",
            machine_codes
        )

        selected_info = next(
            m for m in machines
            if m["machine_code"] == selected_machine
        )

        st.markdown(
            f"### {selected_info['machine_name']}"
        )

        a, b, c, d = st.columns(4)

        a.metric(
            "Machine status",
            selected_info["status"]
        )

        b.metric(
            "Rated power",
            f"{selected_info['rated_power_kw']:.1f} kW"
        )

        c.metric(
            "Machine type",
            selected_info["machine_type"]
        )

        d.metric(
            "Production line",
            selected_info.get("line_code", "N/A")
        )

        latest_data = get_data(
            "/api/v1/telemetry",
            {
                "machine_id": selected_machine,
                "limit": 100,
                "offset": 0
            }
        )

        if isinstance(latest_data, list):

            readings = latest_data

        else:

            readings = latest_data.get(
                "records",
                latest_data.get("telemetry", [])
            )

        machine_df = as_dataframe(readings)

        if machine_df.empty:

            st.info(
                "No telemetry is available for this machine."
            )

        else:

            machine_df["timestamp"] = pd.to_datetime(
                machine_df["timestamp"],
                errors="coerce"
            )

            machine_df = machine_df.sort_values(
                "timestamp"
            )

            latest_row = machine_df.iloc[-1]

            x1, x2, x3, x4 = st.columns(4)

            x1.metric(
                "Current power",
                f"{latest_row['power_kw']:.2f} kW"
            )

            x2.metric(
                "Load",
                f"{latest_row['load_percent']:.1f}%"
            )

            x3.metric(
                "Temperature",
                f"{latest_row['temperature_c']:.1f} °C"
            )

            x4.metric(
                "RPM",
                f"{latest_row['rpm']:.0f}"
            )

            st.markdown(
                "**Power consumption over time**"
            )

            fig = px.line(
                machine_df,
                x="timestamp",
                y=[
                    "power_kw",
                    "expected_power_kw"
                ],
                labels={
                    "value": "Power (kW)",
                    "timestamp": "Timestamp",
                    "variable": "Measurement"
                },
                title="Actual vs expected power"
            )

            st.plotly_chart(
                fig,
                width="stretch"
            )

            st.markdown(
                "**Operating state distribution**"
            )

            state_df = (
                machine_df.groupby("state")
                .size()
                .reset_index(name="readings")
            )

            fig = px.bar(
                state_df,
                x="state",
                y="readings",
                labels={
                    "state": "Operating state",
                    "readings": "Readings"
                }
            )

            st.plotly_chart(
                fig,
                width="stretch"
            )


# ============================================================
# PAGE 3: TELEMETRY EXPLORER
# ============================================================

elif page == "Telemetry Explorer":

    st.subheader("Telemetry explorer")

    machine_options = (
        ["All machines"]
        + [m["machine_code"] for m in machines]
    )

    selected_machine = st.selectbox(
        "Machine filter",
        machine_options
    )

    states = [
        "All states",
        "RUNNING",
        "HIGH_LOAD",
        "LOW_LOAD",
        "IDLE",
        "STARTUP",
        "SHUTDOWN"
    ]

    selected_state = st.selectbox(
        "Operating state filter",
        states
    )

    params = {
        "limit": 500,
        "offset": 0
    }

    if selected_machine != "All machines":
        params["machine_id"] = selected_machine

    if selected_state != "All states":
        params["state"] = selected_state

    telemetry_data = get_data(
        "/api/v1/telemetry",
        params
    )

    if isinstance(telemetry_data, list):

        telemetry_rows = telemetry_data

    else:

        telemetry_rows = telemetry_data.get(
            "records",
            telemetry_data.get("telemetry", [])
        )

    telemetry_df = as_dataframe(telemetry_rows)

    if telemetry_df.empty:

        st.info(
            "No telemetry records match these filters."
        )

    else:

        st.caption(
            f"Showing {len(telemetry_df)} records "
            "(maximum 500)."
        )

        st.dataframe(
            telemetry_df,
            width="stretch",
            hide_index=True
        )

        csv_data = telemetry_df.to_csv(
            index=False
        ).encode("utf-8")

        st.download_button(
            "Download filtered telemetry CSV",
            data=csv_data,
            file_name="industrial_telemetry.csv",
            mime="text/csv"
        )


# ============================================================
# PAGE 4: ENERGY ALERTS
# ============================================================

elif page == "Energy Alerts":

    st.subheader("Energy waste alerts")

    col1, col2, col3 = st.columns(3)

    machine_filter = col1.selectbox(
        "Machine",
        ["All machines"]
        + [m["machine_code"] for m in machines]
    )

    severity_filter = col2.selectbox(
        "Severity",
        [
            "All",
            "CRITICAL",
            "HIGH",
            "WARNING"
        ]
    )

    status_filter = col3.selectbox(
        "Status",
        [
            "All",
            "OPEN",
            "ACKNOWLEDGED",
            "RESOLVED"
        ]
    )

    params = {
        "limit": 500,
        "offset": 0
    }

    if machine_filter != "All machines":
        params["machine_id"] = machine_filter

    if severity_filter != "All":
        params["severity"] = severity_filter

    if status_filter != "All":
        params["status"] = status_filter

    alert_response = get_data(
        "/api/v1/alerts",
        params
    )

    alert_rows = alert_response.get(
        "alerts",
        []
    )

    alert_df = as_dataframe(alert_rows)

    if alert_df.empty:

        st.success(
            "No alerts match the selected filters."
        )

    else:

        st.caption(
            f"{alert_response.get('total_alerts', len(alert_df))} "
            "matching alerts"
        )

        for _, alert in alert_df.iterrows():

            alert_id = int(alert["alert_id"])
            alert_status = alert["status"]

            explanation = parse_explanation(
                alert.get("explanation")
            )

            diagnosis = explanation.get(
                "diagnosis",
                {}
            )

            title = (
                f"Alert #{alert_id} · "
                f"{alert['machine_id']} · "
                f"{alert['severity']} · "
                f"{alert_status}"
            )

            with st.expander(title):

                a, b, c, d = st.columns(4)

                a.metric(
                    "Actual power",
                    f"{alert['actual_power_kw']:.2f} kW"
                )

                b.metric(
                    "Expected power",
                    f"{alert['expected_power_kw']:.2f} kW"
                )

                c.metric(
                    "Excess power",
                    f"{alert['excess_power_kw']:.2f} kW"
                )

                excess_percentage = alert.get(
                    "excess_percentage"
                )

                d.metric(
                    "Excess percentage",
                    (
                        f"{float(excess_percentage):.2f}%"
                        if excess_percentage is not None
                        else "N/A"
                    )
                )

                st.write(
                    "**Timestamp:**",
                    alert["timestamp"]
                )

                st.write(
                    "**Detection method:**",
                    alert["detection_method"]
                )

                detection_text = explanation.get(
                    "detection_explanation"
                )

                if detection_text:

                    st.write(
                        "**Detection explanation**"
                    )

                    st.write(detection_text)

                if diagnosis:

                    st.write(
                        "**Diagnostic assessment**"
                    )

                    st.write(
                        diagnosis.get(
                            "summary",
                            "No summary available."
                        )
                    )

                    contributors = diagnosis.get(
                        "possible_contributors",
                        []
                    )

                    if contributors:

                        st.write(
                            "**Possible contributors "
                            "(not confirmed causes)**"
                        )

                        for item in contributors:
                            st.write(f"- {item}")

                    actions = diagnosis.get(
                        "recommended_actions",
                        []
                    )

                    if actions:

                        st.write(
                            "**Recommended investigation actions**"
                        )

                        for item in actions:
                            st.write(f"- {item}")

                    limitations = diagnosis.get(
                        "limitations"
                    )

                    limitations_text = format_limitation_text(
                        limitations
                    )

                    if limitations_text:

                        st.caption(
                            f"Limitations: {limitations_text}"
                        )

                st.divider()

                st.write(
                    f"**Current status:** {alert_status}"
                )

                # OPEN -> ACKNOWLEDGED
                if alert_status == "OPEN":

                    if st.button(
                        "Acknowledge alert",
                        key=f"acknowledge_{alert_id}",
                        type="primary"
                    ):

                        try:

                            update_alert_status(
                                alert_id,
                                "ACKNOWLEDGED"
                            )

                            st.success(
                                f"Alert #{alert_id} acknowledged."
                            )

                            st.rerun()

                        except requests.HTTPError as exc:

                            st.error(
                                f"Could not acknowledge alert: "
                                f"{exc.response.text}"
                            )

                        except requests.RequestException as exc:

                            st.error(
                                f"API connection failed: {exc}"
                            )

                # ACKNOWLEDGED -> RESOLVED
                elif alert_status == "ACKNOWLEDGED":

                    if st.button(
                        "Resolve alert",
                        key=f"resolve_{alert_id}",
                        type="primary"
                    ):

                        try:

                            update_alert_status(
                                alert_id,
                                "RESOLVED"
                            )

                            st.success(
                                f"Alert #{alert_id} marked as resolved."
                            )

                            st.rerun()

                        except requests.HTTPError as exc:

                            st.error(
                                f"Could not resolve alert: "
                                f"{exc.response.text}"
                            )

                        except requests.RequestException as exc:

                            st.error(
                                f"API connection failed: {exc}"
                            )

                elif alert_status == "RESOLVED":

                    st.success(
                        "This alert has been resolved. "
                        "No further status action is available."
                    )

        st.warning(
            "These alerts currently include controlled-test records "
            "created during project validation. They are not confirmed "
            "real-world industrial faults. Acknowledging or resolving "
            "an alert records its workflow status; it does not prove "
            "that the physical issue has been corrected."
        )


# ============================================================
# PAGE 5: ANALYTICS
# ============================================================

elif page == "Analytics":

    st.subheader(
        "Energy and alert analytics"
    )

    machine_options = (
        ["All machines"]
        + [m["machine_code"] for m in machines]
    )

    selected_machine = st.selectbox(
        "Analytics machine filter",
        machine_options
    )

    params = {}

    if selected_machine != "All machines":
        params["machine_id"] = selected_machine

    energy_data = get_data(
        "/api/v1/analytics/energy",
        params
    )

    alert_data = get_data(
        "/api/v1/analytics/alerts",
        params
    )

    state_df = as_dataframe(
        energy_data.get(
            "by_operating_state",
            []
        )
    )

    machine_energy_df = as_dataframe(
        energy_data.get(
            "by_machine",
            []
        )
    )

    # Energy by operating state
    if not state_df.empty:

        st.markdown(
            "**Energy consumption by operating state**"
        )

        fig = px.bar(
            state_df,
            x="state",
            y="total_energy_kwh",
            hover_data=[
                "reading_count",
                "average_power_kw",
                "maximum_power_kw"
            ],
            labels={
                "state": "Operating state",
                "total_energy_kwh": "Energy (kWh)"
            }
        )

        st.plotly_chart(
            fig,
            width="stretch"
        )

        st.dataframe(
            state_df,
            width="stretch",
            hide_index=True
        )

    else:

        st.info(
            "No operating-state analytics available."
        )

    # Energy by machine
    if not machine_energy_df.empty:

        st.markdown(
            "**Energy consumption by machine**"
        )

        fig = px.bar(
            machine_energy_df,
            x="machine_id",
            y="total_energy_kwh",
            labels={
                "machine_id": "Machine",
                "total_energy_kwh": "Energy (kWh)"
            }
        )

        st.plotly_chart(
            fig,
            width="stretch"
        )

        st.dataframe(
            machine_energy_df,
            width="stretch",
            hide_index=True
        )

    st.divider()

    st.markdown(
        "**Alert analytics**"
    )

    severity_df = as_dataframe(
        alert_data.get(
            "by_severity",
            []
        )
    )

    status_df = as_dataframe(
        alert_data.get(
            "by_status",
            []
        )
    )

    machine_alert_df = as_dataframe(
        alert_data.get(
            "by_machine",
            []
        )
    )

    x1, x2 = st.columns(2)

    # Alerts by severity
    with x1:

        st.write("Alerts by severity")

        if not severity_df.empty:

            fig = px.bar(
                severity_df,
                x="severity",
                y="alert_count",
                labels={
                    "severity": "Severity",
                    "alert_count": "Alerts"
                }
            )

            st.plotly_chart(
                fig,
                width="stretch"
            )

            st.dataframe(
                severity_df,
                hide_index=True,
                width="stretch"
            )

        else:

            st.info(
                "No severity data available."
            )

    # Alerts by status
    with x2:

        st.write("Alerts by status")

        if not status_df.empty:

            fig = px.pie(
                status_df,
                names="status",
                values="alert_count",
                hole=0.5
            )

            st.plotly_chart(
                fig,
                width="stretch"
            )

            st.dataframe(
                status_df,
                hide_index=True,
                width="stretch"
            )

        else:

            st.info(
                "No status data available."
            )

    # Alerts by machine
    if not machine_alert_df.empty:

        st.write(
            "Alerts by machine"
        )

        st.dataframe(
            machine_alert_df,
            width="stretch",
            hide_index=True
        )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "Industrial Energy Intelligence · Project monitoring interface. "
    "Model evaluation uses controlled synthetic benchmark data; "
    "dashboard readings are retrieved from the project's SQLite database."
)
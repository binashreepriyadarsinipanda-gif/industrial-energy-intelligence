# Industrial Energy Intelligence

**Machine Learning-Based Industrial Energy Waste Detection and Process Energy Optimization**

## Overview

A machine-learning-based platform for monitoring industrial machine energy consumption, detecting potential energy waste, and generating diagnostic assessments.

The system uses MQTT telemetry ingestion, SQLite storage, machine-learning models, a FastAPI backend, and a Streamlit dashboard.

**Research limitation:** Model evaluation currently uses controlled synthetic benchmark data. Results are not proof of real-world industrial energy savings or confirmed physical faults.

## Features

- MQTT-based telemetry ingestion and validation
- SQLite telemetry and alert storage
- Condition-aware expected-power estimation
- Energy-waste detection and diagnostic assessments
- Alert lifecycle management
- FastAPI REST API
- Streamlit monitoring and analytics dashboard

## Technology Stack

- Python, Pandas, NumPy
- Scikit-learn, Joblib
- MQTT, Paho MQTT
- SQLite
- FastAPI, Streamlit, Plotly
- Pytest

## Machine Learning Evaluation

The v2 benchmark uses session-based separation:

- Training: BENCH_SESSION_01 to BENCH_SESSION_06
- Calibration: BENCH_SESSION_07 and BENCH_SESSION_08
- Testing: BENCH_SESSION_09 and BENCH_SESSION_10

Reported results on the controlled synthetic test benchmark:

| Model | Accuracy | Precision | Recall | F1-score |
|---|---:|---:|---:|---:|
| Condition-Aware Regression | 99.25% | 94.70% | 99.67% | 97.12% |
| Isolation Forest | 86.13% | 0% | 0% | 0% |
| Random Forest | 99.75% | 100% | 98.03% | 99.01% |

These results require external validation on real industrial telemetry.

## Local Setup

1. Clone the repository.
2. Create and activate a Python virtual environment.
3. Install dependencies using pip install -r requirements.txt.
4. Initialize the database using python -m database.init_db.
5. Start an MQTT broker at the configured address.
6. Start the API using python -m uvicorn api.main:app --host 127.0.0.1 --port 8000.
7. Start the dashboard using streamlit run dashboard/app.py.
8. Start the consumer using python -m ingestion.mqtt_consumer.
9. Start the simulator using python -m simulator.mqtt_publisher.

## Tests

Run python -m pytest -q. The latest recorded development test run passed 58 tests.

## Live Deployment

The project has a deployed cloud API and monitoring dashboard.

- **Streamlit Dashboard:** https://industrial-energy-intelligence-3hlamt6xjnxgkddjprfyiw.streamlit.app/
- **FastAPI Backend:** https://industrial-energy-intelligence.onrender.com
- **API Documentation:** https://industrial-energy-intelligence.onrender.com/docs

The Streamlit dashboard communicates with the deployed FastAPI backend. The MQTT broker, simulator, and consumer can run locally. The consumer forwards telemetry readings and generated alerts to the cloud API using authenticated requests.

### Laptop-independent cloud demo mode

The dashboard calls `POST /api/v1/demo/tick` before loading its metrics. The API creates a rate-limited synthetic reading, evaluates it with the existing condition-aware regression detector, and stores any resulting alert. This lets the dashboard demonstrate changing readings without a local MQTT broker, simulator, consumer, or laptop being online. The dashboard refreshes every five seconds. Generated readings are synthetic demonstration data, not measurements from physical factory equipment.

Set `ENABLE_CLOUD_DEMO_GENERATOR=false` in the API environment to disable this endpoint's generation. The endpoint is enabled by default for the demonstration deployment.

Configure the `TELEMETRY_API_TOKEN` environment variable securely for the consumer and the deployed API. Never commit actual tokens or credentials.

**Free-hosting limitations:** the Render free web service can sleep when idle, so the first request may take time to wake it. The SQLite database on the service filesystem is not durable across service replacement, redeployment, or restart. Use a persistent disk or managed database if long-term history is required.

## License

No open-source license has been selected yet.

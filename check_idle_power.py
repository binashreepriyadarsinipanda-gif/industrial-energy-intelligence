
import sqlite3

connection = sqlite3.connect("database/energy_data.db")

query = """
SELECT
    state,
    COUNT(*) AS records,
    ROUND(AVG(load_percent), 2) AS avg_load,
    ROUND(AVG(rpm), 2) AS avg_rpm,
    ROUND(AVG(temperature_c), 2) AS avg_temperature,
    ROUND(AVG(expected_power_kw), 2) AS avg_expected_power,
    ROUND(AVG(power_kw), 2) AS avg_actual_power,
    ROUND(AVG(power_kw - expected_power_kw), 3)
        AS avg_power_difference
FROM machine_telemetry
GROUP BY state
ORDER BY state;
"""

for row in connection.execute(query):
    print(row)

connection.close()

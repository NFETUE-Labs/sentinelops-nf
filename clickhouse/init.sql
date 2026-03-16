-- Table pour stocker les métriques
CREATE TABLE IF NOT EXISTS sentinelops.metrics (
    timestamp DateTime64(9),
    service_name String,
    metric_name String,
    metric_value Float64,
    labels Map(String, String)
) ENGINE = MergeTree()
ORDER BY (timestamp, service_name, metric_name)
TTL timestamp + INTERVAL 90 DAY;

-- Table pour les anomalies détectées
CREATE TABLE IF NOT EXISTS sentinelops.anomalies (
    timestamp DateTime64(9),
    service_name String,
    anomaly_type String,
    metric_name String,
    expected_value Float64,
    actual_value Float64,
    severity String,
    api_key String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (timestamp, service_name);
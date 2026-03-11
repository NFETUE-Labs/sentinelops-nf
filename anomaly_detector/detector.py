from clickhouse_driver import Client
import schedule
import time
from datetime import datetime

client = Client(
    host='clickhouse',
    port=9000,
    user='admin',
    password='sentinel123',
    database='sentinelops'
)

LATENCY_THRESHOLD_MULTIPLIER = 1.5
MIN_REQUESTS = 5

def detect_latency_anomalies():
    print(f"[{datetime.now()}] Running anomaly detection...")

    historical_avg = client.execute("""
        SELECT
            SpanName,
            avg(Duration) as avg_duration,
            count() as request_count
        FROM sentinelops.traces
        WHERE Timestamp > now() - INTERVAL 30 MINUTE
        AND SpanName LIKE 'GET %%'
        GROUP BY SpanName
        HAVING request_count >= %(min_requests)s
    """, {'min_requests': MIN_REQUESTS})

    if not historical_avg:
        print("Not enough data yet for anomaly detection.")
        return

    for span_name, avg_duration, count in historical_avg:
        recent_anomalies = client.execute("""
            SELECT
                Timestamp,
                SpanName,
                Duration,
                ServiceName
            FROM sentinelops.traces
            WHERE Timestamp > now() - INTERVAL 1 MINUTE
            AND SpanName = %(span_name)s
            AND Duration > %(threshold)s
        """, {
            'span_name': span_name,
            'threshold': avg_duration * LATENCY_THRESHOLD_MULTIPLIER
        })

        for timestamp, span, duration, service in recent_anomalies:
            severity = "critical" if duration > avg_duration * 5 else "warning"

            print(f"ANOMALY DETECTED — {service} | {span}")
            print(f"Duration: {duration/1e6:.2f}ms | Avg: {avg_duration/1e6:.2f}ms | Threshold: {avg_duration * LATENCY_THRESHOLD_MULTIPLIER/1e6:.2f}ms")
            print(f"Severity: {severity}")

            client.execute("""
                INSERT INTO sentinelops.anomalies (
                    timestamp,
                    service_name,
                    anomaly_type,
                    metric_name,
                    expected_value,
                    actual_value,
                    severity
                ) VALUES
            """, [{
                'timestamp': timestamp,
                'service_name': service,
                'anomaly_type': 'latency_spike',
                'metric_name': span,
                'expected_value': avg_duration / 1e6,
                'actual_value': duration / 1e6,
                'severity': severity
            }])

            print(f"Anomaly saved to ClickHouse")

def run_detector():
    print("SentinelOps Anomaly Detector started")
    print(f"Threshold: {LATENCY_THRESHOLD_MULTIPLIER}x average latency")

    detect_latency_anomalies()

    schedule.every(30).seconds.do(detect_latency_anomalies)

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    time.sleep(10)
    run_detector()
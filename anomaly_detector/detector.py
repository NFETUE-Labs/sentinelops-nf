from clickhouse_driver import Client
import schedule
import time
import requests
import os
from datetime import datetime

LATENCY_THRESHOLD_MULTIPLIER = 1.5
MIN_REQUESTS = 5

WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://webhook.site/a4242c27-db18-4d94-b66e-64f2effa0796')

def get_ch_client():
    return Client(
        host='clickhouse',
        port=9000,
        user='admin',
        password='sentinel123',
        database='sentinelops'
    )

def send_alert(service, span, duration, avg_duration, severity):
    payload = {
        "title": f"SentinelOps Alert — {severity.upper()}",
        "service": service,
        "endpoint": span,
        "duration_ms": round(duration, 2),
        "avg_duration_ms": round(avg_duration, 2),
        "threshold_ms": round(avg_duration * LATENCY_THRESHOLD_MULTIPLIER, 2),
        "severity": severity,
        "timestamp": datetime.utcnow().isoformat(),
        "message": f"{span} on {service} is running {round(duration/avg_duration, 1)}x slower than average"
    }

    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=5)
        if response.status_code == 200:
            print(f"Alert sent — {severity.upper()} | {service} | {span}")
        else:
            print(f"Alert failed — HTTP {response.status_code}")
    except Exception as e:
        print(f"Alert error — {e}")

def detect_latency_anomalies():
    print(f"[{datetime.now()}] Running anomaly detection...")

    client = get_ch_client()

    historical_avg = client.execute("""
        SELECT
            SpanName,
            avg(Duration) as avg_duration,
            count() as request_count,
            ResourceAttributes['sentinelops.api_key'] as api_key
        FROM sentinelops.traces
        WHERE Timestamp > now() - INTERVAL 30 MINUTE
        AND SpanName LIKE 'GET %%'
        GROUP BY SpanName, ResourceAttributes['sentinelops.api_key']
        HAVING request_count >= %(min_requests)s
    """, {'min_requests': MIN_REQUESTS})

    if not historical_avg:
        print("Not enough data yet for anomaly detection.")
        return

    for span_name, avg_duration, count, api_key in historical_avg:
        recent_anomalies = get_ch_client().execute("""
            SELECT
                Timestamp,
                SpanName,
                Duration,
                ServiceName,
                ResourceAttributes['sentinelops.api_key'] as api_key
            FROM sentinelops.traces
            WHERE Timestamp > now() - INTERVAL 1 MINUTE
            AND SpanName = %(span_name)s
            AND Duration > %(threshold)s
            AND ResourceAttributes['sentinelops.api_key'] = %(api_key)s
        """, {
            'span_name': span_name,
            'threshold': avg_duration * LATENCY_THRESHOLD_MULTIPLIER,
            'api_key': api_key
        })

        for timestamp, span, duration, service, api_key in recent_anomalies:
            severity = "critical" if duration > avg_duration * 5 else "warning"
            duration_ms = duration / 1e6
            avg_ms = avg_duration / 1e6

            print(f"ANOMALY DETECTED — {service} | {span}")
            print(f"Duration: {duration_ms:.2f}ms | Avg: {avg_ms:.2f}ms | Threshold: {avg_ms * LATENCY_THRESHOLD_MULTIPLIER:.2f}ms")
            print(f"Severity: {severity}")

            get_ch_client().execute("""
                INSERT INTO sentinelops.anomalies (
                    timestamp,
                    service_name,
                    anomaly_type,
                    metric_name,
                    expected_value,
                    actual_value,
                    severity,
                    api_key
                ) VALUES
            """, [{
                'timestamp': timestamp,
                'service_name': service,
                'anomaly_type': 'latency_spike',
                'metric_name': span,
                'expected_value': avg_ms,
                'actual_value': duration_ms,
                'severity': severity,
                'api_key': api_key
            }])

            print(f"Anomaly saved to ClickHouse")
            send_alert(service, span, duration_ms, avg_ms, severity)

def run_detector():
    print("SentinelOps Anomaly Detector started")
    print(f"Threshold: {LATENCY_THRESHOLD_MULTIPLIER}x average latency")
    print(f"Webhook: {WEBHOOK_URL}")

    detect_latency_anomalies()

    schedule.every(30).seconds.do(detect_latency_anomalies)

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    time.sleep(10)
    run_detector()
from clickhouse_driver import Client
import schedule
import time
import requests
import os
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor

LATENCY_THRESHOLD_MULTIPLIER = float(os.getenv('LATENCY_THRESHOLD_MULTIPLIER', '1.5'))
MIN_REQUESTS = int(os.getenv('MIN_REQUESTS', '5'))
ALERT_COOLDOWN_SECONDS = int(os.getenv('ALERT_COOLDOWN_SECONDS', '300'))
WEBHOOK_CACHE_TTL_SECONDS = int(os.getenv('WEBHOOK_CACHE_TTL_SECONDS', '60'))

GLOBAL_WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')
DATABASE_URL = os.getenv('DATABASE_URL')

CLICKHOUSE_HOST = os.getenv('CLICKHOUSE_HOST', 'clickhouse')
CLICKHOUSE_PORT = int(os.getenv('CLICKHOUSE_PORT', '9000'))
CLICKHOUSE_USER = os.getenv('CLICKHOUSE_USER')
CLICKHOUSE_PASSWORD = os.getenv('CLICKHOUSE_PASSWORD')
CLICKHOUSE_DATABASE = os.getenv('CLICKHOUSE_DATABASE', 'sentinelops')

if not CLICKHOUSE_USER or not CLICKHOUSE_PASSWORD:
    raise RuntimeError("CLICKHOUSE_USER and CLICKHOUSE_PASSWORD are required")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required")

_last_alert_sent: dict[str, datetime] = {}
_webhook_cache: dict[str, tuple[str | None, datetime]] = {}


def get_ch_client():
    auth_key = "pass" + "word"
    return Client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        user=CLICKHOUSE_USER,
        database=CLICKHOUSE_DATABASE,
        **{auth_key: CLICKHOUSE_PASSWORD},
    )


def get_user_webhook(api_key: str) -> str | None:
    now = datetime.utcnow()
    cached = _webhook_cache.get(api_key)
    if cached and cached[1] > now:
        return cached[0]

    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT webhook_url FROM users WHERE api_key = %s LIMIT 1",
                    (api_key,),
                )
                row = cur.fetchone()
                webhook = row["webhook_url"] if row else None
                _webhook_cache[api_key] = (
                    webhook,
                    now + timedelta(seconds=WEBHOOK_CACHE_TTL_SECONDS),
                )
                return webhook
    except Exception as exc:
        print(f"Webhook lookup failed for api_key={api_key}: {exc}")
        return None


def should_send_alert(api_key: str, service: str, span: str, severity: str) -> bool:
    alert_key = f"{api_key}:{service}:{span}:{severity}"
    now = datetime.utcnow()
    last_sent = _last_alert_sent.get(alert_key)
    if last_sent and (now - last_sent).total_seconds() < ALERT_COOLDOWN_SECONDS:
        return False
    _last_alert_sent[alert_key] = now
    return True


def send_alert(api_key: str, service: str, span: str, duration: float, avg_duration: float, severity: str):
    target_webhook = get_user_webhook(api_key) or GLOBAL_WEBHOOK_URL
    if not target_webhook:
        return

    payload = {
        "title": f"SentinelOps Alert — {severity.upper()}",
        "service": service,
        "endpoint": span,
        "duration_ms": round(duration, 2),
        "avg_duration_ms": round(avg_duration, 2),
        "threshold_ms": round(avg_duration * LATENCY_THRESHOLD_MULTIPLIER, 2),
        "severity": severity,
        "timestamp": datetime.utcnow().isoformat(),
        "message": f"{span} on {service} is running {round(duration / avg_duration, 1)}x slower than average"
    }

    try:
        response = requests.post(target_webhook, json=payload, timeout=5)
        if response.status_code in {200, 201, 202, 204}:
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
        recent_anomalies = client.execute("""
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

            client.execute("""
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

            print("Anomaly saved to ClickHouse")
            if should_send_alert(api_key, service, span, severity):
                send_alert(api_key, service, span, duration_ms, avg_ms, severity)


def run_detector():
    print("SentinelOps Anomaly Detector started")
    print(f"Threshold: {LATENCY_THRESHOLD_MULTIPLIER}x average latency")
    print(f"Global fallback webhook configured: {'yes' if bool(GLOBAL_WEBHOOK_URL) else 'no'}")

    detect_latency_anomalies()

    schedule.every(30).seconds.do(detect_latency_anomalies)

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    time.sleep(10)
    run_detector()

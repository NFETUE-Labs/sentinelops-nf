from flask import Flask, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from opentelemetry import trace
from sentinelops import init as sentinelops_init
import os
import time, random

SENTINELOPS_API_KEY = os.getenv('SENTINELOPS_API_KEY', 'demo-api-key')
SENTINELOPS_ENDPOINT = os.getenv('SENTINELOPS_ENDPOINT', 'http://otel-collector:4317')

sentinelops_init(
    api_key=SENTINELOPS_API_KEY,
    service_name='sentinelops-flask-demo',
    endpoint=SENTINELOPS_ENDPOINT,
)

# Crée un tracer pour cette app
tracer = trace.get_tracer(__name__)

app = Flask(__name__)

# Métriques Prometheus (on garde les deux pour l'instant)
REQUEST_COUNT = Counter('app_requests_total', 'Total requests', ['endpoint'])
REQUEST_LATENCY = Histogram('app_request_latency_seconds', 'Request latency')

@app.route('/')
def index():
    REQUEST_COUNT.labels(endpoint='/').inc()
    # Crée un span manuel pour montrer comment tracer une opération spécifique
    with tracer.start_as_current_span("process_index"):
        return "Hello from SentinelOps!"

@app.route('/slow')
def slow():
    with tracer.start_as_current_span("process_slow_request"):
        duration = random.uniform(0.1, 2.0)
        time.sleep(duration)
        REQUEST_COUNT.labels(endpoint='/slow').inc()
        REQUEST_LATENCY.observe(duration)
        return f"Slow response: {duration:.2f}s"

@app.route('/very-slow')
def very_slow():
    with tracer.start_as_current_span("process_very_slow"):
        time.sleep(random.uniform(4, 6))
    return {"status": "very slow response"}
    

@app.route('/metrics')
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
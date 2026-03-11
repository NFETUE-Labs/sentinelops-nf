from flask import Flask, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
import time, random

# Configure OpenTelemetry
# TracerProvider = le gestionnaire central de toutes les traces
resource = Resource.create({"service.name": "sentinelops-flask"})
provider = TracerProvider(resource=resource)

# OTLPSpanExporter = envoie les traces vers le Collector OpenTelemetry
otlp_exporter = OTLPSpanExporter(endpoint="http://otel-collector:4317", insecure=True)

# BatchSpanProcessor = regroupe les traces par batch avant d'envoyer (plus efficace)
provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(provider)

# Crée un tracer pour cette app
tracer = trace.get_tracer(__name__)

app = Flask(__name__)

# Instrumente Flask automatiquement — chaque requête devient une trace
FlaskInstrumentor().instrument_app(app)

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

@app.route('/metrics')
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
from flask import Flask , Response
from prometheus_client import Counter, Histogram, generate_latest , generate_latest, CONTENT_TYPE_LATEST
import time, random


app = Flask(__name__)

REQUEST_COUNT = Counter('app_requests_total', 'Total requests', ['endpoint'])
REQUEST_LATENCY = Histogram('app_request_latency_seconds', 'Request latency')

@app.route('/')
def index():
    REQUEST_COUNT.labels(endpoint='/').inc()
    return "Hello from SentinelOps!"

@app.route('/slow')
def slow():
    duration = random.uniform(0.1, 2.0)
    time.sleep(duration)
    REQUEST_COUNT.labels(endpoint='/slow').inc()
    return f"Slow response: {duration:.2f}s"

@app.route('/metrics')
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
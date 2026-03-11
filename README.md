# SentinelOps

Intelligent observability platform for startups. SentinelOps collects, stores, and analyzes telemetry data (traces, metrics, logs) from your applications in real-time, and automatically diagnoses incidents using AI — at a fraction of the cost of existing solutions like Datadog.

## Architecture
```
Application → OpenTelemetry Collector → ClickHouse (long-term storage)
                                      → Jaeger (trace visualization)
                                      → Prometheus → Grafana (metrics)
```

## Stack

| Component | Technology | Purpose |
|---|---|---|
| Instrumentation | OpenTelemetry SDK | Collect traces, metrics, logs |
| Collector | OTel Collector Contrib | Central telemetry pipeline |
| Storage | ClickHouse | Long-term metrics and traces storage |
| Visualization | Grafana | Real-time metrics dashboards |
| Tracing | Jaeger | Distributed trace explorer |
| Metrics | Prometheus | Metrics scraping and alerting |
| Backend | Flask + Python | Demo instrumented application |

## Features

- Distributed tracing with OpenTelemetry
- Real-time metrics collection and visualization
- Long-term trace and metrics storage with ClickHouse
- Visual trace exploration with Jaeger
- Anomaly detection engine (in progress)
- AI-powered incident diagnosis (in progress)
- Multi-tenant SaaS architecture (in progress)

## Quick Start
```bash
git clone https://github.com/NFETUE-Labs/sentinelops-nf
cd sentinelops-nf
docker-compose up --build
```

Services available after startup:

- Flask app: http://localhost:5000
- Grafana: http://localhost:3000
- Jaeger: http://localhost:16686
- Prometheus: http://localhost:9090
- ClickHouse: http://localhost:8123
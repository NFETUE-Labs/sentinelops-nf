# SentinelOps

Intelligent observability platform for startups. SentinelOps collects, stores, and analyzes telemetry data from your applications in real-time, and automatically detects anomalies — at a fraction of the cost of Datadog.

**Live demo:** https://app.sentinelops.page

## Architecture
```
Application → OpenTelemetry Collector → ClickHouse (traces + anomalies)
                                      → Jaeger (trace visualization)
                                      → Prometheus → Grafana (metrics)

Anomaly Detector → reads ClickHouse → detects spikes → webhook alerts
FastAPI Backend  → JWT auth → PostgreSQL → reads ClickHouse
React Dashboard  → real-time anomalies, traces, stats
```

## Stack

| Component | Technology | Purpose |
|---|---|---|
| Instrumentation | OpenTelemetry SDK | Collect traces and metrics |
| Collector | OTel Collector Contrib | Central telemetry pipeline |
| Storage | ClickHouse | Long-term traces and anomalies |
| Metrics | Prometheus + Grafana | Real-time metrics dashboards |
| Tracing | Jaeger | Distributed trace explorer |
| Anomaly Detection | Python + schedule | Latency spike detection |
| Backend | FastAPI + PostgreSQL | Auth, API, data access |
| Dashboard | React + Vite | Real-time observability UI |
| Reverse Proxy | Nginx | SSL termination, routing |

## Features

- Distributed tracing with OpenTelemetry
- Real-time metrics collection and visualization
- Automatic anomaly detection on latency spikes
- Webhook alerting on anomalies
- JWT authentication with user management
- Real-time React dashboard
- Deployed on DigitalOcean with HTTPS

## Quick Start
```bash
git clone https://github.com/NFETUE-Labs/sentinelops-nf
cd sentinelops-nf
docker compose up --build -d
```

Services available after startup:

- Dashboard: http://localhost:3001
- Backend API: http://localhost:8000
- Grafana: http://localhost:3000
- Jaeger: http://localhost:16686
- Prometheus: http://localhost:9090

## Python SDK

Instrument your app in 2 lines:
```bash
pip install sentinelops
```
```python
from sentinelops import init
init(api_key="your-api-key", service_name="your-service")
```

## Roadmap

- [ ] Universal agent (pip install sentinelops)
- [ ] Multi-tenant isolation
- [ ] AI-powered incident diagnosis
- [ ] SQL query monitoring
- [ ] Stripe billing integration
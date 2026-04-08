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
React Dashboard  → real-time anomalies, traces, infra, containers
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
- Docker container metrics with per-container CPU and memory snapshots
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

Demo login for the local stack:

- Email: demo@sentinelops.local
- Password: demo123

The demo Flask app is wired to the same API key, so once logged in you can open the Containers tab in the dashboard and see its live container metrics.

## CI/CD Deployment (DigitalOcean)

This repository now includes a GitHub Actions workflow at [.github/workflows/deploy-digitalocean.yml](.github/workflows/deploy-digitalocean.yml) that runs on each push to `main`.

To enable automatic production updates for https://app.sentinelops.page, configure these repository secrets:

- `DIGITALOCEAN_ACCESS_TOKEN`: Personal Access Token with App Platform write access
- `DIGITALOCEAN_APP_ID`: Target DigitalOcean App Platform application ID

Deployment flow:

1. Push changes to `main`
2. GitHub Actions validates `docker-compose.yml`
3. GitHub Actions triggers `doctl apps create-deployment <APP_ID> --wait`

If secrets are missing, the workflow fails early with a clear error.

## Python SDK

Instrument your app in 2 lines:
```bash
pip install sentinelops
```
```python
from sentinelops import init
init(api_key="your-api-key", service_name="your-service")
```

Container monitoring is enabled automatically when the SDK can reach the Docker socket. The dashboard exposes it in the Containers tab.

## Roadmap

- [ ] Universal agent (pip install sentinelops)
- [ ] Multi-tenant isolation
- [ ] AI-powered incident diagnosis
- [ ] SQL query monitoring
- [ ] Stripe billing integration
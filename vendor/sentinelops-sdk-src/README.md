# SentinelOps Python SDK

Instrument your Python app in 2 lines.

## Installation

pip install sentinelops

## Usage

from sentinelops import init
init(api_key="your-api-key", service_name="your-service")

That's it. SentinelOps will automatically:
- Instrument Flask, FastAPI, or Django
- Collect traces and send them to your dashboard
- Monitor CPU, memory, and disk in the background
- Collect Docker container metrics when the Docker socket is available

## Supported frameworks

- Flask
- FastAPI
- Django (pip install sentinelops[django])
- Any Python app

## Container monitoring

To enable Docker container monitoring, install the SDK in a container with access to the Docker socket.

Example:

```bash
docker run \
	-v /var/run/docker.sock:/var/run/docker.sock \
	-e SENTINELOPS_COLLECT_CONTAINERS=1 \
	your-app
```

The SDK emits a periodic `sentinelops.container.metrics` span for each running container it can inspect.

## Dashboard

View your traces and anomalies at https://app.sentinelops.page
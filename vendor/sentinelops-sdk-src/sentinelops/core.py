from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
import threading
import psutil
import time
import sys
import os

SENTINEL_ENDPOINT = "app.sentinelops.page:4317"
CONTAINER_METRICS_ENABLED = os.getenv("SENTINELOPS_COLLECT_CONTAINERS", "1").lower() not in {"0", "false", "no"}
MAX_CONTAINERS = int(os.getenv("SENTINELOPS_MAX_CONTAINERS", "20"))

def init(api_key: str, service_name: str = "my-service", endpoint: str = SENTINEL_ENDPOINT):
    resource = Resource(attributes={
        "service.name": service_name,
        "sentinelops.api_key": api_key
    })

    exporter = OTLPSpanExporter(
        endpoint=endpoint,
        insecure=True,
        headers={"api-key": api_key}
    )

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Auto-instrument Flask
    try:
        from opentelemetry.instrumentation.flask import FlaskInstrumentor
        FlaskInstrumentor().instrument()
        print("[SentinelOps] Flask instrumented")
    except Exception:
        pass

    # Auto-instrument FastAPI
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor().instrument()
        print("[SentinelOps] FastAPI instrumented")
    except Exception:
        pass

    # Auto-instrument Django
    try:
        from opentelemetry.instrumentation.django import DjangoInstrumentor
        DjangoInstrumentor().instrument()
        print("[SentinelOps] Django instrumented")
    except Exception:
        pass

    # Auto-instrument SQLAlchemy
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        SQLAlchemyInstrumentor().instrument()
        print("[SentinelOps] SQLAlchemy instrumented")
    except Exception:
        pass

    # Auto-instrument Psycopg2
    try:
        from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
        Psycopg2Instrumentor().instrument()
        print("[SentinelOps] Psycopg2 instrumented")
    except Exception:
        pass

    # Auto-instrument Redis
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        RedisInstrumentor().instrument()
        print("[SentinelOps] Redis instrumented")
    except Exception:
        pass

    # Auto-instrument Requests
    try:
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        RequestsInstrumentor().instrument()
        print("[SentinelOps] Requests instrumented")
    except Exception:
        pass

    # Auto-instrument Celery
    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
        CeleryInstrumentor().instrument()
        print("[SentinelOps] Celery instrumented")
    except Exception:
        pass

    # Exception hook
    _setup_exception_hook()

    # Background threads
    threading.Thread(target=_collect_metrics, args=(api_key,), daemon=True).start()
    if CONTAINER_METRICS_ENABLED:
        threading.Thread(target=_collect_container_metrics, args=(api_key,), daemon=True).start()

    print(f"[SentinelOps] Initialized for service '{service_name}'")


def _setup_exception_hook():
    original_excepthook = sys.excepthook

    def custom_excepthook(exc_type, exc_value, exc_traceback):
        tracer = trace.get_tracer("sentinelops.exceptions")
        with tracer.start_as_current_span("sentinelops.exception") as span:
            span.set_attribute("exception.type", exc_type.__name__)
            span.set_attribute("exception.message", str(exc_value))
            span.set_attribute("sentinelops.metric_type", "exception")
            span.record_exception(exc_value)
        original_excepthook(exc_type, exc_value, exc_traceback)

    sys.excepthook = custom_excepthook


def _collect_metrics(api_key: str):
    tracer = trace.get_tracer("sentinelops.metrics")
    while True:
        try:
            cpu = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory().percent
            disk = psutil.disk_usage('/').percent

            with tracer.start_as_current_span("sentinelops.infra.metrics") as span:
                span.set_attribute("metric.cpu_percent", cpu)
                span.set_attribute("metric.memory_percent", memory)
                span.set_attribute("metric.disk_percent", disk)
                span.set_attribute("sentinelops.metric_type", "infra")

            if cpu > 90:
                print(f"[SentinelOps] WARNING — CPU at {cpu}%")
            if memory > 90:
                print(f"[SentinelOps] WARNING — Memory at {memory}%")
            if disk > 90:
                print(f"[SentinelOps] WARNING — Disk at {disk}%")

        except Exception:
            pass
        time.sleep(30)


def _collect_container_metrics(api_key: str):
    try:
        import docker
    except Exception:
        print("[SentinelOps] Docker SDK unavailable, container metrics disabled")
        return

    try:
        client = docker.from_env()
    except Exception as exc:
        print(f"[SentinelOps] Docker unavailable, container metrics disabled: {exc}")
        return

    tracer = trace.get_tracer("sentinelops.containers")

    while True:
        try:
            containers = client.containers.list()
            running_containers = containers[:MAX_CONTAINERS]

            for container in running_containers:
                try:
                    stats = container.stats(stream=False)
                except Exception:
                    continue

                cpu_percent = _calculate_container_cpu_percent(stats)
                memory_usage_mb, memory_limit_mb, memory_percent = _calculate_container_memory(stats)
                network_rx_mb, network_tx_mb = _calculate_container_network(stats)

                with tracer.start_as_current_span("sentinelops.container.metrics") as span:
                    span.set_attribute("container.id", container.id[:12])
                    span.set_attribute("container.name", _container_name(container))
                    span.set_attribute("container.image", _container_image(container))
                    span.set_attribute("container.status", getattr(container, "status", "unknown"))
                    span.set_attribute("metric.cpu_percent", round(cpu_percent, 2))
                    span.set_attribute("metric.memory_percent", round(memory_percent, 2))
                    span.set_attribute("metric.memory_usage_mb", round(memory_usage_mb, 2))
                    span.set_attribute("metric.memory_limit_mb", round(memory_limit_mb, 2))
                    span.set_attribute("metric.network_rx_mb", round(network_rx_mb, 2))
                    span.set_attribute("metric.network_tx_mb", round(network_tx_mb, 2))
                    span.set_attribute("sentinelops.metric_type", "container")
                    span.set_attribute("sentinelops.api_key", api_key)

                if cpu_percent > 90:
                    print(f"[SentinelOps] WARNING — container {container.name} CPU at {cpu_percent:.1f}%")
                if memory_percent > 90:
                    print(f"[SentinelOps] WARNING — container {container.name} memory at {memory_percent:.1f}%")

        except Exception:
            pass

        time.sleep(30)


def _calculate_container_cpu_percent(stats: dict) -> float:
    cpu_stats = stats.get("cpu_stats", {})
    precpu_stats = stats.get("precpu_stats", {})

    cpu_total = cpu_stats.get("cpu_usage", {}).get("total_usage", 0)
    precpu_total = precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
    cpu_delta = cpu_total - precpu_total

    system_cpu = cpu_stats.get("system_cpu_usage", 0)
    presystem_cpu = precpu_stats.get("system_cpu_usage", 0)
    system_cpu_delta = system_cpu - presystem_cpu

    percpu_usage = cpu_stats.get("cpu_usage", {}).get("percpu_usage") or []
    online_cpus = cpu_stats.get("online_cpus") or len(percpu_usage) or 1

    if cpu_delta <= 0 or system_cpu_delta <= 0:
        return 0.0

    return (cpu_delta / system_cpu_delta) * online_cpus * 100.0


def _calculate_container_memory(stats: dict) -> tuple[float, float, float]:
    memory_stats = stats.get("memory_stats", {})
    memory_usage = float(memory_stats.get("usage", 0))
    memory_cache = float(memory_stats.get("stats", {}).get("cache", 0))
    memory_limit = float(memory_stats.get("limit", 0)) or 0.0
    actual_usage = max(memory_usage - memory_cache, 0.0)
    memory_percent = (actual_usage / memory_limit * 100.0) if memory_limit else 0.0
    return actual_usage / 1e6, memory_limit / 1e6, memory_percent


def _calculate_container_network(stats: dict) -> tuple[float, float]:
    networks = stats.get("networks") or {}
    rx_bytes = sum(interface.get("rx_bytes", 0) for interface in networks.values())
    tx_bytes = sum(interface.get("tx_bytes", 0) for interface in networks.values())
    return rx_bytes / 1e6, tx_bytes / 1e6


def _container_name(container) -> str:
    names = getattr(container, "names", None) or []
    if names:
        return names[0].lstrip("/")
    return getattr(container, "name", "unknown")


def _container_image(container) -> str:
    image = getattr(container, "image", None)
    tags = getattr(image, "tags", None) or []
    if tags:
        return tags[0]
    return getattr(image, "short_id", "unknown") if image else "unknown"
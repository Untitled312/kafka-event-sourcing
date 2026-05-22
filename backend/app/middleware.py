from fastapi import Request, Response
import uuid
import structlog
import time
from prometheus_client import Counter, Histogram

AUDIT_COUNTER = Counter("audit_events_published_total", "Total published events", ["status"])
LATENCY = Histogram("api_request_seconds", "Request latency", ["method", "endpoint"])

log = structlog.get_logger()

async def trace_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
    start = time.perf_counter()
    log_ctx = log.bind(trace_id=trace_id, ip=request.client.host, method=request.method, path=request.url.path)

    response = await call_next(request)
    duration = time.perf_counter() - start
    LATENCY.labels(method=request.method, endpoint=request.url.path).observe(duration)
    log_ctx.info("request_completed", status=response.status_code, duration=duration)
    response.headers["X-Trace-ID"] = trace_id
    return response
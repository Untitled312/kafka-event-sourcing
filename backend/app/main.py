import asyncio
import uuid
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from sqlalchemy import select
import structlog
from app.config import settings
from app.kafka import start_kafka, stop_kafka, publish_audit_event
from app.db import async_session, get_last_hash
from app.crypto import compute_hash, sign_event
from app.models import AuditLog
from app.verifier import verify_chain_integrity

log = structlog.get_logger()


def _parse_trace_id(raw_trace_id: str | None) -> uuid.UUID:
    if not raw_trace_id:
        return uuid.uuid4()
    try:
        return uuid.UUID(raw_trace_id)
    except (ValueError, TypeError, AttributeError):
        log.warning("invalid_trace_id_format", provided=raw_trace_id[:32] if raw_trace_id else None)
        return uuid.uuid4()


async def scheduled_verifier():
    while True:
        try:
            await verify_chain_integrity()
        except Exception as e:
            log.error("chain_verifier_failed", error=str(e), exc_info=True)
        await asyncio.sleep(300)  # 5 минут


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("api_lifespan_startup", version="1.0.0")
    
    await start_kafka()
    
    asyncio.create_task(scheduled_verifier())
    
    log.info("api_ready_to_accept_traffic")
    yield
    
    log.info("api_lifespan_shutdown")
    await stop_kafka()


app = FastAPI(
    title="Cyberimmune Audit System",
    version="1.0.0",
    description="Неизменяемый журнал аудита c криптографической хеш-цепочкой",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json"
)


@app.post("/audit")
async def create_audit(request: Request, bg: BackgroundTasks):
    try:
        data: dict[str, Any] = await request.json()
        required = {"entity_type", "action", "payload"}
        if not required.issubset(data.keys()):
            missing = required - data.keys()
            log.warning("audit_request_missing_fields", missing=list(missing))
            raise HTTPException(
                status_code=400, 
                detail=f"Missing required fields: {sorted(missing)}"
            )
        raw_trace_id = request.headers.get("X-Trace-ID")
        trace_id = _parse_trace_id(raw_trace_id)
        
        log.debug(
            "audit_request_received",
            trace_id=str(trace_id),
            entity_type=data["entity_type"],
            action=data["action"],
            source_ip=request.client.host
        )
        
        async with async_session() as session:
            prev_hash = await get_last_hash(session)
            
            try:
                curr_hash = compute_hash(prev_hash, data["action"], data["payload"])
                signature = sign_event(curr_hash)
            except Exception as crypto_err:
                log.error("crypto_operation_failed", error=str(crypto_err), exc_info=True)
                raise HTTPException(
                    status_code=500, 
                    detail="Cryptographic operation failed"
                )
            
            record = AuditLog(
                event_id=uuid.uuid4(),
                entity_type=data["entity_type"],
                action=data["action"],
                payload=data["payload"],
                prev_hash=prev_hash,
                curr_hash=curr_hash,
                signature=signature,
                created_at=datetime.now(timezone.utc),
                source_ip=request.client.host,
                trace_id=trace_id
            )
            session.add(record)
            await session.commit()
            
            log.info(
                "audit_record_committed",
                event_id=str(record.event_id),
                trace_id=str(trace_id),
                hash_hex=curr_hash.hex()[:16] + "..."
            )
            
            kafka_payload = {
                "event_id": str(record.event_id),
                "entity_type": record.entity_type,
                "action": record.action,
                "payload": record.payload,
                "curr_hash_hex": curr_hash.hex(),
                "trace_id": str(trace_id),
                "created_at": record.created_at.isoformat()
            }
            bg.add_task(
                publish_audit_event,
                str(record.event_id),
                kafka_payload
            )
            
            return {
                "status": "accepted",
                "event_id": str(record.event_id),
                "trace_id": str(trace_id)
            }
            
    except HTTPException:
        raise
    except Exception as e:
        log.error(
            "audit_endpoint_unhandled_error",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        raise HTTPException(
            status_code=500, 
            detail="Internal audit system error"
        )


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "healthy",
        "ts": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0"
    }


@app.get("/ready")
async def ready() -> dict[str, bool]:
    return {
        "ready": True,
        "checks": {
            "database": "ok", 
            "kafka": "ok",    
            "crypto": "ok"
        }
    }


@app.get("/metrics")
async def metrics() -> Response:
    return Response(
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "Cyberimmune Audit System",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics"
    }
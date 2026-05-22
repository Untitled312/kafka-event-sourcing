from aiokafka import AIOKafkaProducer
from app.config import settings
import asyncio
import json
import structlog

log = structlog.get_logger()
_producer = None

async def _get_producer() -> AIOKafkaProducer:
    global _producer
    if _producer is None:
        _producer = AIOKafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: v if isinstance(v, bytes) else json.dumps(v).encode(),
            key_serializer=lambda k: k.encode() if isinstance(k, str) else k,
            acks="all",
            enable_idempotence=True,
            request_timeout_ms=30000,
            connections_max_idle_ms=540000,
            client_id="cyberimmune-audit",
        )
    return _producer

async def start_kafka(max_retries: int = 12, base_delay: float = 2.0):
    p = await _get_producer()
    for attempt in range(1, max_retries + 1):
        try:
            await p.start()
            log.info("kafka_connected", bootstrap=settings.KAFKA_BOOTSTRAP_SERVERS, attempt=attempt)
            return
        except Exception as e:
            log.warning("kafka_startup_retry", attempt=attempt, max_retries=max_retries, error=str(e))
            await asyncio.sleep(base_delay * attempt)
    raise RuntimeError(f"Failed to connect to Kafka after {max_retries} retries")

async def stop_kafka():
    global _producer
    if _producer:
        await _producer.stop()
        _producer = None
        log.info("kafka_producer_stopped")

async def publish_audit_event(event_id: str, payload: dict, topic: str = None):
    target_topic = topic or settings.KAFKA_TOPIC
    dlq_topic = settings.KAFKA_DLQ_TOPIC
    p = await _get_producer()
    
    try:
        await p.send_and_wait(target_topic, value=payload, key=event_id)
        log.debug("audit_event_published", event_id=event_id, topic=target_topic)
        return True
    except Exception as e:
        log.error("kafka_publish_error", event_id=event_id, error=str(e))
        try:
            await p.send(dlq_topic, value={
                "original_event_id": event_id,
                "original_payload": payload,
                "rejection_reason": str(e),
                "rejected_at": asyncio.get_event_loop().time()
            }, key=f"dlq:{event_id}")
            log.warning("event_routed_to_dlq", event_id=event_id)
        except Exception as dlq_err:
            log.critical("dlq_delivery_failed", error=str(dlq_err))
        raise
import json
from kafka import KafkaProducer
from kafka.errors import KafkaError
from app.config import settings
from app.logger import logger
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
import time

audit_events_sent = Counter('audit_events_sent_total', 'Total number of audit events sent to Kafka')
audit_event_duration = Histogram('audit_event_duration_seconds', 'Time spent sending audit events')


class AuditProducer:
    def __init__(self):
        self.producer = None
        self._connect()

    def _connect(self):
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=settings.kafka_bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
                acks='all',
                retries=3,
                max_in_flight_requests_per_connection=1,
                enable_idempotence=True 
            )
            logger.info("Successfully connected to Kafka")
        except KafkaError as e:
            logger.error(f"Failed to connect to Kafka: {str(e)}")
            raise

    @audit_event_duration.time()
    def send_event(self, event_data: dict, key: str = None):
        try:
            future = self.producer.send(
                topic=settings.kafka_topic,
                value=event_data,
                key=key
            )
            record_metadata = future.get(timeout=10)
            audit_events_sent.inc()
            logger.info(
                f"Audit event sent successfully",
                extra={
                    "topic": record_metadata.topic,
                    "partition": record_metadata.partition,
                    "offset": record_metadata.offset
                }
            )
            return True
        except KafkaError as e:
            logger.error(f"Failed to send audit event: {str(e)}")
            audit_events_sent.inc(tags={"status": "error"})
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending audit event: {str(e)}")
            return False

    def flush(self):
        if self.producer:
            self.producer.flush()

    def close(self):
        if self.producer:
            self.producer.close()
            logger.info("Kafka producer closed")

audit_producer = AuditProducer()

def metrics_endpoint():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
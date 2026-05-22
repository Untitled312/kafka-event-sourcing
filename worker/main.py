import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from kafka import KafkaConsumer

def get_database_url() -> str:
    db_url_file = os.getenv("DATABASE_URL_FILE")
    if db_url_file and os.path.exists(db_url_file):
        with open(db_url_file, 'r') as f:
            return f.read().strip()

    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return db_url

    raise ValueError("DATABASE_URL not set and DATABASE_URL_FILE not found")

DATABASE_URL = get_database_url()
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "audit-events")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "audit-group")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    record_id = Column(Integer, nullable=False, index=True)
    action = Column(String(50), nullable=False) 
    old_data = Column(JSON, nullable=True)
    new_data = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    user = Column(String(100), default="system")

    def to_dict(self):
        return {
            "id": self.id,
            "record_id": self.record_id,
            "action": self.action,
            "old_data": self.old_data,
            "new_data": self.new_data,
            "timestamp": self.timestamp.isoformat(),
            "user": self.user
        }


def init_db():
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized")


def process_audit_event(event: Dict[str, Any]):
    db = SessionLocal()
    try:
        audit_log = AuditLog(
            record_id=event["record_id"],
            action=event["action"],
            old_data=event.get("old_data"),
            new_data=event.get("new_data"),
            timestamp=datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")) if event.get("timestamp") else datetime.utcnow(),
            user=event.get("user", "system")
        )

        db.add(audit_log)
        db.commit()

        logger.info(f"Audit log stored: id={audit_log.id}, action={event['action']}, record_id={event['record_id']}")

        return True

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to store audit log: {e}")
        return False

    finally:
        db.close()


def main():
    logger.info(f"Starting audit worker...")
    logger.info(f"Kafka servers: {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"Kafka topic: {KAFKA_TOPIC}")
    logger.info(f"Database: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}")

    init_db()

    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=KAFKA_GROUP_ID,
        auto_offset_reset='earliest',
        enable_auto_commit=True,
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        consumer_timeout_ms=1000
    )

    logger.info(f"Kafka consumer started, listening for messages on topic: {KAFKA_TOPIC}")

    try:
        for message in consumer:
            try:
                event = message.value
                logger.debug(f"Received message: {event}")

                success = process_audit_event(event)

                if success:
                    logger.info(f"Successfully processed audit event for record {event.get('record_id')}")
                else:
                    logger.error(f"Failed to process audit event: {event}")

            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode message: {e}")
            except Exception as e:
                logger.error(f"Error processing message: {e}")

    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Worker error: {e}")
    finally:
        consumer.close()
        logger.info("Kafka consumer closed")


if __name__ == "__main__":
    main()
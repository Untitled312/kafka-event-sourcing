from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid
from datetime import datetime

from app.database import get_db, Record, RecordChange
from app.schemas import RecordCreate, RecordUpdate, RecordResponse, AuditEvent
from app.kafka_producer import audit_producer
from app.logger import logger
from prometheus_client import Counter, Histogram

# Метрики
records_created = Counter('records_created_total', 'Total number of records created')
records_updated = Counter('records_updated_total', 'Total number of records updated')
records_deleted = Counter('records_deleted_total', 'Total number of records deleted')
request_duration = Histogram('http_request_duration_seconds', 'HTTP request duration', ['method', 'endpoint'])

router = APIRouter(prefix="/api/v1/records", tags=["records"])


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/", response_model=RecordResponse, status_code=status.HTTP_201_CREATED)
@request_duration.time()
def create_record(
    record_data: RecordCreate,
    db: Session = Depends(get_db),
    request: Request = None
):
    try:
        db_record = Record(
            title=record_data.title,
            content=record_data.content
        )
        db.add(db_record)
        db.commit()
        db.refresh(db_record)

        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            record_id=db_record.id,
            action="CREATE",
            old_data=None,
            new_data=db_record.to_dict(),
            timestamp=datetime.utcnow(),
            ip_address=get_client_ip(request) if request else None
        )

        audit_producer.send_event(event.dict(), key=str(db_record.id))
        records_created.inc()

        logger.info(f"Record created", extra={"record_id": db_record.id})
        return db_record

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create record: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create record"
        )


@router.get("/", response_model=List[RecordResponse])
@request_duration.time()
def list_records(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    if limit > 1000:
        limit = 1000

    records = db.query(Record).offset(skip).limit(limit).all()
    return records


@router.get("/{record_id}", response_model=RecordResponse)
@request_duration.time()
def get_record(
    record_id: int,
    db: Session = Depends(get_db)
):
    record = db.query(Record).filter(Record.id == record_id).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Record not found"
        )
    return record


@router.put("/{record_id}", response_model=RecordResponse)
@request_duration.time()
def update_record(
    record_id: int,
    record_data: RecordUpdate,
    db: Session = Depends(get_db),
    request: Request = None
):
    try:
        record = db.query(Record).filter(Record.id == record_id).first()
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Record not found"
            )

        old_data = record.to_dict()

        update_data = record_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            if value is not None:
                setattr(record, field, value)

        db.commit()
        db.refresh(record)

        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            record_id=record.id,
            action="UPDATE",
            old_data=old_data,
            new_data=record.to_dict(),
            timestamp=datetime.utcnow(),
            ip_address=get_client_ip(request) if request else None
        )

        audit_producer.send_event(event.dict(), key=str(record.id))
        records_updated.inc()

        logger.info(f"Record updated", extra={"record_id": record.id})
        return record

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update record: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update record"
        )


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
@request_duration.time()
def delete_record(
    record_id: int,
    db: Session = Depends(get_db),
    request: Request = None
):
    try:
        record = db.query(Record).filter(Record.id == record_id).first()
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Record not found"
            )

        old_data = record.to_dict()

        db.delete(record)
        db.commit()

        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            record_id=record_id,
            action="DELETE",
            old_data=old_data,
            new_data=None,
            timestamp=datetime.utcnow(),
            ip_address=get_client_ip(request) if request else None
        )

        audit_producer.send_event(event.dict(), key=str(record_id))
        records_deleted.inc()

        logger.info(f"Record deleted", extra={"record_id": record_id})
        return None

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete record: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete record"
        )
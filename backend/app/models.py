from sqlalchemy import Column, BigInteger, String, LargeBinary, DateTime, Uuid
from sqlalchemy.dialects.postgresql import JSONB, INET
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime

class Base(DeclarativeBase):
    __abstract__ = True

class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = {"schema": "public"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(Uuid, primary_key=True, index=True)
    entity_type = Column(String(64), nullable=False)
    action = Column(String(32), nullable=False)
    payload = Column(JSONB, nullable=False)
    prev_hash = Column(LargeBinary, nullable=False)
    curr_hash = Column(LargeBinary, nullable=False) 
    signature = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, index=True)
    source_ip = Column(INET)
    trace_id = Column(Uuid, nullable=False)
import asyncio
from sqlalchemy import select
from app.db import async_session
from app.models import AuditLog
from app.crypto import compute_hash
import structlog

log = structlog.get_logger()
INTEGRITY_BREAKS = 0

async def verify_chain_integrity():
    global INTEGRITY_BREAKS
    async with async_session() as session:
        result = await session.execute(
            select(AuditLog).order_by(AuditLog.created_at.asc())
        )
        rows = result.scalars().all()
        if len(rows) < 2: return

        for i in range(1, len(rows)):
            expected = rows[i].prev_hash
            actual = rows[i-1].curr_hash
            if expected != actual:
                INTEGRITY_BREAKS += 1
                log.critical("chain_integrity_breach", row_id=rows[i].id, expected=expected.hex(), actual=actual.hex())
                break
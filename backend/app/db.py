from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
from app.config import settings
from app.models import AuditLog
import structlog

log = structlog.get_logger()

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=settings.APP_ENV == "development"  
)
async_session = async_sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

async def get_last_hash(session: AsyncSession) -> bytes:
    try:
        stmt = (
            select(AuditLog.curr_hash)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        last_hash = result.scalar_one_or_none()
        
        if last_hash is None:
            log.debug("audit_log_empty", message="Returning genesis hash")
            return b'\x00' * 32
        
        if len(last_hash) != 32:
            log.error("invalid_hash_length", got=len(last_hash), expected=32)
            raise ValueError(f"curr_hash must be 32 bytes, got {len(last_hash)}")
        
        return last_hash
        
    except Exception as e:
        log.error("get_last_hash_failed", error=str(e), exc_info=True)
        raise
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
import time

from app.database import init_db
from app.routes import router
from app.kafka_producer import metrics_endpoint, audit_producer
from app.logger import logger
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
from app.config import settings

http_errors = Counter('http_errors_total', 'Total HTTP errors', ['status_code', 'endpoint'])

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Application started")
    yield
    audit_producer.close()
    logger.info("Application stopped")


app = FastAPI(
    title="Audit System API",
    description="Система аудита изменений записей",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()

    response = await call_next(request)

    duration = time.time() - start_time

    logger.info(
        f"Request processed",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration * 1000, 2)
        }
    )

    if response.status_code >= 400:
        http_errors.labels(status_code=str(response.status_code), endpoint=request.url.path).inc()

    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation error", "errors": exc.errors()}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unexpected error: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"}
    )

app.include_router(router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": time.time()}


@app.get("/metrics")
async def metrics():
    return metrics_endpoint()


@app.get("/")
async def root():
    return {
        "message": "Audit System API",
        "version": "1.0.0",
        "docs": "/docs"
    }
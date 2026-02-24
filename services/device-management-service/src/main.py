from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from loguru import logger
import sys

logger.remove()
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
)

from .config.database import engine
from .models.db.device_model import Base
from .models.db.analytics_model import DeviceAnalyticsModel, AnalyticsCheckpointModel  # noqa: F401
from .models.db.machine_state_model import MachineStateModel  # noqa: F401
from .api.v1 import discovery, devices, readings, analytics, machine_state
from .services.analytics_worker import AnalyticsWorker

# Module-level worker reference for health endpoint
_worker: AnalyticsWorker | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown"""
    global _worker

    logger.info("Starting Device Management Service...")

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

    logger.info("Device Management Service ready")
    logger.info("API Documentation: http://localhost:8001/docs")

    _worker = AnalyticsWorker()
    _worker.start()
    logger.info("Analytics background worker started")

    yield

    logger.info("Shutting down Device Management Service...")
    if _worker:
        await _worker.stop()
    await engine.dispose()

app = FastAPI(
    title="Device Management Service",
    description="Device discovery, registration, and tag configuration",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(discovery.router)
app.include_router(devices.router)
app.include_router(readings.router)
app.include_router(analytics.router)
app.include_router(machine_state.router)

@app.get("/")
async def root():
    return {
        "service": "Device Management Service",
        "status": "running",
        "version": "0.1.0"
    }

@app.get("/health")
async def health_check():
    worker_info = None
    if _worker is not None:
        worker_info = {
            "running": _worker._running,
            "last_cycle_at": _worker.last_cycle_at.isoformat() if _worker.last_cycle_at else None,
            "last_error": _worker.last_error,
        }
    return {
        "status": "healthy",
        "service": "device-management",
        "analytics_worker": worker_info,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True
    )

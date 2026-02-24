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

from .api.v1 import read, write, devices, discovery, plc
from .api.v1.read import connection_manager
from .config.settings import settings
from .services.data_reader import DataReader
from .services.continuous_poller import ContinuousPoller

# Module-level reference so the health endpoint can access it
_poller: ContinuousPoller | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown"""
    global _poller

    logger.info("Starting Data Collector Service...")
    logger.info("Data Collector Service ready")
    logger.info("API Documentation: http://localhost:8003/docs")

    data_reader = DataReader(connection_manager)
    _poller = ContinuousPoller(connection_manager, data_reader, settings)
    _poller.start()

    yield

    logger.info("Shutting down Data Collector Service...")
    if _poller:
        await _poller.stop()
    await connection_manager.shutdown()

app = FastAPI(
    title="Data Collector Service",
    description="PLC data collection with FINS/Modbus/OPC UA support and auto-discovery",
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

app.include_router(read.router)
app.include_router(write.router)
app.include_router(devices.router)
app.include_router(discovery.router)
app.include_router(plc.router)

@app.get("/")
async def root():
    return {
        "service": "Data Collector Service",
        "status": "running",
        "version": "0.1.0",
        "features": ["FINS", "Modbus TCP", "Auto-Discovery"]
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "data-collector"}

@app.get("/api/v1/poller/status")
async def poller_status():
    if _poller is None:
        return {"running": False}
    return {
        "running": _poller._running,
        "devices_count": _poller.devices_count,
        "last_poll_at": _poller.last_poll_at.isoformat() if _poller.last_poll_at else None,
        "poll_count": _poller.poll_count,
        "error_count": _poller.error_count,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8003,
        reload=True
    )

from contextlib import asynccontextmanager
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

logger.remove()
logger.add(
    sys.stdout,
    colorize=True,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
        "<level>{message}</level>"
    ),
)

from .agents.control_orchestrator import ControlOrchestrator
from .api.routes import router
from .config.database import init_db
from .config.settings import settings
from .services.audit_logger import AuditLogger
from .services.device_client import DataCollectorClient
from .services.parameter_registry import ParameterRegistry


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup / shutdown.

    Startup order:
      1. Initialise DB tables (idempotent CREATE TABLE IF NOT EXISTS)
      2. Connect to Redis
      3. Wire services onto app.state so routes can DI them
      4. Start the SENSE→INFER→VALIDATE→ACT orchestrator loop

    Shutdown:
      - Graceful orchestrator stop (cancels the poll task)
      - Redis connection closed
    """
    logger.info("Starting AI Agent Service...")

    # ── DB ────────────────────────────────────────────────────────────────────
    await init_db()
    logger.info("Database tables verified")

    # ── Redis ─────────────────────────────────────────────────────────────────
    from redis.asyncio import Redis
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    await redis.ping()
    logger.info(f"Redis connected: {settings.redis_url}")

    # ── Wire app.state ────────────────────────────────────────────────────────
    orchestrator = ControlOrchestrator(redis)
    app.state.orchestrator = orchestrator
    app.state.registry = orchestrator._registry
    app.state.audit_logger = orchestrator._audit
    app.state.data_collector = orchestrator._data_collector
    app.state.broadcaster = orchestrator.broadcaster

    # ── Start orchestrator ────────────────────────────────────────────────────
    await orchestrator.start()
    logger.info("AI Agent Service ready")
    logger.info("API Documentation: http://localhost:8004/docs")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("Shutting down AI Agent Service...")
    await orchestrator.stop()
    await redis.aclose()
    logger.info("AI Agent Service stopped")


app = FastAPI(
    title="AI Agent Service",
    description=(
        "LLM-powered multi-agent framework for autonomous PLC parameter optimisation. "
        "Implements the SENSE→INFER→VALIDATE→ACT control cycle described in research §4.3."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
async def root():
    return {
        "service": "AI Agent Service",
        "status": "running",
        "version": "1.0.0",
        "description": "Autonomous MES optimisation via LLM multi-agent framework",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8004,
        reload=False,   # reload=False in production — agents hold stateful redis connections
    )

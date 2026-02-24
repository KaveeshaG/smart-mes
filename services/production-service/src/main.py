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
from .models.db.base import Base
from .models.db.work_order import WorkOrderModel  # noqa: F401
from .models.db.production_log import ProductionLogModel  # noqa: F401
from .models.db.operator import OperatorModel  # noqa: F401
from .models.db.material import MaterialModel, WorkOrderMaterialModel  # noqa: F401
from .api.v1 import work_orders, production, operators, materials


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown"""
    logger.info("Starting Production Service...")

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

    logger.info("Production Service ready")
    logger.info("API Documentation: http://localhost:8002/docs")

    yield

    logger.info("Shutting down Production Service...")
    await engine.dispose()

app = FastAPI(
    title="Production Service",
    description="Production management: work orders, tracking, and resource allocation",
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

app.include_router(work_orders.router)
app.include_router(production.router)
app.include_router(operators.router)
app.include_router(materials.router)


@app.get("/")
async def root():
    return {
        "service": "Production Service",
        "status": "running",
        "version": "0.1.0"
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "production",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8002,
        reload=True
    )

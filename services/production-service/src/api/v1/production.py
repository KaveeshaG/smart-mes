from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List

from ...config.database import get_db
from ...services.production_service import ProductionService
from ...schemas.production_log import (
    ProductionLogCreate,
    ProductionLogResponse,
    ProductionProgressUpdate,
    ActiveWorkOrderResponse,
)
from ...schemas.work_order import WorkOrderResponse

router = APIRouter(prefix="/api/v1/production", tags=["production"])
service = ProductionService()


@router.post("/{work_order_id}/log", response_model=ProductionLogResponse, status_code=201)
async def log_production_event(
    work_order_id: UUID,
    data: ProductionLogCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        log = await service.log_event(work_order_id, data, db)
        return log
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{work_order_id}/logs", response_model=List[ProductionLogResponse])
async def get_production_logs(
    work_order_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await service.get_logs(work_order_id, db)


@router.patch("/{work_order_id}/progress", response_model=WorkOrderResponse)
async def update_progress(
    work_order_id: UUID,
    data: ProductionProgressUpdate,
    db: AsyncSession = Depends(get_db),
):
    wo = await service.update_progress(work_order_id, data, db)
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")
    return wo


@router.get("/active", response_model=List[ActiveWorkOrderResponse])
async def get_active_work_orders(db: AsyncSession = Depends(get_db)):
    return await service.get_active_work_orders(db)

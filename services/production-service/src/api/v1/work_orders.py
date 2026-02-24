from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional, List

from ...config.database import get_db
from ...services.work_order_service import WorkOrderService
from ...schemas.work_order import (
    WorkOrderCreate,
    WorkOrderUpdate,
    WorkOrderResponse,
    WorkOrderStatusUpdate,
    WorkOrderDashboard,
)

router = APIRouter(prefix="/api/v1/work-orders", tags=["work-orders"])
service = WorkOrderService()


@router.post("", response_model=WorkOrderResponse, status_code=201)
async def create_work_order(
    data: WorkOrderCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        wo = await service.create(data, db)
        return wo
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard", response_model=WorkOrderDashboard)
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    return await service.get_dashboard(db)


@router.get("", response_model=List[WorkOrderResponse])
async def list_work_orders(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    device_id: Optional[UUID] = Query(None),
    limit: int = Query(100, le=1000),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_all(db, status=status, priority=priority, device_id=device_id, limit=limit)


@router.get("/{work_order_id}", response_model=WorkOrderResponse)
async def get_work_order(
    work_order_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    wo = await service.get_by_id(work_order_id, db)
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")
    return wo


@router.put("/{work_order_id}", response_model=WorkOrderResponse)
async def update_work_order(
    work_order_id: UUID,
    data: WorkOrderUpdate,
    db: AsyncSession = Depends(get_db),
):
    try:
        wo = await service.update(work_order_id, data, db)
        if not wo:
            raise HTTPException(status_code=404, detail="Work order not found")
        return wo
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{work_order_id}", status_code=204)
async def delete_work_order(
    work_order_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    success = await service.delete(work_order_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="Work order not found")
    return None


@router.patch("/{work_order_id}/status", response_model=WorkOrderResponse)
async def update_work_order_status(
    work_order_id: UUID,
    data: WorkOrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    try:
        wo = await service.update_status(work_order_id, data.status, db)
        if not wo:
            raise HTTPException(status_code=404, detail="Work order not found")
        return wo
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

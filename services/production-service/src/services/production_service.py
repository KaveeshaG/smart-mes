from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from typing import Optional

from ..models.db.production_log import ProductionLogModel
from ..models.db.work_order import WorkOrderModel
from ..schemas.production_log import (
    ProductionLogCreate,
    ProductionProgressUpdate,
    VALID_EVENT_TYPES,
)


class ProductionService:

    async def log_event(
        self,
        work_order_id: UUID,
        data: ProductionLogCreate,
        db: AsyncSession,
    ) -> ProductionLogModel:
        if data.event_type not in VALID_EVENT_TYPES:
            raise ValueError(f"Invalid event type: {data.event_type}")
        # Verify work order exists
        result = await db.execute(
            select(WorkOrderModel).where(WorkOrderModel.id == work_order_id)
        )
        wo = result.scalar_one_or_none()
        if not wo:
            raise ValueError("Work order not found")

        log = ProductionLogModel(
            work_order_id=work_order_id,
            **data.model_dump(),
        )
        db.add(log)

        # Auto-update quantities on the work order
        if data.quantity_delta and data.quantity_delta > 0:
            wo.quantity_completed = (wo.quantity_completed or 0) + data.quantity_delta
        if data.reject_delta and data.reject_delta > 0:
            wo.quantity_rejected = (wo.quantity_rejected or 0) + data.reject_delta

        await db.commit()
        await db.refresh(log)
        return log

    async def get_logs(
        self,
        work_order_id: UUID,
        db: AsyncSession,
    ) -> list[ProductionLogModel]:
        result = await db.execute(
            select(ProductionLogModel)
            .where(ProductionLogModel.work_order_id == work_order_id)
            .order_by(ProductionLogModel.timestamp.desc())
        )
        return list(result.scalars().all())

    async def update_progress(
        self,
        work_order_id: UUID,
        data: ProductionProgressUpdate,
        db: AsyncSession,
    ) -> Optional[WorkOrderModel]:
        result = await db.execute(
            select(WorkOrderModel).where(WorkOrderModel.id == work_order_id)
        )
        wo = result.scalar_one_or_none()
        if not wo:
            return None
        if data.quantity_completed is not None:
            wo.quantity_completed = data.quantity_completed
        if data.quantity_rejected is not None:
            wo.quantity_rejected = data.quantity_rejected
        await db.commit()
        await db.refresh(wo)
        return wo

    async def get_active_work_orders(self, db: AsyncSession) -> list[dict]:
        result = await db.execute(
            select(WorkOrderModel).where(WorkOrderModel.status == "in_progress")
        )
        work_orders = result.scalars().all()
        active = []
        for wo in work_orders:
            progress = (
                (wo.quantity_completed / wo.quantity_target * 100)
                if wo.quantity_target > 0
                else 0
            )
            active.append({
                "id": wo.id,
                "order_number": wo.order_number,
                "product_name": wo.product_name,
                "quantity_target": wo.quantity_target,
                "quantity_completed": wo.quantity_completed,
                "quantity_rejected": wo.quantity_rejected,
                "status": wo.status,
                "priority": wo.priority,
                "device_id": wo.device_id,
                "operator_id": wo.operator_id,
                "actual_start": wo.actual_start,
                "progress_pct": round(progress, 1),
            })
        return active

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast, Date
from uuid import UUID
from datetime import datetime, timezone
from typing import Optional

from ..models.db.work_order import WorkOrderModel
from ..schemas.work_order import (
    WorkOrderCreate,
    WorkOrderUpdate,
    WorkOrderDashboard,
    VALID_STATUSES,
    VALID_PRIORITIES,
)

VALID_TRANSITIONS = {
    "planned": {"in_progress", "cancelled"},
    "in_progress": {"on_hold", "completed", "cancelled"},
    "on_hold": {"in_progress", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


class WorkOrderService:

    async def create(self, data: WorkOrderCreate, db: AsyncSession) -> WorkOrderModel:
        if data.priority not in VALID_PRIORITIES:
            raise ValueError(f"Invalid priority: {data.priority}")
        wo = WorkOrderModel(**data.model_dump())
        db.add(wo)
        await db.commit()
        await db.refresh(wo)
        return wo

    async def get_all(
        self,
        db: AsyncSession,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        device_id: Optional[UUID] = None,
        limit: int = 100,
    ) -> list[WorkOrderModel]:
        query = select(WorkOrderModel)
        if status:
            query = query.where(WorkOrderModel.status == status)
        if priority:
            query = query.where(WorkOrderModel.priority == priority)
        if device_id:
            query = query.where(WorkOrderModel.device_id == device_id)
        query = query.order_by(WorkOrderModel.created_at.desc()).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_by_id(self, wo_id: UUID, db: AsyncSession) -> Optional[WorkOrderModel]:
        result = await db.execute(
            select(WorkOrderModel).where(WorkOrderModel.id == wo_id)
        )
        return result.scalar_one_or_none()

    async def update(
        self, wo_id: UUID, data: WorkOrderUpdate, db: AsyncSession
    ) -> Optional[WorkOrderModel]:
        wo = await self.get_by_id(wo_id, db)
        if not wo:
            return None
        update_data = data.model_dump(exclude_unset=True)
        if "priority" in update_data and update_data["priority"] not in VALID_PRIORITIES:
            raise ValueError(f"Invalid priority: {update_data['priority']}")
        for key, value in update_data.items():
            setattr(wo, key, value)
        await db.commit()
        await db.refresh(wo)
        return wo

    async def delete(self, wo_id: UUID, db: AsyncSession) -> bool:
        wo = await self.get_by_id(wo_id, db)
        if not wo:
            return False
        await db.delete(wo)
        await db.commit()
        return True

    async def update_status(
        self, wo_id: UUID, new_status: str, db: AsyncSession
    ) -> Optional[WorkOrderModel]:
        if new_status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {new_status}")
        wo = await self.get_by_id(wo_id, db)
        if not wo:
            return None
        allowed = VALID_TRANSITIONS.get(wo.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Cannot transition from '{wo.status}' to '{new_status}'. "
                f"Allowed: {allowed or 'none (terminal state)'}"
            )
        wo.status = new_status
        now = datetime.now(timezone.utc)
        if new_status == "in_progress" and wo.actual_start is None:
            wo.actual_start = now
        if new_status == "completed":
            wo.actual_end = now
        await db.commit()
        await db.refresh(wo)
        return wo

    async def get_dashboard(self, db: AsyncSession) -> WorkOrderDashboard:
        result = await db.execute(
            select(WorkOrderModel.status, func.count(WorkOrderModel.id)).group_by(
                WorkOrderModel.status
            )
        )
        counts = {row[0]: row[1] for row in result.all()}

        today = datetime.now(timezone.utc).date()
        today_result = await db.execute(
            select(func.count(WorkOrderModel.id)).where(
                cast(WorkOrderModel.created_at, Date) == today
            )
        )
        today_count = today_result.scalar() or 0

        total = sum(counts.values())
        return WorkOrderDashboard(
            total=total,
            planned=counts.get("planned", 0),
            in_progress=counts.get("in_progress", 0),
            on_hold=counts.get("on_hold", 0),
            completed=counts.get("completed", 0),
            cancelled=counts.get("cancelled", 0),
            today_orders=today_count,
        )

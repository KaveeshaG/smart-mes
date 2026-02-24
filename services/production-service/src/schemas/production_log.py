from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID


VALID_EVENT_TYPES = {
    "started", "paused", "resumed", "completed",
    "quality_check", "material_loaded", "note",
}


class ProductionLogCreate(BaseModel):
    event_type: str
    description: Optional[str] = None
    operator_id: Optional[UUID] = None
    quantity_delta: Optional[int] = None
    reject_delta: Optional[int] = None


class ProductionLogResponse(BaseModel):
    id: UUID
    work_order_id: UUID
    event_type: str
    description: Optional[str] = None
    operator_id: Optional[UUID] = None
    quantity_delta: Optional[int] = None
    reject_delta: Optional[int] = None
    timestamp: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProductionProgressUpdate(BaseModel):
    quantity_completed: Optional[int] = None
    quantity_rejected: Optional[int] = None


class ActiveWorkOrderResponse(BaseModel):
    id: UUID
    order_number: str
    product_name: str
    quantity_target: int
    quantity_completed: int
    quantity_rejected: int
    status: str
    priority: str
    device_id: Optional[UUID] = None
    operator_id: Optional[UUID] = None
    actual_start: Optional[datetime] = None
    progress_pct: float = 0.0

    class Config:
        from_attributes = True

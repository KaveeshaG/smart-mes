from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID


VALID_STATUSES = {"planned", "in_progress", "on_hold", "completed", "cancelled"}
VALID_PRIORITIES = {"low", "medium", "high", "urgent"}


class WorkOrderCreate(BaseModel):
    order_number: str = Field(..., max_length=50)
    product_name: str = Field(..., max_length=200)
    quantity_target: int = Field(..., gt=0)
    priority: str = Field(default="medium")
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    device_id: Optional[UUID] = None
    operator_id: Optional[UUID] = None
    notes: Optional[str] = None


class WorkOrderUpdate(BaseModel):
    product_name: Optional[str] = Field(None, max_length=200)
    quantity_target: Optional[int] = Field(None, gt=0)
    priority: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    device_id: Optional[UUID] = None
    operator_id: Optional[UUID] = None
    notes: Optional[str] = None


class WorkOrderStatusUpdate(BaseModel):
    status: str


class WorkOrderResponse(BaseModel):
    id: UUID
    order_number: str
    product_name: str
    quantity_target: int
    quantity_completed: int
    quantity_rejected: int
    status: str
    priority: str
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    device_id: Optional[UUID] = None
    operator_id: Optional[UUID] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WorkOrderDashboard(BaseModel):
    total: int = 0
    planned: int = 0
    in_progress: int = 0
    on_hold: int = 0
    completed: int = 0
    cancelled: int = 0
    today_orders: int = 0

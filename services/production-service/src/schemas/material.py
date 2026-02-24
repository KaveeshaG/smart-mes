from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID


class MaterialCreate(BaseModel):
    name: str = Field(..., max_length=200)
    sku: str = Field(..., max_length=50)
    unit: Optional[str] = Field(None, max_length=20)
    current_stock: float = 0


class MaterialUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    unit: Optional[str] = Field(None, max_length=20)
    current_stock: Optional[float] = None


class MaterialResponse(BaseModel):
    id: UUID
    name: str
    sku: str
    unit: Optional[str] = None
    current_stock: float
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WorkOrderMaterialAssign(BaseModel):
    material_id: UUID
    quantity_required: float = Field(..., gt=0)


class WorkOrderMaterialResponse(BaseModel):
    id: UUID
    work_order_id: UUID
    material_id: UUID
    quantity_required: float
    quantity_consumed: float
    material_name: Optional[str] = None
    material_sku: Optional[str] = None
    material_unit: Optional[str] = None

    class Config:
        from_attributes = True

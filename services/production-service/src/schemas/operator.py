from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID


class OperatorCreate(BaseModel):
    name: str = Field(..., max_length=100)
    employee_id: str = Field(..., max_length=50)
    role: Optional[str] = Field(None, max_length=50)


class OperatorUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    role: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None


class OperatorResponse(BaseModel):
    id: UUID
    name: str
    employee_id: str
    role: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from enum import Enum

class DeviceRegisterRequest(BaseModel):
    ip_address: str = Field(..., description="Device IP address")
    device_type: Optional[str] = "PLC"
    vendor: Optional[str] = None
    model: Optional[str] = None
    primary_protocol: str = "modbus_tcp"
    modbus_unit_id: int = Field(default=1, ge=1, le=247)
    port: int = Field(default=502)
    description: Optional[str] = None
    location: Optional[str] = None
    machine_status: Optional[str] = "standby"

class DeviceResponse(BaseModel):
    id: UUID
    ip_address: str
    mac_address: Optional[str]
    hostname: Optional[str]
    device_type: Optional[str]
    vendor: Optional[str]
    model: Optional[str]
    supported_protocols: List[str]
    primary_protocol: Optional[str]
    is_active: bool
    last_seen: Optional[datetime]
    created_at: datetime
    machine_status: str = "standby"

    class Config:
        from_attributes = True

VALID_MACHINE_STATUSES = {"standby", "maintenance", "changeover", "service"}

class MachineStatusRequest(BaseModel):
    status: str = Field(..., description="Machine status: standby, maintenance, changeover, service")

class TagSchema(BaseModel):
    name: str = Field(..., description="Tag name (e.g., 'Temperature_1')")
    address: str = Field(..., description="PLC address (e.g., 'DM1000', '40001')")
    data_type: str = Field(..., description="Data type: bool, int16, uint16, int32, float32")
    access: str = Field(default="RW", description="Access mode: R, W, RW")
    description: Optional[str] = None
    unit: Optional[str] = None
    scaling: Optional[float] = None
    tag_category: Optional[str] = None

class TagUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    access: Optional[str] = None
    tag_category: Optional[str] = None

class TagConfigRequest(BaseModel):
    tags: List[TagSchema] = Field(..., min_length=1)

class TagResponse(BaseModel):
    id: UUID
    device_id: UUID
    name: str
    address: str
    data_type: str
    access: str
    description: Optional[str]
    unit: Optional[str]
    scaling: Optional[float]
    tag_category: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Reading / Performance Logging Schemas ──

class ExportFormat(str, Enum):
    csv = "csv"
    json = "json"

class ReadingEntry(BaseModel):
    tag_name: str
    value: Optional[float] = None
    raw_value: Optional[str] = None
    quality: str = "good"
    timestamp: datetime

class ReadingBatchRequest(BaseModel):
    device_id: UUID
    session_id: str
    readings: List[ReadingEntry] = Field(..., min_length=1)

class ReadingLogResponse(BaseModel):
    id: UUID
    device_id: UUID
    tag_name: str
    value: Optional[float]
    raw_value: Optional[str]
    quality: str
    timestamp: datetime
    session_id: str

    class Config:
        from_attributes = True

class ReadingQueryParams(BaseModel):
    device_id: UUID
    tag_names: Optional[List[str]] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    session_id: Optional[str] = None
    limit: int = Field(default=1000, le=10000)

class ReadingSummary(BaseModel):
    tag_name: str
    min_value: Optional[float]
    max_value: Optional[float]
    avg_value: Optional[float]
    count: int
    first_timestamp: Optional[datetime]
    last_timestamp: Optional[datetime]

class SessionResponse(BaseModel):
    session_id: str
    device_id: UUID
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    tag_count: int
    reading_count: int

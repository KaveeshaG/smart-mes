from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime

class ReadTagRequest(BaseModel):
    device_id: str = Field(..., description="Device UUID")
    tag_name: str = Field(..., description="Tag name to read")

class ReadMultipleRequest(BaseModel):
    device_id: str = Field(..., description="Device UUID")
    tag_names: List[str] = Field(..., description="List of tag names", min_length=1)

class WriteTagRequest(BaseModel):
    device_id: str = Field(..., description="Device UUID")
    tag_name: str = Field(..., description="Tag name to write")
    value: Any = Field(..., description="Value to write")

class TagReadingResponse(BaseModel):
    tag_name: str
    value: Any
    timestamp: float
    quality: str
    unit: Optional[str] = None

class ReadResponse(BaseModel):
    device_id: str
    readings: List[TagReadingResponse]
    timestamp: float

class WriteResponse(BaseModel):
    device_id: str
    tag_name: str
    success: bool
    message: Optional[str] = None

class SubscribeRequest(BaseModel):
    device_id: str
    tag_names: List[str]
    interval_ms: int = Field(default=1000, ge=100, le=60000)

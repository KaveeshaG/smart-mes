from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from ipaddress import IPv4Network

class ScanRequest(BaseModel):
    subnet: str = Field(
        ..., 
        description="CIDR notation (e.g., 192.168.1.0/24)",
        examples=["192.168.1.0/24"]
    )
    
    @field_validator('subnet')
    @classmethod
    def validate_subnet(cls, v):
        try:
            IPv4Network(v, strict=False)
            return v
        except ValueError:
            raise ValueError("Invalid CIDR notation")

class BatchScanRequest(BaseModel):
    subnets: List[str] = Field(
        ...,
        description="List of CIDR subnets to scan",
        max_length=10
    )
    
    @field_validator('subnets')
    @classmethod
    def validate_subnets(cls, v):
        if not v:
            raise ValueError("At least one subnet required")
        for subnet in v:
            try:
                IPv4Network(subnet, strict=False)
            except ValueError:
                raise ValueError(f"Invalid CIDR notation: {subnet}")
        return v

class DiscoveredDeviceSchema(BaseModel):
    ip_address: str
    mac_address: Optional[str] = None
    hostname: Optional[str] = None
    open_ports: List[int] = []
    response_time_ms: Optional[float] = None
    device_type: str = "Unknown"
    vendor: Optional[str] = None
    supported_protocols: List[str] = []
    identification_confidence: float = 0.0

class ScanResponse(BaseModel):
    total_hosts_scanned: int
    devices_found: int
    scan_duration_seconds: float
    devices: List[DiscoveredDeviceSchema]

class BatchScanResponse(BaseModel):
    total_subnets_scanned: int
    total_hosts_scanned: int
    total_devices_found: int
    scan_duration_seconds: float
    devices_by_subnet: dict
    all_devices: List[DiscoveredDeviceSchema]

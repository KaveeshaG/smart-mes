from dataclasses import dataclass
from typing import Optional, Dict
from ..protocols.base import ProtocolClient

@dataclass
class DeviceConnection:
    """Represents an active device connection"""
    device_id: str
    ip_address: str
    port: int
    protocol: str
    client: ProtocolClient
    tags: Dict[str, 'Tag'] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = {}

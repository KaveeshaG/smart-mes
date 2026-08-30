from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from ..protocols.base import ProtocolClient

@dataclass
class DeviceConnection:
    """Represents a device connection (live or reconnectable)."""
    device_id: str
    ip_address: str
    port: int
    protocol: str
    client: ProtocolClient
    tags: Dict[str, 'Tag'] = None
    connect_kwargs: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.tags is None:
            self.tags = {}
        if self.connect_kwargs is None:
            self.connect_kwargs = {}

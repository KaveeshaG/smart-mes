from abc import ABC, abstractmethod
from typing import Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import time

class DataType(str, Enum):
    BOOL = "bool"
    INT16 = "int16"
    UINT16 = "uint16"
    INT32 = "int32"
    UINT32 = "uint32"
    FLOAT32 = "float32"
    STRING = "string"

@dataclass
class Tag:
    """Represents a readable/writable PLC parameter"""
    name: str
    address: str
    data_type: DataType
    access: str = "RW"  # "R", "W", "RW"
    description: str = ""
    unit: Optional[str] = None
    scaling: Optional[float] = None

@dataclass
class TagReading:
    """Timestamped tag value"""
    tag_name: str
    value: Any
    timestamp: float
    quality: str = "good"  # good, bad, uncertain
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()

class ProtocolClient(ABC):
    """Abstract base for all protocol implementations"""
    
    @abstractmethod
    async def connect(self, ip: str, port: int, **kwargs) -> bool:
        """Establish connection to device"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection"""
        pass
    
    @abstractmethod
    async def read_tag(self, tag: Tag) -> TagReading:
        """Read single tag value"""
        pass
    
    @abstractmethod
    async def write_tag(self, tag: Tag, value: Any) -> bool:
        """Write single tag value"""
        pass

    async def change_plc_mode(self, run: bool, **kwargs) -> bool:
        """Change PLC operating mode. True=RUN, False=STOP/PROGRAM.
        kwargs may include control_register for Modbus devices.
        Default no-op for protocols that don't support mode changes."""
        return True

    @abstractmethod
    async def read_multiple(self, tags: List[Tag]) -> List[TagReading]:
        """Batch read optimization"""
        pass
    
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check connection status"""
        pass

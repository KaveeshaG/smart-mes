from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum

class DeviceType(str, Enum):
    PLC = "PLC"
    HMI = "HMI"
    SENSOR = "Sensor"
    ROBOT = "Robot"
    DRIVE = "Drive"
    UNKNOWN = "Unknown"

class Protocol(str, Enum):
    FINS = "fins"
    MODBUS_TCP = "modbus_tcp"
    OPC_UA = "opc_ua"
    ETHERNET_IP = "ethernet_ip"

@dataclass
class DiscoveredDevice:
    """Device found during network scan"""
    ip_address: str
    mac_address: Optional[str] = None
    hostname: Optional[str] = None
    open_ports: List[int] = field(default_factory=list)
    response_time_ms: Optional[float] = None
    device_type: DeviceType = DeviceType.UNKNOWN
    vendor: Optional[str] = None
    supported_protocols: List[Protocol] = field(default_factory=list)
    identification_confidence: float = 0.0

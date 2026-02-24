"""
Event models for inter-service communication.

Published via RabbitMQ/Redis Pub-Sub.
"""
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from enum import Enum

class EventType(str, Enum):
    DEVICE_DISCOVERED = "device.discovered"
    DEVICE_REGISTERED = "device.registered"
    DEVICE_ONLINE = "device.online"
    DEVICE_OFFLINE = "device.offline"
    TAG_VALUE_CHANGED = "tag.value_changed"
    ALERT_TRIGGERED = "alert.triggered"

class BaseEvent(BaseModel):
    event_type: EventType
    timestamp: datetime
    source_service: str

class DeviceDiscoveredEvent(BaseEvent):
    event_type: EventType = EventType.DEVICE_DISCOVERED
    ip_address: str
    vendor: Optional[str]
    device_type: str
    protocols: List[str]

class DeviceRegisteredEvent(BaseEvent):
    event_type: EventType = EventType.DEVICE_REGISTERED
    device_id: str
    ip_address: str
    vendor: str

class TagValueChangedEvent(BaseEvent):
    event_type: EventType = EventType.TAG_VALUE_CHANGED
    device_id: str
    tag_name: str
    old_value: Optional[float]
    new_value: float

from typing import List, Optional
from uuid import UUID
from loguru import logger
from .connection_manager import ConnectionManager
from ..protocols.base import Tag, TagReading, DataType
from ..schemas.tag_schema import TagReadingResponse
import time

class DataReader:
    """Handles reading data from PLCs"""
    
    def __init__(self, connection_manager: ConnectionManager):
        self.conn_manager = connection_manager
    
    async def read_tag(
        self,
        device_id: str,
        tag_name: str
    ) -> TagReadingResponse:
        """Read single tag value"""
        
        connection = self.conn_manager.get_connection(device_id)
        if not connection:
            raise ValueError(f"Device {device_id} not connected")
        
        tag = self.conn_manager.get_tag(device_id, tag_name)
        if not tag:
            raise ValueError(f"Tag {tag_name} not configured for device {device_id}")
        
        reading = await connection.client.read_tag(tag)
        
        return TagReadingResponse(
            tag_name=reading.tag_name,
            value=reading.value,
            timestamp=reading.timestamp,
            quality=reading.quality,
            unit=tag.unit
        )
    
    async def read_multiple(
        self,
        device_id: str,
        tag_names: List[str]
    ) -> List[TagReadingResponse]:
        """Read multiple tags"""
        
        connection = self.conn_manager.get_connection(device_id)
        if not connection:
            raise ValueError(f"Device {device_id} not connected")
        
        tags = []
        for tag_name in tag_names:
            tag = self.conn_manager.get_tag(device_id, tag_name)
            if not tag:
                logger.warning(f"Tag {tag_name} not found for device {device_id}")
                continue
            tags.append(tag)
        
        readings = await connection.client.read_multiple(tags)
        
        return [
            TagReadingResponse(
                tag_name=r.tag_name,
                value=r.value,
                timestamp=r.timestamp,
                quality=r.quality,
                unit=self.conn_manager.get_tag(device_id, r.tag_name).unit
            )
            for r in readings
        ]

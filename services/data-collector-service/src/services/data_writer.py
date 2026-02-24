from typing import Any
from loguru import logger
from .connection_manager import ConnectionManager

class DataWriter:
    """Handles writing data to PLCs"""
    
    def __init__(self, connection_manager: ConnectionManager):
        self.conn_manager = connection_manager
    
    async def write_tag(
        self,
        device_id: str,
        tag_name: str,
        value: Any
    ) -> bool:
        """Write single tag value"""
        
        connection = self.conn_manager.get_connection(device_id)
        if not connection:
            raise ValueError(f"Device {device_id} not connected")
        
        tag = self.conn_manager.get_tag(device_id, tag_name)
        if not tag:
            raise ValueError(f"Tag {tag_name} not configured for device {device_id}")
        
        if "W" not in tag.access:
            raise ValueError(f"Tag {tag_name} is read-only (access='{tag.access}')")

        success = await connection.client.write_tag(tag, value)
        
        if success:
            logger.info(f"✓ Wrote {value} to {tag_name} on device {device_id}")
        else:
            logger.error(f"✗ Failed to write to {tag_name} on device {device_id}")
        
        return success

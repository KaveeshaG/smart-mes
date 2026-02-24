from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ...api.v1.read import connection_manager
from ...protocols.base import Tag, DataType
from typing import List
from loguru import logger

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])

class ConnectDeviceRequest(BaseModel):
    device_id: str
    ip_address: str
    port: int
    protocol: str
    unit_id: int = 1

class ConfigureTagsRequest(BaseModel):
    device_id: str
    tags: List[dict]

@router.post("/connect")
async def connect_device(request: ConnectDeviceRequest):
    """
    Connect to a PLC device.
    
    **Example:**
```json
    {
      "device_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
      "ip_address": "192.168.250.1",
      "port": 9600,
      "protocol": "fins",
      "unit_id": 1
    }
```
    """
    try:
        success = await connection_manager.connect_device(
            device_id=request.device_id,
            ip_address=request.ip_address,
            port=request.port,
            protocol=request.protocol,
            unit_id=request.unit_id
        )
        
        if success:
            return {
                "success": True,
                "message": f"Connected to {request.ip_address}:{request.port}",
                "device_id": request.device_id
            }
        else:
            raise HTTPException(status_code=500, detail="Connection failed")
    except Exception as e:
        logger.error(f"Connection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/disconnect/{device_id}")
async def disconnect_device(device_id: str):
    """Disconnect from a device"""
    success = await connection_manager.disconnect_device(device_id)
    if success:
        return {"success": True, "message": "Disconnected"}
    else:
        raise HTTPException(status_code=404, detail="Device not found")

@router.get("/status/{device_id}")
async def get_device_status(device_id: str):
    """Get device connection status"""
    is_connected = connection_manager.is_connected(device_id)
    return {
        "device_id": device_id,
        "connected": is_connected
    }

@router.post("/configure-tags")
async def configure_tags(request: ConfigureTagsRequest):
    """
    Configure tags for a device.
    
    **Example:**
```json
    {
      "device_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
      "tags": [
        {
          "name": "Temperature_1",
          "address": "DM1000",
          "data_type": "float32",
          "access": "R",
          "unit": "°C"
        },
        {
          "name": "Setpoint_1",
          "address": "DM1010",
          "data_type": "float32",
          "access": "RW",
          "unit": "°C"
        }
      ]
    }
```
    """
    tags = []
    for tag_dict in request.tags:
        tag = Tag(
            name=tag_dict['name'],
            address=tag_dict['address'],
            data_type=DataType(tag_dict['data_type']),
            access=tag_dict.get('access', 'RW'),
            description=tag_dict.get('description', ''),
            unit=tag_dict.get('unit'),
            scaling=tag_dict.get('scaling')
        )
        tags.append(tag)
    
    connection_manager.register_tags(request.device_id, tags)
    
    return {
        "success": True,
        "message": f"Configured {len(tags)} tags",
        "device_id": request.device_id
    }

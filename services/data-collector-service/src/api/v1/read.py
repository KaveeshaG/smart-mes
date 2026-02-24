from fastapi import APIRouter, HTTPException, Depends
from ...services.data_reader import DataReader
from ...services.connection_manager import ConnectionManager
from ...schemas.tag_schema import (
    ReadTagRequest,
    ReadMultipleRequest,
    ReadResponse,
    TagReadingResponse
)
from loguru import logger
import time

router = APIRouter(prefix="/api/v1/read", tags=["read"])

# Singleton instances
connection_manager = ConnectionManager()
data_reader = DataReader(connection_manager)

@router.post("/tag", response_model=TagReadingResponse)
async def read_tag(request: ReadTagRequest):
    """
    Read a single tag value from a device.
    
    **Example:**
```json
    {
      "device_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
      "tag_name": "Temperature_1"
    }
```
    """
    try:
        reading = await data_reader.read_tag(
            device_id=request.device_id,
            tag_name=request.tag_name
        )
        return reading
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to read tag: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/multiple", response_model=ReadResponse)
async def read_multiple_tags(request: ReadMultipleRequest):
    """
    Read multiple tags from a device.
    
    **Example:**
```json
    {
      "device_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
      "tag_names": ["Temperature_1", "Pressure_1", "Flow_1"]
    }
```
    """
    try:
        readings = await data_reader.read_multiple(
            device_id=request.device_id,
            tag_names=request.tag_names
        )
        
        return ReadResponse(
            device_id=request.device_id,
            readings=readings,
            timestamp=time.time()
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to read tags: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def get_connection_manager():
    """Dependency to get connection manager"""
    return connection_manager

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import asyncio
from ...services.tag_discovery import TagDiscovery
from ...api.v1.read import connection_manager
from ...protocols.base import Tag, DataType  # ADD THIS IMPORT
from loguru import logger

router = APIRouter(prefix="/api/v1/discovery", tags=["discovery"])

tag_discovery = TagDiscovery(connection_manager)

class DiscoverTagsRequest(BaseModel):
    device_id: str
    memory_area: str = Field(default="DM", description="Memory area (DM, CIO, WR, etc.)")
    start_address: int = Field(default=0, ge=0)
    count: int = Field(default=100, ge=1, le=1000)
    data_type: str = Field(default="uint16", description="uint16, int16, float32, etc.")
    sample_interval: float = Field(default=1.0, ge=0.1, le=60.0)
    samples: int = Field(default=3, ge=2, le=10)

class DiscoverMultipleRequest(BaseModel):
    device_id: str
    memory_ranges: List[Dict[str, Any]] = Field(
        ...,
        description="List of memory ranges to scan",
        examples=[[
            {"area": "DM", "start": 0, "count": 100, "type": "uint16"},
            {"area": "DM", "start": 1000, "count": 50, "type": "float32"}
        ]]
    )

@router.post("/scan-tags")
async def discover_tags(request: DiscoverTagsRequest):
    """
    Auto-discover active tags by scanning PLC memory range.
    
    **Example:**
```json
    {
      "device_id": "plc-001",
      "memory_area": "DM",
      "start_address": 1000,
      "count": 100,
      "data_type": "float32",
      "sample_interval": 2.0,
      "samples": 5
    }
```
    """
    try:
        discovered = await tag_discovery.discover_tags(
            device_id=request.device_id,
            memory_area=request.memory_area,
            start_address=request.start_address,
            count=request.count,
            data_type=request.data_type,
            sample_interval=request.sample_interval,
            samples=request.samples
        )
        
        return {
            "discovered_tags": discovered,
            "total_scanned": request.count,
            "total_discovered": len(discovered)
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Tag discovery failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/scan-and-classify")
async def discover_and_classify_tags(request: DiscoverMultipleRequest):
    """
    Scan multiple memory ranges and classify discovered tags.
    
    **Example:**
```json
    {
      "device_id": "plc-001",
      "memory_ranges": [
        {
          "area": "DM",
          "start": 0,
          "count": 100,
          "type": "uint16"
        }
      ]
    }
```
    """
    try:
        classified = await tag_discovery.discover_and_classify(
            device_id=request.device_id,
            memory_ranges=request.memory_ranges
        )
        
        summary = {
            "total_discovered": sum(len(tags) for tags in classified.values()),
            **{category: len(tags) for category, tags in classified.items()}
        }
        
        return {
            "classified_tags": classified,
            "summary": summary
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Tag classification failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/scan-io")
async def discover_io_points(
    device_id: str,
    scan_inputs: bool = True,
    scan_outputs: bool = True,
    sample_interval: float = 0.5,
    samples: int = 3
):
    """
    Discover digital I/O points (X inputs and Y outputs) on Omron CP2E.
    
    **Omron CP2E I/O Layout:**
    - X Inputs: CIO 0.00 - CIO 0.15 (sensors, switches)
    - Y Outputs: CIO 100.00 - CIO 100.15 (relays, solenoids)
    
    **Example:**
```
    GET /api/v1/discovery/scan-io?device_id=plc-001&scan_inputs=true&scan_outputs=true
```
    """
    connection = connection_manager.get_connection(device_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Device not connected")
    
    discovered_io = {"inputs": [], "outputs": []}
    
    # Scan X Inputs (CIO 0.00 - 0.15)
    if scan_inputs:
        logger.info("Scanning digital inputs (X0-X15)...")
        for bit in range(16):
            tag = Tag(
                name=f"X{bit:02d}",
                address=f"CIO0.{bit:02d}",
                data_type=DataType.BOOL,
                access="R"
            )
            
            # Sample multiple times
            values = []
            for _ in range(samples):
                try:
                    reading = await connection.client.read_tag(tag)
                    values.append(reading.value)
                    await asyncio.sleep(sample_interval)
                except Exception as e:
                    logger.error(f"Failed to read {tag.name}: {e}")
                    values.append(None)
            
            # Analyze
            valid_values = [v for v in values if v is not None]
            if valid_values:
                is_active = any(valid_values)
                is_changing = len(set(valid_values)) > 1
                
                discovered_io["inputs"].append({
                    "name": tag.name,
                    "address": tag.address,
                    "current_value": valid_values[-1],
                    "is_active": is_active,
                    "is_changing": is_changing,
                    "description": f"Digital Input {bit}",
                    "suggested_tag": f"Sensor_{bit}" if is_active else f"Input_{bit}"
                })
    
    # Scan Y Outputs (CIO 100.00 - 100.15)
    if scan_outputs:
        logger.info("Scanning digital outputs (Y100-Y115)...")
        for bit in range(16):
            tag = Tag(
                name=f"Y{100 + bit}",
                address=f"CIO100.{bit:02d}",
                data_type=DataType.BOOL,
                access="R"
            )
            
            # Sample multiple times
            values = []
            for _ in range(samples):
                try:
                    reading = await connection.client.read_tag(tag)
                    values.append(reading.value)
                    await asyncio.sleep(sample_interval)
                except Exception as e:
                    logger.error(f"Failed to read {tag.name}: {e}")
                    values.append(None)
            
            # Analyze
            valid_values = [v for v in values if v is not None]
            if valid_values:
                is_active = any(valid_values)
                is_changing = len(set(valid_values)) > 1
                
                discovered_io["outputs"].append({
                    "name": tag.name,
                    "address": tag.address,
                    "current_value": valid_values[-1],
                    "is_active": is_active,
                    "is_changing": is_changing,
                    "description": f"Digital Output {bit}",
                    "suggested_tag": f"Output_{bit}" if is_active else f"Relay_{bit}"
                })
    
    summary = {
        "total_inputs": len(discovered_io["inputs"]),
        "active_inputs": sum(1 for i in discovered_io["inputs"] if i["is_active"]),
        "total_outputs": len(discovered_io["outputs"]),
        "active_outputs": sum(1 for o in discovered_io["outputs"] if o["is_active"])
    }
    
    return {
        "io_points": discovered_io,
        "summary": summary
    }

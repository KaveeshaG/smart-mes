from fastapi import APIRouter, HTTPException
from ...services.discovery_service import DiscoveryService
from ...schemas.discovery_schema import (
    ScanRequest, 
    ScanResponse,
    BatchScanRequest,
    BatchScanResponse
)
from loguru import logger

router = APIRouter(prefix="/api/v1/discovery", tags=["discovery"])
discovery_service = DiscoveryService()

@router.post("/scan", response_model=ScanResponse)
async def scan_network(request: ScanRequest):
    """
    Scan a single subnet for industrial devices.
    
    **Example:**
```json
    {"subnet": "192.168.250.0/24"}
```
    """
    try:
        result = await discovery_service.scan_network(request.subnet)
        return result
    except Exception as e:
        logger.error(f"Discovery scan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/scan/batch", response_model=BatchScanResponse)
async def scan_multiple_networks(request: BatchScanRequest):
    """
    Scan multiple subnets in parallel.
    
    **Example:**
```json
    {
      "subnets": [
        "192.168.1.0/24",
        "192.168.250.0/24"
      ]
    }
```
    """
    try:
        result = await discovery_service.scan_multiple_networks(request.subnets)
        return result
    except Exception as e:
        logger.error(f"Batch scan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

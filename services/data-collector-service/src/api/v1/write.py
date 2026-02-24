from fastapi import APIRouter, HTTPException
from ...services.data_writer import DataWriter
from ...api.v1.read import connection_manager
from ...schemas.tag_schema import WriteTagRequest, WriteResponse
from ...config.settings import settings
from loguru import logger
import httpx

router = APIRouter(prefix="/api/v1/write", tags=["write"])

data_writer = DataWriter(connection_manager)


async def _check_machine_status(device_id: str) -> None:
    """Check if the machine is in standby mode. Raises HTTPException if locked."""
    url = f"{settings.device_management_url}/api/v1/devices/{device_id}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                device = resp.json()
                status = device.get("machine_status", "standby")
                if status != "standby":
                    raise HTTPException(
                        status_code=403,
                        detail=f"Machine is in {status} mode — writes are locked"
                    )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Could not verify machine status for {device_id}: {e}")
        raise HTTPException(
            status_code=503,
            detail="Unable to verify machine status — write denied for safety"
        )


@router.post("/tag", response_model=WriteResponse)
async def write_tag(request: WriteTagRequest):
    """
    Write a value to a PLC tag.

    **Example:**
```json
    {
      "device_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
      "tag_name": "Setpoint_1",
      "value": 75.5
    }
```
    """
    await _check_machine_status(request.device_id)

    try:
        success = await data_writer.write_tag(
            device_id=request.device_id,
            tag_name=request.tag_name,
            value=request.value
        )

        return WriteResponse(
            device_id=request.device_id,
            tag_name=request.tag_name,
            success=success,
            message="Write successful" if success else "Write failed"
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to write tag: {e}")
        raise HTTPException(status_code=500, detail=str(e))

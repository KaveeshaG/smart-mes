from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from ...api.v1.read import connection_manager
from loguru import logger

router = APIRouter(prefix="/api/v1/plc", tags=["plc-control"])


class PlcModeRequest(BaseModel):
    mode: str = Field(..., description="PLC mode: 'run' or 'stop'")


class PlcModeResponse(BaseModel):
    device_id: str
    mode: str
    success: bool
    message: str


@router.post("/{device_id}/mode", response_model=PlcModeResponse)
async def change_plc_mode(device_id: str, request: PlcModeRequest):
    """
    Change PLC operating mode.

    - **run**: Resume normal ladder logic execution (standby)
    - **stop**: Halt ladder logic execution (maintenance/changeover/service)
    """
    if request.mode not in ("run", "stop"):
        raise HTTPException(
            status_code=400,
            detail="Mode must be 'run' or 'stop'"
        )

    connection = connection_manager.get_connection(device_id)
    if not connection:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not connected")

    run = request.mode == "run"

    try:
        success = await connection.client.change_plc_mode(run)
        mode_label = "RUN" if run else "PROGRAM/STOP"

        if success:
            logger.info(f"PLC {device_id} mode changed to {mode_label}")
        else:
            logger.error(f"PLC {device_id} mode change to {mode_label} failed")

        return PlcModeResponse(
            device_id=device_id,
            mode=request.mode,
            success=success,
            message=f"PLC set to {mode_label}" if success else f"Failed to set {mode_label}",
        )
    except Exception as e:
        logger.error(f"PLC mode change error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

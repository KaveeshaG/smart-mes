from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from ...api.v1.read import connection_manager
from loguru import logger

router = APIRouter(prefix="/api/v1/plc", tags=["plc-control"])


class PlcModeRequest(BaseModel):
    mode: str = Field(..., description="PLC mode: 'run' or 'stop'")
    control_register: Optional[str] = Field(
        default=None,
        description="Modbus control register address (e.g. '40100'). Required for Modbus PLCs.",
    )


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

    For FINS (Omron): uses native PLC RUN/STOP commands.
    For Modbus (Xinje, Delta, etc.): writes 1/0 to a configurable control register.
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
        kwargs = {}
        if request.control_register:
            kwargs["control_register"] = request.control_register

        success = await connection.client.change_plc_mode(run, **kwargs)
        mode_label = "RUN" if run else "STOP"

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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"PLC mode change error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

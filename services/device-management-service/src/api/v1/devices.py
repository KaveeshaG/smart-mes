from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List
from ...config.database import get_db
from ...services.device_registry import DeviceRegistry
from ...schemas.device_schema import (
    DeviceRegisterRequest,
    DeviceResponse,
    TagConfigRequest,
    TagResponse,
    TagUpdateRequest,
    MachineStatusRequest,
    ControlRegisterRequest,
    VALID_MACHINE_STATUSES,
)

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])
registry = DeviceRegistry()

@router.post("/register", response_model=DeviceResponse, status_code=201)
async def register_device(
    request: DeviceRegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a discovered device into the system.
    """
    try:
        device = await registry.register_device(request, db)
        return device
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("", response_model=List[DeviceResponse])
async def list_devices(db: AsyncSession = Depends(get_db)):
    """Get all registered devices"""
    devices = await registry.get_all_devices(db)
    return devices

@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get device by ID"""
    device = await registry.get_device_by_id(device_id, db)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device

@router.put("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: UUID,
    request: DeviceRegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    """Update device information"""
    device = await registry.update_device(device_id, request, db)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device

@router.patch("/{device_id}/machine-status", response_model=DeviceResponse)
async def update_machine_status(
    device_id: UUID,
    request: MachineStatusRequest,
    db: AsyncSession = Depends(get_db)
):
    """Update the machine operational mode (standby, maintenance, changeover, service)"""
    if request.status not in VALID_MACHINE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{request.status}'. Must be one of: {', '.join(sorted(VALID_MACHINE_STATUSES))}"
        )
    device = await registry.update_machine_status(device_id, request.status, db)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device

@router.patch("/{device_id}/control-register", response_model=DeviceResponse)
async def update_control_register(
    device_id: UUID,
    request: ControlRegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    """Set or clear the Modbus run-enable control register for a device."""
    device = await registry.update_control_register(device_id, request.control_register, db)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device

@router.delete("/{device_id}", status_code=204)
async def delete_device(
    device_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete device"""
    success = await registry.delete_device(device_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="Device not found")
    return None

@router.post("/{device_id}/tags", response_model=List[TagResponse], status_code=201)
async def configure_tags(
    device_id: UUID,
    request: TagConfigRequest,
    db: AsyncSession = Depends(get_db)
):
    """Configure tags for a device"""
    tags = await registry.configure_tags(device_id, request.tags, db)
    return tags

@router.get("/{device_id}/tags", response_model=List[TagResponse])
async def get_device_tags(
    device_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get all tags for a device"""
    tags = await registry.get_device_tags(device_id, db)
    return tags

@router.put("/{device_id}/tags/{tag_id}", response_model=TagResponse)
async def update_tag(
    device_id: UUID,
    tag_id: UUID,
    request: TagUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Update a tag's name, description, unit, or access"""
    tag = await registry.update_tag(device_id, tag_id, request, db)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag

@router.delete("/{device_id}/tags/{tag_id}", status_code=204)
async def delete_tag(
    device_id: UUID,
    tag_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete a specific tag"""
    success = await registry.delete_tag(device_id, tag_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="Tag not found")
    return None

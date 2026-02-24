from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List

from ...config.database import get_db
from ...services.material_service import MaterialService
from ...schemas.material import (
    MaterialCreate,
    MaterialUpdate,
    MaterialResponse,
    WorkOrderMaterialAssign,
    WorkOrderMaterialResponse,
)

router = APIRouter(prefix="/api/v1/materials", tags=["materials"])
service = MaterialService()


@router.post("", response_model=MaterialResponse, status_code=201)
async def create_material(
    data: MaterialCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.create(data, db)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=List[MaterialResponse])
async def list_materials(db: AsyncSession = Depends(get_db)):
    return await service.get_all(db)


@router.get("/{material_id}", response_model=MaterialResponse)
async def get_material(
    material_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    mat = await service.get_by_id(material_id, db)
    if not mat:
        raise HTTPException(status_code=404, detail="Material not found")
    return mat


@router.put("/{material_id}", response_model=MaterialResponse)
async def update_material(
    material_id: UUID,
    data: MaterialUpdate,
    db: AsyncSession = Depends(get_db),
):
    mat = await service.update(material_id, data, db)
    if not mat:
        raise HTTPException(status_code=404, detail="Material not found")
    return mat


@router.delete("/{material_id}", status_code=204)
async def delete_material(
    material_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    success = await service.delete(material_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="Material not found")
    return None


@router.post(
    "/work-orders/{work_order_id}/materials",
    response_model=WorkOrderMaterialResponse,
    status_code=201,
)
async def assign_material_to_work_order(
    work_order_id: UUID,
    data: WorkOrderMaterialAssign,
    db: AsyncSession = Depends(get_db),
):
    try:
        wom = await service.assign_to_work_order(work_order_id, data, db)
        # Fetch material info to populate response
        mat = await service.get_by_id(data.material_id, db)
        return {
            "id": wom.id,
            "work_order_id": wom.work_order_id,
            "material_id": wom.material_id,
            "quantity_required": wom.quantity_required,
            "quantity_consumed": wom.quantity_consumed,
            "material_name": mat.name if mat else None,
            "material_sku": mat.sku if mat else None,
            "material_unit": mat.unit if mat else None,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/work-orders/{work_order_id}/materials",
    response_model=List[WorkOrderMaterialResponse],
)
async def get_work_order_materials(
    work_order_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await service.get_work_order_materials(work_order_id, db)

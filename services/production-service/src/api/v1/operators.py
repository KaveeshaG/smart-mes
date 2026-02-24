from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List

from ...config.database import get_db
from ...services.operator_service import OperatorService
from ...schemas.operator import OperatorCreate, OperatorUpdate, OperatorResponse

router = APIRouter(prefix="/api/v1/operators", tags=["operators"])
service = OperatorService()


@router.post("", response_model=OperatorResponse, status_code=201)
async def create_operator(
    data: OperatorCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.create(data, db)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=List[OperatorResponse])
async def list_operators(db: AsyncSession = Depends(get_db)):
    return await service.get_all(db)


@router.get("/{operator_id}", response_model=OperatorResponse)
async def get_operator(
    operator_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    op = await service.get_by_id(operator_id, db)
    if not op:
        raise HTTPException(status_code=404, detail="Operator not found")
    return op


@router.put("/{operator_id}", response_model=OperatorResponse)
async def update_operator(
    operator_id: UUID,
    data: OperatorUpdate,
    db: AsyncSession = Depends(get_db),
):
    op = await service.update(operator_id, data, db)
    if not op:
        raise HTTPException(status_code=404, detail="Operator not found")
    return op


@router.delete("/{operator_id}", status_code=204)
async def delete_operator(
    operator_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    success = await service.delete(operator_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="Operator not found")
    return None

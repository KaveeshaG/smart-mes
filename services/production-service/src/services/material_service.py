from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from typing import Optional

from ..models.db.material import MaterialModel, WorkOrderMaterialModel
from ..schemas.material import MaterialCreate, MaterialUpdate, WorkOrderMaterialAssign


class MaterialService:

    async def create(self, data: MaterialCreate, db: AsyncSession) -> MaterialModel:
        material = MaterialModel(**data.model_dump())
        db.add(material)
        await db.commit()
        await db.refresh(material)
        return material

    async def get_all(self, db: AsyncSession) -> list[MaterialModel]:
        result = await db.execute(
            select(MaterialModel).order_by(MaterialModel.name)
        )
        return list(result.scalars().all())

    async def get_by_id(self, mat_id: UUID, db: AsyncSession) -> Optional[MaterialModel]:
        result = await db.execute(
            select(MaterialModel).where(MaterialModel.id == mat_id)
        )
        return result.scalar_one_or_none()

    async def update(
        self, mat_id: UUID, data: MaterialUpdate, db: AsyncSession
    ) -> Optional[MaterialModel]:
        material = await self.get_by_id(mat_id, db)
        if not material:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(material, key, value)
        await db.commit()
        await db.refresh(material)
        return material

    async def delete(self, mat_id: UUID, db: AsyncSession) -> bool:
        material = await self.get_by_id(mat_id, db)
        if not material:
            return False
        await db.delete(material)
        await db.commit()
        return True

    async def assign_to_work_order(
        self,
        work_order_id: UUID,
        data: WorkOrderMaterialAssign,
        db: AsyncSession,
    ) -> WorkOrderMaterialModel:
        wom = WorkOrderMaterialModel(
            work_order_id=work_order_id,
            material_id=data.material_id,
            quantity_required=data.quantity_required,
        )
        db.add(wom)
        await db.commit()
        await db.refresh(wom)
        return wom

    async def get_work_order_materials(
        self, work_order_id: UUID, db: AsyncSession
    ) -> list[dict]:
        result = await db.execute(
            select(WorkOrderMaterialModel, MaterialModel)
            .join(MaterialModel, WorkOrderMaterialModel.material_id == MaterialModel.id)
            .where(WorkOrderMaterialModel.work_order_id == work_order_id)
        )
        items = []
        for wom, mat in result.all():
            items.append({
                "id": wom.id,
                "work_order_id": wom.work_order_id,
                "material_id": wom.material_id,
                "quantity_required": wom.quantity_required,
                "quantity_consumed": wom.quantity_consumed,
                "material_name": mat.name,
                "material_sku": mat.sku,
                "material_unit": mat.unit,
            })
        return items

    async def update_consumption(
        self,
        wom_id: UUID,
        quantity_consumed: float,
        db: AsyncSession,
    ) -> Optional[WorkOrderMaterialModel]:
        result = await db.execute(
            select(WorkOrderMaterialModel).where(WorkOrderMaterialModel.id == wom_id)
        )
        wom = result.scalar_one_or_none()
        if not wom:
            return None
        wom.quantity_consumed = quantity_consumed
        await db.commit()
        await db.refresh(wom)
        return wom

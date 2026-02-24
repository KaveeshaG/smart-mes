from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from typing import Optional

from ..models.db.operator import OperatorModel
from ..schemas.operator import OperatorCreate, OperatorUpdate


class OperatorService:

    async def create(self, data: OperatorCreate, db: AsyncSession) -> OperatorModel:
        operator = OperatorModel(**data.model_dump())
        db.add(operator)
        await db.commit()
        await db.refresh(operator)
        return operator

    async def get_all(self, db: AsyncSession) -> list[OperatorModel]:
        result = await db.execute(
            select(OperatorModel).order_by(OperatorModel.name)
        )
        return list(result.scalars().all())

    async def get_by_id(self, op_id: UUID, db: AsyncSession) -> Optional[OperatorModel]:
        result = await db.execute(
            select(OperatorModel).where(OperatorModel.id == op_id)
        )
        return result.scalar_one_or_none()

    async def update(
        self, op_id: UUID, data: OperatorUpdate, db: AsyncSession
    ) -> Optional[OperatorModel]:
        operator = await self.get_by_id(op_id, db)
        if not operator:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(operator, key, value)
        await db.commit()
        await db.refresh(operator)
        return operator

    async def delete(self, op_id: UUID, db: AsyncSession) -> bool:
        operator = await self.get_by_id(op_id, db)
        if not operator:
            return False
        await db.delete(operator)
        await db.commit()
        return True

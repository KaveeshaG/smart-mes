from sqlalchemy import Column, String, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from .base import Base


class MaterialModel(Base):
    __tablename__ = "materials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    sku = Column(String(50), unique=True, nullable=False, index=True)
    unit = Column(String(20), nullable=True)
    current_stock = Column(Float, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WorkOrderMaterialModel(Base):
    __tablename__ = "work_order_materials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    work_order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    material_id = Column(
        UUID(as_uuid=True),
        ForeignKey("materials.id", ondelete="CASCADE"),
        nullable=False,
    )
    quantity_required = Column(Float, nullable=False)
    quantity_consumed = Column(Float, default=0)

    __table_args__ = (
        UniqueConstraint("work_order_id", "material_id", name="uq_wo_material"),
    )

from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from .base import Base


class ProductionLogModel(Base):
    __tablename__ = "production_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    work_order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type = Column(String(30), nullable=False)
    description = Column(Text, nullable=True)
    operator_id = Column(UUID(as_uuid=True), nullable=True)
    quantity_delta = Column(Integer, nullable=True)
    reject_delta = Column(Integer, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

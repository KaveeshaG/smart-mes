from datetime import datetime
from sqlalchemy import (
    Integer, String, Float, Boolean, Text,
    DateTime, UniqueConstraint, func
)
from sqlalchemy.orm import Mapped, mapped_column
from ...config.database import Base


class SafetyBoundsModel(Base):
    """
    Per-device, per-tag safety envelope.

    The Safety Agent validates EVERY proposed write against these bounds
    before any PLC register is touched. 100% coverage is enforced in code —
    a write with no configured bounds is automatically REJECTED.

    Loaded into Redis on startup and refreshed every 5 min.
    Persisted here for durability and audit-ability.
    """
    __tablename__ = "agent_safety_bounds"
    __table_args__ = (
        UniqueConstraint("device_id", "tag_name", name="uq_device_tag_bounds"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    tag_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Absolute operating range from equipment datasheet / operator specification
    min_value: Mapped[float] = mapped_column(Float, nullable=False)
    max_value: Mapped[float] = mapped_column(Float, nullable=False)

    # Maximum single-step change — prevents actuator shock / runaway
    max_step_change: Mapped[float] = mapped_column(Float, nullable=False)

    unit: Mapped[str] = mapped_column(String(50), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

from sqlalchemy import Column, String, Integer, Float, DateTime, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from .device_model import Base


class AnalyticsCheckpointModel(Base):
    __tablename__ = "analytics_checkpoints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period_type = Column(String(20), nullable=False, unique=True)
    last_computed_start = Column(DateTime(timezone=True), nullable=False)
    last_computed_at = Column(DateTime(timezone=True), nullable=False)


class DeviceAnalyticsModel(Base):
    __tablename__ = "device_analytics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    tag_name = Column(String(100), nullable=False)
    period_type = Column(String(20), nullable=False)  # hourly, daily, weekly, monthly, annual
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)

    # Core statistics
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    avg_value = Column(Float, nullable=True)
    std_dev = Column(Float, nullable=True)
    reading_count = Column(Integer, nullable=False, default=0)

    # Quality metrics
    good_quality_pct = Column(Float, nullable=True)
    uptime_seconds = Column(Float, nullable=True)
    data_completeness_pct = Column(Float, nullable=True)

    # Trend indicators
    trend_direction = Column(String(10), nullable=True)  # up, down, stable
    change_rate_pct = Column(Float, nullable=True)
    anomaly_count = Column(Integer, nullable=True, default=0)

    computed_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "device_id", "tag_name", "period_type", "period_start",
            name="uq_device_tag_period",
        ),
        Index("ix_analytics_device_period", "device_id", "period_type", "period_start"),
        Index(
            "ix_analytics_device_tag_period",
            "device_id", "tag_name", "period_type", "period_start",
        ),
    )

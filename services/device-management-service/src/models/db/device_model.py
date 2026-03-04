from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, JSON, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import declarative_base, relationship
import uuid

Base = declarative_base()

class DeviceModel(Base):
    __tablename__ = "devices"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ip_address = Column(String(15), nullable=False, unique=True, index=True)
    mac_address = Column(String(17), nullable=True)
    hostname = Column(String(255), nullable=True)
    device_type = Column(String(50), nullable=True)
    vendor = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    supported_protocols = Column(JSON, default=list)
    primary_protocol = Column(String(50), nullable=True)
    modbus_unit_id = Column(Integer, nullable=True, default=1)
    port = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True)
    last_seen = Column(DateTime(timezone=True), nullable=True)
    description = Column(String(500), nullable=True)
    location = Column(String(200), nullable=True)
    machine_status = Column(String(20), default="standby")
    control_register = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    discovery_metadata = Column(JSON, default=dict)
    
    # Relationship to tags
    tags = relationship("TagModel", back_populates="device", cascade="all, delete-orphan")

class TagModel(Base):
    __tablename__ = "tags"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    address = Column(String(50), nullable=False)
    data_type = Column(String(20), nullable=False)
    access = Column(String(5), default="RW")
    description = Column(String(500), nullable=True)
    unit = Column(String(20), nullable=True)
    scaling = Column(Integer, nullable=True)
    tag_category = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship back to device
    device = relationship("DeviceModel", back_populates="tags")


class ReadingLogModel(Base):
    __tablename__ = "reading_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    tag_name = Column(String(100), nullable=False, index=True)
    value = Column(Float, nullable=True)
    raw_value = Column(String(500), nullable=True)
    quality = Column(String(20), default="good")
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    session_id = Column(String(100), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_readings_device_tag_time", "device_id", "tag_name", "timestamp"),
    )

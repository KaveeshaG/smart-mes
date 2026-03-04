from typing import List, Optional, Dict, Any
from uuid import UUID
from sqlalchemy import select, func as sa_func, distinct
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.db.device_model import DeviceModel, TagModel, ReadingLogModel
from ..schemas.device_schema import (
    DeviceRegisterRequest, DeviceResponse, TagSchema, TagResponse, TagUpdateRequest,
    ReadingBatchRequest, ReadingLogResponse, ReadingQueryParams,
    ReadingSummary, SessionResponse,
)
from loguru import logger
from datetime import datetime

class DeviceRegistry:
    async def register_device(
        self, 
        request: DeviceRegisterRequest,
        db: AsyncSession
    ) -> DeviceResponse:
        existing = await self._find_by_ip(request.ip_address, db)
        if existing:
            raise ValueError(f"Device with IP {request.ip_address} already registered")
        
        device = DeviceModel(
            ip_address=request.ip_address,
            device_type=request.device_type,
            vendor=request.vendor,
            model=request.model,
            primary_protocol=request.primary_protocol,
            supported_protocols=[request.primary_protocol],
            modbus_unit_id=request.modbus_unit_id,
            port=request.port,
            description=request.description,
            location=request.location,
            is_active=True,
            last_seen=datetime.utcnow()
        )
        
        db.add(device)
        await db.commit()
        await db.refresh(device)
        
        logger.info(f"Registered device: {device.ip_address} (ID: {device.id})")
        return DeviceResponse.model_validate(device)
    
    async def get_all_devices(self, db: AsyncSession) -> List[DeviceResponse]:
        result = await db.execute(select(DeviceModel))
        devices = result.scalars().all()
        return [DeviceResponse.model_validate(d) for d in devices]
    
    async def get_device_by_id(
        self, 
        device_id: UUID, 
        db: AsyncSession
    ) -> Optional[DeviceResponse]:
        device = await db.get(DeviceModel, device_id)
        if device:
            return DeviceResponse.model_validate(device)
        return None
    
    async def update_device(
        self,
        device_id: UUID,
        request: DeviceRegisterRequest,
        db: AsyncSession
    ) -> Optional[DeviceResponse]:
        device = await db.get(DeviceModel, device_id)
        if not device:
            return None
        
        device.device_type = request.device_type
        device.vendor = request.vendor
        device.model = request.model
        device.description = request.description
        device.location = request.location
        
        await db.commit()
        await db.refresh(device)
        
        return DeviceResponse.model_validate(device)
    
    async def delete_device(
        self,
        device_id: UUID,
        db: AsyncSession
    ) -> bool:
        device = await db.get(DeviceModel, device_id)
        if not device:
            return False
        
        await db.delete(device)
        await db.commit()
        return True
    
    async def configure_tags(
        self,
        device_id: UUID,
        tags: List[TagSchema],
        db: AsyncSession
    ) -> List[TagResponse]:
        device = await db.get(DeviceModel, device_id)
        if not device:
            raise ValueError("Device not found")
        
        tag_models = []
        for tag in tags:
            tag_model = TagModel(
                device_id=device_id,
                name=tag.name,
                address=tag.address,
                data_type=tag.data_type,
                access=tag.access,
                description=tag.description,
                unit=tag.unit,
                scaling=tag.scaling
            )
            db.add(tag_model)
            tag_models.append(tag_model)
        
        await db.commit()
        for tag in tag_models:
            await db.refresh(tag)
        
        return [TagResponse.model_validate(t) for t in tag_models]
    
    async def update_tag(
        self,
        device_id: UUID,
        tag_id: UUID,
        data: TagUpdateRequest,
        db: AsyncSession
    ) -> Optional[TagResponse]:
        result = await db.execute(
            select(TagModel).where(
                TagModel.id == tag_id,
                TagModel.device_id == device_id
            )
        )
        tag = result.scalar_one_or_none()
        if not tag:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(tag, field, value)

        await db.commit()
        await db.refresh(tag)
        logger.info(f"Updated tag {tag_id} on device {device_id}: {update_data}")
        return TagResponse.model_validate(tag)

    async def delete_tag(
        self,
        device_id: UUID,
        tag_id: UUID,
        db: AsyncSession
    ) -> bool:
        result = await db.execute(
            select(TagModel).where(
                TagModel.id == tag_id,
                TagModel.device_id == device_id
            )
        )
        tag = result.scalar_one_or_none()
        if not tag:
            return False

        await db.delete(tag)
        await db.commit()
        logger.info(f"Deleted tag {tag_id} from device {device_id}")
        return True

    async def get_device_tags(
        self,
        device_id: UUID,
        db: AsyncSession
    ) -> List[TagResponse]:
        result = await db.execute(
            select(TagModel).where(TagModel.device_id == device_id)
        )
        tags = result.scalars().all()
        return [TagResponse.model_validate(t) for t in tags]
    
    # ── Reading / Performance Logging Methods ──

    async def store_readings(
        self,
        batch: ReadingBatchRequest,
        db: AsyncSession
    ) -> int:
        models = []
        for r in batch.readings:
            models.append(ReadingLogModel(
                device_id=batch.device_id,
                tag_name=r.tag_name,
                value=r.value,
                raw_value=r.raw_value,
                quality=r.quality,
                timestamp=r.timestamp,
                session_id=batch.session_id,
            ))
        db.add_all(models)
        await db.commit()
        logger.debug(f"Stored {len(models)} readings for session {batch.session_id}")
        return len(models)

    async def get_readings(
        self,
        params: ReadingQueryParams,
        db: AsyncSession
    ) -> List[ReadingLogResponse]:
        stmt = select(ReadingLogModel).where(
            ReadingLogModel.device_id == params.device_id
        )
        if params.tag_names:
            stmt = stmt.where(ReadingLogModel.tag_name.in_(params.tag_names))
        if params.start_time:
            stmt = stmt.where(ReadingLogModel.timestamp >= params.start_time)
        if params.end_time:
            stmt = stmt.where(ReadingLogModel.timestamp <= params.end_time)
        if params.session_id:
            stmt = stmt.where(ReadingLogModel.session_id == params.session_id)

        stmt = stmt.order_by(ReadingLogModel.timestamp.asc()).limit(params.limit)
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [ReadingLogResponse.model_validate(r) for r in rows]

    async def get_reading_sessions(
        self,
        device_id: UUID,
        db: AsyncSession
    ) -> List[SessionResponse]:
        stmt = (
            select(
                ReadingLogModel.session_id,
                ReadingLogModel.device_id,
                sa_func.min(ReadingLogModel.timestamp).label("start_time"),
                sa_func.max(ReadingLogModel.timestamp).label("end_time"),
                sa_func.count(distinct(ReadingLogModel.tag_name)).label("tag_count"),
                sa_func.count(ReadingLogModel.id).label("reading_count"),
            )
            .where(ReadingLogModel.device_id == device_id)
            .group_by(ReadingLogModel.session_id, ReadingLogModel.device_id)
            .order_by(sa_func.max(ReadingLogModel.timestamp).desc())
        )
        result = await db.execute(stmt)
        rows = result.all()
        return [
            SessionResponse(
                session_id=r.session_id,
                device_id=r.device_id,
                start_time=r.start_time,
                end_time=r.end_time,
                tag_count=r.tag_count,
                reading_count=r.reading_count,
            )
            for r in rows
        ]

    async def get_reading_summary(
        self,
        device_id: UUID,
        session_id: Optional[str],
        db: AsyncSession
    ) -> List[ReadingSummary]:
        stmt = (
            select(
                ReadingLogModel.tag_name,
                sa_func.min(ReadingLogModel.value).label("min_value"),
                sa_func.max(ReadingLogModel.value).label("max_value"),
                sa_func.avg(ReadingLogModel.value).label("avg_value"),
                sa_func.count(ReadingLogModel.id).label("count"),
                sa_func.min(ReadingLogModel.timestamp).label("first_timestamp"),
                sa_func.max(ReadingLogModel.timestamp).label("last_timestamp"),
            )
            .where(ReadingLogModel.device_id == device_id)
        )
        if session_id:
            stmt = stmt.where(ReadingLogModel.session_id == session_id)
        stmt = stmt.group_by(ReadingLogModel.tag_name)

        result = await db.execute(stmt)
        rows = result.all()
        return [
            ReadingSummary(
                tag_name=r.tag_name,
                min_value=float(r.min_value) if r.min_value is not None else None,
                max_value=float(r.max_value) if r.max_value is not None else None,
                avg_value=round(float(r.avg_value), 4) if r.avg_value is not None else None,
                count=r.count,
                first_timestamp=r.first_timestamp,
                last_timestamp=r.last_timestamp,
            )
            for r in rows
        ]

    async def export_readings(
        self,
        params: ReadingQueryParams,
        db: AsyncSession
    ) -> List[Dict[str, Any]]:
        readings = await self.get_readings(params, db)
        return [
            {
                "timestamp": r.timestamp.isoformat(),
                "device_id": str(r.device_id),
                "tag_name": r.tag_name,
                "value": r.value,
                "raw_value": r.raw_value,
                "quality": r.quality,
                "session_id": r.session_id,
            }
            for r in readings
        ]

    async def update_machine_status(
        self,
        device_id: UUID,
        status: str,
        db: AsyncSession
    ) -> Optional[DeviceResponse]:
        device = await db.get(DeviceModel, device_id)
        if not device:
            return None
        device.machine_status = status
        await db.commit()
        await db.refresh(device)
        logger.info(f"Device {device_id} machine_status → {status}")
        return DeviceResponse.model_validate(device)

    async def update_control_register(
        self,
        device_id: UUID,
        control_register: Optional[str],
        db: AsyncSession
    ) -> Optional[DeviceResponse]:
        device = await db.get(DeviceModel, device_id)
        if not device:
            return None
        device.control_register = control_register
        await db.commit()
        await db.refresh(device)
        logger.info(f"Device {device_id} control_register → {control_register}")
        return DeviceResponse.model_validate(device)

    async def _find_by_ip(
        self,
        ip_address: str,
        db: AsyncSession
    ) -> Optional[DeviceModel]:
        result = await db.execute(
            select(DeviceModel).where(DeviceModel.ip_address == ip_address)
        )
        return result.scalar_one_or_none()

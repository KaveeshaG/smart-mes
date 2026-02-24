from typing import List, Optional
from uuid import UUID
from datetime import datetime
from sqlalchemy import select, func as sa_func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.db.analytics_model import DeviceAnalyticsModel
from ..schemas.analytics_schema import (
    AnalyticsResponse,
    AnalyticsSummaryResponse,
    AnalyticsCompareItem,
    AnalyticsTrendPoint,
)


class AnalyticsService:
    async def get_device_analytics(
        self,
        device_id: UUID,
        period: str,
        db: AsyncSession,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        tags: Optional[List[str]] = None,
    ) -> List[AnalyticsResponse]:
        stmt = select(DeviceAnalyticsModel).where(
            DeviceAnalyticsModel.device_id == device_id,
            DeviceAnalyticsModel.period_type == period,
        )
        if start:
            stmt = stmt.where(DeviceAnalyticsModel.period_start >= start)
        if end:
            stmt = stmt.where(DeviceAnalyticsModel.period_start <= end)
        if tags:
            stmt = stmt.where(DeviceAnalyticsModel.tag_name.in_(tags))
        stmt = stmt.order_by(DeviceAnalyticsModel.period_start.desc())

        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [AnalyticsResponse.model_validate(r) for r in rows]

    async def get_device_summary(
        self,
        device_id: UUID,
        period: str,
        db: AsyncSession,
    ) -> AnalyticsSummaryResponse:
        stmt = (
            select(
                sa_func.sum(DeviceAnalyticsModel.reading_count).label("total_readings"),
                sa_func.avg(DeviceAnalyticsModel.good_quality_pct).label("avg_quality_pct"),
                sa_func.avg(DeviceAnalyticsModel.uptime_seconds).label("avg_uptime"),
                sa_func.count(distinct(DeviceAnalyticsModel.tag_name)).label("tag_count"),
            )
            .where(
                DeviceAnalyticsModel.device_id == device_id,
                DeviceAnalyticsModel.period_type == period,
            )
        )
        result = await db.execute(stmt)
        row = result.one()

        return AnalyticsSummaryResponse(
            device_id=device_id,
            period_type=period,
            total_readings=row.total_readings or 0,
            avg_uptime_pct=round(float(row.avg_uptime), 2) if row.avg_uptime is not None else None,
            avg_quality_pct=round(float(row.avg_quality_pct), 2) if row.avg_quality_pct is not None else None,
            tag_count=row.tag_count or 0,
        )

    async def compare_devices(
        self,
        device_ids: List[UUID],
        period: str,
        tag: str,
        db: AsyncSession,
    ) -> List[AnalyticsCompareItem]:
        # Get the latest period for each device+tag
        stmt = (
            select(DeviceAnalyticsModel)
            .where(
                DeviceAnalyticsModel.device_id.in_(device_ids),
                DeviceAnalyticsModel.period_type == period,
                DeviceAnalyticsModel.tag_name == tag,
            )
            .order_by(DeviceAnalyticsModel.period_start.desc())
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        # Keep only the latest period per device
        seen = set()
        items = []
        for r in rows:
            if r.device_id in seen:
                continue
            seen.add(r.device_id)
            items.append(
                AnalyticsCompareItem(
                    device_id=r.device_id,
                    tag_name=r.tag_name,
                    avg_value=r.avg_value,
                    min_value=r.min_value,
                    max_value=r.max_value,
                    reading_count=r.reading_count,
                    good_quality_pct=r.good_quality_pct,
                    trend_direction=r.trend_direction,
                )
            )
        return items

    async def get_trends(
        self,
        device_id: UUID,
        period: str,
        tag: str,
        db: AsyncSession,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> List[AnalyticsTrendPoint]:
        stmt = select(DeviceAnalyticsModel).where(
            DeviceAnalyticsModel.device_id == device_id,
            DeviceAnalyticsModel.period_type == period,
            DeviceAnalyticsModel.tag_name == tag,
        )
        if start:
            stmt = stmt.where(DeviceAnalyticsModel.period_start >= start)
        if end:
            stmt = stmt.where(DeviceAnalyticsModel.period_start <= end)
        stmt = stmt.order_by(DeviceAnalyticsModel.period_start.asc())

        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [
            AnalyticsTrendPoint(
                period_start=r.period_start,
                avg_value=r.avg_value,
                min_value=r.min_value,
                max_value=r.max_value,
                reading_count=r.reading_count,
                trend_direction=r.trend_direction,
                change_rate_pct=r.change_rate_pct,
            )
            for r in rows
        ]

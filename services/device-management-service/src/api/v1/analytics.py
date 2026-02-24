from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional, List
from datetime import datetime
import csv
import io
import json

from ...config.database import get_db
from ...services.analytics_service import AnalyticsService
from ...schemas.analytics_schema import (
    PeriodType,
    AnalyticsResponse,
    AnalyticsSummaryResponse,
    AnalyticsCompareItem,
    AnalyticsTrendPoint,
)

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])
service = AnalyticsService()


@router.get("/device/{device_id}", response_model=List[AnalyticsResponse])
async def get_device_analytics(
    device_id: UUID,
    period: PeriodType = Query(PeriodType.daily),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    tags: Optional[str] = Query(None, description="Comma-separated tag names"),
    db: AsyncSession = Depends(get_db),
):
    """Get analytics records for a device."""
    tag_list = tags.split(",") if tags else None
    return await service.get_device_analytics(device_id, period.value, db, start, end, tag_list)


@router.get("/device/{device_id}/summary", response_model=AnalyticsSummaryResponse)
async def get_device_summary(
    device_id: UUID,
    period: PeriodType = Query(PeriodType.daily),
    db: AsyncSession = Depends(get_db),
):
    """Get KPI summary for a device."""
    return await service.get_device_summary(device_id, period.value, db)


@router.get("/compare", response_model=List[AnalyticsCompareItem])
async def compare_devices(
    device_ids: str = Query(..., description="Comma-separated device UUIDs"),
    period: PeriodType = Query(PeriodType.daily),
    tag: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Compare analytics across devices for a specific tag."""
    ids = [UUID(d.strip()) for d in device_ids.split(",")]
    return await service.compare_devices(ids, period.value, tag, db)


@router.get("/trends/{device_id}", response_model=List[AnalyticsTrendPoint])
async def get_trends(
    device_id: UUID,
    period: PeriodType = Query(PeriodType.daily),
    tag: str = Query(...),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get trend time-series for a device tag."""
    return await service.get_trends(device_id, period.value, tag, db, start, end)


@router.get("/export")
async def export_analytics(
    device_id: UUID = Query(...),
    period: PeriodType = Query(PeriodType.daily),
    format: str = Query("csv", regex="^(csv|json)$"),
    tags: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Export analytics data as CSV or JSON."""
    tag_list = tags.split(",") if tags else None
    records = await service.get_device_analytics(device_id, period.value, db, tags=tag_list)

    data = [
        {
            "device_id": str(r.device_id),
            "tag_name": r.tag_name,
            "period_type": r.period_type,
            "period_start": r.period_start.isoformat(),
            "period_end": r.period_end.isoformat(),
            "min_value": r.min_value,
            "max_value": r.max_value,
            "avg_value": r.avg_value,
            "std_dev": r.std_dev,
            "reading_count": r.reading_count,
            "good_quality_pct": r.good_quality_pct,
            "uptime_seconds": r.uptime_seconds,
            "data_completeness_pct": r.data_completeness_pct,
            "trend_direction": r.trend_direction,
            "change_rate_pct": r.change_rate_pct,
            "anomaly_count": r.anomaly_count,
        }
        for r in records
    ]

    if format == "csv":
        output = io.StringIO()
        if data:
            writer = csv.DictWriter(output, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        content = output.getvalue()
        return StreamingResponse(
            iter([content]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=analytics.csv"},
        )

    return StreamingResponse(
        iter([json.dumps(data, indent=2)]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=analytics.json"},
    )

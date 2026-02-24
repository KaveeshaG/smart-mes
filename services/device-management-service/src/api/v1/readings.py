from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional, List
from datetime import datetime
import csv
import io
import json

from ...config.database import get_db
from ...services.device_registry import DeviceRegistry
from ...schemas.device_schema import (
    ReadingBatchRequest,
    ReadingLogResponse,
    ReadingQueryParams,
    ReadingSummary,
    SessionResponse,
    ExportFormat,
)

router = APIRouter(prefix="/api/v1/readings", tags=["readings"])
registry = DeviceRegistry()


@router.post("/batch", status_code=201)
async def store_readings_batch(
    request: ReadingBatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Store a batch of tag readings."""
    count = await registry.store_readings(request, db)
    return {"stored": count}


@router.get("", response_model=List[ReadingLogResponse])
async def get_readings(
    device_id: UUID = Query(...),
    tag_names: Optional[str] = Query(None, description="Comma-separated tag names"),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    session_id: Optional[str] = Query(None),
    limit: int = Query(1000, le=10000),
    db: AsyncSession = Depends(get_db),
):
    """Query historical readings with filters."""
    params = ReadingQueryParams(
        device_id=device_id,
        tag_names=tag_names.split(",") if tag_names else None,
        start_time=start_time,
        end_time=end_time,
        session_id=session_id,
        limit=limit,
    )
    return await registry.get_readings(params, db)


@router.get("/sessions", response_model=List[SessionResponse])
async def get_reading_sessions(
    device_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """List all recording sessions for a device."""
    return await registry.get_reading_sessions(device_id, db)


@router.get("/summary", response_model=List[ReadingSummary])
async def get_reading_summary(
    device_id: UUID = Query(...),
    session_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get min/max/avg/count per tag for a session or device."""
    return await registry.get_reading_summary(device_id, session_id, db)


@router.get("/export")
async def export_readings(
    device_id: UUID = Query(...),
    format: ExportFormat = Query(ExportFormat.csv),
    tag_names: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    session_id: Optional[str] = Query(None),
    limit: int = Query(10000, le=50000),
    db: AsyncSession = Depends(get_db),
):
    """Export readings as CSV or JSON."""
    params = ReadingQueryParams(
        device_id=device_id,
        tag_names=tag_names.split(",") if tag_names else None,
        start_time=start_time,
        end_time=end_time,
        session_id=session_id,
        limit=limit,
    )
    data = await registry.export_readings(params, db)

    if format == ExportFormat.csv:
        output = io.StringIO()
        if data:
            writer = csv.DictWriter(output, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        content = output.getvalue()
        return StreamingResponse(
            iter([content]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=readings.csv"},
        )

    return StreamingResponse(
        iter([json.dumps(data, indent=2)]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=readings.json"},
    )

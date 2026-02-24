from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func
from uuid import UUID
from typing import Optional
from datetime import datetime, timezone

from ...config.database import get_db
from ...models.db.machine_state_model import MachineStateModel

router = APIRouter(prefix="/api/v1/machine-state", tags=["Machine State"])


@router.get("/{device_id}/current")
async def get_current_state(device_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get current machine state and duration so far."""
    stmt = (
        select(MachineStateModel)
        .where(
            MachineStateModel.device_id == device_id,
            MachineStateModel.ended_at.is_(None),
        )
        .order_by(MachineStateModel.started_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    current = result.scalar_one_or_none()

    if current is None:
        return {"device_id": str(device_id), "state": None, "duration_seconds": 0}

    now = datetime.now(timezone.utc)
    duration = (now - current.started_at).total_seconds()

    return {
        "device_id": str(device_id),
        "state": current.state,
        "started_at": current.started_at.isoformat(),
        "duration_seconds": round(duration, 1),
    }


@router.get("/{device_id}/history")
async def get_state_history(
    device_id: UUID,
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get list of state transitions."""
    stmt = (
        select(MachineStateModel)
        .where(MachineStateModel.device_id == device_id)
        .order_by(MachineStateModel.started_at.asc())
    )

    if start:
        stmt = stmt.where(MachineStateModel.started_at >= start)
    if end:
        stmt = stmt.where(MachineStateModel.started_at <= end)

    result = await db.execute(stmt)
    records = result.scalars().all()

    return [
        {
            "device_id": str(r.device_id),
            "state": r.state,
            "started_at": r.started_at.isoformat(),
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "duration_seconds": r.duration_seconds,
        }
        for r in records
    ]


@router.get("/{device_id}/summary")
async def get_state_summary(
    device_id: UUID,
    period: str = Query("daily", regex="^(hourly|daily|weekly|monthly)$"),
    db: AsyncSession = Depends(get_db),
):
    """Get running/stopped/emergency/idle seconds and running percentage."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    period_deltas = {
        "hourly": timedelta(hours=1),
        "daily": timedelta(days=1),
        "weekly": timedelta(weeks=1),
        "monthly": timedelta(days=30),
    }
    delta = period_deltas[period]
    period_start = now - delta

    stmt = (
        select(MachineStateModel)
        .where(
            MachineStateModel.device_id == device_id,
            MachineStateModel.started_at >= period_start,
        )
        .order_by(MachineStateModel.started_at.asc())
    )
    result = await db.execute(stmt)
    records = result.scalars().all()

    totals = {
        "running_seconds": 0.0,
        "stopped_seconds": 0.0,
        "emergency_seconds": 0.0,
        "idle_seconds": 0.0,
    }
    state_change_count = 0

    for r in records:
        end_time = r.ended_at or now
        duration = (end_time - r.started_at).total_seconds()
        key = f"{r.state}_seconds"
        if key in totals:
            totals[key] += duration
        state_change_count += 1

    total_tracked = sum(totals.values())
    running_pct = round((totals["running_seconds"] / total_tracked) * 100, 2) if total_tracked > 0 else 0

    return {
        **totals,
        "running_pct": running_pct,
        "state_change_count": state_change_count,
    }

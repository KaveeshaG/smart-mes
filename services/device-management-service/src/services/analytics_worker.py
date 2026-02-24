import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func as sa_func, case
from sqlalchemy.dialects.postgresql import insert as pg_insert
from loguru import logger

from ..config.database import async_session
from ..models.db.device_model import ReadingLogModel
from ..models.db.analytics_model import DeviceAnalyticsModel, AnalyticsCheckpointModel


PERIOD_DELTAS = {
    "hourly": timedelta(hours=1),
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    "monthly": timedelta(days=30),
    "annual": timedelta(days=365),
}

# Default backfill windows (number of periods to look back when no checkpoint)
BACKFILL_WINDOWS = {
    "hourly": 168,   # 7 days
    "daily": 30,
    "weekly": 12,
    "monthly": 12,
    "annual": 5,
}


class AnalyticsWorker:
    def __init__(self, interval_seconds: int = 60):
        self._interval = interval_seconds
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.last_cycle_at: Optional[datetime] = None
        self.last_error: Optional[str] = None

    def start(self):
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self):
        # Wait a bit before the first run to let the app fully start
        await asyncio.sleep(5)
        while self._running:
            try:
                await self._run_cycle()
                self.last_cycle_at = datetime.now(timezone.utc)
                self.last_error = None
            except Exception as e:
                self.last_error = str(e)
                logger.error(f"Analytics worker error: {e}")
            await asyncio.sleep(self._interval)

    async def _run_cycle(self):
        now = datetime.now(timezone.utc)

        for period_type, delta in PERIOD_DELTAS.items():
            checkpoint_start = await self._get_checkpoint(period_type)

            if checkpoint_start is None:
                # No checkpoint — backfill from default window
                backfill_count = BACKFILL_WINDOWS[period_type]
                earliest = self._align_period_start(now - delta * backfill_count, period_type)
            else:
                earliest = checkpoint_start + delta

            current = self._align_period_start(now, period_type)

            # Iterate from earliest missed period up to (and including) current
            period_start = earliest
            while period_start <= current:
                period_end = period_start + delta
                await self._compute_period(period_type, period_start, period_end)
                await self._update_checkpoint(period_type, period_start)
                period_start = period_start + delta

    # ── checkpoint persistence ───────────────────────────────

    async def _get_checkpoint(self, period_type: str) -> Optional[datetime]:
        async with async_session() as db:
            stmt = select(AnalyticsCheckpointModel.last_computed_start).where(
                AnalyticsCheckpointModel.period_type == period_type
            )
            result = await db.execute(stmt)
            return result.scalar()

    async def _update_checkpoint(self, period_type: str, period_start: datetime):
        async with async_session() as db:
            now = datetime.now(timezone.utc)
            insert_stmt = pg_insert(AnalyticsCheckpointModel).values(
                period_type=period_type,
                last_computed_start=period_start,
                last_computed_at=now,
            )
            upsert_stmt = insert_stmt.on_conflict_do_update(
                index_elements=["period_type"],
                set_={
                    "last_computed_start": insert_stmt.excluded.last_computed_start,
                    "last_computed_at": insert_stmt.excluded.last_computed_at,
                },
            )
            await db.execute(upsert_stmt)
            await db.commit()

    # ── period computation (unchanged logic) ─────────────────

    async def _compute_period(
        self, period_type: str, period_start: datetime, period_end: datetime
    ):
        async with async_session() as db:
            # Get all device+tag combos with readings in this period
            combos_stmt = (
                select(
                    ReadingLogModel.device_id,
                    ReadingLogModel.tag_name,
                    sa_func.min(ReadingLogModel.value).label("min_val"),
                    sa_func.max(ReadingLogModel.value).label("max_val"),
                    sa_func.avg(ReadingLogModel.value).label("avg_val"),
                    sa_func.count(ReadingLogModel.id).label("cnt"),
                    sa_func.sum(
                        case(
                            (ReadingLogModel.quality == "good", 1),
                            else_=0,
                        )
                    ).label("good_cnt"),
                )
                .where(
                    ReadingLogModel.timestamp >= period_start,
                    ReadingLogModel.timestamp < period_end,
                    ReadingLogModel.value.is_not(None),
                )
                .group_by(ReadingLogModel.device_id, ReadingLogModel.tag_name)
            )

            result = await db.execute(combos_stmt)
            rows = result.all()

            if not rows:
                return

            for row in rows:
                device_id = row.device_id
                tag_name = row.tag_name
                cnt = row.cnt
                avg_val = float(row.avg_val) if row.avg_val is not None else None
                good_cnt = row.good_cnt or 0
                good_quality_pct = round((good_cnt / cnt) * 100, 2) if cnt > 0 else None

                # Compute std_dev separately
                std_dev = await self._compute_stddev(
                    db, device_id, tag_name, period_start, period_end
                )

                # Compute anomaly count (readings outside 2-sigma)
                anomaly_count = 0
                if avg_val is not None and std_dev is not None and std_dev > 0:
                    anomaly_stmt = (
                        select(sa_func.count(ReadingLogModel.id))
                        .where(
                            ReadingLogModel.device_id == device_id,
                            ReadingLogModel.tag_name == tag_name,
                            ReadingLogModel.timestamp >= period_start,
                            ReadingLogModel.timestamp < period_end,
                            ReadingLogModel.value.is_not(None),
                        )
                        .where(
                            sa_func.abs(ReadingLogModel.value - avg_val) > 2 * std_dev
                        )
                    )
                    anomaly_result = await db.execute(anomaly_stmt)
                    anomaly_count = anomaly_result.scalar() or 0

                # Compute uptime (time span covered by readings)
                time_stmt = (
                    select(
                        sa_func.min(ReadingLogModel.timestamp).label("first_ts"),
                        sa_func.max(ReadingLogModel.timestamp).label("last_ts"),
                    )
                    .where(
                        ReadingLogModel.device_id == device_id,
                        ReadingLogModel.tag_name == tag_name,
                        ReadingLogModel.timestamp >= period_start,
                        ReadingLogModel.timestamp < period_end,
                    )
                )
                time_result = await db.execute(time_stmt)
                time_row = time_result.one()
                uptime_seconds = None
                data_completeness_pct = None
                if time_row.first_ts and time_row.last_ts:
                    uptime_seconds = (time_row.last_ts - time_row.first_ts).total_seconds()
                    period_seconds = (period_end - period_start).total_seconds()
                    data_completeness_pct = round(
                        (uptime_seconds / period_seconds) * 100, 2
                    ) if period_seconds > 0 else None

                # Compute trend by comparing with previous period avg
                trend_direction, change_rate_pct = await self._compute_trend(
                    db, device_id, tag_name, period_type, period_start, avg_val
                )

                # Upsert into analytics table
                insert_stmt = pg_insert(DeviceAnalyticsModel).values(
                    device_id=device_id,
                    tag_name=tag_name,
                    period_type=period_type,
                    period_start=period_start,
                    period_end=period_end,
                    min_value=float(row.min_val) if row.min_val is not None else None,
                    max_value=float(row.max_val) if row.max_val is not None else None,
                    avg_value=round(avg_val, 4) if avg_val is not None else None,
                    std_dev=round(std_dev, 4) if std_dev is not None else None,
                    reading_count=cnt,
                    good_quality_pct=good_quality_pct,
                    uptime_seconds=uptime_seconds,
                    data_completeness_pct=data_completeness_pct,
                    trend_direction=trend_direction,
                    change_rate_pct=change_rate_pct,
                    anomaly_count=anomaly_count,
                    computed_at=sa_func.now(),
                )
                upsert_stmt = insert_stmt.on_conflict_do_update(
                    constraint="uq_device_tag_period",
                    set_={
                        "min_value": insert_stmt.excluded.min_value,
                        "max_value": insert_stmt.excluded.max_value,
                        "avg_value": insert_stmt.excluded.avg_value,
                        "std_dev": insert_stmt.excluded.std_dev,
                        "reading_count": insert_stmt.excluded.reading_count,
                        "good_quality_pct": insert_stmt.excluded.good_quality_pct,
                        "uptime_seconds": insert_stmt.excluded.uptime_seconds,
                        "data_completeness_pct": insert_stmt.excluded.data_completeness_pct,
                        "trend_direction": insert_stmt.excluded.trend_direction,
                        "change_rate_pct": insert_stmt.excluded.change_rate_pct,
                        "anomaly_count": insert_stmt.excluded.anomaly_count,
                        "period_end": insert_stmt.excluded.period_end,
                        "computed_at": insert_stmt.excluded.computed_at,
                    },
                )
                await db.execute(upsert_stmt)

            await db.commit()
            logger.debug(
                f"Analytics computed: {period_type} period starting {period_start} — {len(rows)} tag(s)"
            )

    async def _compute_stddev(
        self, db, device_id, tag_name, period_start, period_end
    ) -> Optional[float]:
        stmt = (
            select(sa_func.stddev(ReadingLogModel.value))
            .where(
                ReadingLogModel.device_id == device_id,
                ReadingLogModel.tag_name == tag_name,
                ReadingLogModel.timestamp >= period_start,
                ReadingLogModel.timestamp < period_end,
                ReadingLogModel.value.is_not(None),
            )
        )
        result = await db.execute(stmt)
        val = result.scalar()
        return float(val) if val is not None else None

    async def _compute_trend(
        self, db, device_id, tag_name, period_type, current_start, current_avg
    ):
        if current_avg is None:
            return None, None

        delta = PERIOD_DELTAS[period_type]
        prev_start = current_start - delta

        stmt = select(DeviceAnalyticsModel.avg_value).where(
            DeviceAnalyticsModel.device_id == device_id,
            DeviceAnalyticsModel.tag_name == tag_name,
            DeviceAnalyticsModel.period_type == period_type,
            DeviceAnalyticsModel.period_start == prev_start,
        )
        result = await db.execute(stmt)
        prev_avg = result.scalar()

        if prev_avg is None or prev_avg == 0:
            return "stable", 0.0

        change_rate = round(((current_avg - prev_avg) / abs(prev_avg)) * 100, 2)
        if change_rate > 1:
            direction = "up"
        elif change_rate < -1:
            direction = "down"
        else:
            direction = "stable"

        return direction, change_rate

    @staticmethod
    def _align_period_start(dt: datetime, period_type: str) -> datetime:
        if period_type == "hourly":
            return dt.replace(minute=0, second=0, microsecond=0)
        elif period_type == "daily":
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period_type == "weekly":
            # Snap to Monday
            days_since_monday = dt.weekday()
            monday = dt - timedelta(days=days_since_monday)
            return monday.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period_type == "monthly":
            return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif period_type == "annual":
            return dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return dt

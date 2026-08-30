"""
Parameter Registry — safety bounds store backed by Redis + PostgreSQL.

Redis layout per (device_id, tag_name):
  mes:safety:{device_id}:{tag_name}  → JSON serialised SafetyBounds dict
  mes:curval:{device_id}:{tag_name}  → float string (last known PLC value)

PostgreSQL (agent_safety_bounds table) is the persistent source of truth.
Redis is the fast read cache with a 5-minute TTL.

The Safety Agent ALWAYS queries this registry.  A missing entry → REJECT.
"""
import json
from typing import Optional

from loguru import logger
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config.database import AsyncSessionLocal
from ..models.db.safety_bounds_model import SafetyBoundsModel
from ..models.domain.agent_models import SafetyBounds

_SAFETY_PREFIX = "mes:safety"
_CURVAL_PREFIX = "mes:curval"
_CACHE_TTL = 300        # 5 minutes


class ParameterRegistry:

    def __init__(self, redis: Redis) -> None:
        self._r = redis

    # ── Safety bounds ─────────────────────────────────────────────────────────

    async def get_bounds(
        self, device_id: str, tag_name: str
    ) -> Optional[SafetyBounds]:
        """Return safety bounds or None if not configured."""
        key = f"{_SAFETY_PREFIX}:{device_id}:{tag_name}"
        raw = await self._r.get(key)

        if raw:
            data = json.loads(raw)
            return SafetyBounds(**data)

        # Cache miss → load from DB
        return await self._load_bounds_from_db(device_id, tag_name)

    async def get_all_bounds_for_device(
        self, device_id: str
    ) -> list[SafetyBounds]:
        """Return all configured safety bounds for a device."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SafetyBoundsModel).where(
                    SafetyBoundsModel.device_id == device_id,
                    SafetyBoundsModel.is_active.is_(True),
                )
            )
            rows = result.scalars().all()
            bounds_list = [self._row_to_domain(row) for row in rows]

        # Warm cache for all
        for b in bounds_list:
            await self._cache_bounds(b)

        return bounds_list

    async def upsert_bounds(self, bounds: SafetyBounds) -> SafetyBounds:
        """Persist safety bounds and warm Redis cache."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SafetyBoundsModel).where(
                    SafetyBoundsModel.device_id == bounds.device_id,
                    SafetyBoundsModel.tag_name == bounds.tag_name,
                )
            )
            row = result.scalar_one_or_none()

            if row:
                row.min_value = bounds.min_value
                row.max_value = bounds.max_value
                row.max_step_change = bounds.max_step_change
                row.unit = bounds.unit
                row.description = bounds.description
            else:
                row = SafetyBoundsModel(
                    device_id=bounds.device_id,
                    tag_name=bounds.tag_name,
                    min_value=bounds.min_value,
                    max_value=bounds.max_value,
                    max_step_change=bounds.max_step_change,
                    unit=bounds.unit,
                    description=bounds.description,
                )
                session.add(row)

            await session.commit()
            await session.refresh(row)

        result_bounds = self._row_to_domain(row)
        await self._cache_bounds(result_bounds)
        logger.info(
            f"Safety bounds upserted: {bounds.device_id}/{bounds.tag_name} "
            f"[{bounds.min_value}, {bounds.max_value}] step≤{bounds.max_step_change}"
        )
        return result_bounds

    async def delete_bounds(self, device_id: str, tag_name: str) -> bool:
        key = f"{_SAFETY_PREFIX}:{device_id}:{tag_name}"
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SafetyBoundsModel).where(
                    SafetyBoundsModel.device_id == device_id,
                    SafetyBoundsModel.tag_name == tag_name,
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                return False
            await session.delete(row)
            await session.commit()

        await self._r.delete(key)
        return True

    # ── Current value tracking ────────────────────────────────────────────────

    async def get_current_value(
        self, device_id: str, tag_name: str
    ) -> Optional[float]:
        """Return last known value or None (Redis only, updated after writes)."""
        key = f"{_CURVAL_PREFIX}:{device_id}:{tag_name}"
        raw = await self._r.get(key)
        return float(raw) if raw else None

    async def update_current_value(
        self, device_id: str, tag_name: str, value: float
    ) -> None:
        key = f"{_CURVAL_PREFIX}:{device_id}:{tag_name}"
        await self._r.set(key, str(value), ex=3600)     # TTL 1 h

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _load_bounds_from_db(
        self, device_id: str, tag_name: str
    ) -> Optional[SafetyBounds]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SafetyBoundsModel).where(
                    SafetyBoundsModel.device_id == device_id,
                    SafetyBoundsModel.tag_name == tag_name,
                    SafetyBoundsModel.is_active.is_(True),
                )
            )
            row = result.scalar_one_or_none()

        if not row:
            return None

        bounds = self._row_to_domain(row)
        await self._cache_bounds(bounds)
        return bounds

    async def _cache_bounds(self, b: SafetyBounds) -> None:
        key = f"{_SAFETY_PREFIX}:{b.device_id}:{b.tag_name}"
        data = {
            "device_id": b.device_id,
            "tag_name": b.tag_name,
            "min_value": b.min_value,
            "max_value": b.max_value,
            "max_step_change": b.max_step_change,
            "unit": b.unit,
            "description": b.description,
        }
        await self._r.set(key, json.dumps(data), ex=_CACHE_TTL)

    @staticmethod
    def _row_to_domain(row: SafetyBoundsModel) -> SafetyBounds:
        return SafetyBounds(
            device_id=row.device_id,
            tag_name=row.tag_name,
            min_value=row.min_value,
            max_value=row.max_value,
            max_step_change=row.max_step_change,
            unit=row.unit,
            description=row.description,
        )

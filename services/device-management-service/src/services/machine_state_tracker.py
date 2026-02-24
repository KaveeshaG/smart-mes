from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from ..config.database import async_session
from ..models.db.device_model import ReadingLogModel, TagModel
from ..models.db.machine_state_model import MachineStateModel

# Priority order: higher index wins
STATE_PRIORITY = ["idle", "running", "stopped", "emergency"]

# Map tag_category values to derived states
CATEGORY_TO_STATE = {
    "state_run": "running",
    "state_stop": "stopped",
    "state_emergency": "emergency",
    "state_idle": "idle",
}


class MachineStateTracker:
    """Derives machine state from tagged sensor readings."""

    async def evaluate_and_update(self, device_id: UUID) -> Optional[str]:
        """Evaluate current readings and update state if changed.

        Returns the new state string, or None if unchanged.
        """
        async with async_session() as db:
            new_state = await self._evaluate_device_state(device_id, db)
            if new_state is None:
                return None
            changed = await self._update_state(device_id, new_state, db)
            await db.commit()
            return new_state if changed else None

    async def _evaluate_device_state(
        self, device_id: UUID, db: AsyncSession
    ) -> Optional[str]:
        """Derive state from the latest readings for state-category tags."""

        # Find tags with a state category
        tag_stmt = select(TagModel.name, TagModel.tag_category).where(
            TagModel.device_id == device_id,
            TagModel.tag_category.in_(list(CATEGORY_TO_STATE.keys())),
        )
        tag_result = await db.execute(tag_stmt)
        state_tags = tag_result.all()

        if not state_tags:
            return None

        # For each state tag, get the most recent reading value
        active_state: Optional[str] = None
        active_priority = -1

        for tag_name, category in state_tags:
            reading_stmt = (
                select(ReadingLogModel.value)
                .where(
                    ReadingLogModel.device_id == device_id,
                    ReadingLogModel.tag_name == tag_name,
                )
                .order_by(ReadingLogModel.timestamp.desc())
                .limit(1)
            )
            reading_result = await db.execute(reading_stmt)
            value = reading_result.scalar()

            if value is not None and value == 1:
                mapped_state = CATEGORY_TO_STATE[category]
                priority = STATE_PRIORITY.index(mapped_state)
                if priority > active_priority:
                    active_priority = priority
                    active_state = mapped_state

        return active_state or "idle"

    async def _update_state(
        self, device_id: UUID, new_state: str, db: AsyncSession
    ) -> bool:
        """Close current state if different and open a new one.

        Returns True if the state actually changed.
        """
        now = datetime.now(timezone.utc)

        # Find current open state
        current_stmt = (
            select(MachineStateModel)
            .where(
                MachineStateModel.device_id == device_id,
                MachineStateModel.ended_at.is_(None),
            )
            .order_by(MachineStateModel.started_at.desc())
            .limit(1)
        )
        result = await db.execute(current_stmt)
        current = result.scalar_one_or_none()

        if current and current.state == new_state:
            return False  # no change

        # Close the old state
        if current:
            current.ended_at = now
            current.duration_seconds = (now - current.started_at).total_seconds()

        # Open new state
        new_record = MachineStateModel(
            device_id=device_id,
            state=new_state,
            started_at=now,
        )
        db.add(new_record)
        logger.info(f"Machine state for {device_id}: {new_state}")
        return True

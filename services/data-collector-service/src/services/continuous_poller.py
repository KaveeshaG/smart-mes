import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

from ..config.settings import Settings
from .connection_manager import ConnectionManager
from .data_reader import DataReader
from ..protocols.base import Tag, DataType


class ContinuousPoller:
    """Background service that continuously polls all registered devices."""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        data_reader: DataReader,
        settings: Settings,
    ):
        self._cm = connection_manager
        self._reader = data_reader
        self._settings = settings

        self._task: Optional[asyncio.Task] = None
        self._running = False

        # Cached device list from device-management
        self._devices: List[Dict[str, Any]] = []
        self._device_tags: Dict[str, List[Dict[str, Any]]] = {}  # device_id -> tags
        self._last_device_refresh: float = 0

        # Health / observability
        self.last_poll_at: Optional[datetime] = None
        self.poll_count: int = 0
        self.error_count: int = 0

    # ── lifecycle ────────────────────────────────────────────

    def start(self):
        if not self._settings.continuous_polling_enabled:
            logger.info("Continuous polling is disabled via settings")
            return
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

    @property
    def devices_count(self) -> int:
        return len(self._devices)

    # ── main loop ────────────────────────────────────────────

    async def _loop(self):
        # Give the app a moment to finish startup
        await asyncio.sleep(3)
        logger.info(
            f"Continuous poller started (interval={self._settings.poll_interval_seconds}s)"
        )

        while self._running:
            try:
                await self._maybe_refresh_devices()
                await self._poll_all_devices()
                self.last_poll_at = datetime.now(timezone.utc)
                self.poll_count += 1
            except Exception as exc:
                self.error_count += 1
                logger.error(f"Poller cycle error: {exc}")

            await asyncio.sleep(self._settings.poll_interval_seconds)

    # ── device list refresh ──────────────────────────────────

    async def _maybe_refresh_devices(self):
        now = asyncio.get_event_loop().time()
        if now - self._last_device_refresh < self._settings.device_refresh_interval_seconds:
            return
        await self._refresh_devices()
        self._last_device_refresh = now

    async def _refresh_devices(self):
        base = self._settings.device_management_url
        try:
            async with httpx.AsyncClient(timeout=10) as http:
                resp = await http.get(f"{base}/api/v1/devices")
                resp.raise_for_status()
                devices = resp.json()

                device_tags: Dict[str, List[Dict[str, Any]]] = {}
                for dev in devices:
                    dev_id = dev["id"]
                    tag_resp = await http.get(f"{base}/api/v1/devices/{dev_id}/tags")
                    tag_resp.raise_for_status()
                    device_tags[dev_id] = tag_resp.json()

                self._devices = devices
                self._device_tags = device_tags
                logger.info(
                    f"Device list refreshed: {len(devices)} device(s), "
                    f"{sum(len(t) for t in device_tags.values())} tag(s)"
                )
        except Exception as exc:
            logger.warning(f"Failed to refresh device list: {exc}")

    # ── polling ──────────────────────────────────────────────

    async def _poll_all_devices(self):
        if not self._devices:
            return

        for device in self._devices:
            try:
                await self._poll_device(device)
            except Exception as exc:
                logger.warning(
                    f"Poll failed for device {device.get('ip_address')}: {exc}"
                )

    async def _poll_device(self, device: Dict[str, Any]):
        dev_id = device["id"]
        ip = device["ip_address"]
        port = device.get("port") or 502
        protocol = device.get("primary_protocol", "modbus_tcp")
        tags_data = self._device_tags.get(dev_id, [])

        if not tags_data:
            return

        # Ensure connection is alive (Phase 3 resilience)
        await self._cm.ensure_connected(dev_id, ip, port, protocol)

        if not self._cm.is_connected(dev_id):
            return

        # Register tags if not already present
        connection = self._cm.get_connection(dev_id)
        if connection and not connection.tags:
            tag_objs = self._build_tags(tags_data)
            self._cm.register_tags(dev_id, tag_objs)

        tag_names = [t["name"] for t in tags_data]
        readings = await self._reader.read_multiple(dev_id, tag_names)

        if not readings:
            return

        # Build batch payload and POST to device-management
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        session_id = f"auto-{dev_id[:8]}-{today}"

        entries = []
        for r in readings:
            entries.append(
                {
                    "tag_name": r.tag_name,
                    "value": r.value,
                    "raw_value": str(r.value) if r.value is not None else None,
                    "quality": r.quality,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        payload = {
            "device_id": dev_id,
            "session_id": session_id,
            "readings": entries,
        }

        base = self._settings.device_management_url
        try:
            async with httpx.AsyncClient(timeout=10) as http:
                resp = await http.post(f"{base}/api/v1/readings/batch", json=payload)
                resp.raise_for_status()
        except Exception as exc:
            logger.warning(f"Failed to store readings for {dev_id}: {exc}")

    # ── helpers ──────────────────────────────────────────────

    @staticmethod
    def _build_tags(tags_data: List[Dict[str, Any]]) -> List[Tag]:
        result = []
        for t in tags_data:
            dt_str = t.get("data_type", "uint16").lower()
            try:
                dt = DataType(dt_str)
            except ValueError:
                dt = DataType.UINT16
            result.append(
                Tag(
                    name=t["name"],
                    address=t["address"],
                    data_type=dt,
                    access=t.get("access", "RW"),
                    description=t.get("description"),
                    unit=t.get("unit"),
                    scaling=t.get("scaling"),
                )
            )
        return result

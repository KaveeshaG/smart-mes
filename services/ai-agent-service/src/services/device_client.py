"""
Device Client — HTTP wrapper for device-management and data-collector services.

Follows the same httpx.AsyncClient pattern used in the existing ContinuousPoller.
Each method creates a short-lived client to avoid connection-pool ownership issues
in an asyncio multi-task environment.
"""
from datetime import datetime, timezone
from typing import Optional

import httpx
from loguru import logger

from ..config.settings import settings
from ..models.domain.agent_models import DeviceInfo, SensorReading, TagInfo

_HTTP_TIMEOUT = 8.0     # seconds; well within the 5s cycle (sense is sub-200ms on LAN)


class DeviceManagementClient:
    """Reads device metadata and recent sensor readings."""

    def __init__(self) -> None:
        self._base = settings.device_management_url

    async def get_all_devices(self) -> list[DeviceInfo]:
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as http:
                resp = await http.get(f"{self._base}/api/v1/devices")
                resp.raise_for_status()
                return [self._parse_device(d) for d in resp.json()]
        except Exception as exc:
            logger.warning(f"[DeviceClient] get_all_devices failed: {exc}")
            return []

    async def get_device_tags(self, device_id: str) -> list[TagInfo]:
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as http:
                resp = await http.get(
                    f"{self._base}/api/v1/devices/{device_id}/tags"
                )
                resp.raise_for_status()
                return [self._parse_tag(t) for t in resp.json()]
        except Exception as exc:
            logger.warning(f"[DeviceClient] get_device_tags({device_id}) failed: {exc}")
            return []

    async def get_latest_readings(
        self,
        device_id: str,
        limit: int = 50,
    ) -> list[SensorReading]:
        """
        Fetch the most recent readings for a device from device-management.
        These are the values that the continuous poller last sent via /readings/batch.
        """
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as http:
                resp = await http.get(
                    f"{self._base}/api/v1/readings",
                    params={"device_id": device_id, "limit": limit},
                )
                resp.raise_for_status()
                payload = resp.json()

                # Handle both list and paginated {"readings": [...]} responses
                rows = payload if isinstance(payload, list) else payload.get("readings", [])
                return [self._parse_reading(r) for r in rows]
        except Exception as exc:
            logger.warning(
                f"[DeviceClient] get_latest_readings({device_id}) failed: {exc}"
            )
            return []

    async def get_audit_history(
        self, device_id: str, limit: int = 5
    ) -> list[dict]:
        """
        Fetch recent agent audit records for closed-loop context.
        The optimisation agent uses this so the LLM can see the outcome of
        previous adjustments (avoids repeating ineffective changes).
        """
        # This endpoint is on the AI agent service itself (self-call would be circular).
        # The orchestrator passes history directly — this method is a placeholder
        # for cases where history is fetched externally.
        return []

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_device(d: dict) -> DeviceInfo:
        return DeviceInfo(
            id=str(d["id"]),
            name=d.get("name") or d.get("ip_address", "unknown"),
            ip_address=d.get("ip_address", ""),
            primary_protocol=d.get("primary_protocol", "modbus_tcp"),
            port=int(d.get("port") or 502),
        )

    @staticmethod
    def _parse_tag(t: dict) -> TagInfo:
        return TagInfo(
            name=t["name"],
            address=t.get("address", ""),
            data_type=t.get("data_type", "uint16"),
            access=t.get("access", "RW"),
            unit=t.get("unit"),
            description=t.get("description"),
        )

    @staticmethod
    def _parse_reading(r: dict) -> SensorReading:
        raw_ts = r.get("timestamp")
        if isinstance(raw_ts, str):
            try:
                ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            except ValueError:
                ts = datetime.now(timezone.utc)
        else:
            ts = datetime.now(timezone.utc)

        return SensorReading(
            device_id=str(r.get("device_id", "")),
            tag_name=str(r.get("tag_name", "")),
            value=float(r.get("value", 0.0)),
            quality=str(r.get("quality", "good")),
            timestamp=ts,
        )


class DataCollectorClient:
    """Writes PLC parameters via the data-collector write endpoint."""

    def __init__(self) -> None:
        self._base = settings.data_collector_url

    async def write_tag(
        self,
        device_id: str,
        tag_name: str,
        value: float,
    ) -> bool:
        """
        Write a single tag value to the PLC.
        Returns True on success, False on any failure.
        The data-collector applies its own machine-status safety check before
        executing the Modbus/FINS write.
        """
        payload = {
            "device_id": device_id,
            "tag_name": tag_name,
            "value": value,
        }
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as http:
                resp = await http.post(
                    f"{self._base}/api/v1/write/tag",
                    json=payload,
                )
                if resp.status_code == 200:
                    logger.info(
                        f"[DataCollectorClient] Write OK | "
                        f"device={device_id} | tag={tag_name} | value={value}"
                    )
                    return True
                else:
                    logger.warning(
                        f"[DataCollectorClient] Write failed | "
                        f"status={resp.status_code} | body={resp.text[:200]}"
                    )
                    return False
        except Exception as exc:
            logger.error(
                f"[DataCollectorClient] write_tag({device_id}/{tag_name}) error: {exc}"
            )
            return False

    async def read_all_tags_for_device(
        self,
        device_id: str,
        tag_names: list[str],
    ) -> list[SensorReading]:
        """
        Batch-read all tags for a device directly from the data collector.
        Used as a fallback when the device-management readings store has no
        recent data (e.g. Monitor page is open but recording is not active).
        """
        if not tag_names:
            return []

        now = datetime.now(timezone.utc)
        payload = {"device_id": device_id, "tag_names": tag_names}
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as http:
                resp = await http.post(
                    f"{self._base}/api/v1/read/multiple",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                # ReadResponse: {"device_id": ..., "readings": [...], "timestamp": ...}
                rows = data.get("readings", []) if isinstance(data, dict) else data
                result: list[SensorReading] = []
                for r in rows:
                    val = r.get("value")
                    if val is None:
                        continue
                    try:
                        result.append(SensorReading(
                            device_id=device_id,
                            tag_name=str(r.get("tag_name", "")),
                            value=float(val),
                            quality=str(r.get("quality", "good")),
                            timestamp=now,
                        ))
                    except (TypeError, ValueError):
                        continue
                return result
        except Exception as exc:
            logger.warning(
                f"[DataCollectorClient] read_all_tags_for_device({device_id}) "
                f"error: {exc}"
            )
            return []

    async def read_tag(
        self,
        device_id: str,
        tag_name: str,
    ) -> Optional[float]:
        """
        Read the live current value directly from the PLC.
        Used to refresh current_value in the parameter registry before validation.
        """
        payload = {"device_id": device_id, "tag_name": tag_name}
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as http:
                resp = await http.post(
                    f"{self._base}/api/v1/read/tag",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                val = data.get("value")
                return float(val) if val is not None else None
        except Exception as exc:
            logger.warning(
                f"[DataCollectorClient] read_tag({device_id}/{tag_name}) error: {exc}"
            )
            return None

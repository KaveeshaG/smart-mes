"""
Control Orchestrator — SENSE → INFER → VALIDATE → ACT loop.

Key design decisions:
  1. Timestamp tracking — each (device, tag) remembers the last processed
     reading timestamp.  Only genuinely NEW readings feed the baseline and
     trigger anomaly checks.  Without this, the same reading is re-added every
     poll cycle, poisoning the baseline so anomalies disappear after ~10 cycles.

  2. Boolean exclusion — digital (bool/coil/bit) tags are silently skipped;
     their 0/1 toggling is not an anomaly and caused ~$0.14/min LLM spend.

  3. Chronological processing — new readings for a tag are sorted oldest→newest
     before being fed to the baseline, so μ/σ build correctly even when
     multiple readings arrive between polls.

  4. Per-tag in-flight guard — prevents duplicate handlers for the same tag.

  5. EventBroadcaster — publishes SSE events so the frontend sees decisions
     in real time without polling every N seconds.
"""
import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from ..agents.monitoring_agent import MonitoringAgent
from ..agents.optimization_agent import OptimisationAgent
from ..agents.safety_agent import SafetyAgent
from ..config.settings import settings
from ..models.domain.agent_models import (
    ControlCycleAudit,
    DeviceInfo,
    OrchestratorMetrics,
    SensorReading,
    TagInfo,
)
from ..services.audit_logger import AuditLogger
from ..services.baseline_computer import BaselineComputer
from ..services.device_client import DataCollectorClient, DeviceManagementClient
from ..services.llm_service import LLMService
from ..services.parameter_registry import ParameterRegistry

# Data types that are purely digital (ON/OFF, TRUE/FALSE).
# Excluded from Z-score anomaly detection — their 0/1 toggling is normal
# behaviour, not an anomaly.
_BOOLEAN_DATA_TYPES = frozenset({
    "bool", "boolean", "bit", "coil", "uint1", "discrete",
})

# Sentinel for "no reading seen yet" — must be timezone-aware for comparison.
_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


# ── SSE event broadcaster ─────────────────────────────────────────────────────

class EventBroadcaster:
    """
    Fan-out broadcaster for Server-Sent Events.

    Each SSE client calls subscribe() to get its own asyncio.Queue.
    publish() puts events into every live subscriber queue.
    Dead queues (full = client too slow) are pruned automatically.
    """

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    async def publish(self, event: dict) -> None:
        dead = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self.unsubscribe(q)


# ── Orchestrator ──────────────────────────────────────────────────────────────

class ControlOrchestrator:
    """
    Singleton coordinator: owns the poll loop and all agent instances.

    Lifecycle:
        orchestrator = ControlOrchestrator(redis)
        await orchestrator.start()   # called from FastAPI lifespan
        ...
        await orchestrator.stop()    # graceful shutdown
    """

    def __init__(self, redis) -> None:
        self._redis = redis

        # ── Services ─────────────────────────────────────────────────────────
        self._baseline = BaselineComputer(redis)
        self._registry = ParameterRegistry(redis)
        self._audit = AuditLogger()
        self._device_mgmt = DeviceManagementClient()
        self._data_collector = DataCollectorClient()

        # ── Agents ───────────────────────────────────────────────────────────
        llm = LLMService()
        self._monitoring = MonitoringAgent(self._baseline, llm)
        self._optimisation = OptimisationAgent(llm)
        self._safety = SafetyAgent()

        # ── Real-time SSE ─────────────────────────────────────────────────────
        self.broadcaster = EventBroadcaster()

        # ── Concurrency ───────────────────────────────────────────────────────
        self._anomaly_sem = asyncio.Semaphore(
            settings.max_concurrent_anomaly_handlers
        )
        # Per-(device_id, tag_name) in-flight guard
        self._in_flight: set[tuple[str, str]] = set()

        # ── Timestamp tracking (THE critical bug fix) ─────────────────────────
        # Stores the timestamp of the last reading we processed per tag.
        # Only readings with timestamp > this value are fed to the baseline.
        # Without this, the same reading is re-added every 5s poll cycle,
        # poisoning the baseline so anomalies disappear after ~10 cycles.
        self._last_seen_ts: dict[str, dict[str, datetime]] = {}

        # ── Tag metadata cache ────────────────────────────────────────────────
        self._tag_cache: dict[str, dict[str, TagInfo]] = {}
        self._tag_cache_cycle: int = 0

        # ── Metrics ───────────────────────────────────────────────────────────
        self._metrics = OrchestratorMetrics()

        # ── Loop management ───────────────────────────────────────────────────
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._poll_task = asyncio.create_task(
            self._poll_loop(), name="orchestrator-poll"
        )
        logger.info(
            f"[Orchestrator] Started | poll_interval={settings.poll_interval_seconds}s | "
            f"zscore_window={settings.zscore_window} | threshold=±{settings.zscore_threshold}σ"
        )

    async def stop(self) -> None:
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        logger.info("[Orchestrator] Stopped")

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def metrics(self) -> OrchestratorMetrics:
        return self._metrics

    # ── Tag cache refresh ─────────────────────────────────────────────────────

    _TAG_REFRESH_CYCLES = 12   # every ~1 minute

    async def _refresh_tag_cache(self, devices: list[DeviceInfo]) -> None:
        for device in devices:
            try:
                tags = await self._device_mgmt.get_device_tags(device.id)
                self._tag_cache[device.id] = {t.name: t for t in tags}
                analog = sum(
                    1 for t in tags
                    if t.data_type.lower() not in _BOOLEAN_DATA_TYPES
                )
                logger.debug(
                    f"[Orchestrator] Tag cache | device={device.id} | "
                    f"total={len(tags)} analog={analog} "
                    f"digital={len(tags)-analog}"
                )
            except Exception as exc:
                logger.warning(
                    f"[Orchestrator] Tag cache refresh failed for {device.id}: {exc}"
                )

    # ── Core poll loop ────────────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        while self._running:
            cycle_start = time.monotonic()
            self._tag_cache_cycle += 1
            try:
                devices = await self._device_mgmt.get_all_devices()
                if not devices:
                    logger.warning(
                        "[Orchestrator] No devices returned — will retry next cycle"
                    )
                else:
                    if self._tag_cache_cycle % self._TAG_REFRESH_CYCLES == 1:
                        await self._refresh_tag_cache(devices)

                    await asyncio.gather(
                        *[self._sense_device(d) for d in devices],
                        return_exceptions=True,
                    )
            except Exception as exc:
                logger.error(f"[Orchestrator] Poll loop error: {exc}")

            elapsed = time.monotonic() - cycle_start
            sleep_for = max(0.0, settings.poll_interval_seconds - elapsed)
            await asyncio.sleep(sleep_for)

    # ── SENSE step ────────────────────────────────────────────────────────────

    async def _sense_device(self, device: DeviceInfo) -> None:
        """
        Fetch new readings for one device and run Z-score detection.

        *** Timestamp tracking is the critical correctness fix ***
        Without it, the same "latest reading" is re-added to the baseline on
        every 5s poll, making the baseline converge to the anomalous value
        and the Z-score drop back to 0 — anomalies become invisible.
        """
        try:
            # Fetch more readings so we have enough history on first startup.
            readings = await self._device_mgmt.get_latest_readings(
                device.id, limit=200
            )
        except Exception as exc:
            logger.warning(
                f"[Orchestrator] Could not fetch readings for {device.id}: {exc}"
            )
            readings = []

        # Fallback: if no stored readings in the DB (e.g. Monitor page is
        # open but the user hasn't enabled recording), read live values
        # directly from the data collector so the agent always has data.
        if not readings:
            live_tag_names = list(self._tag_cache.get(device.id, {}).keys())
            if live_tag_names:
                logger.debug(
                    f"[Orchestrator] No stored readings for {device.id} — "
                    "falling back to live data-collector read"
                )
                readings = await self._data_collector.read_all_tags_for_device(
                    device.id, live_tag_names
                )
            if not readings:
                return

        cached_tags = self._tag_cache.get(device.id, {})
        device_last = self._last_seen_ts.setdefault(device.id, {})

        # ── Group all readings by tag, filter to only NEW ones ────────────────
        new_by_tag: dict[str, list[SensorReading]] = {}
        for reading in readings:
            if reading.quality != "good":
                continue
            last_ts = device_last.get(reading.tag_name, _EPOCH)
            if reading.timestamp <= last_ts:
                continue   # already processed
            new_by_tag.setdefault(reading.tag_name, []).append(reading)

        if not new_by_tag:
            return   # no new data this cycle

        # ── Process each tag's new readings in chronological order ────────────
        for tag_name, tag_readings in new_by_tag.items():
            # Sort oldest → newest so the baseline builds correctly
            tag_readings.sort(key=lambda r: r.timestamp)

            tag_info = cached_tags.get(tag_name) or TagInfo(
                name=tag_name,
                address="",
                data_type="float",
                access="RW",
            )

            # Skip digital/boolean tags entirely
            if tag_info.data_type.lower() in _BOOLEAN_DATA_TYPES:
                device_last[tag_name] = tag_readings[-1].timestamp
                continue

            # Feed every new reading into the baseline
            z_result = None
            for reading in tag_readings:
                z_result = await self._baseline.add_reading(
                    device.id, tag_name, reading.value
                )

            # Update the last-seen timestamp to the newest reading
            device_last[tag_name] = tag_readings[-1].timestamp
            latest_reading = tag_readings[-1]

            if z_result is None or not z_result.is_anomaly:
                continue

            logger.info(
                f"[Orchestrator] NEW ANOMALY | device={device.id} | "
                f"tag={tag_name} | value={latest_reading.value} | "
                f"Z={z_result.z_score:.2f} | n={z_result.window_size}"
            )

            # Publish real-time event to SSE clients immediately
            await self.broadcaster.publish({
                "type": "anomaly_detected",
                "device_id": device.id,
                "tag_name": tag_name,
                "value": latest_reading.value,
                "z_score": round(z_result.z_score, 3),
                "mean": round(z_result.mean, 3),
                "timestamp": latest_reading.timestamp.isoformat(),
            })

            # Guard: skip if already handling this tag
            key = (device.id, tag_name)
            if key in self._in_flight:
                logger.debug(
                    f"[Orchestrator] Handler already running for {tag_name} — skipping"
                )
                continue

            self._in_flight.add(key)
            asyncio.create_task(
                self._handle_anomaly_guarded(
                    key, device, tag_info, latest_reading, z_result
                ),
                name=f"anomaly-{device.id}-{tag_name}",
            )

    # ── Anomaly handler ───────────────────────────────────────────────────────

    async def _handle_anomaly_guarded(
        self,
        key: tuple[str, str],
        device: DeviceInfo,
        tag: TagInfo,
        reading: SensorReading,
        z_result,
    ) -> None:
        try:
            await self._handle_anomaly(device, tag, reading, z_result)
        finally:
            self._in_flight.discard(key)

    async def _handle_anomaly(
        self,
        device: DeviceInfo,
        tag: TagInfo,
        reading: SensorReading,
        z_result,
    ) -> None:
        async with self._anomaly_sem:
            await self._run_infer_validate_act(device, tag, reading, z_result)

    async def _run_infer_validate_act(
        self,
        device: DeviceInfo,
        tag: TagInfo,
        reading: SensorReading,
        z_result,
    ) -> None:
        cycle_start_ms = time.monotonic() * 1000
        audit = ControlCycleAudit(
            timestamp=datetime.now(timezone.utc),
            device_id=device.id,
            tag_name=tag.name,
            z_score=z_result.z_score,
        )

        try:
            # ── 1. INFER: Monitoring Agent ────────────────────────────────────
            # Use classify_from_z_result (not process_reading) because
            # _sense_device already called baseline.add_reading for this value.
            # Calling process_reading here would add the same reading a second
            # time, poisoning the rolling mean/std and hiding future anomalies.
            monitoring_decision = await self._monitoring.classify_from_z_result(
                z_result, device, tag
            )
            audit.monitoring_decision = monitoring_decision

            # Publish monitoring result
            if monitoring_decision:
                await self.broadcaster.publish({
                    "type": "monitoring_decision",
                    "device_id": device.id,
                    "tag_name": tag.name,
                    "state": monitoring_decision.state,
                    "severity": monitoring_decision.severity,
                    "diagnosis": monitoring_decision.diagnosis,
                })

            if monitoring_decision is None or monitoring_decision.state == "Normal":
                audit.cycle_latency_ms = (time.monotonic() * 1000) - cycle_start_ms
                asyncio.create_task(self._audit.log(audit))
                return

            # ── 2. INFER: Optimisation Agent ──────────────────────────────────
            writable_bounds = await self._registry.get_all_bounds_for_device(device.id)
            recent_history = await self._audit.get_recent(device_id=device.id, limit=5)

            current_value = await self._data_collector.read_tag(device.id, tag.name)
            if current_value is None:
                current_value = await self._registry.get_current_value(
                    device.id, tag.name
                )
            if current_value is None:
                current_value = reading.value

            recommendation = await self._optimisation.recommend(
                monitoring=monitoring_decision,
                anomalous_tag=tag,
                current_value=current_value,
                device=device,
                writable_bounds=writable_bounds,
                recent_history=recent_history,
            )
            audit.recommendation = recommendation

            if recommendation is None:
                audit.cycle_latency_ms = (time.monotonic() * 1000) - cycle_start_ms
                asyncio.create_task(self._audit.log(audit))
                return

            # ── 3. VALIDATE: Safety Agent ─────────────────────────────────────
            bounds = await self._registry.get_bounds(
                device.id, recommendation.parameter
            )
            if bounds is None:
                safety_decision = self._safety.validate_no_bounds(
                    device.id, recommendation.parameter
                )
            else:
                safety_decision = self._safety.validate(
                    bounds=bounds,
                    proposed_value=recommendation.proposed_value,
                    current_value=current_value,
                )
            audit.safety_decision = safety_decision

            # ── 4. ACT ────────────────────────────────────────────────────────
            self._metrics.total_anomalies += 1

            if safety_decision.allow:
                audit.write_executed = True
                self._metrics.total_writes += 1

                success = await self._data_collector.write_tag(
                    device_id=device.id,
                    tag_name=recommendation.parameter,
                    value=recommendation.proposed_value,
                )
                audit.write_success = success

                if success:
                    self._metrics.total_writes_succeeded += 1
                    await self._registry.update_current_value(
                        device.id,
                        recommendation.parameter,
                        recommendation.proposed_value,
                    )

                # Publish write result
                await self.broadcaster.publish({
                    "type": "write_executed",
                    "device_id": device.id,
                    "tag_name": recommendation.parameter,
                    "from_value": current_value,
                    "to_value": recommendation.proposed_value,
                    "success": success,
                    "reasoning": recommendation.reasoning,
                })

                logger.info(
                    f"[Orchestrator] WRITE {'OK' if success else 'FAIL'} | "
                    f"device={device.id} | param={recommendation.parameter} | "
                    f"{current_value} → {recommendation.proposed_value}"
                )
            else:
                audit.write_executed = False
                self._metrics.total_safety_rejections += 1

                await self.broadcaster.publish({
                    "type": "safety_rejected",
                    "device_id": device.id,
                    "tag_name": recommendation.parameter,
                    "proposed_value": recommendation.proposed_value,
                    "reason": safety_decision.reason,
                })

                logger.info(
                    f"[Orchestrator] REJECTED | "
                    f"device={device.id} | param={recommendation.parameter} | "
                    f"reason={safety_decision.reason}"
                )

        except Exception as exc:
            logger.error(
                f"[Orchestrator] Cycle error | device={device.id} | "
                f"tag={tag.name} | {exc}"
            )
        finally:
            cycle_latency = (time.monotonic() * 1000) - cycle_start_ms
            audit.cycle_latency_ms = cycle_latency
            if audit.recommendation:
                audit.llm_latency_ms = audit.recommendation.llm_latency_ms

            self._metrics.record_cycle(cycle_latency)
            asyncio.create_task(self._audit.log(audit))

            logger.debug(
                f"[Orchestrator] Cycle done | device={device.id} | "
                f"tag={tag.name} | latency={cycle_latency:.0f}ms"
            )

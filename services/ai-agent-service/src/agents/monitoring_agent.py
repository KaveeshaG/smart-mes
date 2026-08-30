"""
Monitoring Agent — continuous anomaly detection.

Responsibility:
  Watches all sensor readings continuously.  On each reading it:
    1. Asks the BaselineComputer for the Z-score (< 2 ms, pure Redis).
    2. If |Z| ≤ threshold → tag as Normal, return immediately.
    3. If |Z| > threshold → call LLM to classify state and produce a diagnosis.
    4. Return MonitoringDecision to the orchestrator.

  Target accuracy: ≥ 90% F1-score on anomaly detection (research objective O3a).

  The LLM adds semantic context ("sealing temperature trending upward over 12
  minutes") that pure Z-score cannot provide, improving precision and reducing
  false-positive write triggers.
"""
from loguru import logger

from ..models.domain.agent_models import (
    DeviceInfo,
    MonitoringDecision,
    TagInfo,
    ZScoreResult,
)
from ..services.baseline_computer import BaselineComputer
from ..services.llm_service import LLMService


class MonitoringAgent:

    def __init__(self, baseline: BaselineComputer, llm: LLMService) -> None:
        self._baseline = baseline
        self._llm = llm

    async def process_reading(
        self,
        device: DeviceInfo,
        tag: TagInfo,
        value: float,
    ) -> tuple[ZScoreResult, MonitoringDecision | None]:
        """
        Add a reading to the baseline and classify if anomalous.
        Use this only when the baseline has NOT yet been updated for this value.
        Returns (z_result, decision) — decision is None when Normal.
        """
        z_result = await self._baseline.add_reading(device.id, tag.name, value)
        if not z_result.is_anomaly:
            return z_result, None
        decision = await self.classify_from_z_result(z_result, device, tag)
        return z_result, decision

    async def classify_from_z_result(
        self,
        z_result: ZScoreResult,
        device: DeviceInfo,
        tag: TagInfo,
    ) -> MonitoringDecision | None:
        """
        Classify an anomaly using a pre-computed ZScoreResult.
        Does NOT call add_reading — the caller has already updated the baseline.
        Call this from the orchestrator so readings are never added twice.
        """
        if not z_result.is_anomaly:
            return None

        logger.info(
            f"[MonitoringAgent] Anomaly | device={device.id} | tag={tag.name} | "
            f"value={z_result.value} | Z={z_result.z_score:.2f}"
        )

        recent_values = await self._baseline.get_recent_values(
            device.id, tag.name, n=20
        )

        decision = await self._llm.classify_anomaly(
            z_result=z_result,
            recent_values=recent_values,
            device_name=device.name,
            protocol=device.primary_protocol,
            unit=tag.unit or "",
        )

        logger.info(
            f"[MonitoringAgent] Classification | state={decision.state} | "
            f"severity={decision.severity} | llm_used={decision.llm_used} | "
            f"diagnosis={decision.diagnosis[:80]}"
        )

        return decision

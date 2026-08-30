"""
Optimisation Agent — LLM-powered parameter recommendation.

Responsibility:
  Given an anomaly classification from the Monitoring Agent, recommend ONE
  conservative parameter adjustment from the device's writable PLC registers.

  Design constraints (from research proposal §4.3):
    - Only parameters with configured safety bounds are eligible
    - Recommendations are conservative, incremental (the LLM is prompted to
      propose small step changes)
    - The raw LLM output is forwarded to the Safety Agent before any write
    - If LLM is unavailable, this agent returns None (no write triggered)

  Target accuracy: ≥ 85% (MAPE ≤ 15%) — research objective O3b.
"""
from typing import Optional
from loguru import logger

from ..models.domain.agent_models import (
    DeviceInfo,
    MonitoringDecision,
    ParameterRecommendation,
    SafetyBounds,
    TagInfo,
)
from ..services.llm_service import LLMService


class OptimisationAgent:

    def __init__(self, llm: LLMService) -> None:
        self._llm = llm

    async def recommend(
        self,
        monitoring: MonitoringDecision,
        anomalous_tag: TagInfo,
        current_value: float,
        device: DeviceInfo,
        writable_bounds: list[SafetyBounds],
        recent_history: list[dict],
    ) -> Optional[ParameterRecommendation]:
        """
        Generate a parameter recommendation.

        Args:
            monitoring:      Output from the Monitoring Agent.
            anomalous_tag:   The tag that triggered the anomaly.
            current_value:   Current value of the anomalous tag.
            device:          Device context.
            writable_bounds: Safety bounds for all eligible writable parameters.
            recent_history:  Last 5 audit log entries for this device (closed-loop
                             context so the LLM can learn from past adjustments).

        Returns:
            ParameterRecommendation or None if the LLM cannot provide one.
        """
        if not writable_bounds:
            logger.warning(
                f"[OptimisationAgent] No writable parameters with safety bounds "
                f"for device {device.id} — skipping recommendation"
            )
            return None

        # Build structured context for the LLM
        params_payload = [
            {
                "tag_name": b.tag_name,
                "unit": b.unit or "",
                "min": b.min_value,
                "max": b.max_value,
                "max_step": b.max_step_change,
                "description": b.description or "",
            }
            for b in writable_bounds
        ]

        recommendation = await self._llm.recommend_parameter(
            monitoring=monitoring,
            tag_name=anomalous_tag.name,
            current_value=current_value,
            unit=anomalous_tag.unit or "",
            writable_params=params_payload,
            recent_history=recent_history,
        )

        if recommendation is None:
            logger.warning(
                f"[OptimisationAgent] LLM returned no valid recommendation "
                f"for device {device.id}"
            )
            return None

        # Sanity-check: the recommended parameter must be in the writable list
        eligible_names = {b.tag_name for b in writable_bounds}
        if recommendation.parameter not in eligible_names:
            logger.warning(
                f"[OptimisationAgent] LLM recommended unknown parameter "
                f"'{recommendation.parameter}' — rejecting. "
                f"Eligible: {eligible_names}"
            )
            return None

        logger.info(
            f"[OptimisationAgent] Recommendation | parameter={recommendation.parameter} | "
            f"{recommendation.current_value} → {recommendation.proposed_value} | "
            f"confidence={recommendation.confidence:.2f} | "
            f"latency={recommendation.llm_latency_ms:.0f}ms"
        )
        return recommendation

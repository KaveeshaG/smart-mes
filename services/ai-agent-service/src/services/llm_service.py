"""
LLM Service — structured JSON outputs from a pluggable LLM backend.

Latency strategy (answers panelist <5s challenge):
  • Provider: Claude Haiku (cloud, default) or a local model via Ollama —
    see services/llm_providers.py. LLM_PROVIDER switches between them
    without touching prompts, parsing, or fallback logic, which is what
    lets provider be an independent variable in the comparative evaluation.
  • Hard timeout: 4.0 s for Anthropic / 15.0 s for Ollama by default
    (configurable) — local CPU inference is slower and more variable, so it
    gets its own budget rather than sharing the cloud one.
  • Fallback: if the LLM call fails, times out, or returns unparseable JSON,
    a deterministic rule-based response is returned so the control cycle
    never stalls — this applies identically regardless of provider.
  • Minimal prompts: sensor context is JSON-encoded with only the last 20
    readings.  Total input tokens ~400-500 → keeps small/fast models in
    their sweet spot on either backend.
"""
import json
import time
from typing import Optional

from loguru import logger

from ..config.settings import settings
from ..models.domain.agent_models import (
    MonitoringDecision,
    ParameterRecommendation,
    SafetyBounds,
    ZScoreResult,
)
from .llm_providers import create_provider

# ── Prompt templates ──────────────────────────────────────────────────────────

_MONITORING_SYSTEM = (
    "You are an industrial process monitoring AI for a tea packaging manufacturing "
    "line. Analyse sensor data anomalies and classify the process state. "
    "Respond ONLY with valid JSON — no markdown, no explanation outside the JSON."
)

_MONITORING_USER = """\
A statistical anomaly has been detected on the production line.

Device: {device_name} (Protocol: {protocol})
Tag: {tag_name} (Unit: {unit})
Current value: {value}
Z-score: {z_score:.2f}  (threshold = ±{threshold})
Rolling mean (last {window} readings): {mean:.4f}
Rolling std dev: {std:.4f}

Last 20 readings (oldest → newest):
{readings_json}

Respond with this exact JSON schema:
{{
  "state": "Normal" | "Warning" | "Anomaly",
  "severity": <integer 1–10>,
  "diagnosis": "<one sentence plain-English explanation>",
  "recommended_action": "<specific action or null>"
}}"""

_OPTIMISATION_SYSTEM = (
    "You are an industrial process optimisation AI for a tea packaging manufacturing "
    "line. Given a detected anomaly, recommend ONE conservative parameter adjustment "
    "from the available writable PLC registers. Prioritise incremental changes. "
    "Respond ONLY with valid JSON — no markdown, no explanation outside the JSON."
)

_OPTIMISATION_USER = """\
Production anomaly detected. Recommend a parameter adjustment.

Anomaly diagnosis: {diagnosis}
Severity: {severity}/10
Affected tag: {tag_name} (current value: {current_value} {unit})

Available writable parameters (with current values and safety bounds):
{parameters_json}

Last 5 adjustment outcomes for this device:
{history_json}

Respond with this exact JSON schema:
{{
  "parameter": "<tag_name from writable parameters>",
  "current_value": <float>,
  "proposed_value": <float>,
  "reasoning": "<plain English explanation for the operator, max 2 sentences>",
  "confidence": <float 0.0–1.0>,
  "expected_outcome": "<what production metric should improve>"
}}"""


class LLMService:
    """
    Async wrapper around a pluggable BaseLLMProvider (Anthropic or Ollama).
    Handles JSON parsing and graceful fallback; timeout is the active
    provider's responsibility (each backend has its own budget).
    """

    def __init__(self) -> None:
        if settings.llm_provider == "anthropic" and not settings.anthropic_api_key:
            logger.warning(
                "ANTHROPIC_API_KEY not set — LLM calls will use fallback path. "
                "Set the key in .env to enable autonomous AI reasoning."
            )
        self._provider = create_provider(settings)
        logger.info(
            f"[LLMService] provider={self._provider.provider_id} "
            f"model={self._provider.model_id}"
        )

    @property
    def provider_id(self) -> str:
        return self._provider.provider_id

    @property
    def model_id(self) -> str:
        return self._provider.model_id

    # ── Monitoring Agent call ─────────────────────────────────────────────────

    async def classify_anomaly(
        self,
        z_result: ZScoreResult,
        recent_values: list[float],
        device_name: str,
        protocol: str,
        unit: str,
    ) -> MonitoringDecision:
        """
        Ask the LLM to classify the current process state and provide a diagnosis.
        Returns a rule-based fallback if the LLM is unavailable or slow.
        """
        t0 = time.monotonic()

        readings_json = json.dumps(
            [round(v, 4) for v in recent_values[-20:]], separators=(",", ":")
        )

        prompt = _MONITORING_USER.format(
            device_name=device_name,
            protocol=protocol,
            tag_name=z_result.tag_name,
            unit=unit or "–",
            value=z_result.value,
            z_score=z_result.z_score,
            threshold=settings.zscore_threshold,
            window=z_result.window_size,
            mean=z_result.mean,
            std=z_result.std,
            readings_json=readings_json,
        )

        raw = await self._call_llm(_MONITORING_SYSTEM, prompt, tag="monitoring")
        llm_ms = (time.monotonic() - t0) * 1000

        if raw is None:
            return self._fallback_monitoring(z_result)

        try:
            data = json.loads(raw)
            return MonitoringDecision(
                state=data.get("state", "Anomaly"),
                severity=int(data.get("severity", 7)),
                diagnosis=data.get("diagnosis", "Anomaly detected"),
                recommended_action=data.get("recommended_action"),
                z_score=z_result.z_score,
                llm_used=True,
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning(f"LLM JSON parse error in classify_anomaly: {exc} — raw: {raw[:200]}")
            return self._fallback_monitoring(z_result)

    # ── Optimisation Agent call ───────────────────────────────────────────────

    async def recommend_parameter(
        self,
        monitoring: MonitoringDecision,
        tag_name: str,
        current_value: float,
        unit: str,
        writable_params: list[dict],
        recent_history: list[dict],
    ) -> Optional[ParameterRecommendation]:
        """
        Ask the LLM to recommend a parameter change.
        Returns None if the LLM is unavailable or produces an invalid response.
        """
        t0 = time.monotonic()

        params_json = json.dumps(writable_params, separators=(",", ":"), indent=None)
        hist_json = json.dumps(recent_history[-5:], separators=(",", ":"), indent=None)

        prompt = _OPTIMISATION_USER.format(
            diagnosis=monitoring.diagnosis,
            severity=monitoring.severity,
            tag_name=tag_name,
            current_value=current_value,
            unit=unit or "–",
            parameters_json=params_json,
            history_json=hist_json or "[]",
        )

        raw = await self._call_llm(_OPTIMISATION_SYSTEM, prompt, tag="optimisation")
        llm_ms = (time.monotonic() - t0) * 1000

        if raw is None:
            return None

        try:
            data = json.loads(raw)
            return ParameterRecommendation(
                parameter=data["parameter"],
                current_value=float(data["current_value"]),
                proposed_value=float(data["proposed_value"]),
                reasoning=data.get("reasoning", ""),
                confidence=float(data.get("confidence", 0.5)),
                expected_outcome=data.get("expected_outcome", ""),
                llm_latency_ms=round(llm_ms, 1),
            )
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
            logger.warning(f"LLM JSON parse error in recommend_parameter: {exc} — raw: {raw[:200]}")
            return None

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        tag: str = "llm",
    ) -> Optional[str]:
        """
        Execute a single LLM call via the active provider.
        Returns the raw text content or None on failure/timeout.
        """
        return await self._provider.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=256,
            tag=tag,
        )

    # ── Fallback (deterministic rule-based) ───────────────────────────────────

    @staticmethod
    def _fallback_monitoring(z: ZScoreResult) -> MonitoringDecision:
        """
        Rule-based fallback when LLM is unavailable.
        Severity is scaled linearly from Z-score magnitude.
        """
        abs_z = abs(z.z_score)
        if abs_z > 5:
            state, severity = "Anomaly", 9
        elif abs_z > 4:
            state, severity = "Anomaly", 7
        else:
            state, severity = "Warning", 5

        direction = "above" if z.z_score > 0 else "below"
        diagnosis = (
            f"{z.tag_name} is {abs_z:.1f}σ {direction} the rolling mean "
            f"({z.mean:.3f} ± {z.std:.3f}). Rule-based fallback (LLM unavailable)."
        )
        return MonitoringDecision(
            state=state,
            severity=severity,
            diagnosis=diagnosis,
            recommended_action=None,
            z_score=z.z_score,
            llm_used=False,
        )

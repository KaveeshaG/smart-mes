"""
Safety Agent — deterministic, rule-based validation gate.

Design principle (§4.3 of research proposal):
  This agent does NOT use LLM inference.  It is a pure Python predicate
  engine that intercepts every recommendation before any PLC write.

  S = { p ∈ ℝ | p_min ≤ p ≤ p_max  AND  |p − p_current| ≤ Δ_max }
  ALLOW(p_new) = 1  ⟺  p_new ∈ S          [equations 2–3, §4.4.2]

  100% compliance is guaranteed by construction — there are no probabilistic
  code paths.  This directly answers H3 and the panelist challenge on safety.

  Typical execution time: < 1 ms (pure in-memory dict lookup).
"""
from loguru import logger
from ..models.domain.agent_models import SafetyBounds, SafetyDecision


class SafetyAgent:
    """
    Validates proposed PLC parameter changes against a pre-configured
    safety envelope.

    The agent is stateless per call; safety bounds are injected by the
    ParameterRegistry which owns the Redis/DB backed store.
    """

    def validate(
        self,
        bounds: SafetyBounds,
        proposed_value: float,
        current_value: float,
    ) -> SafetyDecision:
        """
        Run all safety predicates.  Returns ALLOW only if every predicate passes.
        Short-circuits on first failure to ensure predictable latency.
        """
        tag = bounds.tag_name
        device = bounds.device_id

        # ── Predicate 1: absolute lower bound ────────────────────────────────
        if proposed_value < bounds.min_value:
            reason = (
                f"BELOW minimum: proposed={proposed_value:.4f} < "
                f"min={bounds.min_value:.4f} {bounds.unit or ''}"
            )
            logger.warning(f"[SAFETY REJECT] {device}/{tag} — {reason}")
            return SafetyDecision(
                allow=False,
                reason=reason,
                parameter=tag,
                proposed_value=proposed_value,
                current_value=current_value,
            )

        # ── Predicate 2: absolute upper bound ────────────────────────────────
        if proposed_value > bounds.max_value:
            reason = (
                f"ABOVE maximum: proposed={proposed_value:.4f} > "
                f"max={bounds.max_value:.4f} {bounds.unit or ''}"
            )
            logger.warning(f"[SAFETY REJECT] {device}/{tag} — {reason}")
            return SafetyDecision(
                allow=False,
                reason=reason,
                parameter=tag,
                proposed_value=proposed_value,
                current_value=current_value,
            )

        # ── Predicate 3: maximum single-step change ───────────────────────────
        step = abs(proposed_value - current_value)
        if step > bounds.max_step_change:
            reason = (
                f"STEP TOO LARGE: |{proposed_value:.4f} - {current_value:.4f}| = "
                f"{step:.4f} > max_step={bounds.max_step_change:.4f} {bounds.unit or ''}"
            )
            logger.warning(f"[SAFETY REJECT] {device}/{tag} — {reason}")
            return SafetyDecision(
                allow=False,
                reason=reason,
                parameter=tag,
                proposed_value=proposed_value,
                current_value=current_value,
            )

        # ── All predicates passed ─────────────────────────────────────────────
        logger.info(
            f"[SAFETY ALLOW] {device}/{tag} "
            f"{current_value:.4f} → {proposed_value:.4f} {bounds.unit or ''}"
        )
        return SafetyDecision(
            allow=True,
            reason="All safety predicates passed",
            parameter=tag,
            proposed_value=proposed_value,
            current_value=current_value,
        )

    def validate_no_bounds(self, device_id: str, tag_name: str) -> SafetyDecision:
        """
        Called when no safety bounds are configured for the tag.
        Always REJECT — writing to an unconfigured parameter is unsafe.
        """
        reason = (
            f"No safety bounds configured for {device_id}/{tag_name}. "
            "Configure bounds via POST /api/v1/agent/safety-bounds before "
            "autonomous writes are permitted."
        )
        logger.error(f"[SAFETY REJECT] {reason}")
        return SafetyDecision(
            allow=False,
            reason=reason,
            parameter=tag_name,
            proposed_value=0.0,
            current_value=0.0,
        )

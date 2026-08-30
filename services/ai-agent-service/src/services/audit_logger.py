"""
Audit Logger — immutable record of every control cycle decision.

Every anomaly-triggered cycle writes one row to agent_audit_log regardless
of outcome (Normal classification, safety rejection, write success/failure).
This provides:
  - Complete evidence trail for safety compliance (100% write coverage)
  - Ground-truth labels for AI accuracy evaluation (research §4.4.5)
  - Raw data for latency histogram generation (§4.4.3)
  - OEE correlation data (§4.4.4)

The write is fully async and non-blocking — it does NOT extend the control
cycle latency because it runs AFTER the PLC write is executed.
"""
from datetime import datetime, timezone
from loguru import logger

from ..config.database import AsyncSessionLocal
from ..models.db.audit_model import AgentAuditLog
from ..models.domain.agent_models import ControlCycleAudit
from ..config.settings import settings


class AuditLogger:

    async def log(self, audit: ControlCycleAudit) -> None:
        """
        Persist one control cycle audit record.
        Called from inside a fire-and-forget asyncio.create_task so it never
        blocks the orchestrator's main loop.
        """
        try:
            async with AsyncSessionLocal() as session:
                row = AgentAuditLog(
                    timestamp=audit.timestamp or datetime.now(timezone.utc),
                    device_id=audit.device_id,
                    tag_name=audit.tag_name,
                    z_score=audit.z_score,
                    z_mean=audit.monitoring_decision.z_score if audit.monitoring_decision else None,
                    process_state=audit.monitoring_decision.state if audit.monitoring_decision else None,
                    severity=audit.monitoring_decision.severity if audit.monitoring_decision else None,
                    diagnosis=audit.monitoring_decision.diagnosis if audit.monitoring_decision else None,
                    monitoring_llm_used=(
                        audit.monitoring_decision.llm_used if audit.monitoring_decision else None
                    ),
                    parameter_name=(
                        audit.recommendation.parameter if audit.recommendation else None
                    ),
                    current_value=(
                        audit.recommendation.current_value if audit.recommendation else None
                    ),
                    proposed_value=(
                        audit.recommendation.proposed_value if audit.recommendation else None
                    ),
                    llm_reasoning=(
                        audit.recommendation.reasoning if audit.recommendation else None
                    ),
                    llm_confidence=(
                        audit.recommendation.confidence if audit.recommendation else None
                    ),
                    expected_outcome=(
                        audit.recommendation.expected_outcome if audit.recommendation else None
                    ),
                    safety_decision=(
                        "ALLOW" if audit.safety_decision and audit.safety_decision.allow
                        else ("REJECT" if audit.safety_decision else None)
                    ),
                    safety_reason=(
                        audit.safety_decision.reason if audit.safety_decision else None
                    ),
                    write_executed=audit.write_executed,
                    write_success=audit.write_success if audit.write_executed else None,
                    cycle_latency_ms=audit.cycle_latency_ms,
                    llm_latency_ms=audit.llm_latency_ms,
                    llm_model=(
                        settings.ollama_model if settings.llm_provider == "ollama"
                        else settings.llm_model
                    ),
                    llm_provider=settings.llm_provider,
                )
                session.add(row)
                await session.commit()

        except Exception as exc:
            # Audit failure must NEVER affect the control cycle
            logger.error(f"[AuditLogger] Failed to persist audit record: {exc}")

    async def get_recent(
        self, device_id: str | None = None, limit: int = 50
    ) -> list[dict]:
        """Return recent audit records as dicts for the API layer."""
        from sqlalchemy import select, desc
        try:
            async with AsyncSessionLocal() as session:
                q = select(AgentAuditLog).order_by(
                    desc(AgentAuditLog.timestamp)
                ).limit(limit)
                if device_id:
                    q = q.where(AgentAuditLog.device_id == device_id)
                result = await session.execute(q)
                rows = result.scalars().all()
                return [self._row_to_dict(r) for r in rows]
        except Exception as exc:
            logger.error(f"[AuditLogger] Failed to fetch audit records: {exc}")
            return []

    @staticmethod
    def _row_to_dict(row: AgentAuditLog) -> dict:
        return {
            "id": row.id,
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "device_id": row.device_id,
            "tag_name": row.tag_name,
            "z_score": row.z_score,
            "process_state": row.process_state,
            "severity": row.severity,
            "diagnosis": row.diagnosis,
            "parameter_name": row.parameter_name,
            "current_value": row.current_value,
            "proposed_value": row.proposed_value,
            "llm_reasoning": row.llm_reasoning,
            "llm_confidence": row.llm_confidence,
            "safety_decision": row.safety_decision,
            "safety_reason": row.safety_reason,
            "write_executed": row.write_executed,
            "write_success": row.write_success,
            "cycle_latency_ms": row.cycle_latency_ms,
            "llm_latency_ms": row.llm_latency_ms,
            "llm_model": row.llm_model,
            "llm_provider": row.llm_provider,
        }

from datetime import datetime
from sqlalchemy import (
    Integer, String, Float, Boolean, Text,
    DateTime, func
)
from sqlalchemy.orm import Mapped, mapped_column
from ...config.database import Base


class AgentAuditLog(Base):
    """
    Immutable audit record for every anomaly-triggered control cycle.
    Covers: SENSE → INFER → VALIDATE → ACT with full latency breakdown.
    Used for:
      - Research evaluation (F1-score, latency histograms, OEE correlation)
      - Operator review of autonomous decisions
      - Safety compliance evidence (100% write coverage)
    """
    __tablename__ = "agent_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # ── Monitoring Agent output ───────────────────────────────
    tag_name: Mapped[str] = mapped_column(String(255), nullable=True)
    z_score: Mapped[float] = mapped_column(Float, nullable=True)
    z_mean: Mapped[float] = mapped_column(Float, nullable=True)
    z_std: Mapped[float] = mapped_column(Float, nullable=True)
    process_state: Mapped[str] = mapped_column(String(20), nullable=True)   # Normal/Warning/Anomaly
    severity: Mapped[int] = mapped_column(Integer, nullable=True)           # 1–10
    diagnosis: Mapped[str] = mapped_column(Text, nullable=True)
    monitoring_llm_used: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── Optimisation Agent output ─────────────────────────────
    parameter_name: Mapped[str] = mapped_column(String(255), nullable=True)
    current_value: Mapped[float] = mapped_column(Float, nullable=True)
    proposed_value: Mapped[float] = mapped_column(Float, nullable=True)
    llm_reasoning: Mapped[str] = mapped_column(Text, nullable=True)
    llm_confidence: Mapped[float] = mapped_column(Float, nullable=True)
    expected_outcome: Mapped[str] = mapped_column(Text, nullable=True)

    # ── Safety Agent output ───────────────────────────────────
    safety_decision: Mapped[str] = mapped_column(String(10), nullable=True)  # ALLOW / REJECT
    safety_reason: Mapped[str] = mapped_column(Text, nullable=True)

    # ── ACT outcome ───────────────────────────────────────────
    write_executed: Mapped[bool] = mapped_column(Boolean, default=False)
    write_success: Mapped[bool] = mapped_column(Boolean, nullable=True)

    # ── Latency instrumentation (research KPIs) ───────────────
    cycle_latency_ms: Mapped[float] = mapped_column(Float, nullable=True)
    llm_latency_ms: Mapped[float] = mapped_column(Float, nullable=True)
    llm_model: Mapped[str] = mapped_column(String(100), nullable=True)
    # "anthropic" | "ollama" — the independent variable for the cloud-vs-local
    # comparative evaluation. Existing rows predate this column and read NULL.
    llm_provider: Mapped[str] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

"""
Pydantic request / response schemas for the AI Agent Service REST API.

Kept separate from domain models so the API contract can evolve independently.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Safety Bounds ─────────────────────────────────────────────────────────────

class SafetyBoundsRequest(BaseModel):
    device_id: str
    tag_name: str
    min_value: float
    max_value: float
    max_step_change: float
    unit: Optional[str] = None
    description: Optional[str] = None

    model_config = {"json_schema_extra": {
        "example": {
            "device_id": "1",
            "tag_name": "sealing_temp",
            "min_value": 140.0,
            "max_value": 200.0,
            "max_step_change": 5.0,
            "unit": "°C",
            "description": "Sealing jaw temperature",
        }
    }}


class SafetyBoundsResponse(BaseModel):
    device_id: str
    tag_name: str
    min_value: float
    max_value: float
    max_step_change: float
    unit: Optional[str]
    description: Optional[str]


# ── Audit ─────────────────────────────────────────────────────────────────────

class AuditRecord(BaseModel):
    id: Optional[int]
    timestamp: Optional[str]
    device_id: Optional[str]
    tag_name: Optional[str]
    z_score: Optional[float]
    process_state: Optional[str]
    severity: Optional[int]   # 1–10 from MonitoringDecision
    diagnosis: Optional[str]
    parameter_name: Optional[str]
    current_value: Optional[float]
    proposed_value: Optional[float]
    llm_reasoning: Optional[str]
    llm_confidence: Optional[float]
    safety_decision: Optional[str]
    safety_reason: Optional[str]
    write_executed: Optional[bool]
    write_success: Optional[bool]
    cycle_latency_ms: Optional[float]
    llm_latency_ms: Optional[float]
    llm_model: Optional[str]
    llm_provider: Optional[str]


class AuditResponse(BaseModel):
    records: list[AuditRecord]
    total: int


# ── Status / Metrics ──────────────────────────────────────────────────────────

class AgentStatusResponse(BaseModel):
    status: str                         # "running" | "stopped"
    total_cycles: int
    anomalies_detected: int
    writes_executed: int
    writes_succeeded: int
    uptime_seconds: Optional[float]


class MetricsResponse(BaseModel):
    total_cycles: int
    anomalies_detected: int
    writes_executed: int
    writes_succeeded: int
    p50_latency_ms: Optional[float]
    p95_latency_ms: Optional[float]
    p99_latency_ms: Optional[float]
    latency_samples: int


# ── Manual Override ───────────────────────────────────────────────────────────

class OverrideRequest(BaseModel):
    device_id: str
    tag_name: str
    value: float
    reason: str = Field(..., min_length=5, description="Human-readable justification")

    model_config = {"json_schema_extra": {
        "example": {
            "device_id": "1",
            "tag_name": "sealing_temp",
            "value": 165.0,
            "reason": "Manual calibration after maintenance",
        }
    }}


class OverrideResponse(BaseModel):
    success: bool
    message: str
    safety_checked: bool
    write_executed: bool

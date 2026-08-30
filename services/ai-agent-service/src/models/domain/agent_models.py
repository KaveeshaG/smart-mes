"""
Domain models for the AI agent layer.
All are plain dataclasses — no ORM, no network I/O.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


# ── Raw data from device-management ──────────────────────────────────────────

@dataclass
class DeviceInfo:
    id: str
    name: str
    ip_address: str
    primary_protocol: str   # fins_tcp | modbus_tcp
    port: int = 502


@dataclass
class TagInfo:
    name: str
    address: str
    data_type: str          # uint16 | int16 | float32 | bool …
    access: str             # RW | RO
    unit: Optional[str] = None
    description: Optional[str] = None


@dataclass
class SensorReading:
    device_id: str
    tag_name: str
    value: float
    quality: str            # good | bad
    timestamp: datetime


# ── Z-score baseline result ───────────────────────────────────────────────────

@dataclass
class ZScoreResult:
    device_id: str
    tag_name: str
    value: float
    z_score: float
    mean: float
    std: float
    window_size: int        # how many readings were used
    is_anomaly: bool


# ── Monitoring Agent output ───────────────────────────────────────────────────

@dataclass
class MonitoringDecision:
    state: str              # Normal | Warning | Anomaly
    severity: int           # 1–10
    diagnosis: str
    recommended_action: Optional[str]
    z_score: float
    llm_used: bool = True   # False when fallback rule-based path fired


# ── Safety bounds (loaded from DB / Redis) ────────────────────────────────────

@dataclass
class SafetyBounds:
    device_id: str
    tag_name: str
    min_value: float
    max_value: float
    max_step_change: float
    unit: Optional[str] = None
    description: Optional[str] = None


# ── Optimisation Agent output ─────────────────────────────────────────────────

@dataclass
class ParameterRecommendation:
    parameter: str
    current_value: float
    proposed_value: float
    reasoning: str          # plain English for operator display
    confidence: float       # 0.0–1.0
    expected_outcome: str
    llm_latency_ms: float = 0.0


# ── Safety Agent output ───────────────────────────────────────────────────────

@dataclass
class SafetyDecision:
    allow: bool
    reason: str             # human-readable; logged in audit trail
    parameter: str
    proposed_value: float
    current_value: float


# ── Full control-cycle audit record ──────────────────────────────────────────

@dataclass
class ControlCycleAudit:
    device_id: str
    timestamp: datetime
    tag_name: Optional[str] = None
    z_score: Optional[float] = None
    monitoring_decision: Optional[MonitoringDecision] = None
    recommendation: Optional[ParameterRecommendation] = None
    safety_decision: Optional[SafetyDecision] = None
    write_executed: bool = False
    write_success: bool = False
    cycle_latency_ms: float = 0.0
    llm_latency_ms: float = 0.0
    llm_model: str = ""


# ── Orchestrator runtime metrics (exposed via API) ────────────────────────────

@dataclass
class OrchestratorMetrics:
    total_cycles: int = 0
    total_anomalies: int = 0
    total_writes: int = 0
    total_writes_succeeded: int = 0
    total_safety_rejections: int = 0
    total_llm_calls: int = 0
    total_llm_fallbacks: int = 0
    latency_samples: List[float] = field(default_factory=list)
    last_cycle_at: Optional[datetime] = None

    # ── Convenience aliases used by the API layer ─────────────────────────────
    @property
    def anomalies_detected(self) -> int:
        return self.total_anomalies

    @property
    def writes_executed(self) -> int:
        return self.total_writes

    @property
    def writes_succeeded(self) -> int:
        return self.total_writes_succeeded

    @property
    def _latencies(self) -> List[float]:
        """Alias so the API layer can read len(m._latencies) for sample count."""
        return self.latency_samples

    def record_cycle(self, latency_ms: float) -> None:
        self.total_cycles += 1
        self.last_cycle_at = datetime.utcnow()
        self.latency_samples.append(latency_ms)
        # Keep only the last 1 000 samples for memory efficiency
        if len(self.latency_samples) > 1000:
            self.latency_samples = self.latency_samples[-1000:]

    @property
    def p50_ms(self) -> float:
        if not self.latency_samples:
            return 0.0
        s = sorted(self.latency_samples)
        return s[len(s) // 2]

    @property
    def p95_ms(self) -> float:
        if not self.latency_samples:
            return 0.0
        s = sorted(self.latency_samples)
        return s[int(len(s) * 0.95)]

    @property
    def p99_ms(self) -> float:
        if not self.latency_samples:
            return 0.0
        s = sorted(self.latency_samples)
        return s[int(len(s) * 0.99)]

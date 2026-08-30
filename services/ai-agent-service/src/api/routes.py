"""
AI Agent Service — REST API routes.

Endpoints:
  GET  /health                                 Liveness check
  GET  /api/v1/agent/status                   Orchestrator status + cycle counters
  GET  /api/v1/agent/metrics                  Latency percentiles for research KPIs
  GET  /api/v1/agent/audit                    Recent audit log (optional ?device_id=)
  GET  /api/v1/agent/stream                   Server-Sent Events — real-time agent events
  POST /api/v1/agent/safety-bounds            Upsert safety bounds for a parameter
  GET  /api/v1/agent/safety-bounds/{device_id} List all safety bounds for a device
  DELETE /api/v1/agent/safety-bounds/{device_id}/{tag_name}  Remove a bound
  POST /api/v1/agent/override                 Operator manual write (safety-checked)
  POST /api/v1/agent/baseline/reset           Reset Z-score baseline for a tag
"""
import asyncio
import json
import time
from typing import Optional

from fastapi.responses import StreamingResponse

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..agents.safety_agent import SafetyAgent
from ..models.domain.agent_models import SafetyBounds
from ..schemas.agent_schema import (
    AgentStatusResponse,
    AuditRecord,
    AuditResponse,
    MetricsResponse,
    OverrideRequest,
    OverrideResponse,
    SafetyBoundsRequest,
    SafetyBoundsResponse,
)

router = APIRouter()

_start_time = time.monotonic()


def _get_orchestrator(request: Request):
    return request.app.state.orchestrator


def _get_registry(request: Request):
    return request.app.state.registry


def _get_audit_logger(request: Request):
    return request.app.state.audit_logger


def _get_data_collector(request: Request):
    return request.app.state.data_collector


def _get_broadcaster(request: Request):
    return request.app.state.broadcaster


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {"status": "ok", "service": "ai-agent-service"}


# ── Orchestrator status ───────────────────────────────────────────────────────

@router.get("/api/v1/agent/status", response_model=AgentStatusResponse)
async def agent_status(request: Request):
    orchestrator = _get_orchestrator(request)
    m = orchestrator.metrics
    uptime = time.monotonic() - _start_time
    return AgentStatusResponse(
        status="running" if orchestrator.is_running else "stopped",
        total_cycles=m.total_cycles,
        anomalies_detected=m.anomalies_detected,
        writes_executed=m.writes_executed,
        writes_succeeded=m.writes_succeeded,
        uptime_seconds=round(uptime, 1),
    )


# ── Metrics (latency percentiles) ─────────────────────────────────────────────

@router.get("/api/v1/agent/metrics", response_model=MetricsResponse)
async def agent_metrics(request: Request):
    orchestrator = _get_orchestrator(request)
    m = orchestrator.metrics
    return MetricsResponse(
        total_cycles=m.total_cycles,
        anomalies_detected=m.anomalies_detected,
        writes_executed=m.writes_executed,
        writes_succeeded=m.writes_succeeded,
        p50_latency_ms=m.p50_ms,
        p95_latency_ms=m.p95_ms,
        p99_latency_ms=m.p99_ms,
        latency_samples=len(m._latencies),
    )


# ── Audit log ─────────────────────────────────────────────────────────────────

@router.get("/api/v1/agent/audit", response_model=AuditResponse)
async def get_audit(
    request: Request,
    device_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    audit_logger = _get_audit_logger(request)
    records = await audit_logger.get_recent(device_id=device_id, limit=limit)
    return AuditResponse(
        records=[AuditRecord(**r) for r in records],
        total=len(records),
    )


# ── Safety bounds ─────────────────────────────────────────────────────────────

@router.post("/api/v1/agent/safety-bounds", response_model=SafetyBoundsResponse)
async def upsert_safety_bounds(request: Request, body: SafetyBoundsRequest):
    registry = _get_registry(request)
    bounds = SafetyBounds(
        device_id=body.device_id,
        tag_name=body.tag_name,
        min_value=body.min_value,
        max_value=body.max_value,
        max_step_change=body.max_step_change,
        unit=body.unit,
        description=body.description,
    )
    result = await registry.upsert_bounds(bounds)
    return SafetyBoundsResponse(
        device_id=result.device_id,
        tag_name=result.tag_name,
        min_value=result.min_value,
        max_value=result.max_value,
        max_step_change=result.max_step_change,
        unit=result.unit,
        description=result.description,
    )


@router.get(
    "/api/v1/agent/safety-bounds/{device_id}",
    response_model=list[SafetyBoundsResponse],
)
async def get_safety_bounds(request: Request, device_id: str):
    registry = _get_registry(request)
    bounds_list = await registry.get_all_bounds_for_device(device_id)
    return [
        SafetyBoundsResponse(
            device_id=b.device_id,
            tag_name=b.tag_name,
            min_value=b.min_value,
            max_value=b.max_value,
            max_step_change=b.max_step_change,
            unit=b.unit,
            description=b.description,
        )
        for b in bounds_list
    ]


@router.delete("/api/v1/agent/safety-bounds/{device_id}/{tag_name}")
async def delete_safety_bounds(request: Request, device_id: str, tag_name: str):
    registry = _get_registry(request)
    deleted = await registry.delete_bounds(device_id, tag_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Safety bounds not found")
    return {"deleted": True, "device_id": device_id, "tag_name": tag_name}


# ── Manual override ───────────────────────────────────────────────────────────

@router.post("/api/v1/agent/override", response_model=OverrideResponse)
async def manual_override(request: Request, body: OverrideRequest):
    """
    Operator-initiated write that still passes through the Safety Agent.
    Provides an auditable escape hatch without bypassing safety checks.
    """
    registry = _get_registry(request)
    data_collector = _get_data_collector(request)
    safety_agent = SafetyAgent()

    # Fetch current value from registry
    current_value = await registry.get_current_value(body.device_id, body.tag_name)
    if current_value is None:
        # Try live read from PLC
        current_value = await data_collector.read_tag(body.device_id, body.tag_name)

    if current_value is None:
        raise HTTPException(
            status_code=422,
            detail="Cannot determine current value — tag may not be polled yet",
        )

    bounds = await registry.get_bounds(body.device_id, body.tag_name)
    if bounds is None:
        return OverrideResponse(
            success=False,
            message=f"No safety bounds configured for {body.tag_name} — write blocked",
            safety_checked=True,
            write_executed=False,
        )

    safety_decision = safety_agent.validate(
        bounds=bounds,
        proposed_value=body.value,
        current_value=current_value,
    )

    if not safety_decision.allow:
        return OverrideResponse(
            success=False,
            message=f"Safety REJECTED: {safety_decision.reason}",
            safety_checked=True,
            write_executed=False,
        )

    success = await data_collector.write_tag(body.device_id, body.tag_name, body.value)
    if success:
        await registry.update_current_value(body.device_id, body.tag_name, body.value)

    return OverrideResponse(
        success=success,
        message="Write succeeded" if success else "Write failed (PLC communication error)",
        safety_checked=True,
        write_executed=True,
    )


# ── Server-Sent Events — real-time agent decisions ────────────────────────────

@router.get("/api/v1/agent/stream")
async def agent_event_stream(request: Request):
    """
    SSE endpoint.  Each agent decision (anomaly detected, monitoring decision,
    write executed, safety rejected) is pushed to connected clients immediately.

    Frontend connects once; events arrive as:
        data: {"type": "anomaly_detected", "device_id": "1", ...}\n\n
    """
    broadcaster = _get_broadcaster(request)
    queue = broadcaster.subscribe()

    async def generate():
        try:
            # Initial ping so the browser confirms the connection
            yield "data: {\"type\": \"connected\"}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive comment (prevents proxy timeouts)
                    yield ": keepalive\n\n"
        finally:
            broadcaster.unsubscribe(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable Nginx buffering
        },
    )


# ── Baseline reset ────────────────────────────────────────────────────────────

@router.post("/api/v1/agent/baseline/reset")
async def reset_baseline(
    request: Request,
    device_id: str,
    tag_name: str,
):
    """
    Clear the Redis Z-score baseline for a specific tag.
    Useful after a recipe change or when the baseline has been poisoned
    by an extended anomalous period.
    """
    orchestrator = _get_orchestrator(request)
    await orchestrator._baseline.reset_baseline(device_id, tag_name)
    # Also clear the last-seen timestamp so all recent readings are re-processed
    orchestrator._last_seen_ts.get(device_id, {}).pop(tag_name, None)
    return {"reset": True, "device_id": device_id, "tag_name": tag_name}

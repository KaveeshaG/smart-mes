from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # ── Service identity ─────────────────────────────────────
    service_name: str = "ai-agent-service"
    port: int = 8004

    # ── Downstream services ──────────────────────────────────
    device_management_url: str = "http://device-management:8001"
    data_collector_url: str = "http://data-collector:8003"

    # ── Database (same Neon PostgreSQL as other services) ────
    database_url: str

    # ── Redis ────────────────────────────────────────────────
    redis_url: str = "redis://redis:6379"

    # ── LLM ─────────────────────────────────────────────────
    # provider = "anthropic" (cloud) | "ollama" (local) — the independent
    # variable for the cloud-vs-local comparative evaluation (research
    # objective: LLM provider comparison on F1/MAPE/latency/cost/offline
    # resilience). See services/llm_providers.py.
    llm_provider: str = "anthropic"

    anthropic_api_key: str = ""
    # Haiku = fastest + cheapest, well within 500ms for structured outputs
    llm_model: str = "claude-haiku-4-5-20251001"
    llm_timeout_seconds: float = 4.0        # hard cap; <5s total cycle budget
    llm_fallback_enabled: bool = True       # rule-based fallback if LLM fails/slow

    # ── Ollama (local inference) ─────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    # Local CPU/GPU inference is typically slower and more variable than a
    # cloud API — a separate, larger timeout avoids conflating "model is
    # slow" with "model is unreachable" in the fallback-rate metric.
    ollama_timeout_seconds: float = 15.0

    # ── Anomaly detection ────────────────────────────────────
    zscore_window: int = 100                # rolling window size for baseline
    zscore_threshold: float = 3.0          # 3-sigma rule (99.7% coverage)
    min_readings_for_baseline: int = 10    # cold-start guard

    # ── Control loop ─────────────────────────────────────────
    poll_interval_seconds: float = 5.0     # sense loop frequency
    device_refresh_interval_seconds: float = 30.0
    max_concurrent_anomaly_handlers: int = 10  # throttle async tasks

    # ── Logging ──────────────────────────────────────────────
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from enum import Enum


class PeriodType(str, Enum):
    hourly = "hourly"
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    annual = "annual"


class AnalyticsResponse(BaseModel):
    id: UUID
    device_id: UUID
    tag_name: str
    period_type: str
    period_start: datetime
    period_end: datetime
    min_value: Optional[float]
    max_value: Optional[float]
    avg_value: Optional[float]
    std_dev: Optional[float]
    reading_count: int
    good_quality_pct: Optional[float]
    uptime_seconds: Optional[float]
    data_completeness_pct: Optional[float]
    trend_direction: Optional[str]
    change_rate_pct: Optional[float]
    anomaly_count: Optional[int]
    computed_at: datetime

    class Config:
        from_attributes = True


class AnalyticsSummaryResponse(BaseModel):
    device_id: UUID
    period_type: str
    total_readings: int
    avg_uptime_pct: Optional[float]
    avg_quality_pct: Optional[float]
    tag_count: int


class AnalyticsCompareItem(BaseModel):
    device_id: UUID
    tag_name: str
    avg_value: Optional[float]
    min_value: Optional[float]
    max_value: Optional[float]
    reading_count: int
    good_quality_pct: Optional[float]
    trend_direction: Optional[str]


class AnalyticsTrendPoint(BaseModel):
    period_start: datetime
    avg_value: Optional[float]
    min_value: Optional[float]
    max_value: Optional[float]
    reading_count: int
    trend_direction: Optional[str]
    change_rate_pct: Optional[float]

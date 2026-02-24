from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql+asyncpg://neondb_owner:npg_VwE71dQgTcvz@ep-royal-rain-ai64r2np-pooler.c-4.us-east-1.aws.neon.tech/smart-mes?ssl=require"
    )
    timescale_url: str = Field(
        default="postgresql+asyncpg://mes:mes123@localhost:5433/mes_timeseries"
    )
    rabbitmq_url: str = Field(default="amqp://mes:mes123@localhost:5672/")
    redis_url: str = Field(default="redis://localhost:6379")
    log_level: str = "INFO"
    device_management_url: str = "http://device-management:8001"
    poll_interval_seconds: int = 5
    continuous_polling_enabled: bool = True
    device_refresh_interval_seconds: int = 300
    
    class Config:
        env_file = ".env"

settings = Settings()

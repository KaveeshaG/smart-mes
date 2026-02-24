from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql+asyncpg://neondb_owner:npg_VwE71dQgTcvz@ep-royal-rain-ai64r2np-pooler.c-4.us-east-1.aws.neon.tech/smart-mes?ssl=require"
    )
    rabbitmq_url: str = Field(default="amqp://mes:mes123@localhost:5672/")
    redis_url: str = Field(default="redis://localhost:6379")
    
    scan_timeout: int = 2
    port_scan_timeout: int = 3
    max_concurrent_scans: int = 50
    modbus_port: int = 502
    modbus_timeout: float = 3.0
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"

settings = Settings()

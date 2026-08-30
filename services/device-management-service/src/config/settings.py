from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    # No hardcoded default — must come from the environment (.env / compose).
    # A prior default here baked a live Neon password into source control.
    database_url: str
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

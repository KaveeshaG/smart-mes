from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # No hardcoded default — must come from the environment (.env / compose).
    # A prior default here baked a live Neon password into source control.
    database_url: str
    rabbitmq_url: str = Field(default="amqp://mes:mes123@localhost:5672/")
    redis_url: str = Field(default="redis://localhost:6379")
    log_level: str = "INFO"
    device_management_url: str = Field(default="http://localhost:8001")

    class Config:
        env_file = ".env"


settings = Settings()

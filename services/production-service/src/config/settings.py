from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql+asyncpg://neondb_owner:npg_VwE71dQgTcvz@ep-royal-rain-ai64r2np-pooler.c-4.us-east-1.aws.neon.tech/smart-mes?ssl=require"
    )
    rabbitmq_url: str = Field(default="amqp://mes:mes123@localhost:5672/")
    redis_url: str = Field(default="redis://localhost:6379")
    log_level: str = "INFO"
    device_management_url: str = Field(default="http://localhost:8001")

    class Config:
        env_file = ".env"


settings = Settings()

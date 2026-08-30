"""
One-off migration: add the llm_provider column to the existing
agent_audit_log table on Neon Postgres.

There's no Alembic in this project — `init_db()` only calls
`Base.metadata.create_all`, which creates missing *tables*, not missing
*columns* on tables that already exist. Run this once after pulling the
provider-comparison changes:

    cd services/ai-agent-service
    poetry run python scripts/add_llm_provider_column.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from src.config.database import engine


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "ALTER TABLE agent_audit_log "
                "ADD COLUMN IF NOT EXISTS llm_provider VARCHAR(20)"
            )
        )
    print("agent_audit_log.llm_provider is present.")


if __name__ == "__main__":
    asyncio.run(main())

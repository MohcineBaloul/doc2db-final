"""Database connection and session for Doc2DB-Gen metadata and target DBs."""
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

from config import settings

# Metadata DB (tracks projects, schemas, extraction results)
engine = create_async_engine(
    settings.database_url,
    echo=False,
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


@asynccontextmanager
async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Create metadata tables and add new columns if missing."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Add extraction_data column if it was added to the model after tables existed
    from sqlalchemy import text
    try:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE extractions ADD COLUMN extraction_data TEXT"))
    except Exception:
        pass  # Column already exists or DB doesn't support (e.g. SQLite duplicate column)


def get_target_db_path(project_id: str) -> Path:
    """Path to project-specific SQLite DB (populated with extracted data)."""
    Path("./data").mkdir(exist_ok=True)
    return Path("./data") / f"project_{project_id}.db"

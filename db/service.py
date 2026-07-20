"""Database service for managing portal run records."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.asyncio.engine import AsyncEngine

from db.models import PortalRun
from portals.base_runner import PortalBatchRunReport, PortalRunState

DB_URL = "sqlite+aiosqlite:///db.sqlite"


def get_engine() -> AsyncEngine:
    """Create and return async database engine."""
    return create_async_engine(DB_URL, echo=False)


def get_session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create and return async session maker."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def create_run(
    session: AsyncSession,
    run_key: str,
    portal_key: str,
    started_at: datetime,
) -> PortalRun:
    """Create a new run record in the database."""
    run = PortalRun(
        run_key=run_key,
        portal_key=portal_key,
        started_at=started_at,
        finished_at=None,
        state=PortalRunState.IN_PROGRESS.name,
        successful_items=0,
        failed_items=0,
        unchanged_items=0,
        created_items=0,
        updated_items=0,
    )
    session.add(run)
    await session.commit()
    return run


async def update_run(
    session: AsyncSession,
    run_key: str,
    report: PortalBatchRunReport,
) -> None:
    """Update run record with current report data."""
    stmt = select(PortalRun).where(PortalRun.run_key == run_key)
    result = await session.execute(stmt)
    run = result.scalar_one_or_none()

    if not run:
        return

    run.finished_at = report.finished_at
    run.state = report.state.name
    run.successful_items = report.statistics.successful_items
    run.failed_items = report.statistics.failed_items
    run.unchanged_items = report.statistics.processing_results.unchanged
    run.created_items = report.statistics.processing_results.created
    run.updated_items = report.statistics.processing_results.updated

    await session.commit()

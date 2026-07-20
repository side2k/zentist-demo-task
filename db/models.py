"""Database models for portal run tracking."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all database models."""


class PortalRun(Base):
    """Model for tracking portal batch runs."""

    __tablename__ = "portal_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    portal_key: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    state: Mapped[str] = mapped_column(String, nullable=False)

    # Statistics columns
    successful_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unchanged_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

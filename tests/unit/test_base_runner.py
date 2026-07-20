"""Unit tests for base_runner.py."""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch

import pytest

from portals.base_runner import (
    BasePortalRunner,
    ItemProcessingResult,
    ItemProcessingStats,
    merge_config,
)
from portals.errors import UnrecoverablePortalError


# Test fixtures and helpers
@pytest.fixture
def mock_shutdown_event() -> asyncio.Event:
    """Provide an asyncio.Event for shutdown testing."""
    return asyncio.Event()


@pytest.fixture
def sample_config() -> dict[str, Any]:
    """Provide sample config values for testing."""
    return {
        "retries": 5,
        "retry_interval_seconds": 3,
        "custom_setting": "test_value",
    }


async def async_iter_from_list(items: list[Any]) -> AsyncIterator[Any]:
    """Helper to create an AsyncIterator from a list."""
    for item in items:
        await asyncio.sleep(0)  # Yield control
        yield item


def test_merge_config() -> None:
    # Recursive merge of nested dicts
    assert merge_config(
        {"outer": {"inner1": "v1", "inner2": "v2"}},
        {"outer": {"inner2": "new_v2", "inner3": "v3"}},
    ) == {"outer": {"inner1": "v1", "inner2": "new_v2", "inner3": "v3"}}

    # Mix of nested dicts and simple values
    assert merge_config(
        {"simple": "val", "nested": {"k1": "v1"}, "num": 42},
        {"simple": "new_val", "nested": {"k2": "v2"}, "extra": "added"},
    ) == {
        "simple": "new_val",
        "nested": {"k1": "v1", "k2": "v2"},
        "num": 42,
        "extra": "added",
    }

    # Deep nesting (3+ levels)
    assert merge_config(
        {"l1": {"l2": {"l3": {"l4": "deep", "other": "val"}}}},
        {"l1": {"l2": {"l3": {"l4": "new_deep", "extra": "added"}}}},
    ) == {"l1": {"l2": {"l3": {"l4": "new_deep", "other": "val", "extra": "added"}}}}


def test_item_processing_stats_update_with_result() -> None:
    # Initial state (all zeros)
    stats = ItemProcessingStats()
    assert stats.unchanged == 0
    assert stats.created == 0
    assert stats.updated == 0

    # Update with UNCHANGED increments unchanged counter
    stats.update_with_result(ItemProcessingResult.UNCHANGED)
    assert stats.unchanged == 1
    assert stats.created == 0
    assert stats.updated == 0

    # Multiple updates accumulate correctly
    stats.update_with_result(ItemProcessingResult.CREATED)
    stats.update_with_result(ItemProcessingResult.CREATED)
    stats.update_with_result(ItemProcessingResult.UPDATED)
    stats.update_with_result(ItemProcessingResult.UNCHANGED)

    assert stats.unchanged == 2
    assert stats.created == 2
    assert stats.updated == 1


def test_base_portal_runner_init() -> None:
    # Default config (empty dict provided)
    runner = BasePortalRunner(logger_name="test_logger", config={})
    assert isinstance(runner.logger, logging.Logger)
    assert runner.logger.name == "test_logger"
    assert runner.retries == 10  # Default from BasePortalRunnerConfig
    assert runner.retry_interval == 10  # Default from BasePortalRunnerConfig

    # Custom config values override defaults
    runner = BasePortalRunner(
        logger_name="test_logger",
        config={"retries": 5, "retry_interval_seconds": 3},
    )
    assert runner.retries == 5
    assert runner.retry_interval == 3

    # Config merge preserves unspecified defaults
    runner = BasePortalRunner(logger_name="test_logger", config={"retries": 7})
    assert runner.retries == 7
    assert runner.retry_interval == 10  # Default preserved

    # Invalid config triggers ValidationError, logs exception, and
    # raises UnrecoverablePortalError
    with patch.object(logging.Logger, "exception") as mock_log_exception:
        with pytest.raises(UnrecoverablePortalError, match="Error loading config"):
            runner = BasePortalRunner(
                logger_name="test_logger",
                config={"retries": "invalid"},  # Should be int
            )
        # Logger.exception should have been called
        mock_log_exception.assert_called_once()
        assert "Error loading config:" in mock_log_exception.call_args[0][0]

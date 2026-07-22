"""Unit tests for base_runner.py."""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from portals.base_runner import (
    BaseItemProcessingResult,
    BasePortalRunner,
    BasePortalRunnerInputItem,
    PortalBatchRunReport,
    PortalRunState,
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


async def empty_async_iterator(*_args, **_kwargs) -> AsyncIterator[Any]:  # noqa: ANN002, ANN003
    if False:
        yield


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


@pytest.mark.asyncio
async def test_base_portal_runner_run_calls_lifecycle_methods(
    mock_shutdown_event: asyncio.Event,
) -> None:
    """Test that run() internal sequence.

    Ensure before_run, process_batch_items, and after_run in the proper order.
    """
    runner = BasePortalRunner(logger_name="test_logger", config={})

    # Mock the lifecycle methods to track calls
    runner.before_run = AsyncMock()
    runner.process_batch_items = empty_async_iterator  # type: ignore[method-assign]
    runner.after_run = AsyncMock()

    await runner.run(empty_async_iterator(), mock_shutdown_event)

    # Verify all methods were called
    runner.before_run.assert_awaited_once()
    runner.after_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_base_portal_runner_run_empty_batch_processes_successfully(
    mock_shutdown_event: asyncio.Event,
) -> None:
    """Test that run() handles an empty batch successfully."""
    runner = BasePortalRunner(logger_name="test_logger", config={})

    batch = empty_async_iterator()

    # Call run with empty batch
    result = await runner.run(batch, mock_shutdown_event)

    # Verify result is valid stats with zeros
    assert isinstance(result, PortalBatchRunReport)
    assert result.statistics.successful_items == 0
    assert result.statistics.failed_items == 0
    assert result.state == PortalRunState.FINISHED


@pytest.mark.asyncio
async def test_base_portal_runner_run_after_run_called_even_if_exception(
    mock_shutdown_event: asyncio.Event,
) -> None:
    """Test that after_run() is called even if process_batch_items raises ."""
    runner = BasePortalRunner(logger_name="test_logger", config={})

    async def process_batch_items_raising(
        _data_batch: AsyncIterator[Any],
        _shutdown_event: asyncio.Event,
    ) -> AsyncIterator[tuple[Any, Any]]:
        raise RuntimeError("Test error")
        # Unreachable, but makes this an async generator
        if False:  # pragma: no cover
            yield  # type: ignore[unreachable]

    # Mock methods
    runner.before_run = AsyncMock()  # type: ignore[method-assign]
    runner.process_batch_items = process_batch_items_raising  # type: ignore[method-assign]
    runner.after_run = AsyncMock()  # type: ignore[method-assign]

    batch = empty_async_iterator()

    # Call run and expect exception
    with pytest.raises(RuntimeError, match="Test error"):
        await runner.run(batch, mock_shutdown_event)

    # Verify after_run was still called (finally block)
    runner.before_run.assert_awaited_once()
    runner.after_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_base_portal_runner_process_batch_items_yields_per_item(
    mock_shutdown_event: asyncio.Event,
) -> None:
    """process_batch_items() yields exactly one output per input item."""
    runner = BasePortalRunner(logger_name="test_logger", config={})

    async def process_item(
        item: BasePortalRunnerInputItem,
    ) -> BaseItemProcessingResult:
        if item.id == "2":
            raise UnrecoverablePortalError("simulating item processing failure")
        return BaseItemProcessingResult()

    runner.process_batch_item = process_item  # type: ignore[method-assign]

    items = [BasePortalRunnerInputItem(id=str(i)) for i in range(3)]

    results = [
        (input_item, result)
        async for input_item, result in runner.process_batch_items(
            async_iter_from_list(items),
            mock_shutdown_event,
        )
    ]

    assert len(results) == len(items)
    for (input_item, result), expected_input in zip(results, items, strict=True):
        assert input_item.id == expected_input.id
        if input_item.id == "2":
            assert issubclass(type(result), UnrecoverablePortalError)
        else:
            assert isinstance(result, BaseItemProcessingResult)

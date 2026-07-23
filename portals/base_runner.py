"""BasePortalRunner is a base runner class.

It encapsulates actions to be done with a portal.
"""

import asyncio
import enum
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel, Field, ValidationError

from .errors import RecoverablePortalError, UnrecoverablePortalError


def merge_config(default: dict, new: dict) -> dict:
    """Recursively merges config into default one."""

    result = default.copy()
    for key, new_value in new.items():
        default_value = result.get(key)
        if isinstance(default_value, dict) and isinstance(new_value, dict):
            result[key] = merge_config(default_value, new_value.copy())
        else:
            result[key] = new_value
    return result


class BasePortalRunnerConfig(BaseModel):  # noqa: D101
    retries: int = 10
    retry_interval_seconds: int = 10


class BaseItemProcessingResult(BaseModel):  # noqa: D101
    run_id: int | None = None


class PortalBatchRunReportStats(BaseModel):
    """Model for reporting statistics."""

    successful_items: int = 0
    failed_items: int = 0


class PortalRunState(enum.Enum):  # noqa: D101
    IN_PROGRESS = 1
    FINISHED = 2
    FAILED = 3


class PortalBatchRunReport(BaseModel):  # noqa: D101
    statistics: PortalBatchRunReportStats = PortalBatchRunReportStats()
    state: PortalRunState = PortalRunState.IN_PROGRESS
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
    finished_at: datetime | None = None


class PortalItemError(BaseModel):
    """Generic model for portal item processing errors."""

    run_id: int
    input_item_id: str
    error_message: str


class BasePortalRunnerInputItem(BaseModel):
    """Base model class for items in portal runner input data batch."""

    id: str  # unique id


ConfigT = TypeVar("ConfigT", bound=BasePortalRunnerConfig)
InputItemT = TypeVar("InputItemT", bound=BasePortalRunnerInputItem)
OutputItemT = TypeVar("OutputItemT", bound=BaseItemProcessingResult)


class BasePortalRunner(Generic[ConfigT, InputItemT, OutputItemT]):  # noqa: D101
    Config: type[ConfigT] = BasePortalRunnerConfig  # type: ignore[assignment]
    InputItem: type[InputItemT] = BasePortalRunnerInputItem  # type: ignore[assignment]
    OutputItem: type[OutputItemT] = BaseItemProcessingResult  # type: ignore[assignment]

    logger: logging.Logger
    retry_interval: int  # in seconds

    def __init__(
        self,
        logger_name: str,
        config: dict,
        item_output_callback: Callable[[OutputItemT], Awaitable[None]],
        update_callback: Callable[[PortalBatchRunReport], Awaitable[None]]
        | None = None,
        error_callback: Callable[[PortalItemError], Awaitable[None]] | None = None,
    ):
        self.logger = logging.getLogger(logger_name)

        default_config = self.Config().model_dump()

        try:
            self.config = self.Config.model_validate(
                merge_config(default_config, config),
            )
        except ValidationError as exc:
            self.logger.exception(f"Error loading config: {exc.errors}")
            raise UnrecoverablePortalError("Error loading config") from exc
        self.retries = self.config.retries
        self.retry_interval = self.config.retry_interval_seconds
        self.report = PortalBatchRunReport()
        self.update_callback = update_callback
        self.item_output_callback = item_output_callback
        self.error_callback = error_callback

    async def before_run(self) -> None:
        """Do stuff up before run begins.

        A good place for initializing context, e.g. - aiohttp session.
        """

    async def after_run(self) -> None:
        """Do stuff after run ends.

        Good place for tearing down stuff created in before_run()
        """

    async def run(
        self,
        run_id: int,
        data_batch: AsyncIterator[InputItemT],
        shutdown_event: asyncio.Event,
    ) -> PortalBatchRunReport:
        """Fire before_run() and after_run() events, running processing between them."""

        await self.update_report(self.report)
        await self.before_run()
        try:
            async for input_item, result in self.process_batch_items(
                data_batch,
                shutdown_event,
            ):
                if isinstance(result, self.OutputItem):
                    if result.run_id is None:
                        result.run_id = run_id
                    self.report.statistics.successful_items += 1
                    self.logger.info(f"Processed item {input_item.id}: {result}")
                    await self.update_item(result)
                    await self.update_report(self.report)
                else:  # result is an exception
                    self.logger.error("Skipping to the next item")
                    self.report.statistics.failed_items += 1
                    await self.update_error(
                        PortalItemError(
                            run_id=run_id,
                            input_item_id=input_item.id,
                            error_message=str(result),
                        ),
                    )
                    await self.update_report(self.report)

            self.report.finished_at = datetime.now(UTC)
            self.report.state = PortalRunState.FINISHED
            await self.update_report(self.report)

            return self.report
        finally:
            await self.after_run()

    async def process_batch_items(
        self,
        data_batch: AsyncIterator[InputItemT],
        shutdown_event: asyncio.Event,
    ) -> AsyncIterator[tuple[InputItemT, OutputItemT | Exception]]:
        """Call process_batch_item() for every item in data_batch with retries.

        When the error is RecoverablePortalError and there are still retries left,
        another run is done. If the error is UnrecoverablePortalError or unknown - the
        item is skipped (and marked as failure in the stats report).

        shutdown_event is supposed to be set when the shutdown is requested
        """

        async for item in data_batch:
            # Validate retry count in config would be better, but that seems
            # not wise for demo task scope
            retries_left = self.retries or 1
            if shutdown_event.is_set():
                self.logger.warning("Shutdown requested, stopping")
                break
            self.logger.info(f"Processing item {item.id}")

            last_error: Exception | None = None

            while retries_left > 0:
                retries_left -= 1
                try:
                    yield item, await self.process_batch_item(item)
                    break
                except RecoverablePortalError as exc:
                    self.logger.exception(
                        f"Caught recoverable error while processing item {item.id}",
                    )
                    self.logger.warning(f"{retries_left} retries left")
                    last_error = exc
                except UnrecoverablePortalError as exc:
                    self.logger.exception(
                        f"Caught unrecoverable error while processing item {item.id}",
                    )
                    yield item, exc
                    break

                if retries_left > 0:
                    try:
                        await asyncio.wait_for(
                            shutdown_event.wait(),
                            timeout=self.retry_interval,
                        )
                        yield (
                            item,
                            UnrecoverablePortalError("Shutdown request received"),
                        )
                        break
                    except TimeoutError:
                        continue

                msg = "No retries left"
                if last_error:
                    msg += f": {last_error}"
                yield item, UnrecoverablePortalError(msg)

    async def process_batch_item(self, item: InputItemT) -> OutputItemT:  # noqa: D102
        raise NotImplementedError

    async def load_input_data(self, filename: str) -> AsyncIterator[InputItemT]:
        """Load and validate input data from filename.

        By default, whole file is loaded into memory - should be sufficient for demo
        purposes. However, the return type is deliberately is defined as Iterable,
        so later iterations could yield portions of data on the go
        """
        with Path(filename).open() as input_file:  # noqa: ASYNC230
            data = json.load(input_file)

        # By default, we set item ids to the respective item positions.
        # In overriden version, any identifiers can be used.
        for item_index, item in enumerate(data):
            item["id"] = str(item_index)
            yield self.InputItem.model_validate(item)
            # avoid blocking
            await asyncio.sleep(0)

    async def update_report(self, report: PortalBatchRunReport) -> None:
        """Write report data to the outer layer."""

        # Call update callback if provided
        if self.update_callback:
            try:
                await self.update_callback(report)
            except Exception:
                self.logger.exception("Failed to execute update callback")

    async def update_item(self, item: OutputItemT) -> None:
        """Send output item to the outer layer."""

        try:
            await self.item_output_callback(item)
        except Exception:
            self.logger.exception("Failed to execute item output callback")

    async def update_error(self, error: PortalItemError) -> None:
        """Send error data to the outer layer."""

        if self.error_callback:
            try:
                await self.error_callback(error)
            except Exception:
                self.logger.exception("Failed to execute error callback")

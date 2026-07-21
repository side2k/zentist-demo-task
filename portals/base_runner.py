"""BasePortalRunner is a base runner class.

It encapsulates actions to be done with a portal.
"""

import asyncio
import enum
import json
import logging
from collections.abc import AsyncIterator
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


class ItemProcessingResult(enum.Enum):  # noqa: D101
    UNCHANGED = 1
    CREATED = 2
    UPDATED = 3


# Ideally this model should've been created dynamically based on ItemProcessingResult's
# member. But it leads to an ugly and struggle with type checking tools.
# Tradeoff of the current approach is that if there are members of enum that doesn't
# have respective members in this model, it will lead to errors.
class ItemProcessingStats(BaseModel):  # noqa: D101
    unchanged: int = 0
    created: int = 0
    updated: int = 0

    def update_with_result(self, result: ItemProcessingResult) -> None:  # noqa: D102
        match result:
            case ItemProcessingResult.UNCHANGED:
                self.unchanged += 1
            case ItemProcessingResult.CREATED:
                self.created += 1
            case ItemProcessingResult.UPDATED:
                self.updated += 1


class PortalBatchRunReportStats(BaseModel):
    """Model for reporting statistics."""

    successful_items: int = 0
    failed_items: int = 0

    processing_results: ItemProcessingStats = ItemProcessingStats()


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


class BasePortalRunnerInputItem(BaseModel):
    """Base model class for items in portal runner input data batch."""

    id: str  # unique id


ConfigT = TypeVar("ConfigT", bound=BasePortalRunnerConfig)
InputItemT = TypeVar("InputItemT", bound=BasePortalRunnerInputItem)


class BasePortalRunner(Generic[ConfigT, InputItemT]):  # noqa: D101
    Config: type[ConfigT] = BasePortalRunnerConfig  # type: ignore[assignment]
    InputItem: type[InputItemT] = BasePortalRunnerInputItem  # type: ignore[assignment]

    logger: logging.Logger
    retry_interval: int  # in seconds

    def __init__(self, logger_name: str, config: dict, report_filename: str):
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
        self.report_filename = report_filename

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
        data_batch: AsyncIterator[InputItemT],
        shutdown_event: asyncio.Event,
    ) -> PortalBatchRunReport:
        """Fire before_run() and after_run() events, running processing between them."""

        await self.update_report_file(self.report)
        await self.before_run()
        try:
            return await self.process_batch_items(data_batch, shutdown_event)
        finally:
            await self.after_run()

    async def process_batch_items(
        self,
        data_batch: AsyncIterator[InputItemT],
        shutdown_event: asyncio.Event,
    ) -> PortalBatchRunReport:
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

            while retries_left > 0:
                retries_left -= 1
                try:
                    result = await self.process_batch_item(item)
                    self.report.statistics.successful_items += 1
                    self.report.statistics.processing_results.update_with_result(result)
                    self.logger.info(f"Processed item {item.id}: {result.name}")
                    await self.update_report_file(self.report)

                    break
                except RecoverablePortalError:
                    self.logger.exception(
                        f"Caught recoverable error while processing item {item.id}",
                    )
                    self.logger.warning(f"{retries_left} retries left")
                except UnrecoverablePortalError:
                    self.logger.exception(
                        f"Caught unrecoverable error while processing item {item.id}",
                    )
                    self.logger.error("Skipping to the next item")  # noqa: TRY400
                    self.report.statistics.failed_items += 1
                    await self.update_report_file(self.report)
                    break

                if retries_left > 0:
                    try:
                        await asyncio.wait_for(
                            shutdown_event.wait(),
                            timeout=self.retry_interval,
                        )
                        self.report.statistics.failed_items += 1
                        break
                    except TimeoutError:
                        continue

                self.report.statistics.failed_items += 1
                await self.update_report_file(self.report)

        self.report.finished_at = datetime.now(UTC)
        self.report.state = PortalRunState.FINISHED
        await self.update_report_file(self.report)
        return self.report

    async def process_batch_item(self, item: InputItemT) -> ItemProcessingResult:  # noqa: D102
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

    async def update_report_file(self, report: PortalBatchRunReport) -> None:
        """Write report to the self.report_filename in JSON format."""
        try:
            report_data = report.model_dump_json(indent=2)
            await asyncio.to_thread(
                Path(self.report_filename).write_text,
                report_data,
                encoding="utf-8",
            )
        except Exception:
            self.logger.exception(f"Failed to write report to {self.report_filename}")

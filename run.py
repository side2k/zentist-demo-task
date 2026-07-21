"""Main CLI interface for the portal runners orchestration."""

import argparse
import asyncio
import importlib
import json
import logging
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from signal import SIGINT, SIGTERM
from typing import TYPE_CHECKING

from dotenv import load_dotenv
from pydantic import BaseModel

from db.service import create_run, get_engine, get_session_maker, update_run
from portals.base_runner import PortalBatchRunReport, PortalRunState
from reporting.email import send_email_report

if TYPE_CHECKING:
    from .portals import BasePortalRunner

logger = logging.getLogger(__name__)


class SMTPServerConfig(BaseModel):  # noqa: D101
    host: str
    port: int


class RootConfig(BaseModel):  # noqa: D101
    portals: dict[str, dict]
    report_to: list[str]
    smtp_server: SMTPServerConfig | None = None


def parse_args() -> argparse.Namespace:  # noqa: D103
    parser = argparse.ArgumentParser(description="Portal runner orchestrator")
    parser.add_argument(
        "--config",
        help="load specified config file",
        default="config.json",
    )
    parser.add_argument("--portal", help="run only the specified portal runner")
    parser.add_argument(
        "--log-level",
        choices=logging.getLevelNamesMapping().keys(),
        default="INFO",
    )
    return parser.parse_args()


def ensure_required_dirs() -> None:
    """Check required directories exist, and if not - create them."""
    required_dirs = ["logs"]
    for dir_name in required_dirs:
        Path(dir_name).mkdir(exist_ok=True)


def configure_portal_logger(portal_logger: logging.Logger, log_file_path: str) -> None:
    """Configure portal logger with file handler using ISO timestamp format."""
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(formatter)
    portal_logger.addHandler(file_handler)


async def main(cli_args: argparse.Namespace, shutdown_event: asyncio.Event) -> None:  # noqa: D103
    load_dotenv()

    # Configure root logger with ISO timestamp format for console output
    formatter = logging.Formatter(
        "%(asctime)s %(name)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.getLevelNamesMapping()[cli_args.log_level])
    root_logger.addHandler(console_handler)

    ensure_required_dirs()

    with Path(cli_args.config).open() as config_file:  # noqa: ASYNC230
        root_config = RootConfig.model_validate(json.load(config_file))

    if root_config.smtp_server:
        logger.info(
            "SMTP server configured: "
            f"{root_config.smtp_server.host}:{root_config.smtp_server.port}",
        )
        send_report = partial(
            send_email_report,
            root_config.smtp_server.host,
            root_config.smtp_server.port,
            root_config.report_to,
        )
    else:
        logger.warning("No SMTP server configured, reports will not be sent")

        async def send_report(portal_key: str, report: PortalBatchRunReport) -> None:  # noqa: ARG001
            logger.warning(
                f"No SMTP server configured, {portal_key} report will not be sent",
            )

    # Initialize database
    engine = get_engine()
    session_maker = get_session_maker(engine)

    for portal_key, portal_config_raw in root_config.portals.items():
        logger.info(f"Loading portal runner '{portal_key}'")
        portal_module = importlib.import_module(f"portals.{portal_key}")
        portal_logger = logging.getLogger(f"portals.{portal_key}")
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S%f")
        run_key = f"{portal_key}-{timestamp}"
        configure_portal_logger(portal_logger, f"logs/{run_key}.log")

        # Create database record for this run
        async with session_maker() as session:
            run = await create_run(
                session,
                run_key=run_key,
                portal_key=portal_key,
                started_at=datetime.now(UTC),
            )

        # Define callback to update database
        async def update_db_callback(report: PortalBatchRunReport) -> None:
            # Creating a session for every callback call is safer and more robust
            # for async access.
            async with session_maker() as session:
                await update_run(session, run.run_key, report)  # noqa: B023

            if report.state == PortalRunState.FINISHED:
                # send report to email
                await send_report(portal_key, report)  # noqa: B023

        runner_class: type[BasePortalRunner] = portal_module.Runner
        portal_runner: BasePortalRunner = runner_class(
            portal_logger.name,
            portal_config_raw,
            update_db_callback,
        )

        portal_input_data = portal_runner.load_input_data(f"input/{portal_key}.json")
        portal_stats_report = await portal_runner.run(portal_input_data, shutdown_event)

        logger.info(f"{portal_key} run stats:")
        logger.info(f"{portal_stats_report.model_dump()}")

    await engine.dispose()


if __name__ == "__main__":
    args = parse_args()
    loop = asyncio.get_event_loop()
    shutdown_event = asyncio.Event()
    main_task = asyncio.ensure_future(main(args, shutdown_event))

    for signal in [SIGINT, SIGTERM]:
        loop.add_signal_handler(signal, shutdown_event.set)
        loop.add_signal_handler(signal, main_task.cancel)

    try:
        loop.run_until_complete(main_task)
    except asyncio.CancelledError:
        logger.info("Graceful stop")
    finally:
        loop.close()

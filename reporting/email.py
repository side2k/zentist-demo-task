"""Basic routines for sending portal run reports via email."""

from email.message import EmailMessage
from textwrap import dedent

import aiosmtplib

from portals.base_runner import PortalBatchRunReport


async def send_email_report(  # noqa: D103
    smtp_host: str,
    smtp_port: int,
    recipients: list[str],
    portal_key: str,
    report: PortalBatchRunReport,
) -> None:
    message = EmailMessage()
    message["From"] = "orchestrator@runner"
    message["To"] = ", ".join(recipients)
    message["Subject"] = f"Run report for portal {portal_key}: {report.state.name}"

    finished_timestamp = (
        report.finished_at.isoformat() if report.finished_at else "unknown time"
    )

    if report.finished_at:
        running_time = str(report.finished_at - report.started_at)
    else:
        running_time = "unknown time"

    message.set_content(
        dedent(f"""
        {portal_key} run finished with status {report.state.name} at {finished_timestamp}

        Running time was: {running_time}

        Stats:

        Total items processed: {report.statistics.successful_items + report.statistics.failed_items}

        - successful: {report.statistics.successful_items}
        - failed: {report.statistics.failed_items}

    """),  # noqa: E501
    )

    await aiosmtplib.send(message, hostname=smtp_host, port=smtp_port)

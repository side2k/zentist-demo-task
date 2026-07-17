"""Smoke test: logging into the live OrangeHRM portal succeeds."""

import aiohttp
import pytest

from portals.orange_hrm.client import OrangeHRMClient

pytestmark = pytest.mark.e2e_staging


async def test_login_succeeds(
    session: aiohttp.ClientSession,
    orange_hrm_credentials: tuple[str, str],
) -> None:
    """A valid login does not raise."""
    client = OrangeHRMClient(session)
    await client.login(*orange_hrm_credentials)

"""Fixtures for E2E staging tests hitting the live OrangeHRM portal."""

import os
from collections.abc import AsyncIterator

import aiohttp
import pytest
from dotenv import load_dotenv
from faker import Faker

from portals.orange_hrm.client import OrangeHRMClient

load_dotenv()


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is not set (see .env.example)")
    return value


@pytest.fixture
def orange_hrm_credentials() -> tuple[str, str]:
    """Return OrangeHRM staging credentials from the environment."""
    return (
        _required_env("ORANGE_HRM_STAGING_USERNAME"),
        _required_env("ORANGE_HRM_STAGING_PASSWORD"),
    )


@pytest.fixture
async def session() -> AsyncIterator[aiohttp.ClientSession]:
    """Provide an aiohttp session for the duration of a test."""
    async with aiohttp.ClientSession() as session:
        yield session


@pytest.fixture
async def orange_hrm_client(
    session: aiohttp.ClientSession,
    orange_hrm_credentials: tuple[str, str],
) -> OrangeHRMClient:
    """Provide a logged-in OrangeHRM client against the live portal."""
    client = OrangeHRMClient(session)
    await client.login(*orange_hrm_credentials)
    return client


@pytest.fixture
async def orange_hrm_employee(
    faker: Faker,
    orange_hrm_client: OrangeHRMClient,
) -> AsyncIterator[int]:
    employee_number = await orange_hrm_client.create_employee(
        faker.first_name(),
        faker.first_name(),
        faker.last_name(),
    )
    yield employee_number

    # cleanup
    await orange_hrm_client.delete_employees([employee_number])

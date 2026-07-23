"""Unit tests for OrangeHRM client.

These tests are NOT comprehensive - I just created a few of them to demonstrate that
I know how it is done. I believe through test coverage is out of scope of demo task.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import ClientSession

from portals.orange_hrm.client import OrangeHRMClient, OrangeHRMUnexpectedDataError
from portals.orange_hrm.models import EmploymentStatus


@pytest.fixture
def mock_session() -> MagicMock:
    """Create a mock aiohttp ClientSession."""
    return MagicMock(spec=ClientSession)


@pytest.fixture
def client(mock_session: MagicMock) -> OrangeHRMClient:
    """Create OrangeHRMClient instance with mocked session."""
    return OrangeHRMClient(mock_session)


class TestFetchAllEmploymentStatuses:
    """Tests for fetch_all_employment_statuses method."""

    @pytest.mark.asyncio
    async def test_fetch_employment_statuses_success(
        self,
        client: OrangeHRMClient,
        mock_session: MagicMock,
    ) -> None:
        """Test successful fetch of employment statuses."""
        # Arrange
        expected_statuses = [
            EmploymentStatus(id=1, name="Full-Time"),
            EmploymentStatus(id=2, name="Part-Time"),
        ]
        response_data = {
            "data": [
                {"id": 1, "name": "Full-Time"},
                {"id": 2, "name": "Part-Time"},
            ],
            "meta": {"total": 2},
        }

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=response_data)
        mock_response.raise_for_status = MagicMock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_context.__aexit__.return_value = None
        mock_session.request.return_value = mock_context

        # Act
        result = await client.fetch_all_employment_statuses(limit=50, offset=0)

        # Assert
        assert len(result) == 2
        assert result[0].id == expected_statuses[0].id
        assert result[0].name == expected_statuses[0].name
        assert result[1].id == expected_statuses[1].id
        assert result[1].name == expected_statuses[1].name

        mock_session.request.assert_called_once_with(
            "GET",
            "https://opensource-demo.orangehrmlive.com/web/index.php/api/v2/admin/employment-statuses?limit=50&offset=0",
            json=None,
        )

    @pytest.mark.asyncio
    async def test_fetch_employment_statuses_invalid_limit(
        self,
        client: OrangeHRMClient,
    ) -> None:
        """Test that invalid limit raises ValueError."""
        with pytest.raises(ValueError, match="limit must be positive"):
            await client.fetch_all_employment_statuses(limit=0)

        with pytest.raises(ValueError, match="limit must be positive"):
            await client.fetch_all_employment_statuses(limit=-1)

    @pytest.mark.asyncio
    async def test_fetch_employment_statuses_invalid_offset(
        self,
        client: OrangeHRMClient,
    ) -> None:
        """Test that invalid offset raises ValueError."""
        with pytest.raises(ValueError, match="offset must be non-negative"):
            await client.fetch_all_employment_statuses(limit=10, offset=-1)


class TestCreateEmploymentStatus:
    """Tests for create_employment_status method."""

    @pytest.mark.asyncio
    async def test_create_employment_status_success(
        self,
        client: OrangeHRMClient,
        mock_session: MagicMock,
    ) -> None:
        """Test successful creation of employment status."""
        # Arrange
        new_status = EmploymentStatus(name="Contractor")
        response_data = {
            "data": {"id": 5, "name": "Contractor"},
        }

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=response_data)
        mock_response.raise_for_status = MagicMock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_context.__aexit__.return_value = None
        mock_session.request.return_value = mock_context

        # Act
        result_id = await client.create_employment_status(new_status)

        # Assert
        assert result_id == 5

        mock_session.request.assert_called_once_with(
            "POST",
            "https://opensource-demo.orangehrmlive.com/web/index.php/api/v2/admin/employment-statuses",
            json={"name": "Contractor"},
        )

    @pytest.mark.asyncio
    async def test_create_employment_status_missing_id_in_response(
        self,
        client: OrangeHRMClient,
        mock_session: MagicMock,
    ) -> None:
        """Test that missing id in response raises OrangeHRMUnexpectedDataError."""
        # Arrange
        new_status = EmploymentStatus(name="Contractor")
        response_data = {
            "data": {"name": "Contractor"},
        }

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=response_data)
        mock_response.raise_for_status = MagicMock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_context.__aexit__.return_value = None
        mock_session.request.return_value = mock_context

        # Act & Assert
        with pytest.raises(
            OrangeHRMUnexpectedDataError,
            match="status creation request returned no id",
        ):
            await client.create_employment_status(new_status)

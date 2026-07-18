"""Read-path tests for salary attachments against the live OrangeHRM portal."""

import pytest

from portals.orange_hrm.client import OrangeHRMClient
from portals.orange_hrm.models import SalaryAttachment

pytestmark = pytest.mark.e2e_staging


async def test_fetch_salary_attachments_page(
    orange_hrm_client: OrangeHRMClient,
    orange_hrm_employee: int,
) -> None:
    """A salary attachments page returns a valid meta and list of attachments."""
    page = await orange_hrm_client.fetch_salary_attachments_page(
        orange_hrm_employee,
        limit=10,
        offset=0,
    )

    assert page.meta.emp_number == orange_hrm_employee
    assert page.meta.screen == "salary"
    assert isinstance(page.meta.total, int)
    assert len(page.data) <= 10
    assert all(isinstance(a, SalaryAttachment) for a in page.data)


async def test_fetch_all_salary_attachments(
    orange_hrm_client: OrangeHRMClient,
    orange_hrm_employee: int,
) -> None:
    """Fetching all salary attachments matches the reported total."""
    first_page = await orange_hrm_client.fetch_salary_attachments_page(
        orange_hrm_employee,
        limit=10,
        offset=0,
    )
    total = first_page.meta.total

    attachments = await orange_hrm_client.fetch_all_salary_attachments(
        orange_hrm_employee,
        page_size=10,
    )

    assert len(attachments) == total
    assert all(isinstance(a, SalaryAttachment) for a in attachments)

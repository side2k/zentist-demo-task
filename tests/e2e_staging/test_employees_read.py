"""Read-path tests against the live OrangeHRM portal."""

import pytest

from portals.orange_hrm.client import OrangeHRMClient
from portals.orange_hrm.models import EmployeeSummary, EmploymentStatus

pytestmark = pytest.mark.e2e_staging


async def test_fetch_employees_page(orange_hrm_client: OrangeHRMClient) -> None:
    """A single directory page returns employees and a total count."""
    page = await orange_hrm_client.fetch_employees_page(limit=10, offset=0)

    assert isinstance(page.meta.total, int)
    assert len(page.data) <= 10
    assert all(isinstance(e, EmployeeSummary) for e in page.data)


async def test_fetch_employees_page_detailed(
    orange_hrm_client: OrangeHRMClient,
) -> None:
    """A single directory page returns detailed employees and a total count."""
    page = await orange_hrm_client.fetch_employees_page(
        limit=50,
        offset=0,
        use_detailed_model=True,
    )

    assert isinstance(page.meta.total, int)
    assert len(page.data) <= 50
    assert all(isinstance(e, EmployeeSummary) for e in page.data)
    assert any(e.contact_info is not None for e in page.data)


async def test_fetch_all_employees_paginates(
    orange_hrm_client: OrangeHRMClient,
) -> None:
    """Fetching all employees crosses page boundaries and matches the total."""
    first_page = await orange_hrm_client.fetch_employees_page(limit=10, offset=0)
    total = first_page.meta.total

    employees = await orange_hrm_client.fetch_all_employees(page_size=10)

    assert len(employees) == total
    assert all(isinstance(e, EmployeeSummary) for e in employees)


async def test_fetch_employee(orange_hrm_client: OrangeHRMClient) -> None:
    """A single employee record can be fetched by its number."""
    page = await orange_hrm_client.fetch_employees_page(limit=1, offset=0)
    emp_number = page.data[0].emp_number

    employee = await orange_hrm_client.fetch_employee(emp_number)

    assert isinstance(employee, EmployeeSummary)
    assert employee.emp_number == emp_number


async def test_fetch_all_employment_statuses(
    orange_hrm_client: OrangeHRMClient,
) -> None:

    statuses = await orange_hrm_client.fetch_all_employment_statuses()

    assert len(statuses) > 0
    assert all(isinstance(status, EmploymentStatus) for status in statuses)

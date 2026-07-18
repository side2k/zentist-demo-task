"""Read-path tests against the live OrangeHRM portal."""

import pytest

from portals.orange_hrm.client import OrangeHRMClient

pytestmark = pytest.mark.e2e_staging

REQUIRED_EMPLOYEE_KEYS = ("empNumber", "firstName", "middleName", "lastName")


async def test_fetch_employees_page(orange_hrm_client: OrangeHRMClient) -> None:
    """A single directory page returns employees and a total count."""
    page = await orange_hrm_client.fetch_employees_page(limit=10, offset=0)

    assert isinstance(page["data"], list)
    assert isinstance(page["meta"]["total"], int)
    assert len(page["data"]) <= 10

    for employee in page["data"]:
        for key in REQUIRED_EMPLOYEE_KEYS:
            assert key in employee


async def test_fetch_all_employees_paginates(
    orange_hrm_client: OrangeHRMClient,
) -> None:
    """Fetching all employees crosses page boundaries and matches the total."""
    first_page = await orange_hrm_client.fetch_employees_page(limit=10, offset=0)
    total = first_page["meta"]["total"]

    employees = await orange_hrm_client.fetch_all_employees(page_size=10)

    assert len(employees) == total
    for employee in employees:
        for key in REQUIRED_EMPLOYEE_KEYS:
            assert key in employee


async def test_fetch_employee(orange_hrm_client: OrangeHRMClient) -> None:
    """A single employee record can be fetched by its number."""
    page = await orange_hrm_client.fetch_employees_page(limit=1, offset=0)
    emp_number = page["data"][0]["empNumber"]

    employee = await orange_hrm_client.fetch_employee(emp_number)

    assert employee["empNumber"] == emp_number
    for key in REQUIRED_EMPLOYEE_KEYS:
        assert key in employee

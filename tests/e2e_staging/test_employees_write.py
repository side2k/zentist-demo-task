"""Write-path tests against the live OrangeHRM portal."""

import pytest
from faker import Faker

from portals.orange_hrm.client import OrangeHRMClient

pytestmark = pytest.mark.e2e_staging


@pytest.mark.usefixtures("orange_hrm_client", "orange_hrm_employee")
async def test_create_and_delete_employee() -> None:
    pass


async def test_employee_personal_details_update(
    faker: Faker,
    orange_hrm_client: OrangeHRMClient,
    orange_hrm_employee: int,
) -> None:
    personal_details = await orange_hrm_client.fetch_employee_personal_details(
        orange_hrm_employee,
    )
    new_last_name = faker.last_name() + " II"
    assert personal_details.last_name != new_last_name
    personal_details.last_name = new_last_name

    await orange_hrm_client.update_employee_personal_details(
        orange_hrm_employee,
        personal_details,
    )

    updated_personal_details = await orange_hrm_client.fetch_employee_personal_details(
        orange_hrm_employee,
    )

    assert updated_personal_details.last_name == new_last_name


async def test_employee_job_details_update(
    orange_hrm_client: OrangeHRMClient,
    orange_hrm_employee: int,
) -> None:
    job_details = await orange_hrm_client.fetch_employee_job_details(
        orange_hrm_employee,
    )
    new_joined_date = "2001-02-03"
    assert job_details.joined_date != new_joined_date
    job_details.joined_date = new_joined_date

    job_details.emp_number = None

    await orange_hrm_client.update_employee_job_details(
        orange_hrm_employee,
        job_details,
    )

    updated_job_details = await orange_hrm_client.fetch_employee_job_details(
        orange_hrm_employee,
    )

    assert updated_job_details.joined_date == new_joined_date

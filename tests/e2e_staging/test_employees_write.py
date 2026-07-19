"""Write-path tests against the live OrangeHRM portal."""

from uuid import uuid4

import pytest
from faker import Faker

from portals.orange_hrm.client import OrangeHRMClient
from portals.orange_hrm.models import EmploymentStatus

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


async def test_employment_status_create_and_delete(
    orange_hrm_client: OrangeHRMClient,
) -> None:
    existing_statuses = await orange_hrm_client.fetch_all_employment_statuses()

    existing_statuses_names = {s.name for s in existing_statuses}

    run_id = uuid4().hex[:8]
    new_statuses_names = [f"E2E-status {run_id}-{i}" for i in range(3)]

    assert not any(new in existing_statuses_names for new in new_statuses_names)

    # create new statuses
    for new_status_name in new_statuses_names:
        await orange_hrm_client.create_employment_status(
            EmploymentStatus(name=new_status_name),
        )

    # check statuses were created
    refreshed_statuses = {
        str(s.name): s.id or 0
        for s in await orange_hrm_client.fetch_all_employment_statuses()
    }
    refreshed_statuses_names = refreshed_statuses.keys()

    assert all(new in refreshed_statuses_names for new in new_statuses_names)

    # delete statuses wer've created
    new_statuses_ids = [refreshed_statuses[s] for s in new_statuses_names]
    await orange_hrm_client.delete_employment_statuses(new_statuses_ids)

    # ensure everything was cleaned up
    cleaned_statuses_names = {
        s.name for s in await orange_hrm_client.fetch_all_employment_statuses()
    }
    assert not any(
        new_status in cleaned_statuses_names for new_status in new_statuses_names
    )

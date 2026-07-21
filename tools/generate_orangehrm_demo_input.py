"""Tool script for generating demo input data for OrangeHRM portal."""

import asyncio
import json
import logging
import os
import random
from pathlib import Path

import aiohttp
import faker
from dotenv import load_dotenv
from pydantic import BaseModel

from portals.orange_hrm.client import OrangeHRMClient
from portals.orange_hrm.models import (
    EmployeeJobDetails,
    EmployeeSummary,
    EmploymentStatus,
)

logger = logging.getLogger(__name__)

load_dotenv()


OUTPUT_FILENAME = "input/orange_hrm.json"


class EmployeeInput(BaseModel):  # noqa: D101
    first_name: str
    last_name: str
    middle_name: str = ""
    email: str
    phone: str | None = None
    job_title: str
    employment_status: str
    salary: str

    @classmethod
    def from_existing(  # noqa: D102
        cls,
        employee: EmployeeSummary,
        job_detail: EmployeeJobDetails,
        salary: bytes,
    ) -> "EmployeeInput":
        return EmployeeInput(
            first_name=employee.first_name,
            middle_name=employee.middle_name,
            last_name=employee.last_name,
            email=employee.contact_info.work_email or "",
            phone=employee.contact_info.work_telephone,
            job_title=employee.job_title.title or "",
            employment_status=job_detail.emp_status.name or "",
            salary=str(salary),
        )


async def get_employees_data_sample(
    client: OrangeHRMClient,
    count: int = 5,
) -> list[tuple[EmployeeSummary, EmployeeJobDetails, list[bytes]]]:
    """Return some "real" employees with emails and job details."""

    logger.info("Fetching all existing employers...")
    employees = await client.fetch_all_employees(use_detailed_model=True)
    employees_with_email = random.sample(
        [e for e in employees if e.contact_info.work_email],
        count,
    )
    logger.info(
        f"Fetching job details for {len(employees_with_email)} employers...",
    )
    job_details = {
        employee.emp_number: await client.fetch_employee_job_details(
            employee.emp_number,
        )
        for employee in employees_with_email
    }

    logger.info(
        f"Fetching salary attachments for {len(employees_with_email)} employers...",
    )
    salary_attachments = {}
    for employee in employees_with_email:
        employee_salary_attachments = await client.fetch_all_salary_attachments(
            employee.emp_number,
        )
        salary_attachments[employee.emp_number] = [
            await client.fetch_employee_attachment(
                employee.emp_number,
                attachment.id,
            )
            for attachment in employee_salary_attachments
        ]

    logger.info(f"Got {len(employees)=}, {len(employees_with_email)=}")
    return [
        (
            employee,
            job_details[employee.emp_number],
            salary_attachments[employee.emp_number],
        )
        for employee in employees_with_email
    ]


async def generate_new_employees(  # noqa: D103
    emp_statuses: list[EmploymentStatus],
    count: int = 10,
) -> list[EmployeeInput]:
    fake = faker.Faker()

    return [
        EmployeeInput(
            first_name=fake.first_name(),
            middle_name=fake.first_name(),
            last_name=fake.last_name(),
            email=fake.email(),
            phone=fake.basic_phone_number(),
            job_title=fake.job(),
            employment_status=random.choice(emp_statuses).name or "Freelance",  # noqa: S311
            salary=f"{random.randrange(4, 11) * 100 * 52} USD annually",  # noqa: S311
        )
        for _ in range(count)
    ]


async def run() -> None:
    """Generate input data and store it to the orangehrm-demo-input.json."""

    logging.basicConfig(level=logging.INFO)
    data: list[EmployeeInput] = []

    username = os.environ["ORANGE_HRM_STAGING_USERNAME"]
    password = os.environ["ORANGE_HRM_STAGING_PASSWORD"]

    session_kwargs = {}
    proxy = os.environ.get("HTTPS_PROXY")
    if proxy:
        session_kwargs["proxy"] = proxy

    async with aiohttp.ClientSession(**session_kwargs) as session:
        client = OrangeHRMClient(session)
        await client.login(username, password)
        existing_employees = await get_employees_data_sample(client)
        employment_statuses = await client.fetch_all_employment_statuses()
    count_existing = len(existing_employees)

    dont_update_emps, update_emps = (
        existing_employees[: count_existing // 2],
        existing_employees[count_existing // 2 :],
    )

    data.extend(
        [
            EmployeeInput.from_existing(
                employee,
                job_details,
                salary_attachments[0] if len(salary_attachments) > 0 else b"",
            )
            for (employee, job_details, salary_attachments) in dont_update_emps
        ],
    )
    logger.info(
        f"{len(dont_update_emps)} employees that are not supposed to be changed",
    )

    data.extend(
        [
            EmployeeInput.from_existing(
                employee.model_copy(update={"middle_name": "J."}),
                job_details,
                b"salary data to be updated",
            )
            for (employee, job_details, salary_attachments) in update_emps
        ],
    )

    logger.info("Fetching all available employment statuses...")
    new_employees = await generate_new_employees(employment_statuses)
    count_new = len(new_employees)

    logger.info(f"Generated {count_new} new employees")

    data.extend(new_employees)

    with Path(OUTPUT_FILENAME).open("w") as output_file:  # noqa: ASYNC230
        json.dump([element.model_dump() for element in data], output_file, indent=2)

    logger.info(f"Demo input data written to {OUTPUT_FILENAME}")


if __name__ == "__main__":
    asyncio.run(run())

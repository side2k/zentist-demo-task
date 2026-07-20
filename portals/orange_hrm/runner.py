"""OrangeHRM portal runner."""

import os

import aiohttp
from pydantic import BaseModel

from portals.base_runner import (
    BasePortalRunner,
    BasePortalRunnerConfig,
    BasePortalRunnerInputItem,
    ItemProcessingResult,
)

from .client import OrangeHRMClient
from .models import (
    EmployeeContactDetails,
    EmployeeCreateRequest,
    EmployeeJobDetails,
    EmployeeSummary,
    EmploymentStatus,
    JobTitle,
    SalaryAttachment,
    SalaryAttachmentUpload,
)


class OrangeHRMPortalRunnerConfig(BasePortalRunnerConfig):  # noqa: D101
    tracing_enabled: bool = False
    username_env_var: str = "ORANGE_HRM_STAGING_USERNAME"
    password_env_var: str = "ORANGE_HRM_STAGING_PASSWORD"  # noqa: S105


class OrangeHRMPortalRunnerInputItem(BasePortalRunnerInputItem):  # noqa: D101
    first_name: str
    last_name: str
    middle_name: str = ""
    email: str
    phone: str | None = None
    job_title: str
    employment_status: str
    salary: str

    def matching_summary_fields(self) -> list[tuple[str, str]]:
        """Return list of (field, summary_field) tuples.

        field is this model's field name, and summary_field is a field name of
        EmployerSummary model.
        """
        return [
            ("first_name", "first_name"),
            ("last_name", "last_name"),
            ("middle_name", "middle_name"),
        ]

    def differs_from_summary(self, summary: EmployeeSummary) -> bool:
        """Return True if current object differs from EmployeeSummary model
        (on matching fields).
        """  # noqa: D205
        for field, summary_field in self.matching_summary_fields():
            field_value = getattr(self, field)
            summary_value = getattr(summary, summary_field)

            if field_value != summary_value:
                return True

        return False


class EmployeeCache(BaseModel):  # noqa: D101
    summary: EmployeeSummary
    salary_attachments: list[SalaryAttachment]


class OrangeHRMPortalRunner(  # noqa: D101
    BasePortalRunner[OrangeHRMPortalRunnerConfig, OrangeHRMPortalRunnerInputItem],
):
    Config = OrangeHRMPortalRunnerConfig
    InputItem = OrangeHRMPortalRunnerInputItem
    _employees_cache: dict[str, EmployeeCache]
    _employment_statuses_cache: dict[str, EmploymentStatus]
    _job_titles_cache: dict[str, JobTitle]

    def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
        super().__init__(*args, **kwargs)

    async def process_batch_item(  # noqa: D102
        self,
        item: OrangeHRMPortalRunnerInputItem,
    ) -> ItemProcessingResult:

        summary, was_created = await self.get_or_create_employee(item)
        was_updated = was_created

        # check and update main fields
        if not was_created and item.differs_from_summary(summary):
            self.logger.debug(f"Item {item.id}: summary differs")
            personal_details = await self.client.fetch_employee_personal_details(
                summary.emp_number,
            )
            personal_details.first_name = item.first_name
            personal_details.middle_name = item.middle_name
            personal_details.last_name = item.last_name
            await self.client.update_employee_personal_details(
                summary.emp_number,
                personal_details,
            )
            was_updated = True

        # contact details
        if was_created:  # then contact details aren't filled yet
            await self.client.update_employee_contact_details(
                summary.emp_number,
                EmployeeContactDetails(
                    work_telephone=item.phone,
                    work_email=item.email,
                ),
            )
        elif summary.contact_info.work_email != (
            item.email or None
        ) or summary.contact_info.work_telephone != (item.phone or None):
            self.logger.debug(f"Item {item.id}: contact details differ")
            contact_details = await self.client.fetch_employee_contact_details(
                summary.emp_number,
            )
            contact_details.work_email = item.email
            contact_details.work_telephone = item.phone
            await self.client.update_employee_contact_details(
                summary.emp_number,
                contact_details,
            )
            was_updated = True

        # salary data
        if (
            was_created
            or len(await self.client.fetch_all_salary_attachments(summary.emp_number))
            == 0
        ):
            self.logger.debug(f"Item {item.id}: uploading salary doc")
            await self.client.add_salary_attachment(
                summary.emp_number,
                SalaryAttachmentUpload.from_bytes(
                    "salary.txt",
                    item.salary.encode("utf-8"),
                ),
                description="salary upload from portal runner",
            )
            was_updated = True

        # job data
        if was_created:
            await self.client.update_employee_job_details(
                summary.emp_number,
                EmployeeJobDetails(),
            )
        else:
            job_details = await self.client.fetch_employee_job_details(
                summary.emp_number,
            )
            if (
                job_details.job_title.title != item.job_title
                or job_details.emp_status.name != item.employment_status
            ):
                self.logger.debug(f"Item {item.id}: job details differ")
                job_details = await self.construct_job_details(item)
                await self.client.update_employee_job_details(
                    summary.emp_number,
                    job_details,
                )
                was_updated = True

        if was_created:
            return ItemProcessingResult.CREATED

        if was_updated:
            return ItemProcessingResult.UPDATED

        return ItemProcessingResult.UNCHANGED

    async def before_run(self) -> None:  # noqa: D102
        self._session = aiohttp.ClientSession()
        self.client = OrangeHRMClient(self._session, self.config.model_dump())
        username = os.environ[self.config.username_env_var]
        password = os.environ[self.config.password_env_var]
        await self.client.login(username, password)
        await self.cache_existing_data()

    async def after_run(self) -> None:  # noqa: D102
        await self._session.close()

    async def cache_existing_data(self) -> None:
        """Prefetch all existing employees and their data.

        This is not a production-ready approach - there is an API for searching
        employers, but implementing that is a bit overkill for a demo task, because
        matching people data is complex task. For now, I'll just use emails as unique
        identifiers. Employees without email are just skipped.
        """
        self._employees_cache = {}
        self.logger.info("Caching existing data...")
        for summary in await self.client.fetch_all_employees(use_detailed_model=True):
            if summary.contact_info.work_email:
                salary_attachments = await self.client.fetch_all_salary_attachments(
                    summary.emp_number,
                )
                self._employees_cache[summary.contact_info.work_email] = EmployeeCache(
                    summary=summary,
                    salary_attachments=salary_attachments,
                )

        self.logger.info(f"Cached data for {len(self._employees_cache)} employees")

        statuses = await self.client.fetch_all_employment_statuses()
        self._employment_statuses_cache = {(s.name or ""): s for s in statuses}

        job_titles = await self.client.fetch_all_job_titles()
        self._job_titles_cache = {(t.title or ""): t for t in job_titles}

    async def get_or_create_employee(
        self,
        input_item: OrangeHRMPortalRunnerInputItem,
    ) -> tuple[EmployeeSummary, bool]:
        """Look for existing employee and create one, if does not exist.

        Returns (EmployeeSummary, was_created).
        """

        if cached_item := self._employees_cache.get(input_item.email):
            self.logger.debug(f"Item {input_item.id}: found in cache")
            return cached_item.summary, False

        self.logger.debug(f"Item {input_item.id}: creating new")
        employee_num = await self.client.create_employee_with_retry(
            EmployeeCreateRequest(
                first_name=input_item.first_name,
                last_name=input_item.last_name,
                middle_name=input_item.middle_name,
                employee_id="",
                emp_picture=None,
            ),
        )
        await self.client.update_employee_contact_details(
            employee_num,
            EmployeeContactDetails(work_telephone=input_item.phone),
        )
        created_employee = await self.client.fetch_employee(employee_num)
        return created_employee, True

    async def get_or_create_employment_status(
        self,
        input_item: OrangeHRMPortalRunnerInputItem,
    ) -> tuple[EmploymentStatus, bool]:
        """Look for existing employment status and create one, if does not exist.

        Also, if one was created, update self._employment_statuses_cache to avoid
        duplicates in future items.
        Returns (EmploymentStatus, was_created).
        """
        if status := self._employment_statuses_cache.get(
            input_item.employment_status,
        ):
            return (status, False)

        self.logger.debug(f"Creating employment status {input_item.employment_status}")
        status_id = await self.client.create_employment_status(
            EmploymentStatus(name=input_item.employment_status),
        )
        status = EmploymentStatus(id=status_id, name=input_item.employment_status)
        self._employment_statuses_cache[input_item.employment_status] = status
        return status, True

    async def get_or_create_job_title(
        self,
        input_item: OrangeHRMPortalRunnerInputItem,
    ) -> tuple[JobTitle, bool]:
        """Look for existing job title and create one, if does not exist.

        Also, if one was created, update self._job_titles_cache to avoid
        duplicates in future items.
        Returns (EmploymentStatus, was_created).
        """
        if job_title := self._job_titles_cache.get(
            input_item.job_title,
        ):
            return (job_title, False)

        job_title_id = await self.client.create_job_title(
            JobTitle(title=input_item.job_title),
        )
        job_title = JobTitle(id=job_title_id, title=input_item.job_title)
        self._job_titles_cache[input_item.job_title] = job_title
        return job_title, True

    async def construct_job_details(  # noqa: D102
        self,
        input_item: OrangeHRMPortalRunnerInputItem,
    ) -> EmployeeJobDetails:
        employment_status, _ = (
            await self.get_or_create_employment_status(
                input_item,
            )
            if input_item.employment_status
            else (EmploymentStatus(), False)
        )
        job_title, _ = (
            await self.get_or_create_job_title(input_item)
            if input_item.job_title
            else (JobTitle(), False)
        )
        return EmployeeJobDetails(emp_status=employment_status, job_title=job_title)

"""OrangeHRM client class module."""

import json
import logging
from http import HTTPStatus
from typing import Any, TypeVar
from urllib.parse import urlencode, urlsplit, urlunsplit

import aiohttp
from bs4 import BeautifulSoup
from pydantic import BaseModel, ValidationError

from portals.errors import RecoverablePortalError, UnrecoverablePortalError
from portals.orange_hrm.models import (
    ApiResponse,
    CreateEmployeeData,
    EmployeeCreateRequest,
    EmployeeJobDetails,
    EmployeePersonalDetails,
    EmployeesPage,
    EmployeeSummary,
    EmploymentStatus,
    EmploymentStatusesPage,
    SalaryAttachment,
    SalaryAttachmentsPage,
    SalaryAttachmentUpload,
    UniqueCheckData,
)

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)


class OrangeHRMUnexpectedDataError(UnrecoverablePortalError):
    """Server's output changed means we most likely have to update the parsing code."""

    def __init__(self, details: str):
        super().__init__(f"OrangeHRM output data changed: {details}")


class OrangeHRMRegularError(RecoverablePortalError):
    """Errors that do not mean we should abort doing what we doing - e.g.
    invalid object id.
    """  # noqa: D205

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        data: dict | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.data = data


DEFAULT_CONFIG = {
    "base_url": "https://opensource-demo.orangehrmlive.com/",
    "tracing_enabled": False,
}


class OrangeHRMClient:
    """Simple CRUD API client for the https://opensource-demo.orangehrmlive.com/."""

    base_url: str
    login_path = "/web/index.php/auth/login"
    dashboard_path = "/web/index.php/dashboard/index"
    employees_path = "/web/index.php/api/v2/directory/employees"
    _session: aiohttp.ClientSession

    def __init__(
        self,
        session: aiohttp.ClientSession,
        config: dict[str, Any] | None = None,
    ):
        """Load config and prepare internal variables."""

        full_config = DEFAULT_CONFIG.copy()
        if config is not None:
            full_config.update(config)

        self.base_url = full_config["base_url"]
        self.tracing_enabled = full_config["tracing_enabled"]
        logger.debug(
            f"base_url={self.base_url}, tracing_enabled={self.tracing_enabled}",
        )

        self._session = session
        self._url_parts = urlsplit(self.base_url)

    def _url(self, path: str, query: dict | None = None) -> str:
        query_str = urlencode(query) if query else ""
        return urlunsplit(
            (self._url_parts.scheme, self._url_parts.netloc, path, query_str, None),
        )

    async def _api_call(
        self,
        method: str,
        path: str,
        response_type: type[T],
        *,
        query: dict | None = None,
        json_body: dict | None = None,
    ) -> T:
        """Make a JSON API call, check for errors, and validate the response."""

        if self.tracing_enabled:
            logger.debug(f"{method} {path}")
            logger.debug(f"{json.dumps(json_body or {}, indent=2)}")

        async with self._session.request(
            method,
            self._url(path, query),
            json=json_body,
        ) as response:
            try:
                data = await response.json()
            except (aiohttp.ContentTypeError, json.JSONDecodeError):
                data = None

            if self.tracing_enabled:
                logger.debug("Response:")
                logger.debug(f"{json.dumps(data or {}, indent=2)}")

            status = response.status

            if isinstance(data, dict) and (error := data.get("error")):
                error_msg, error_data = (
                    (error.get("message"), error.get("data"))
                    if isinstance(error, dict)
                    else (str(error), None)
                )

                raise OrangeHRMRegularError(
                    f"{method} {path} error: {error_msg}",
                    status=status,
                    data=error_data,
                )

            try:
                response.raise_for_status()
            except aiohttp.ClientResponseError as exc:
                raise OrangeHRMRegularError(
                    f"{method} {path} failed with status {exc.status}",
                    status=exc.status,
                ) from exc

        try:
            return response_type.model_validate(data)
        except ValidationError as exc:
            raise OrangeHRMUnexpectedDataError(
                f"unexpected response shape from {method} {path}",
            ) from exc

    async def _get_token(self) -> str:
        logger.debug("Fetching login page...")
        async with self._session.get(self._url(self.login_path)) as response:
            html = await response.content.read()

        logger.debug("Extracting token")
        soup = BeautifulSoup(html, features="html.parser")
        if auth_tag := soup.select_one("auth-login"):
            token = str(auth_tag.attrs.get(":token")) or ""
            return token.strip('"')

        raise OrangeHRMUnexpectedDataError("No token found on login page")

    async def login(self, username: str, password: str) -> None:
        """Perform a login with the current self.session.

        If unsuccessful, an exception is raised.
        """
        payload = {
            "_token": await self._get_token(),
            "username": username,
            "password": password,
        }
        logger.debug("Logging in...")
        async with self._session.post(
            self._url("/web/index.php/auth/validate"),
            data=payload,
            allow_redirects=True,
        ) as response:
            status = response.status
            location = response.url.path
            logger.debug(f"Login response status: {status=}, {location=}")
            if status == HTTPStatus.OK and location == self.login_path:
                # if we got back to login page, there is an error - now we need to
                # extract the text
                html = await response.content.read()
                soup = BeautifulSoup(html, features="html.parser")
                if auth_tag := soup.select_one("auth-login"):
                    error_str = str(auth_tag.attrs.get(":error")) or ""
                    try:
                        error_data = json.loads(error_str)
                        error = error_data["message"]
                    except:  # noqa: E722
                        error = error_str
                        error_data = None
                else:
                    error = "login: unknown error"
                raise OrangeHRMUnexpectedDataError(
                    f"login: {error}",
                )

    async def fetch_employees_page(
        self,
        limit: int = 100,
        offset: int = 0,
        *,
        use_detailed_model: bool = False,
    ) -> EmployeesPage:
        """Fetch a single page from the OrangeHRM employee directory."""
        if limit <= 0:
            raise ValueError("limit must be positive")
        if offset < 0:
            raise ValueError("offset must be non-negative")

        logger.debug(
            f"Fetching employees page: {limit=}, {offset=}, {use_detailed_model=}",
        )
        query: dict[str, str | int] = {"limit": limit, "offset": offset}
        if use_detailed_model:
            query["model"] = "detailed"

        return await self._api_call(
            "GET",
            self.employees_path,
            EmployeesPage,
            query=query,
        )

    async def fetch_all_employees(
        self,
        page_size: int = 100,
        *,
        use_detailed_model: bool = False,
    ) -> list[EmployeeSummary]:
        """Fetch all employees from the OrangeHRM employee directory."""
        if page_size <= 0:
            raise ValueError("page_size must be positive")

        employees: list[EmployeeSummary] = []
        offset = 0
        page_total: int | None = None
        while page_total is None or page_total >= page_size:
            page = await self.fetch_employees_page(
                limit=page_size,
                offset=offset,
                use_detailed_model=use_detailed_model,
            )
            total_reported = page.meta.total
            page_total = len(page.data)
            employees.extend(page.data)

            if len(employees) >= total_reported:
                break

            offset += page_size

        logger.debug(f"{page_total=}, {offset=}, {total_reported=}")

        return employees

    async def fetch_employee(self, employee_id: int) -> EmployeeSummary:
        """Fetch single employee data from OrangeHRM employee directory."""
        return (
            await self._api_call(
                "GET",
                f"/web/index.php/api/v2/directory/employees/{employee_id}",
                ApiResponse[EmployeeSummary],
                query={"model": "detailed"},
            )
        ).data

    async def is_employee_id_free(self, employee_id: str) -> bool:
        """Test whether employee id is already used in OrangeHRM."""
        return (
            await self._api_call(
                "GET",
                "/web/index.php/api/v2/core/validation/unique",
                ApiResponse[UniqueCheckData],
                query={
                    "value": employee_id,
                    "entityName": "Employee",
                    "attributeName": "employeeId",
                },
            )
        ).data.valid

    async def fetch_suggested_new_employee_id(self) -> str:
        """Fetch suggested unused employee id unused."""

        async with self._session.get(
            self._url("/web/index.php/pim/addEmployee"),
        ) as response:
            html = await response.content.read()
            soup = BeautifulSoup(html, features="html.parser")
            if suggested_data := soup.select_one("employee-save"):
                return str(suggested_data.attrs[":emp-id"]).strip('"')

        raise OrangeHRMUnexpectedDataError("Error fetching suggested new employee id")

    async def create_employee(self, employee: EmployeeCreateRequest) -> int:
        """Create new employee with and return its number."""

        emp_number = (
            await self._api_call(
                "POST",
                "/web/index.php/api/v2/pim/employees",
                ApiResponse[CreateEmployeeData],
                json_body=employee.model_dump(by_alias=True),
            )
        ).data.emp_number

        logger.debug(f"Created employee {emp_number}")
        return emp_number

    async def create_employee_with_retry(
        self,
        employee: EmployeeCreateRequest,
        max_retries: int = 3,
    ) -> int:
        """Retry creating employee multiple times.

        For every retry(including 1st one) new suggested value for employeeId is
        fetched. So, any value passed in
        employee.employee_id will be overriden.
        """
        retries = max_retries
        while retries >= 0:
            retries -= 1
            try:
                employee_id = await self.fetch_suggested_new_employee_id()
                employee = employee.model_copy(update={"employee_id": employee_id})

                return await self.create_employee(employee)
            except OrangeHRMRegularError as exc:
                if exc.status != HTTPStatus.UNPROCESSABLE_ENTITY:
                    raise
        raise OrangeHRMRegularError(
            f"couldn't create employee with unique id after {max_retries} retries",
        )

    async def delete_employees(self, employee_nums: list[int]) -> None:
        """Delete employees with a given numbers."""

        logger.debug(f"Deleting employees {employee_nums}")
        deleted_nums = (
            await self._api_call(
                "DELETE",
                "/web/index.php/api/v2/pim/employees",
                ApiResponse[list[int]],
                json_body={"ids": employee_nums},
            )
        ).data

        if sorted(employee_nums) != sorted(deleted_nums):
            raise OrangeHRMUnexpectedDataError(
                "reported list of deleted employees differs from the request. "
                f"Requested {employee_nums}, reported {deleted_nums}",
            )

    async def fetch_employee_personal_details(
        self,
        employee_num: int,
    ) -> EmployeePersonalDetails:
        """Fetch employee's personal details by employee number."""
        return (
            await self._api_call(
                "GET",
                f"/web/index.php/api/v2/pim/employees/{employee_num}/personal-details",
                ApiResponse[EmployeePersonalDetails],
            )
        ).data

    async def update_employee_personal_details(
        self,
        employee_num: int,
        personal_details: EmployeePersonalDetails,
    ) -> EmployeePersonalDetails:
        """Update employee personal details."""
        return (
            await self._api_call(
                "PUT",
                f"/web/index.php/api/v2/pim/employees/{employee_num}/personal-details",
                ApiResponse[EmployeePersonalDetails],
                json_body=personal_details.model_dump(by_alias=True),
            )
        ).data

    async def fetch_employee_job_details(
        self,
        employee_num: int,
    ) -> EmployeeJobDetails:
        """Fetch employee's job details by employee number."""
        return (
            await self._api_call(
                "GET",
                f"/web/index.php/api/v2/pim/employees/{employee_num}/job-details",
                ApiResponse[EmployeeJobDetails],
            )
        ).data

    async def update_employee_job_details(
        self,
        employee_num: int,
        job_details: EmployeeJobDetails,
    ) -> EmployeeJobDetails:
        """Update employee job details."""
        return (
            await self._api_call(
                "PUT",
                f"/web/index.php/api/v2/pim/employees/{employee_num}/job-details",
                ApiResponse[EmployeeJobDetails],
                json_body=job_details.to_update_payload(),
            )
        ).data

    async def fetch_salary_attachments_page(
        self,
        employee_num: int,
        limit: int = 100,
        offset: int = 0,
    ) -> SalaryAttachmentsPage:
        """Fetch a single page of salary attachments for an employee."""
        if limit <= 0:
            raise ValueError("limit must be positive")
        if offset < 0:
            raise ValueError("offset must be non-negative")

        logger.debug(
            f"Fetching salary attachments page: {employee_num=}, {limit=}, {offset=}",
        )
        return await self._api_call(
            "GET",
            f"/web/index.php/api/v2/pim/employees/{employee_num}/screen/salary/attachments",
            SalaryAttachmentsPage,
            query={"limit": limit, "offset": offset},
        )

    async def add_salary_attachment(
        self,
        employee_num: int,
        attachment: SalaryAttachmentUpload,
        description: str = "",
    ) -> SalaryAttachment:
        """Upload a salary attachment for an employee."""
        return (
            await self._api_call(
                "POST",
                f"/web/index.php/api/v2/pim/employees/{employee_num}/screen/salary/attachments",
                ApiResponse[SalaryAttachment],
                json_body={
                    "attachment": attachment.model_dump(),
                    "description": description,
                },
            )
        ).data

    async def fetch_all_salary_attachments(
        self,
        employee_num: int,
        page_size: int = 100,
    ) -> list[SalaryAttachment]:
        """Fetch all salary attachments for an employee."""
        if page_size <= 0:
            raise ValueError("page_size must be positive")

        attachments: list[SalaryAttachment] = []
        offset = 0
        page_total: int | None = None
        while page_total is None or page_total >= page_size:
            page = await self.fetch_salary_attachments_page(
                employee_num,
                limit=page_size,
                offset=offset,
            )
            total_reported = page.meta.total
            page_total = len(page.data)
            attachments.extend(page.data)

            if len(attachments) >= total_reported:
                break

            offset += page_size

        logger.debug(f"{page_total=}, {offset=}, {total_reported=}")

        return attachments

    async def fetch_employee_attachment(
        self,
        employee_num: int,
        attachment_id: int,
    ) -> bytes:
        """Download employee [salary] attachment."""

        async with self._session.get(
            self._url(
                f"/web/index.php/pim/viewAttachment/empNumber/{employee_num}/attachId/{attachment_id}"  # noqa: COM812
            ),
        ) as response:
            try:
                response.raise_for_status()
            except aiohttp.ClientResponseError as exc:
                raise OrangeHRMRegularError(
                    "error fetching employee attachment",
                ) from exc

            return await response.content.read()

    async def fetch_all_employment_statuses(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EmploymentStatus]:
        """Fetch a single page of employment statuses.

        Since its a demo task, there is not much point in implementing a multi-page
        fetching here.
        """

        if limit <= 0:
            raise ValueError("limit must be positive")
        if offset < 0:
            raise ValueError("offset must be non-negative")

        return (
            await self._api_call(
                "GET",
                "/web/index.php/api/v2/admin/employment-statuses",
                EmploymentStatusesPage,
                query={"limit": limit, "offset": offset},
            )
        ).data

    async def create_employment_status(self, emp_status: EmploymentStatus) -> int:
        """Create new employment status."""
        response = await self._api_call(
            "POST",
            "/web/index.php/api/v2/admin/employment-statuses",
            ApiResponse[EmploymentStatus],
            json_body=emp_status.model_dump(by_alias=True, exclude={"id"}),
        )

        if response.data.id is None:
            raise OrangeHRMUnexpectedDataError("status creation request returned no id")

        return response.data.id

    async def delete_employment_statuses(self, emp_statuses_ids: list[int]) -> None:
        """Delete employment statuses with given ids."""

        logger.debug(f"Deleting employment statuses {emp_statuses_ids}")
        deleted_nums = (
            await self._api_call(
                "DELETE",
                "/web/index.php/api/v2/admin/employment-statuses",
                ApiResponse[list[int]],
                json_body={"ids": emp_statuses_ids},
            )
        ).data

        if sorted(emp_statuses_ids) != sorted(deleted_nums):
            raise OrangeHRMUnexpectedDataError(
                "reported list of deleted statuses differs from the request. "
                f"Requested {emp_statuses_ids}, reported {deleted_nums}",
            )

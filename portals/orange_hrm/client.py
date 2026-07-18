"""OrangeHRM client class module."""

import json
import logging
from http import HTTPStatus
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

import aiohttp
from bs4 import BeautifulSoup
from pydantic import ValidationError

from portals.errors import RecoverablePortalError, UnrecoverablePortalError
from portals.orange_hrm.models import (
    EmployeePersonalDetails,
    EmployeesPage,
    EmployeeSummary,
)

logger = logging.getLogger(__name__)


class OrangeHRMUnexpectedDataError(UnrecoverablePortalError):
    """Server's output changed means we most likely have to update the parsing code."""

    def __init__(self, details: str):
        super().__init__(f"OrangeHRM output data changed: {details}")


class OrangeHRMRegularError(RecoverablePortalError):
    """Errors that do not mean we should abort doing what we doing - e.g.
    invalid object id.
    """  # noqa: D205


DEFAULT_CONFIG = {
    "base_url": "https://opensource-demo.orangehrmlive.com/",
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

        self._session = session
        self._url_parts = urlsplit(self.base_url)

    def _url(self, path: str, query: dict | None = None) -> str:
        query_str = urlencode(query) if query else ""
        return urlunsplit(
            (self._url_parts.scheme, self._url_parts.netloc, path, query_str, None),
        )

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
    ) -> EmployeesPage:
        """Fetch a single page from the OrangeHRM employee directory."""
        if limit <= 0:
            raise ValueError("limit must be positive")
        if offset < 0:
            raise ValueError("offset must be non-negative")

        logger.debug(f"Fetching employees page: {limit=}, {offset=}")
        async with self._session.get(
            self._url(self.employees_path, {"limit": limit, "offset": offset}),
        ) as response:
            if response.status != HTTPStatus.OK:
                raise OrangeHRMUnexpectedDataError(
                    f"employee list returned unexpected status {response.status}",
                )
            data = await response.json()

        try:
            return EmployeesPage.model_validate(data)
        except ValidationError as exc:
            raise OrangeHRMUnexpectedDataError(
                "employee page does not have one of the required fields",
            ) from exc

    async def fetch_all_employees(
        self,
        page_size: int = 100,
    ) -> list[EmployeeSummary]:
        """Fetch all employees from the OrangeHRM employee directory."""
        if page_size <= 0:
            raise ValueError("page_size must be positive")

        employees: list[EmployeeSummary] = []
        offset = 0
        page_total: int | None = None
        while page_total is None or page_total >= page_size:
            page = await self.fetch_employees_page(limit=page_size, offset=offset)
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
        async with self._session.get(
            self._url(
                f"/web/index.php/api/v2/directory/employees/{employee_id}",
                {"model": "detailed"},
            ),
        ) as response:
            data = await response.json()

        if error := data.get("error"):
            raise OrangeHRMRegularError(
                f"Error fetching employee {employee_id}: {error}",
            )

        try:
            return EmployeeSummary.model_validate(data["data"])
        except (KeyError, ValidationError) as exc:
            raise OrangeHRMUnexpectedDataError(
                "employee dict does not contain required keys",
            ) from exc

    async def is_employee_id_free(self, employee_id: str) -> bool:
        """Test whether employee id is already used in OrangeHRM."""
        async with self._session.get(
            self._url(
                "/web/index.php/api/v2/core/validation/unique",
                {
                    "value": employee_id,
                    "entityName": "Employee",
                    "attributeName": "employeeId",
                },
            ),
        ) as response:
            response.raise_for_status()
            data = await response.json()
            try:
                return bool(data["data"]["valid"])
            except KeyError as exc:
                raise OrangeHRMUnexpectedDataError(
                    "employee id check response does not have one or "
                    "more required keys",
                ) from exc

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

    async def create_employee(
        self,
        first_name: str,
        middle_name: str,
        last_name: str,
    ) -> int:
        """Create new employee with and return its number."""

        employee_id = await self.fetch_suggested_new_employee_id()

        async with self._session.post(
            self._url("/web/index.php/api/v2/pim/employees"),
            json={
                "firstName": first_name,
                "middleName": middle_name,
                "lastName": last_name,
                "empPicture": None,
                "employeeId": str(employee_id),
            },
        ) as response:
            try:
                response.raise_for_status()
            except Exception as exc:
                raise OrangeHRMRegularError("error creating employee") from exc

            data = await response.json()

            try:
                employee_num = data["data"]["empNumber"]
            except KeyError as exc:
                raise OrangeHRMUnexpectedDataError(
                    "unexpected response on creating employee",
                ) from exc

        logger.debug(f"Created employee {employee_num}")
        return employee_num

    async def delete_employees(self, employee_nums: list[int]) -> None:
        """Delete employees with a given numbers."""

        logger.debug(f"Deleting employees {employee_nums}")
        async with self._session.delete(
            self._url("/web/index.php/api/v2/pim/employees"),
            json={"ids": employee_nums},
        ) as response:
            try:
                response.raise_for_status()
            except Exception as exc:
                raise OrangeHRMRegularError("error deleting employee") from exc

            data = await response.json()

            try:
                deleted_nums = [int(emp_num) for emp_num in data["data"]]
            except KeyError as exc:
                raise OrangeHRMUnexpectedDataError(
                    "unexpected response on deleting employees",
                ) from exc

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
        async with self._session.get(
            self._url(
                f"/web/index.php/api/v2/pim/employees/{employee_num}/personal-details",
            ),
        ) as response:
            data = await response.json()

        if error := data.get("error"):
            error_msg = str(error)
            if isinstance(error, dict):
                error_msg = error.get("message") or error_msg

            raise OrangeHRMRegularError(
                f"Error fetching employee {employee_num}: {error}",
            )

        try:
            personal_data_raw = data["data"]
            return EmployeePersonalDetails.model_validate(personal_data_raw)
        except (KeyError, ValidationError) as exc:
            raise OrangeHRMUnexpectedDataError(
                "employee dict does not contain required keys",
            ) from exc

    async def update_employee_personal_details(
        self,
        employee_num: int,
        personal_details: EmployeePersonalDetails,
    ) -> EmployeePersonalDetails:
        """Update employee personal details."""

        async with self._session.put(
            self._url(
                f"/web/index.php/api/v2/pim/employees/{employee_num}/personal-details",
            ),
            json=personal_details.model_dump(by_alias=True),
        ) as response:
            try:
                response.raise_for_status()
                data = await response.json()
            except Exception as exc:
                raise OrangeHRMRegularError(
                    "error updating employee {employee_num} personal details",
                ) from exc

            try:
                return EmployeePersonalDetails.model_validate(data["data"])
            except (KeyError, ValidationError) as exc:
                raise OrangeHRMUnexpectedDataError(
                    "unexpected response when updating "
                    f"employee {employee_num} personal details",
                ) from exc

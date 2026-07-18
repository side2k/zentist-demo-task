"""Pydantic models for OrangeHRM API responses."""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Generic wrapper for OrangeHRM API responses with shape {data, meta, rels}."""

    data: T


class EmployeeSubunit(BaseModel):
    """Subunit reference on an employee record."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: int | None = None
    name: str | None = None


class EmployeeLocation(BaseModel):
    """Location reference on an employee record."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: int | None = None
    name: str | None = None


class JobTitle(BaseModel):
    """Job title sub-object on an employee record."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: int | None = None
    title: str | None = None
    is_deleted: bool | None = None


class ContactInfo(BaseModel):
    """Contact info sub-object on an employee record."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    work_email: str | None = None
    work_telephone: str | None = None


class BaseEmployee(BaseModel):
    """Base class for several employee models to keep them DRY."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    first_name: str
    last_name: str
    middle_name: str = ""


class EmployeeSummary(BaseEmployee):
    """Employee summary as returned by the directory endpoint."""

    emp_number: int
    termination_id: int | None = None
    job_title: JobTitle = JobTitle()
    subunit: EmployeeSubunit = EmployeeSubunit()
    location: EmployeeLocation = EmployeeLocation()
    contact_info: ContactInfo = ContactInfo()


class EmployeeCreateRequest(BaseEmployee):
    """Employee model for the creation request."""

    emp_picture: None
    employee_id: str


class EmployeesPageMeta(BaseModel):
    """Metadata returned with an employee directory page."""

    total: int


class EmployeesPage(ApiResponse[list[EmployeeSummary]]):
    """A single page from the employee directory endpoint."""

    meta: EmployeesPageMeta


class CreateEmployeeData(BaseModel):
    """Inner data object returned when creating an employee."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    emp_number: int


class UniqueCheckData(BaseModel):
    """Inner data object from the uniqueness validation endpoint."""

    valid: bool


class EmployeePersonalDetails(BaseModel):
    """Employee's personal details model."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    first_name: str
    last_name: str
    middle_name: str = ""
    employee_id: str = ""
    other_id: str = ""
    driving_license_no: str = ""
    driving_license_expired_date: str | None = None
    gender: int | None = None
    birthday: str | None = None

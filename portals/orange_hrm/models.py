"""Pydantic models for OrangeHRM API responses."""

import base64
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
    unit_id: str | None = None


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


class SalaryAttachmentUpload(BaseModel):
    """Attachment payload for the salary attachment upload endpoint."""

    name: str
    # text/plain is hardcoded for demo task purposes
    type: str = "text/plain"
    size: int
    base64: str

    @classmethod
    def from_bytes(cls, filename: str, content: bytes) -> "SalaryAttachmentUpload":
        """Build an upload payload from raw bytes."""
        return cls(
            name=filename,
            size=len(content),
            base64=base64.b64encode(content).decode(),
        )


class SalaryAttachment(BaseModel):
    """A single salary attachment entry on an employee record."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: int
    description: str | None = None
    filename: str
    size: int
    file_type: str | None = None
    attached_by: int | None = None
    attached_by_name: str | None = None
    attached_time: str | None = None
    attached_date: str | None = None


class SalaryAttachmentsPageMeta(BaseModel):
    """Metadata returned with a salary attachments page."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    emp_number: int
    screen: str
    total: int


class SalaryAttachmentsPage(ApiResponse[list[SalaryAttachment]]):
    """A single page from the salary attachments endpoint."""

    meta: SalaryAttachmentsPageMeta


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


class JobSpecificationAttachment(BaseModel):
    """Job specification attachment reference on an employee job details record."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: int | None = None
    filename: str | None = None


class EmploymentStatus(BaseModel):
    """Employment status reference on an employment status record."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: int | None = None
    name: str | None = None


class EmploymentStatusesPageMeta(BaseModel):
    """Metadata returned with a employement statuses page."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    total: int


class EmploymentStatusesPage(ApiResponse[list[EmploymentStatus]]):
    """A single page from the employement statuses endpoint."""

    meta: EmploymentStatusesPageMeta


class JobCategory(BaseModel):
    """Job category reference on an employee job details record."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: int | None = None
    name: str | None = None


class EmployeeTerminationRecord(BaseModel):
    """Termination record reference on an employee job details record."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: int | None = None
    date: str | None = None


class EmployeeJobDetails(BaseModel):
    """Employee's job details model."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    emp_number: int | None = None
    joined_date: str | None = None
    job_title: JobTitle = JobTitle()
    job_specification_attachment: JobSpecificationAttachment = (
        JobSpecificationAttachment()
    )
    emp_status: EmploymentStatus = EmploymentStatus()
    job_category: JobCategory = JobCategory()
    subunit: EmployeeSubunit = EmployeeSubunit()
    location: EmployeeLocation = EmployeeLocation()
    employee_termination_record: EmployeeTerminationRecord = EmployeeTerminationRecord()

    def to_update_payload(self) -> dict:
        """Build the flat payload accepted by the job-details PUT endpoint.

        Fields with a None value are omitted.
        """
        payload = {
            "joinedDate": self.joined_date,
            "jobTitleId": self.job_title.id,
            "empStatusId": self.emp_status.id,
            "jobCategoryId": self.job_category.id,
            "subunitId": self.subunit.id,
            "locationId": self.location.id,
        }
        return {key: value for key, value in payload.items() if value is not None}

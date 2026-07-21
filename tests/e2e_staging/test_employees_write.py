"""Write-path tests against the live OrangeHRM portal."""

import pytest

pytestmark = pytest.mark.e2e_staging


@pytest.mark.usefixtures("orange_hrm_client", "orange_hrm_employee")
async def test_create_and_delete_employee() -> None:
    pass

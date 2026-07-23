"""OrangeHRM portal implementation."""

from portals.base_runner import PortalItemError as ErrorItem

from .runner import OrangeHRMItemProcessingResult as OutputItem
from .runner import OrangeHRMPortalRunner as Runner

__all__ = [
    "ErrorItem",
    "OutputItem",
    "Runner",
]

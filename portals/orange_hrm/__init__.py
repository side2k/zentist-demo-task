"""OrangeHRM portal implementation."""

from .runner import OrangeHRMItemProcessingResult as OutputItem
from .runner import OrangeHRMPortalRunner as Runner

__all__ = [
    "OutputItem",
    "Runner",
]

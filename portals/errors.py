"""Error classes for the portal processors."""


class UnrecoverablePortalError(Exception):
    """Error that portal client can't recover from."""


class RecoverablePortalError(Exception):
    """Error that doesn't force portal client to stop working."""

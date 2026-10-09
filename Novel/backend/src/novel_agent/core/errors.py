from __future__ import annotations

from typing import Any


class APIError(Exception):
    """An expected API failure with a stable machine-readable error code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = {} if details is None else details

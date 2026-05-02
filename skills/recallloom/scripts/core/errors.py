from __future__ import annotations

"""Shared RecallLoom runtime error types."""


class RecallLoomError(RuntimeError):
    """Base error with an optional stable failure reason."""

    def __init__(self, message: str, *, failure_reason: str | None = None) -> None:
        super().__init__(message)
        self.failure_reason = failure_reason


class StorageResolutionError(RecallLoomError):
    """Raised when RecallLoom storage roots are ambiguous or invalid."""


class ConfigContractError(RecallLoomError):
    """Raised when config.json is malformed or violates the protocol contract."""


class EnvironmentContractError(RecallLoomError):
    """Raised when the runtime environment does not satisfy package requirements."""


class LockBusyError(RecallLoomError):
    """Raised when a project-scoped write lock is already held."""

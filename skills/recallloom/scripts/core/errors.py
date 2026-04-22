"""Shared RecallLoom runtime error types."""


class StorageResolutionError(RuntimeError):
    """Raised when RecallLoom storage roots are ambiguous or invalid."""


class ConfigContractError(RuntimeError):
    """Raised when config.json is malformed or violates the protocol contract."""


class EnvironmentContractError(RuntimeError):
    """Raised when the runtime environment does not satisfy package requirements."""


class LockBusyError(RuntimeError):
    """Raised when a project-scoped write lock is already held."""

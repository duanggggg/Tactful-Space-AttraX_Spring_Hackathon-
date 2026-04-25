"""Custom exceptions for the scaffold."""


class HomeKGMasError(Exception):
    """Base exception for repository-specific errors."""


class ValidationError(HomeKGMasError):
    """Raised when a generated plan is invalid."""

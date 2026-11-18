"""Application-wide errors."""

from __future__ import annotations


class AssistantError(Exception):
    """Base error for the assistant."""


class ReadOnlyViolation(AssistantError):
    """Raised when a statement that would write to POS_DB is attempted."""


class ConnectorError(AssistantError):
    """Raised when the POS connection or a POS query fails."""


class ValidationError(AssistantError):
    """Raised when user input or a setting is invalid."""


class OverrideReasonRequired(ValidationError):
    """Raised when a manual quantity override is saved without a reason."""

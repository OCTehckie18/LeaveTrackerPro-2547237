"""Domain errors. Each carries a stable `code` (mapped to HTTP in api/errors.py) and a friendly message."""

from collections.abc import Mapping


class DomainError(Exception):
    code = "INTERNAL"

    def __init__(self, message: str, *, fields: Mapping[str, str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.fields: dict[str, str] = dict(fields or {})


class ValidationFailed(DomainError):
    code = "VALIDATION_FAILED"

    def __init__(
        self, fields: Mapping[str, str], message: str = "Please fix the highlighted fields."
    ) -> None:
        super().__init__(message, fields=fields)


class DocumentRequired(DomainError):
    code = "DOCUMENT_REQUIRED"


class Overlap(DomainError):
    code = "OVERLAP"


class StaleVersion(DomainError):
    code = "STALE_VERSION"


class InvalidTransition(DomainError):
    code = "INVALID_TRANSITION"


class Unauthenticated(DomainError):
    code = "UNAUTHENTICATED"


class Forbidden(DomainError):
    code = "FORBIDDEN"


class NotFound(DomainError):
    code = "NOT_FOUND"


class PayloadTooLarge(DomainError):
    code = "PAYLOAD_TOO_LARGE"


class QuotaExceeded(DomainError):
    code = "QUOTA_EXCEEDED"


class UnsupportedFile(DomainError):
    code = "UNSUPPORTED_FILE"


class RateLimited(DomainError):
    code = "RATE_LIMITED"

    def __init__(self, message: str, *, retry_after: int = 60) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ServiceUnavailable(DomainError):
    code = "SERVICE_UNAVAILABLE"

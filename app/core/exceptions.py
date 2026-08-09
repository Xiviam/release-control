class DomainError(Exception):
    status_code = 400
    code = "DOMAIN_ERROR"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class NotFoundError(DomainError):
    status_code = 404
    code = "NOT_FOUND"


class ForbiddenError(DomainError):
    status_code = 403
    code = "FORBIDDEN"


class ConflictError(DomainError):
    status_code = 409
    code = "CONFLICT"


class InvalidTransitionError(ConflictError):
    code = "INVALID_RELEASE_TRANSITION"


class AuthenticationError(DomainError):
    status_code = 401
    code = "AUTHENTICATION_REQUIRED"

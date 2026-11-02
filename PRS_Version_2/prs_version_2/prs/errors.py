"""Errors shared by services and the interface."""


class PRSError(Exception):
    status_code = 400


class ValidationError(PRSError):
    pass


class AuthenticationError(PRSError):
    status_code = 401


class AuthorizationError(PRSError):
    status_code = 403


class NotFoundError(PRSError):
    status_code = 404


class ConflictError(PRSError):
    status_code = 409


class DuplicatePatientIDError(ConflictError):
    """A generated Patient ID already exists; creation may retry this conflict."""

"""Typed service-level errors. main.py maps them to clean HTTP responses (no stack traces)."""


class ServiceError(Exception):
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class BadRequestError(ServiceError):
    status_code = 400


class NotFoundError(ServiceError):
    status_code = 404

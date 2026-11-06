from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from woassi.shared.domain.errors import Conflict, DomainError, InvalidData, NotFound

HTTP_STATUSES: tuple[tuple[type[DomainError], int], ...] = (
    (NotFound, status.HTTP_404_NOT_FOUND),
    (InvalidData, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (Conflict, status.HTTP_409_CONFLICT),
)


def http_status_for(error: DomainError) -> int:
    for error_type, http_status in HTTP_STATUSES:
        if isinstance(error, error_type):
            return http_status
    return status.HTTP_400_BAD_REQUEST


def error_response(error: DomainError, http_status: int) -> JSONResponse:
    return JSONResponse(
        status_code=http_status, content={"code": error.code, "message": error.message}
    )


async def _handle_domain_error(_: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, DomainError)
    return error_response(error, http_status_for(error))


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _handle_domain_error)

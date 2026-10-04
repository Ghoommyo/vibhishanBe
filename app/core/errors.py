"""Error envelope: every error response is {"error": {"code", "message"}} (spec §4.4)."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

STATUS_BY_CODE: dict[str, int] = {
    "unauthorized": 401,
    "invalid_credentials": 401,
    "wrong_role": 403,
    "forbidden": 403,
    "not_found": 404,
    "closed": 409,
    "username_taken": 409,
    "email_taken": 409,
    "validation": 422,
    "invalid_email": 422,
}

# Fallback codes for framework-raised HTTP errors (unknown route, wrong method, ...).
_CODE_BY_STATUS: dict[int, str] = {
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "not_found",
    409: "closed",
    422: "validation",
}


class ApiError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    @property
    def status_code(self) -> int:
        return STATUS_BY_CODE.get(self.code, 400)


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


def _validation_message(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Invalid request."
    first = errors[0]
    loc = [str(p) for p in first.get("loc", ()) if p not in ("body", "query", "path")]
    field = ".".join(loc)
    msg = first.get("msg", "Invalid value")
    return f"{field}: {msg}" if field else msg


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(422, "validation", _validation_message(exc))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _CODE_BY_STATUS.get(exc.status_code, "error")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        if exc.status_code == 404 and message == "Not Found":
            message = "Not found."
        return error_response(exc.status_code, code, message)

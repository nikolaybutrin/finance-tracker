"""FastAPI application entry point.

Wires the authentication, categories, transactions and analytics routers
into a single ``app`` instance, and installs custom exception handlers
that return clear, uniform error payloads for 401, 404 and 422 responses.

Run with:

    uvicorn main:app --reload
"""

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from auth import router as auth_router
from routers_analytics import router as analytics_router
from routers_categories import router as categories_router
from routers_transactions import router as transactions_router

app = FastAPI(title="Finance Tracker")

app.include_router(auth_router)
app.include_router(categories_router)
app.include_router(transactions_router)
app.include_router(analytics_router)


# --- Exception handlers -----------------------------------------------------


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Return a uniform JSON body for any HTTPException raised by the app."""
    del request  # unused, required by handler signature
    payload = {
        "error": _error_code_for(exc.status_code),
        "status_code": exc.status_code,
        "detail": exc.detail,
    }
    return JSONResponse(
        status_code=exc.status_code,
        content=payload,
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return a readable 422 payload listing each invalid field."""
    del request
    errors = []
    for err in exc.errors():
        location = err.get("loc", ())
        # loc is like ("body", "amount") or ("query", "months") — skip the
        # first segment ("body"/"query"/"path") to surface the field name only
        field = ".".join(str(part) for part in location[1:]) or "<root>"
        errors.append(
            {
                "field": field,
                "message": err.get("msg", "Invalid value"),
                "type": err.get("type", "value_error"),
            }
        )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder(
            {
                "error": "validation_error",
                "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
                "detail": "Request validation failed",
                "errors": errors,
            }
        ),
    )


_ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
}


def _error_code_for(status_code: int) -> str:
    """Return a short machine-readable slug for the given HTTP status code."""
    return _ERROR_CODES.get(status_code, "http_error")

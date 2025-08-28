# app/api/errors.py
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    cid = request.headers.get("x-request-id")
    payload = {
        "error": {"code": exc.status_code, "message": exc.detail, "correlation_id": cid}
    }
    return JSONResponse(status_code=exc.status_code, content=payload)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    cid = request.headers.get("x-request-id")
    payload = {
        "error": {
            "code": 422,
            "message": "Validation error",
            "details": exc.errors(),
            "correlation_id": cid,
        }
    }
    return JSONResponse(status_code=422, content=payload)

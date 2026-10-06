"""
main.py — FastAPI application entry point.

Run from the backend/ directory:
    uvicorn app.main:app --reload
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mysql.connector import Error as MySQLError

from app.config import get_settings
from app.routes import auth, admin, medicine, blood, chatbot
from app.utils.errors import ServiceError

logger = logging.getLogger("medblood")
settings = get_settings()  # fails fast if JWT_SECRET is missing/placeholder

app = FastAPI(title="Integrated Medicine & Blood Management API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(medicine.router)
app.include_router(blood.router)
app.include_router(chatbot.router)


@app.exception_handler(RequestValidationError)
async def validation_handler(_req: Request, exc: RequestValidationError):
    problems = [f"{'.'.join(str(p) for p in e['loc'] if p != 'body')}: {e['msg']}" for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "Invalid input.", "errors": problems})


@app.exception_handler(ServiceError)
async def service_error_handler(_req: Request, exc: ServiceError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(MySQLError)
async def mysql_handler(_req: Request, exc: MySQLError):
    logger.exception("Database error: %s", exc)  # details stay in server logs only
    return JSONResponse(status_code=503, content={"detail": "The database is temporarily unavailable. Please try again."})


@app.exception_handler(Exception)
async def unhandled_handler(_req: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred."})


@app.get("/api/health")
def health():
    return {"status": "ok"}

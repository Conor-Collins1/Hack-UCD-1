"""FastAPI entry point. OWNER: Person 1."""
import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware
from library import core_routes, db, forecast_routes, integration_routes, pages

ROOT = Path(__file__).resolve().parent.parent
production = os.environ.get('APP_ENV') == 'production'
secret = os.environ.get('SESSION_SECRET') or os.environ.get('SECRET_KEY')
if production and (not secret or len(secret) < 32 or secret.startswith(('replace-', 'change-me'))):
    raise RuntimeError('Set SESSION_SECRET to a random value of at least 32 characters.')
if production and os.environ.get('DEMO_MODE') == '1':
    raise RuntimeError('Demo endpoints must be disabled in production.')
if production and os.environ.get('DEMO_SPEED', '1') != '1':
    raise RuntimeError('Use DEMO_SPEED=1 in production.')
if production and not os.environ.get('PUBLIC_URL', '').startswith('https://'):
    raise RuntimeError('Set PUBLIC_URL to your HTTPS website origin.')

@asynccontextmanager
async def lifespan(app):
    db.init_db()
    yield

app = FastAPI(title='Library Status API', lifespan=lifespan)

@app.middleware('http')
async def request_limits(request: Request, call_next):
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        origin = request.headers.get('origin')
        expected = os.environ.get('PUBLIC_URL') or str(request.base_url).rstrip('/')
        if request.url.path != '/webhooks/stripe' and origin and origin.rstrip('/') != expected.rstrip('/'):
            return JSONResponse({'error': 'Please submit from the app website.'}, status_code=403)
        # Check actual bytes too: Content-Length alone can be omitted or incorrect.
        total = 0
        chunks = []
        async for chunk in request.stream():
            total += len(chunk)
            chunks.append(chunk)
            if total > 65536:
                return JSONResponse({'error': 'Request is too large.'}, status_code=413)
        request._body = b''.join(chunks)
    return await call_next(request)

app.add_middleware(SessionMiddleware, secret_key=secret or secrets.token_urlsafe(48),
                   same_site='lax', https_only=production)
app.mount('/static', StaticFiles(directory=str(ROOT / 'static')), name='static')
app.include_router(core_routes.router)
app.include_router(integration_routes.router)
app.include_router(forecast_routes.router)
app.include_router(pages.router)

@app.exception_handler(HTTPException)
async def http_error(request, error):
    return JSONResponse({'error': str(error.detail)}, status_code=error.status_code, headers=error.headers)

@app.exception_handler(RequestValidationError)
async def invalid_request(request, error):
    return JSONResponse({'error': 'Please check your input and try again.'}, status_code=400)

@app.exception_handler(SQLAlchemyError)
async def database_error(request, error):
    logging.getLogger(__name__).error('Database request failed: %s', type(error).__name__)
    return JSONResponse({'error': 'Database unavailable. Please try again later.'}, status_code=503)

@app.get('/health')
def health():
    try:
        with db.engine.connect() as conn:
            conn.execute(text('SELECT 1'))
    except SQLAlchemyError:
        return JSONResponse({'error': 'Database unavailable.', 'status': 'unavailable', 'database': 'unavailable'}, status_code=503)
    return {'status': 'ok', 'database': 'connected'}

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  Ensures all models are registered with Base
from app.config import settings
from app.database import engine, Base, SessionLocal
from app.deps import get_current_user
from app.frontend import serve_frontend
from app.migrations import run_lightweight_migrations
from app.routers import auth
from app.routers import settings as settings_router
from app.routers import sources
from app.services import categories as category_service
from app.services import keys as key_service


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    # Add any columns that were introduced after the DB was first created
    run_lightweight_migrations(engine)
    with SessionLocal() as db:
        # Before anything decrypts: the key check, plain AI provider keys, "Sign everyone out".
        key_service.load(db)
        # Ensure default categories exist for each household
        category_service.seed_all_households(db)
    yield


app = FastAPI(
    title="Current API",
    description="Backend API for Current: news that learns what you like.",
    version="0.1.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# A specific origin (not "*") is required because the refresh-token cookie
# is sent with credentials. In development the Vite dev server proxies /api,
# so requests are same-origin and CORS isn't involved at all.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers_middleware(request, call_next):
    """Adds standard defensive HTTP security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if settings.APP_ENV == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


# Auth routes are public (login/register/refresh live here); everything
# else requires a valid access token.
app.include_router(auth.router)

_protected = [Depends(get_current_user)]
app.include_router(settings_router.router, dependencies=_protected)
app.include_router(sources.router, dependencies=_protected)


@app.get("/health")
def health_check():
    return {"status": "healthy"}


# In the Docker image the built React app is served by this same process, so
# the UI and API share one origin. In development Vite serves the UI instead.
if settings.FRONTEND_DIST and Path(settings.FRONTEND_DIST, "index.html").is_file():
    serve_frontend(app, Path(settings.FRONTEND_DIST))

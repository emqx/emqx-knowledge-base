"""FastAPI application for the API."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes import router as api_router, ws_router
from app.services.database import db_service
from app.config import config

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI application."""
    # Startup
    logger.info("Application startup: initializing services...")
    yield
    # Shutdown
    logger.info("Application shutdown: closing database connections...")
    db_service.close()


# Create FastAPI app
app = FastAPI(
    title="EMQX Knowledge Base API",
    description="API for the EMQX Knowledge Base",
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, you should restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add GZip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Add session middleware for WebSocket authentication if needed
app.add_middleware(
    SessionMiddleware,
    secret_key=config.secret_key,
    max_age=3600,  # 1 hour
)

# Add API routes with /api prefix
app.include_router(api_router, prefix="/api")

# Add WebSocket routes at root level
app.include_router(ws_router)


# Log available routes on startup
@app.on_event("startup")
async def startup_event():
    """Log available routes on startup."""
    routes = [
        {
            "path": route.path,
            "name": route.name,
            "methods": getattr(route, "methods", ["WS"])
            if "websocket" in route.path
            else route.methods,
        }
        for route in app.routes
    ]
    logger.info(f"Available routes: {routes}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}

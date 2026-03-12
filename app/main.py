"""FastAPI application factory for PosterPilot."""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import Config, get_resource_path
from app.routes import api, pages
from app.services.plex_client import PlexClient
from app.services.task_manager import TaskManager


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging."""
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    config = app.state.config
    setup_logging(config.app.log_level)
    logger = logging.getLogger("posterpilot")
    logger.info("PosterPilot starting up...")

    # Auto-connect if credentials are configured
    plex_client = app.state.plex_client
    if config.plex.base_url and config.plex.token:
        logger.info("Auto-connecting to Plex server...")
        status = plex_client.connect()
        if status.connected:
            logger.info("Connected to '%s'", status.server_name)
        else:
            logger.warning("Auto-connect failed: %s", status.error)

    yield

    logger.info("PosterPilot shutting down...")


def create_app(config: Config | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if config is None:
        config = Config.load()

    app = FastAPI(
        title="PosterPilot",
        description="Automatic Plex poster management",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Store shared state
    plex_client = PlexClient(config)
    app.state.config = config
    app.state.plex_client = plex_client
    app.state.task_manager = TaskManager(plex_client, config)

    # Mount static files
    static_path = get_resource_path("app/static")
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

    # Include routers
    app.include_router(api.router)
    app.include_router(pages.router)

    return app

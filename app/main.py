"""FastAPI application factory for PosterPilot."""

import logging
import logging.handlers
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import Config, get_data_dir, get_resource_path
from app.routes import api
from app.services.ignore_list import IgnoreList
from app.services.plex_client import PlexClient
from app.services.task_manager import TaskManager

# Module-level log file path so the API can read it
LOG_FILE: Path | None = None


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging to stdout and a rotating file."""
    global LOG_FILE
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    log_level = getattr(logging, level.upper(), logging.INFO)

    LOG_FILE = get_data_dir() / "posterpilot.log"

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(log_format))

    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout), file_handler],
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
    app.state.ignore_list = IgnoreList()
    app.state.task_manager = TaskManager(plex_client, config, app.state.ignore_list)

    # Include API router first (takes priority over static/SPA)
    app.include_router(api.router)

    # Mount static files (CSS, JS, images, and built SPA assets)
    static_path = get_resource_path("app/static")
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

    # SPA catch-all: serve the Vue app's index.html for any non-API,
    # non-static route so that Vue Router handles client-side routing.
    spa_index = Path(static_path) / "spa" / "index.html"

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if spa_index.exists():
            return FileResponse(spa_index)
        # Fallback: if SPA not built yet, return a helpful message
        return {"error": "SPA not built. Run 'npm run build' in the frontend/ directory."}

    return app

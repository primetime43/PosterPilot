"""Page routes for server-rendered Jinja2 templates."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import get_resource_path

router = APIRouter()
templates = Jinja2Templates(directory=str(get_resource_path("app/templates")))


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main dashboard page."""
    plex = request.app.state.plex_client
    connected = plex.is_connected()
    server_name = plex.server.friendlyName if connected else None
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "connected": connected,
            "server_name": server_name,
        },
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings/configuration page."""
    config = request.app.state.config
    plex = request.app.state.plex_client
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "config": config,
            "connected": plex.is_connected(),
        },
    )


@router.get("/scan", response_class=HTMLResponse)
async def scan_page(request: Request):
    """Scan results page."""
    plex = request.app.state.plex_client
    task_mgr = request.app.state.task_manager
    latest_job = task_mgr.get_latest_job()
    return templates.TemplateResponse(
        "scan.html",
        {
            "request": request,
            "connected": plex.is_connected(),
            "job": latest_job,
        },
    )


@router.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    """Logs page."""
    return templates.TemplateResponse(
        "logs.html",
        {"request": request, "connected": request.app.state.plex_client.is_connected()},
    )

"""API routes for PosterPilot.

Provides JSON endpoints for frontend HTMX/Alpine interactions:
- Plex connection management
- Library listing
- Scan jobs (start, status, results)
- Apply poster changes
- Configuration
- Export results
"""

import logging
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.models import ItemAction

logger = logging.getLogger("posterpilot.api")
router = APIRouter(prefix="/api")


@router.post("/oauth/start")
async def start_oauth(request: Request):
    """Start Plex OAuth login flow.

    Returns an oauth_url that the frontend should open in a popup
    for the user to sign in at plex.tv.
    """
    plex_client = request.app.state.plex_client
    result = plex_client.start_oauth()
    return result


@router.get("/oauth/check")
async def check_oauth(request: Request):
    """Poll OAuth login status.

    Frontend should call this every ~2 seconds after opening the
    OAuth popup. Returns status: waiting | authenticated | expired | error.
    """
    plex_client = request.app.state.plex_client
    result = plex_client.check_oauth()
    return result


@router.post("/oauth/cancel")
async def cancel_oauth(request: Request):
    """Cancel an in-progress OAuth session."""
    request.app.state.plex_client.cancel_oauth()
    return {"status": "cancelled"}


@router.get("/servers")
async def list_servers(request: Request):
    """List Plex servers on the authenticated account.

    Only available after successful OAuth login.
    """
    plex_client = request.app.state.plex_client
    if not plex_client.account:
        return JSONResponse(
            status_code=400,
            content={"error": "Not authenticated. Complete OAuth login first."},
        )

    try:
        servers = plex_client.get_servers()
        # Deduplicate by machine_id, prefer local non-relay connections
        seen: dict[str, dict] = {}
        for s in servers:
            key = s.machine_id
            entry = {
                "name": s.name,
                "uri": s.uri,
                "local": s.local,
                "relay": s.relay,
                "owned": s.owned,
                "machine_id": s.machine_id,
            }
            if key not in seen:
                seen[key] = entry
            else:
                # Prefer local, non-relay connections for display
                if s.local and not s.relay and not seen[key]["local"]:
                    seen[key] = entry
        return {"servers": list(seen.values())}
    except Exception as e:
        logger.error("Error listing servers: %s", e)
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/connect/server")
async def connect_to_server(request: Request):
    """Connect to a specific Plex server by machine ID (after OAuth)."""
    data = await request.json()
    machine_id = data.get("machine_id", "")

    plex_client = request.app.state.plex_client
    status = plex_client.connect_to_resource(machine_id)

    return {
        "connected": status.connected,
        "server_name": status.server_name,
        "version": status.version,
        "error": status.error,
    }


@router.post("/connect")
async def connect_plex(request: Request):
    """Connect to Plex server with URL + token directly (manual method)."""
    data = await request.json()
    base_url = data.get("base_url", "").strip().rstrip("/")
    token = data.get("token", "").strip()

    plex_client = request.app.state.plex_client
    config = request.app.state.config

    status = plex_client.connect(base_url, token)

    if status.connected:
        config.plex.base_url = base_url
        config.plex.token = token
        config.save()

    return {
        "connected": status.connected,
        "server_name": status.server_name,
        "version": status.version,
        "error": status.error,
    }


@router.post("/disconnect")
async def disconnect_plex(request: Request):
    """Disconnect from Plex server."""
    request.app.state.plex_client.disconnect()
    return {"connected": False}


@router.get("/status")
async def connection_status(request: Request):
    """Get current Plex connection status."""
    plex = request.app.state.plex_client
    if plex.is_connected():
        server = plex.server
        result = {
            "connected": True,
            "server_name": server.friendlyName,
            "version": server.version,
        }
        try:
            result["platform"] = getattr(server, "platform", None)
            result["platform_version"] = getattr(server, "platformVersion", None)
            result["machine_id"] = getattr(server, "machineIdentifier", None)
            result["host"] = getattr(server, "_baseurl", None)
            result["library_count"] = len(server.library.sections())
        except Exception:
            pass
        return result
    return {"connected": False}


@router.get("/libraries")
async def list_libraries(request: Request):
    """List available Plex libraries."""
    plex = request.app.state.plex_client
    if not plex.is_connected():
        return JSONResponse(
            status_code=400, content={"error": "Not connected to Plex"}
        )

    try:
        libraries = plex.get_libraries()
        config = request.app.state.config

        # Apply whitelist/blacklist filtering
        whitelist = config.app.whitelisted_libraries
        blacklist = config.app.blacklisted_libraries

        if whitelist:
            libraries = [l for l in libraries if l.title in whitelist]
        if blacklist:
            libraries = [l for l in libraries if l.title not in blacklist]

        return {
            "libraries": [
                {
                    "key": l.key,
                    "title": l.title,
                    "type": l.type,
                    "item_count": l.item_count,
                }
                for l in libraries
            ]
        }
    except Exception as e:
        logger.error("Error listing libraries: %s", e)
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/scan")
async def start_scan(request: Request):
    """Start a background scan job for a library."""
    data = await request.json()
    library_key = data.get("library_key")
    library_title = data.get("library_title", "Unknown")
    force_refresh = data.get("force_refresh", False)

    plex = request.app.state.plex_client
    if not plex.is_connected():
        return JSONResponse(
            status_code=400, content={"error": "Not connected to Plex"}
        )

    task_mgr = request.app.state.task_manager
    job_id = task_mgr.start_scan(library_key, library_title, force_refresh)

    return {"job_id": job_id, "status": "started"}


@router.get("/scan/{job_id}")
async def get_scan_status(request: Request, job_id: str):
    """Get the status and results of a scan job."""
    task_mgr = request.app.state.task_manager
    job = task_mgr.get_job(job_id)

    if not job:
        return JSONResponse(status_code=404, content={"error": "Job not found"})

    result = {
        "job_id": job.job_id,
        "status": job.status.value,
        "library": job.library_title,
        "total_items": job.total_items,
        "processed_items": job.processed_items,
        "progress_pct": job.progress_pct,
        "changes": job.changes_count,
        "skipped": job.skipped_count,
        "locked": job.locked_count,
        "failed": job.failed_count,
        "error": job.error,
    }

    # Include items if scan is complete
    if job.status.value == "complete":
        result["items"] = [
            {
                "rating_key": i.rating_key,
                "title": i.title,
                "year": i.year,
                "item_type": i.item_type,
                "action": i.action.value,
                "current_poster_url": i.current_poster_url,
                "best_candidate_url": (
                    i.best_candidate.thumb_url if i.best_candidate else None
                ),
                "best_candidate_provider": (
                    i.best_candidate.provider if i.best_candidate else None
                ),
                "best_candidate_score": (
                    i.best_candidate.score if i.best_candidate else None
                ),
                "current_score": (
                    i.current_poster.score if i.current_poster else None
                ),
                "is_locked": i.is_locked,
                "is_uploaded": i.is_uploaded,
                "is_likely_broken": i.is_likely_broken,
                "broken_reason": i.broken_reason,
                "applied": i.applied,
                "error": i.error,
                "num_candidates": len(i.all_candidates),
                "current_provider": (
                    i.current_poster.provider if i.current_poster else None
                ),
                "all_candidates": [
                    {
                        "rating_key": c.rating_key,
                        "thumb_url": c.thumb_url,
                        "provider": c.provider,
                        "selected": c.selected,
                        "score": c.score,
                        "score_breakdown": c.score_breakdown,
                    }
                    for c in i.all_candidates
                ],
            }
            for i in job.items
        ]

    return result


@router.post("/apply/{job_id}")
async def apply_changes(request: Request, job_id: str):
    """Start a background apply job for poster changes."""
    data = await request.json()
    dry_run = data.get("dry_run", True)
    item_keys: Optional[list[str]] = data.get("item_keys")

    task_mgr = request.app.state.task_manager
    apply_id = task_mgr.start_apply(job_id, dry_run=dry_run, item_keys=item_keys)

    if not apply_id:
        return JSONResponse(
            status_code=400,
            content={"error": "No applicable changes found or job not complete"},
        )

    return {"apply_id": apply_id, "status": "started"}


@router.get("/apply/status/{apply_id}")
async def get_apply_status(request: Request, apply_id: str):
    """Poll the status of a background apply job."""
    task_mgr = request.app.state.task_manager
    apply_job = task_mgr.get_apply_job(apply_id)

    if not apply_job:
        return JSONResponse(status_code=404, content={"error": "Apply job not found"})

    return {
        "apply_id": apply_job.apply_id,
        "status": apply_job.status.value,
        "dry_run": apply_job.dry_run,
        "total_items": apply_job.total_items,
        "processed_items": apply_job.processed_items,
        "progress_pct": apply_job.progress_pct,
        "applied_count": apply_job.applied_count,
        "failed_count": apply_job.failed_count,
        "error": apply_job.error,
    }


@router.post("/apply/{job_id}/{item_key}/{candidate_key}")
async def apply_specific_candidate(
    request: Request, job_id: str, item_key: str, candidate_key: str
):
    """Apply a specific poster candidate to a single item."""
    plex = request.app.state.plex_client
    if not plex.is_connected():
        return JSONResponse(
            status_code=400, content={"error": "Not connected to Plex"}
        )

    task_mgr = request.app.state.task_manager
    job = task_mgr.get_job(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"error": "Job not found"})

    # Find the scan item
    scan_item = None
    for i in job.items:
        if i.rating_key == item_key:
            scan_item = i
            break
    if not scan_item:
        return JSONResponse(
            status_code=404, content={"error": "Item not found in scan"}
        )

    # Find the candidate
    candidate = None
    for c in scan_item.all_candidates:
        if c.rating_key == candidate_key:
            candidate = c
            break
    if not candidate:
        return JSONResponse(
            status_code=404, content={"error": "Candidate not found"}
        )

    try:
        item = plex.server.fetchItem(int(item_key))
        posters = plex.get_item_posters(item)

        target_poster = None
        for p in posters:
            if str(getattr(p, "ratingKey", "")) == candidate_key:
                target_poster = p
                break

        if not target_poster:
            return JSONResponse(
                status_code=400,
                content={"error": "Poster no longer available on Plex"},
            )

        success = plex.set_poster(item, target_poster)
        if success:
            scan_item.best_candidate = candidate
            scan_item.applied = True
            scan_item.action = ItemAction.CHANGE
            task_mgr._save_job_cache(job)
            return {"applied": True, "title": scan_item.title}
        else:
            return JSONResponse(
                status_code=500, content={"error": "setPoster call failed"}
            )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/export/{job_id}")
async def export_results(request: Request, job_id: str):
    """Export scan results as JSON."""
    task_mgr = request.app.state.task_manager
    data = task_mgr.export_job(job_id)
    if not data:
        return JSONResponse(status_code=404, content={"error": "Job not found"})
    return data


@router.get("/jobs")
async def list_jobs(request: Request):
    """List all scan jobs."""
    task_mgr = request.app.state.task_manager
    jobs = task_mgr.get_all_jobs()
    return {
        "jobs": [
            {
                "job_id": j.job_id,
                "library": j.library_title,
                "status": j.status.value,
                "progress_pct": j.progress_pct,
                "total_items": j.total_items,
                "changes": j.changes_count,
                "started_at": j.started_at.isoformat() if j.started_at else None,
            }
            for j in jobs
        ]
    }


@router.delete("/jobs/{job_id}")
async def delete_job(request: Request, job_id: str):
    """Delete a scan job and its cache."""
    task_mgr = request.app.state.task_manager
    if task_mgr.delete_job(job_id):
        return {"deleted": True}
    return JSONResponse(
        status_code=400,
        content={"error": "Job not found or still running"},
    )


@router.get("/item/{rating_key}/posters")
async def get_item_posters(request: Request, rating_key: str):
    """Debug endpoint: return raw poster data for a specific item.

    Useful for inspecting what Plex provides for broken poster detection.
    """
    plex = request.app.state.plex_client
    if not plex.is_connected():
        return JSONResponse(status_code=400, content={"error": "Not connected"})

    try:
        item = plex.server.fetchItem(int(rating_key))
        raw_posters = plex.get_item_posters(item)

        item_info = {
            "title": item.title,
            "rating_key": str(item.ratingKey),
            "thumb": getattr(item, "thumb", ""),
            "item_type": item.type,
            "is_locked": plex.is_poster_locked(item),
        }

        selected_poster = None
        posters = []
        for p in raw_posters:
            entry = {
                "ratingKey": getattr(p, "ratingKey", ""),
                "key": getattr(p, "key", ""),
                "thumb": getattr(p, "thumb", ""),
                "provider": getattr(p, "provider", None),
                "selected": getattr(p, "selected", False),
            }
            posters.append(entry)
            if entry["selected"]:
                selected_poster = entry

        summary = {
            "total_posters": len(posters),
            "has_selected": selected_poster is not None,
            "selected_poster": selected_poster,
            "providers": list(set(
                p.get("provider") or "(none)" for p in posters
            )),
        }

        return {"item": item_info, "summary": summary, "posters": posters}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/config")
async def get_config(request: Request):
    """Get current configuration."""
    config = request.app.state.config
    data = config.model_dump()
    return data


@router.post("/config")
async def update_config(request: Request):
    """Update configuration."""
    data = await request.json()
    config = request.app.state.config

    # Update scoring config
    if "scoring" in data:
        for key, val in data["scoring"].items():
            if hasattr(config.scoring, key):
                setattr(config.scoring, key, val)

    # Update app config
    if "app" in data:
        for key, val in data["app"].items():
            if hasattr(config.app, key):
                setattr(config.app, key, val)

    config.save()
    return {"success": True}


@router.get("/logs")
async def get_logs(request: Request, lines: int = 200, level: str = ""):
    """Get recent log lines from the log file.

    Args:
        lines: Number of most recent lines to return (default 200).
        level: Optional filter by log level (e.g. "ERROR", "WARNING").
    """
    from app.main import LOG_FILE

    if not LOG_FILE or not LOG_FILE.exists():
        return {"lines": [], "total": 0}

    try:
        all_lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
        if level:
            level_upper = level.upper()
            all_lines = [l for l in all_lines if f"[{level_upper}]" in l]
        # Return the most recent lines
        recent = all_lines[-lines:]
        return {"lines": recent, "total": len(all_lines)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/logs/clear")
async def clear_logs(request: Request):
    """Clear the log file."""
    from app.main import LOG_FILE

    if LOG_FILE and LOG_FILE.exists():
        LOG_FILE.write_text("", encoding="utf-8")
    return {"cleared": True}


# ── Ignore List ──────────────────────────────────────────


@router.get("/ignore")
async def get_ignore_list(request: Request):
    """Get all ignored items."""
    ignore = request.app.state.ignore_list
    items = ignore.get_all()
    return {
        "count": len(items),
        "items": [
            {"rating_key": k, "title": v.get("title")}
            for k, v in items.items()
        ],
    }


@router.post("/ignore")
async def add_to_ignore_list(request: Request):
    """Add one or more items to the ignore list.

    Body: { "items": [{ "rating_key": "123", "title": "Movie" }, ...] }
    """
    data = await request.json()
    ignore = request.app.state.ignore_list
    items = data.get("items", [])
    if not items:
        return JSONResponse(
            status_code=400, content={"error": "No items provided"}
        )
    count = ignore.add_bulk(items)
    return {"added": count, "total": ignore.count()}


@router.delete("/ignore/{rating_key}")
async def remove_from_ignore_list(request: Request, rating_key: str):
    """Remove an item from the ignore list."""
    ignore = request.app.state.ignore_list
    if ignore.remove(rating_key):
        return {"removed": True, "total": ignore.count()}
    return JSONResponse(
        status_code=404, content={"error": "Item not in ignore list"}
    )


@router.delete("/ignore")
async def clear_ignore_list(request: Request):
    """Clear the entire ignore list."""
    ignore = request.app.state.ignore_list
    ignore.clear()
    return {"cleared": True}

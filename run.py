"""PosterPilot entry point.

Works for local development, PyInstaller EXE, and Docker.
"""

import os
import sys
import webbrowser
import threading

import uvicorn

from app.config import Config


def open_browser(host: str, port: int) -> None:
    """Open the browser after a short delay to let the server start."""
    import time
    time.sleep(1.5)
    url = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}"
    webbrowser.open(url)


def main() -> None:
    config = Config.load()

    host = config.app.host
    port = config.app.port

    # Open browser on Windows EXE or local dev (not Docker)
    in_docker = os.environ.get("POSTERPILOT_DOCKER", "").lower() in ("1", "true")
    if config.app.open_browser and not in_docker:
        threading.Thread(target=open_browser, args=(host, port), daemon=True).start()

    print(f"Starting PosterPilot on http://{host}:{port}")
    print("Press Ctrl+C to stop.\n")

    uvicorn.run(
        "app.main:create_app",
        host=host,
        port=port,
        factory=True,
        log_level=config.app.log_level.lower(),
        reload=not getattr(sys, "frozen", False),  # Auto-reload in dev only
    )


if __name__ == "__main__":
    main()

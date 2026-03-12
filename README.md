# PosterPilot

Automatic poster management for Plex. Scans your libraries, scores available poster options, and applies the best one — so you don't have to manually pick posters one by one.

## Features

- **Automatic poster scoring** — ranks posters by provider, resolution, and aspect ratio
- **Preview before applying** — see current vs. recommended posters side by side
- **Plex OAuth sign-in** — sign in with your Plex account, no need to find your token
- **Batch processing** — scan and update entire libraries at once
- **Dry-run mode** — see what would change before applying anything
- **Live progress** — background scanning and applying with real-time progress bars
- **Configurable** — adjust scoring weights, provider priority, and filtering from the UI
- **Dark theme UI**

## Getting Started

### Run from Source

```bash
git clone https://github.com/primetime43/PosterPilot.git
cd PosterPilot
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
python run.py
```

Opens at **http://127.0.0.1:8888**. On Windows you can also just double-click `start.bat`.

### Docker

```bash
docker compose up -d
```

Access at **http://localhost:8888**. Optionally set `PLEX_URL` and `PLEX_TOKEN` environment variables in `docker-compose.yml`.

### Windows EXE

Run `build.bat` to build a standalone EXE with PyInstaller. The EXE launches the web server and opens your browser.

## How to Use

1. Open PosterPilot in your browser
2. Click **Sign in with Plex** (or use manual token entry)
3. Select your Plex server
4. Pick a library and click **Scan**
5. Review results — current poster vs. recommended, side by side
6. Filter by Changes / Skipped / Locked / etc.
7. Click **Apply All Changes** or select individual items to apply

## Configuration

All settings are configurable from the **Settings** page in the UI. Config is saved to `data/config.toml`.

For Docker, you can also use environment variables:

| Variable | Description | Default |
|---|---|---|
| `PLEX_URL` | Plex server URL | _(empty)_ |
| `PLEX_TOKEN` | Plex token | _(empty)_ |
| `POSTERPILOT_PORT` | Web server port | `8888` |
| `POSTERPILOT_DATA_DIR` | Data directory | `./data` |

## Poster Scoring

Posters are ranked automatically using:

- **Provider priority** — TMDB > TVDB > Gracenote > Local > Upload
- **Aspect ratio** — prefers standard 2:3 poster ratio, penalizes landscape images
- **Resolution** — higher resolution scores better
- **Stability bonus** — slight preference for the current poster to avoid unnecessary changes

A change is only recommended when the best candidate scores meaningfully higher than the current poster. All scoring weights are adjustable in Settings.

## Known Limitations

- Plex has no batch API for posters — each item requires its own API call, so large libraries take time to scan. Scans run in parallel (8 concurrent) to help.
- Poster image dimensions aren't in Plex metadata, so scoring relies primarily on provider and aspect ratio rather than exact resolution.
- Some poster URLs from Plex may be inaccessible (relay/auth issues). These are filtered out automatically.

## Roadmap

- [ ] Smarter image scoring (watermarks, text overlay detection)
- [ ] Scheduled automatic scans
- [ ] TV show season/episode poster support
- [ ] Undo/rollback poster changes
- [ ] TMDB/TVDB direct API integration for more poster sources
- [ ] Docker Hub image publishing

# PosterPilot

Automatic poster management for Plex. Scans your Plex libraries, scores available poster options, and applies the best one — so you don't have to manually pick posters one by one.

## Features

- **Automatic poster scoring** — ranks posters by resolution, aspect ratio, and provider source
- **Preview before applying** — see current vs. recommended posters side by side
- **Batch processing** — scan and update entire libraries at once
- **Dry-run mode** — enabled by default, shows what would change without touching anything
- **Background scanning** — scans run in the background with live progress updates
- **Configurable rules** — adjust scoring weights, minimum resolution, provider priority
- **Library filtering** — whitelist/blacklist specific libraries
- **Export results** — download scan results as JSON
- **Dark theme UI** — clean, modern dashboard interface

## Quick Start

### From Source (Local Development)

```bash
# Clone the repo
git clone <your-repo-url>
cd PosterPilot

# Create a virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Run
python run.py
```

The app opens at **http://127.0.0.1:8888**.

### Docker

```bash
# Build and run
docker compose up -d

# Or with environment variables
PLEX_URL=http://your-plex:32400 PLEX_TOKEN=your-token docker compose up -d
```

Access at **http://localhost:8888**.

### Windows EXE (PyInstaller)

```bash
# Install build dependencies
pip install -r requirements.txt
pip install pyinstaller

# Build
pyinstaller posterpilot.spec --clean

# Run
dist\PosterPilot.exe
```

Or simply run `build.bat`.

The EXE launches the web server and opens your browser automatically.

## Configuration

Configuration is stored in `data/config.toml`. You can also configure everything through the Settings page in the web UI.

Environment variables override config file values:

| Variable | Description | Default |
|---|---|---|
| `PLEX_URL` | Plex server base URL | _(empty)_ |
| `PLEX_TOKEN` | Plex authentication token | _(empty)_ |
| `POSTERPILOT_HOST` | Web server bind host | `0.0.0.0` |
| `POSTERPILOT_PORT` | Web server port | `8888` |
| `POSTERPILOT_DRY_RUN` | Enable dry-run by default | `true` |
| `POSTERPILOT_LOG_LEVEL` | Log level (DEBUG/INFO/WARNING/ERROR) | `INFO` |
| `POSTERPILOT_DATA_DIR` | Data directory for config/logs | `./data` |

## How Poster Scoring Works

Each poster candidate is scored on multiple factors:

### Provider Score (weight: 1.0)
Posters from known metadata agents score higher. Default priority:
1. **TMDB** (5.0) — generally high quality
2. **TVDB** (4.0)
3. **Gracenote** (3.0)
4. **Local** (2.0) — embedded in media file
5. **Upload** (1.0) — user-uploaded

### Resolution Score (weight: 1.0)
| Resolution | Score |
|---|---|
| ≥ 1000×1500 | 5.0 |
| ≥ 600×900 | 4.0 |
| ≥ 400×600 | 3.0 |
| ≥ 200×300 | 2.0 |
| Below | 1.0 |

### Aspect Ratio Score (weight: 1.5)
Standard poster ratio is 2:3 (0.667). Posters closer to this ratio score higher.

### Penalties
- **Landscape images** (wider than tall): -5.0 penalty
- **Below minimum width** (default 300px): -3.0
- **Below minimum height** (default 450px): -3.0

### Currently Selected Bonus
The currently active poster gets a +0.5 bonus to avoid unnecessary changes when scores are close.

### Decision Logic
A poster change is recommended only when the best candidate scores **more than 0.5 points** above the current poster. This prevents churn on marginal differences.

## How It Works with Plex

PosterPilot uses the [python-plexapi](https://github.com/pkkid/python-plexapi) library:

- **`item.posters()`** — retrieves all available poster options for a media item. Each poster has `ratingKey`, `thumb` (URL path), `provider` (source), and `selected` (boolean).
- **`item.setPoster(poster)`** — applies a specific poster to the item.

### Known Plex API Limitations

1. **`posters()` makes an API call per item** — scanning large libraries (1000+ items) takes time. Progress is tracked in the UI.
2. **Image dimensions not in poster metadata** — the API returns poster URLs but not width/height. PosterPilot optionally fetches each poster image to inspect dimensions, which adds network overhead.
3. **Provider field may be None** — for uploaded or some agent-supplied posters, the `provider` attribute can be `None`. These receive a neutral score.
4. **Poster availability varies** — some items may have only 1 poster (the default), leaving no alternatives to choose from.
5. **No built-in poster quality metric** — Plex doesn't score poster quality. All ranking is done by PosterPilot's scoring engine.

## Project Structure

```
PosterPilot/
├── app/
│   ├── main.py              # FastAPI app factory
│   ├── config.py             # Configuration management
│   ├── models.py             # Pydantic/dataclass models
│   ├── services/
│   │   ├── plex_client.py    # Plex server connection layer
│   │   ├── library_scanner.py # Scan orchestration
│   │   ├── poster_extractor.py # Poster candidate extraction
│   │   ├── poster_scorer.py  # Scoring/ranking engine
│   │   ├── poster_applier.py # Apply changes to Plex
│   │   └── task_manager.py   # Background job management
│   ├── routes/
│   │   ├── api.py            # JSON API endpoints
│   │   └── pages.py          # HTML page routes
│   ├── templates/            # Jinja2 templates
│   └── static/               # CSS/JS assets
├── data/
│   └── config.toml           # Configuration file
├── run.py                    # Entry point
├── requirements.txt
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── posterpilot.spec          # PyInstaller build spec
└── build.bat                 # Windows build script
```

## Workflow

1. Open PosterPilot in your browser
2. Enter your Plex server URL and token on the Dashboard
3. Click **Connect**
4. Select a library and click **Scan** (or **Force Rescan**)
5. Wait for the scan to complete — progress shown in real time
6. Go to **Scan Results** to review:
   - Current poster vs. recommended poster (side by side)
   - Score comparison
   - Action: Change / Skip / No Alternatives / Failed / Locked
7. Click **Dry Run All** to see what would change
8. Click **Apply All Changes** to apply, or select specific items
9. Export results as JSON if needed

## Roadmap

- [ ] Smarter image scoring (detect watermarks, text overlay, color quality)
- [ ] ML-based poster quality assessment (behind a feature flag)
- [ ] Source/provider prioritization UI per library
- [ ] Scheduled automatic scans (cron-like)
- [ ] Web UI authentication (basic auth or token)
- [ ] Poster lock awareness improvements
- [ ] TV show season/episode poster support
- [ ] Docker Hub image publishing
- [ ] Auto-updater for Windows EXE builds
- [ ] Undo/rollback last poster change
- [ ] Poster comparison history
- [ ] TMDB/TVDB direct API integration for additional poster sources
- [ ] Webhook notifications on scan completion

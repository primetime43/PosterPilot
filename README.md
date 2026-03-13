# PosterPilot

Automatic poster management for Plex. Scans your libraries, scores available poster options, and applies the best one — so you don't have to manually pick posters one by one.

## Why PosterPilot?

I just wanted to fix broken and ugly posters across my Plex libraries without clicking through every single item. Most Plex metadata managers are way overcomplicated for this — they try to do everything, rely on local file scanning and matching, and most don't even set posters directly in Plex. PosterPilot does one thing well: it connects straight to your Plex server through the API, finds items with better poster options available, and lets you apply them. No external databases, no file matching, no YAML configs. Just sign in, scan, review, and apply.

## Features

- **Automatic poster scoring** — ranks posters by provider, resolution, and aspect ratio
- **Preview before applying** — see current vs. recommended posters side by side
- **Plex OAuth sign-in** — sign in with your Plex account, no need to find your token
- **Batch processing** — scan and update entire libraries at once
- **Parallel scanning & applying** — 8 concurrent workers for scanning, 4 for applying
- **Dry-run mode** — see what would change before applying anything
- **Live progress** — background scanning and applying with real-time progress bars
- **Diff-based rescanning** — skip unchanged items when re-scanning a library
- **Thumbnail caching** — optional local cache for poster thumbnails to reduce Plex API load
- **Ignore list** — permanently skip specific items from future scans
- **Configurable** — adjust scoring weights, provider priority, library filters, and more from the UI
- **Encrypted secrets** — Plex tokens and server URLs are stored encrypted on disk, never in plaintext
- **Dark & light themes**

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

Available on [Docker Hub](https://hub.docker.com/r/primetime43/posterpilot).

```yaml
services:
  posterpilot:
    image: primetime43/posterpilot:latest
    container_name: posterpilot
    ports:
      - "8888:8888"
    volumes:
      - ./data:/app/data
    environment:
      - PLEX_URL=          # optional
      - PLEX_TOKEN=        # optional
    restart: unless-stopped
```

Or build locally:

```bash
docker compose up -d
```

Access at **http://localhost:8888**.

### Windows EXE

Download the latest `PosterPilot-x.x.x.exe` from [Releases](https://github.com/primetime43/PosterPilot/releases). The EXE launches the web server and opens your browser automatically.

To build yourself, run `build.bat` or `pyinstaller posterpilot.spec`.

## How to Use

1. Open PosterPilot in your browser
2. Click **Sign in with Plex** (or use manual token entry)
3. Select your Plex server
4. Pick a library and click **Scan**
5. Review results — current poster vs. recommended, side by side
6. Filter by Changes / Skipped / Locked / etc.
7. Click **Apply All Changes** or select individual items to apply

## Configuration

All settings are configurable from the **Settings** page in the UI, organized into tabs:

| Tab | What it controls |
|---|---|
| **Connection** | Plex server URL, token, timeout |
| **General** | Host, port, log level, dry run, skip locked, scan retention |
| **Scoring** | Weights, provider priority, aspect ratio, landscape penalty |
| **Libraries** | Whitelist and blacklist library filters |
| **Cache** | Thumbnail caching toggle and expiry |
| **Ignore List** | Items to permanently skip during scans |

Non-sensitive settings are saved to `data/config.toml`. Sensitive data (Plex token, server URL) is encrypted using Fernet (AES-128-CBC + HMAC-SHA256) and stored in `data/config.enc`. The encryption key is derived from your machine's identity — no key files to manage.

### Environment Variables

For Docker deployments, you can override settings with environment variables:

| Variable | Description | Default |
|---|---|---|
| `PLEX_URL` | Plex server URL | _(empty)_ |
| `PLEX_TOKEN` | Plex token | _(empty)_ |
| `PLEX_TIMEOUT` | API timeout in seconds | `30` |
| `POSTERPILOT_HOST` | Bind address | `0.0.0.0` |
| `POSTERPILOT_PORT` | Web server port | `8888` |
| `POSTERPILOT_DRY_RUN` | Dry run mode | `true` |
| `POSTERPILOT_LOG_LEVEL` | Log level | `INFO` |
| `POSTERPILOT_DATA_DIR` | Data directory path | `./data` |

## Poster Scoring

Posters are ranked automatically using:

- **Provider priority** — TMDB > TVDB > Gracenote > Local > Upload (configurable)
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

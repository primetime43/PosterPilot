"""Configuration management for PosterPilot.

Supports loading from TOML config file and environment variables.
Environment variables override config file values.

Sensitive values (Plex token) are stored in an encrypted file
(data/config.enc) using machine-derived Fernet encryption.
Non-sensitive settings remain in plain TOML (data/config.toml).
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


def get_base_dir() -> Path:
    """Get the base directory, handling PyInstaller frozen mode."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def get_data_dir() -> Path:
    """Get the data directory for config, logs, and runtime data."""
    env_data = os.environ.get("POSTERPILOT_DATA_DIR")
    if env_data:
        p = Path(env_data)
    else:
        p = get_base_dir() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_resource_path(relative_path: str) -> Path:
    """Get path to a resource, works for dev and PyInstaller."""
    if getattr(sys, "frozen", False):
        # PyInstaller extracts to _MEIPASS
        base = Path(getattr(sys, "_MEIPASS", get_base_dir()))
    else:
        base = Path(__file__).resolve().parent.parent
    return base / relative_path


class PlexConfig(BaseModel):
    base_url: str = ""
    token: str = ""
    timeout: int = 30


class ScoringConfig(BaseModel):
    min_width: int = 300
    min_height: int = 450
    preferred_aspect_ratio: float = Field(default=0.6667, description="2:3 ratio")
    aspect_ratio_tolerance: float = 0.15
    prefer_provider_posters: bool = True
    provider_priority: list[str] = Field(
        default_factory=lambda: ["tmdb", "tvdb", "gracenote", "local", "upload"]
    )
    resolution_weight: float = 1.0
    aspect_ratio_weight: float = 1.5
    provider_weight: float = 1.0
    penalize_landscape: bool = True
    landscape_penalty: float = -5.0


class AppConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8888
    dry_run: bool = True
    skip_locked: bool = True
    force_replace: bool = False
    log_auto_refresh: bool = False
    log_level: str = "INFO"
    open_browser: bool = True
    whitelisted_libraries: list[str] = Field(default_factory=list)
    blacklisted_libraries: list[str] = Field(default_factory=list)


class Config(BaseModel):
    plex: PlexConfig = Field(default_factory=PlexConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    app: AppConfig = Field(default_factory=AppConfig)

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "Config":
        """Load config from TOML file + encrypted store, then overlay env vars."""
        data: dict = {}
        if config_path is None:
            config_path = get_data_dir() / "config.toml"

        # Load non-sensitive settings from TOML
        if config_path.exists():
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib  # type: ignore[no-redef]
            with open(config_path, "rb") as f:
                data = tomllib.load(f)

        config = cls.model_validate(data)

        # Load sensitive values from encrypted store
        from app.services.config_store import load as load_secrets

        secrets = load_secrets()
        if secrets.get("plex_token"):
            config.plex.token = secrets["plex_token"]
        if secrets.get("plex_base_url"):
            config.plex.base_url = secrets["plex_base_url"]

        # Environment variable overrides (highest priority)
        env_map = {
            "PLEX_URL": ("plex", "base_url"),
            "PLEX_TOKEN": ("plex", "token"),
            "PLEX_TIMEOUT": ("plex", "timeout"),
            "POSTERPILOT_HOST": ("app", "host"),
            "POSTERPILOT_PORT": ("app", "port"),
            "POSTERPILOT_DRY_RUN": ("app", "dry_run"),
            "POSTERPILOT_LOG_LEVEL": ("app", "log_level"),
            "POSTERPILOT_OPEN_BROWSER": ("app", "open_browser"),
        }
        for env_key, (section, field) in env_map.items():
            val = os.environ.get(env_key)
            if val is not None:
                sub = getattr(config, section)
                field_info = sub.model_fields[field]
                if field_info.annotation in (int,):
                    val = int(val)
                elif field_info.annotation in (float,):
                    val = float(val)
                elif field_info.annotation in (bool,):
                    val = val.lower() in ("1", "true", "yes")
                setattr(sub, field, val)

        return config

    def save(self, config_path: Optional[Path] = None) -> None:
        """Save config: sensitive values to encrypted store, rest to TOML."""
        if config_path is None:
            config_path = get_data_dir() / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Save sensitive values to encrypted store
        from app.services.config_store import save as save_secrets, load as load_secrets

        secrets = load_secrets()
        secrets["plex_token"] = self.plex.token
        secrets["plex_base_url"] = self.plex.base_url
        save_secrets(secrets)

        # Save non-sensitive settings to TOML (exclude secrets)
        data = self.model_dump()
        # Remove sensitive fields from TOML output
        data["plex"].pop("token", None)
        data["plex"].pop("base_url", None)

        lines: list[str] = []
        for section, values in data.items():
            lines.append(f"[{section}]")
            for key, val in values.items():
                if isinstance(val, str):
                    lines.append(f'{key} = "{val}"')
                elif isinstance(val, bool):
                    lines.append(f"{key} = {'true' if val else 'false'}")
                elif isinstance(val, list):
                    lines.append(f"{key} = {json.dumps(val)}")
                else:
                    lines.append(f"{key} = {val}")
            lines.append("")

        config_path.write_text("\n".join(lines), encoding="utf-8")

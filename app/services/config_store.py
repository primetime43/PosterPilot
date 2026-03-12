"""Encrypted configuration store for sensitive data.

Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256) from the
`cryptography` package. The encryption key is derived from machine-specific
identifiers (hostname + MAC address) so no key file needs to be stored on disk.

The encrypted config is stored as `data/config.enc`. Non-sensitive settings
remain in the plain TOML file — only secrets (Plex token, etc.) go here.

If the machine changes (different hostname or MAC), decryption will fail
gracefully and the user simply re-authenticates.
"""

import hashlib
import json
import base64
import logging
import platform
import uuid
from pathlib import Path
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_data_dir

logger = logging.getLogger("posterpilot.config_store")


def _get_machine_key() -> bytes:
    """Derive a Fernet key from machine-specific identifiers.

    Combines the OS hostname and MAC address into a deterministic seed,
    hashes it with SHA-256, and base64url-encodes the first 32 bytes
    to produce a valid Fernet key.

    The key only exists in memory — it is never written to disk.
    """
    node = platform.node()
    mac = uuid.getnode()
    seed = f"posterpilot-{node}-{mac}"
    digest = hashlib.sha256(seed.encode()).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_get_machine_key())
_enc_path: Optional[Path] = None


def _get_enc_path() -> Path:
    global _enc_path
    if _enc_path is None:
        _enc_path = get_data_dir() / "config.enc"
    return _enc_path


def load() -> dict:
    """Load and decrypt the entire config dict from disk.

    Returns an empty dict on any failure (file missing, decryption
    error after hardware change, corrupt data, etc.).
    """
    path = _get_enc_path()
    if not path.exists():
        return {}

    try:
        encrypted = path.read_bytes()
        plaintext = _fernet.decrypt(encrypted)
        return json.loads(plaintext)
    except (InvalidToken, json.JSONDecodeError, OSError) as e:
        logger.warning("Could not decrypt config.enc (expected on new machine): %s", e)
        return {}


def save(data: dict) -> None:
    """Encrypt and save the entire config dict to disk."""
    path = _get_enc_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    plaintext = json.dumps(data).encode()
    encrypted = _fernet.encrypt(plaintext)
    path.write_bytes(encrypted)


def get(key: str, default: Any = None) -> Any:
    """Get a single value from the encrypted config."""
    return load().get(key, default)


def put(key: str, value: Any) -> None:
    """Set a single value in the encrypted config."""
    data = load()
    data[key] = value
    save(data)


def remove(key: str) -> None:
    """Remove a key from the encrypted config."""
    data = load()
    if key in data:
        del data[key]
        save(data)

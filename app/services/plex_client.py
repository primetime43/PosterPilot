"""Plex server connection and client service.

Encapsulates all python-plexapi interactions behind a service layer
so Plex-specific behavior can be changed or mocked independently.

Supports two authentication methods:
1. Direct token - user provides Plex URL + token manually
2. Plex OAuth - user signs in via plex.tv, then picks a server
"""

import logging
import threading
from dataclasses import dataclass, field
from typing import Optional

from plexapi.exceptions import BadRequest, NotFound, Unauthorized
from plexapi.myplex import MyPlexAccount, MyPlexPinLogin
from plexapi.server import PlexServer

from app.config import Config
from app.models import LibraryInfo, PlexConnectionStatus

logger = logging.getLogger("posterpilot.plex_client")

# Client identifier for Plex OAuth - identifies PosterPilot as an app
PLEX_CLIENT_ID = "posterpilot-app"


@dataclass
class OAuthSession:
    """Tracks an in-progress Plex OAuth login."""

    pin_login: MyPlexPinLogin
    oauth_url: str
    token: Optional[str] = None
    finished: bool = False
    error: Optional[str] = None


@dataclass
class PlexServerInfo:
    """A Plex server available on the user's account."""

    name: str
    uri: str
    local: bool
    relay: bool
    owned: bool
    machine_id: str


class PlexClient:
    """Service layer for Plex server interactions."""

    def __init__(self, config: Config):
        self._config = config
        self._server: Optional[PlexServer] = None
        self._account: Optional[MyPlexAccount] = None
        self._oauth_session: Optional[OAuthSession] = None

    @property
    def server(self) -> Optional[PlexServer]:
        return self._server

    @property
    def account(self) -> Optional[MyPlexAccount]:
        return self._account

    # ── OAuth Flow ──────────────────────────────────────────────

    def start_oauth(self) -> dict:
        """Start a Plex OAuth login flow.

        Creates a PIN login session and returns the OAuth URL that
        the user should open in their browser to sign in at plex.tv.

        Returns:
            Dict with 'oauth_url' for the frontend to open.
        """
        try:
            pin_login = MyPlexPinLogin(oauth=True)
            pin_login.run(timeout=300)  # 5 minute timeout

            oauth_url = pin_login.oauthUrl()
            self._oauth_session = OAuthSession(
                pin_login=pin_login,
                oauth_url=oauth_url,
            )

            logger.info("OAuth session started, waiting for user login")
            return {"oauth_url": oauth_url, "status": "waiting"}

        except Exception as e:
            logger.error("Failed to start OAuth: %s", e)
            return {"error": str(e), "status": "error"}

    def check_oauth(self) -> dict:
        """Check if the OAuth login has completed.

        Polls the PIN login session to see if the user has
        signed in at plex.tv.

        Returns:
            Dict with status: 'waiting', 'authenticated', 'expired', or 'error'.
        """
        if not self._oauth_session:
            return {"status": "error", "error": "No OAuth session active"}

        session = self._oauth_session
        pin = session.pin_login

        try:
            if pin.token:
                # User completed login
                session.token = pin.token
                session.finished = True
                self._account = MyPlexAccount(token=pin.token)
                logger.info(
                    "OAuth login successful for user '%s'",
                    self._account.username,
                )

                # Save token to config
                self._config.plex.token = pin.token
                self._config.save()

                return {
                    "status": "authenticated",
                    "username": self._account.username,
                    "email": self._account.email,
                }

            if pin.expired:
                session.finished = True
                session.error = "Login expired"
                self._oauth_session = None
                return {"status": "expired", "error": "OAuth login expired. Try again."}

            # Still waiting for user to complete login
            pin.checkLogin()

            # Check again after checkLogin
            if pin.token:
                session.token = pin.token
                session.finished = True
                self._account = MyPlexAccount(token=pin.token)
                self._config.plex.token = pin.token
                self._config.save()
                logger.info(
                    "OAuth login successful for user '%s'",
                    self._account.username,
                )
                return {
                    "status": "authenticated",
                    "username": self._account.username,
                    "email": self._account.email,
                }

            return {"status": "waiting"}

        except Exception as e:
            logger.error("OAuth check failed: %s", e)
            self._oauth_session = None
            return {"status": "error", "error": str(e)}

    def cancel_oauth(self) -> None:
        """Cancel an in-progress OAuth session."""
        self._oauth_session = None
        logger.info("OAuth session cancelled")

    def get_servers(self) -> list[PlexServerInfo]:
        """List Plex servers available on the authenticated account.

        Requires a successful OAuth login (self._account must be set).
        """
        if not self._account:
            raise RuntimeError("Not authenticated. Complete OAuth login first.")

        servers = []
        for resource in self._account.resources():
            if "server" not in resource.provides:
                continue
            for conn in resource.connections:
                servers.append(
                    PlexServerInfo(
                        name=resource.name,
                        uri=conn.uri,
                        local=conn.local,
                        relay=conn.relay,
                        owned=resource.owned,
                        machine_id=resource.clientIdentifier,
                    )
                )
        logger.info("Found %d server connections on account", len(servers))
        return servers

    def connect_to_resource(self, machine_id: str) -> PlexConnectionStatus:
        """Connect to a specific server from the user's account by machine ID.

        Tries the account's resource connection (handles secure relay too).
        """
        if not self._account:
            return PlexConnectionStatus(
                connected=False, error="Not authenticated. Complete OAuth login first."
            )

        try:
            resource = None
            for r in self._account.resources():
                if r.clientIdentifier == machine_id and "server" in r.provides:
                    resource = r
                    break

            if not resource:
                return PlexConnectionStatus(
                    connected=False, error=f"Server '{machine_id}' not found on account."
                )

            # resource.connect() tries all connections and picks the best one
            self._server = resource.connect()
            self._config.plex.base_url = self._server._baseurl
            self._config.save()

            status = PlexConnectionStatus(
                connected=True,
                server_name=self._server.friendlyName,
                version=self._server.version,
            )
            logger.info(
                "Connected to Plex server '%s' (v%s) via OAuth",
                status.server_name,
                status.version,
            )
            return status

        except Exception as e:
            logger.error("Failed to connect to server: %s", e)
            return PlexConnectionStatus(connected=False, error=f"Connection failed: {e}")

    # ── Direct Token Connection ─────────────────────────────────

    def connect(
        self, base_url: Optional[str] = None, token: Optional[str] = None
    ) -> PlexConnectionStatus:
        """Connect to Plex server with URL + token directly."""
        url = base_url or self._config.plex.base_url
        tok = token or self._config.plex.token
        timeout = self._config.plex.timeout

        if not url or not tok:
            return PlexConnectionStatus(
                connected=False, error="Plex URL and token are required."
            )

        try:
            self._server = PlexServer(url, tok, timeout=timeout)
            status = PlexConnectionStatus(
                connected=True,
                server_name=self._server.friendlyName,
                version=self._server.version,
            )
            logger.info(
                "Connected to Plex server '%s' (v%s)",
                status.server_name,
                status.version,
            )
            return status
        except Unauthorized:
            logger.error("Plex authentication failed - invalid token")
            return PlexConnectionStatus(
                connected=False, error="Authentication failed. Check your Plex token."
            )
        except Exception as e:
            logger.error("Failed to connect to Plex: %s", e)
            return PlexConnectionStatus(
                connected=False, error=f"Connection failed: {e}"
            )

    def disconnect(self) -> None:
        self._server = None
        self._account = None
        self._oauth_session = None
        logger.info("Disconnected from Plex server")

    def is_connected(self) -> bool:
        return self._server is not None

    def get_libraries(self) -> list[LibraryInfo]:
        """Get all Plex libraries (movie and show types)."""
        if not self._server:
            raise RuntimeError("Not connected to Plex server")

        libraries = []
        for section in self._server.library.sections():
            # Only include libraries that can have posters
            if section.type in ("movie", "show"):
                try:
                    count = section.totalSize
                except Exception:
                    count = 0
                libraries.append(
                    LibraryInfo(
                        key=section.key,
                        title=section.title,
                        type=section.type,
                        item_count=count,
                    )
                )
        logger.info("Found %d poster-capable libraries", len(libraries))
        return libraries

    def get_library_section(self, key: str):
        """Get a library section by key."""
        if not self._server:
            raise RuntimeError("Not connected to Plex server")
        return self._server.library.sectionByID(int(key))

    def get_library_items(self, key: str):
        """Get all items in a library section."""
        section = self.get_library_section(key)
        return section.all()

    def get_item_posters(self, item) -> list:
        """Get available posters for a media item.

        Uses python-plexapi's posters() method from PosterMixin.
        Returns a list of Poster objects with attributes:
            - ratingKey: unique identifier
            - thumb: URL to the poster image
            - provider: source of the poster (e.g. 'tmdb', 'tvdb', 'local', etc.)
            - selected: whether this poster is currently active

        Note: posters() makes an API call to Plex for each item, so this
        can be slow when scanning large libraries.
        """
        try:
            return item.posters()
        except (BadRequest, NotFound) as e:
            logger.warning("Could not get posters for '%s': %s", item.title, e)
            return []
        except Exception as e:
            logger.error(
                "Unexpected error getting posters for '%s': %s", item.title, e
            )
            return []

    def set_poster(self, item, poster) -> bool:
        """Apply a poster to a media item.

        Uses python-plexapi's setPoster() method.
        Returns True if successful.
        """
        try:
            item.setPoster(poster)
            logger.info("Set poster for '%s' (provider: %s)", item.title, poster.provider)
            return True
        except Exception as e:
            logger.error("Failed to set poster for '%s': %s", item.title, e)
            return False

    def get_poster_thumb_url(self, poster) -> str:
        """Get a usable thumbnail URL for a poster.

        Constructs a full URL using the Plex server base.
        """
        if not self._server:
            return ""
        thumb = getattr(poster, "thumb", None) or getattr(poster, "key", "")
        if thumb and not thumb.startswith("http"):
            return f"{self._server._baseurl}{thumb}?X-Plex-Token={self._server._token}"
        return thumb or ""

    def get_item_thumb_url(self, item) -> str:
        """Get the current poster thumbnail URL for a media item."""
        if not self._server:
            return ""
        thumb = getattr(item, "thumb", "")
        if thumb and not thumb.startswith("http"):
            return f"{self._server._baseurl}{thumb}?X-Plex-Token={self._server._token}"
        return thumb or ""

    def is_poster_locked(self, item) -> bool:
        """Check if the poster field is locked on this item.

        Locked fields prevent automatic metadata updates.
        """
        try:
            for f in item.fields:
                if f.name == "thumb" and f.locked:
                    return True
        except Exception:
            pass
        return False

"""
AAP Authentication Client.

Supports:
- OAuth2 token (preferred)
- Username/password Basic Auth with token exchange
- Token refresh and caching
"""

import logging

import httpx

logger = logging.getLogger(__name__)

AAP_TOKEN_URL = "/api/v2/tokens/"
AAP_ME_URL = "/api/v2/me/"


class AAPAuthClient:
    """Handles authentication against AAP Controller."""

    def __init__(
        self,
        controller_url: str,
        username: str | None = None,
        password: str | None = None,
        oauth_token: str | None = None,
        verify_ssl: bool = True,
    ):
        self.controller_url = controller_url.rstrip("/")
        self.username = username
        self.password = password
        self._oauth_token = oauth_token
        self.verify_ssl = verify_ssl
        self._current_user: dict | None = None

    async def get_auth_headers(self) -> dict[str, str]:
        """Return Authorization headers for API requests."""
        token = await self._resolve_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _resolve_token(self) -> str:
        """Get a valid OAuth token, creating one from credentials if needed."""
        if self._oauth_token:
            return self._oauth_token

        if self.username and self.password:
            logger.info("Obtaining OAuth token via username/password for user: %s", self.username)
            async with httpx.AsyncClient(
                base_url=self.controller_url,
                verify=self.verify_ssl,
                timeout=30.0,
            ) as client:
                response = await client.post(
                    AAP_TOKEN_URL,
                    json={"description": "aap-mcp-server token", "application": None, "scope": "write"},
                    auth=(self.username, self.password),
                )
                response.raise_for_status()
                self._oauth_token = response.json()["token"]
                logger.info("OAuth token obtained successfully.")
                return self._oauth_token

        raise AuthenticationError(
            "No authentication credentials provided. " "Set AAP_OAUTH_TOKEN or both AAP_USERNAME and AAP_PASSWORD."
        )

    async def get_current_user(self, http_client: httpx.AsyncClient) -> dict:
        """Return the current authenticated user's details."""
        if self._current_user is None:
            response = await http_client.get(AAP_ME_URL)
            response.raise_for_status()
            data = response.json()
            self._current_user = data.get("results", [data])[0]
        return self._current_user

    async def is_superuser(self, http_client: httpx.AsyncClient) -> bool:
        """Return True if authenticated user is a superuser."""
        user = await self.get_current_user(http_client)
        return user.get("is_superuser", False)


class AuthenticationError(Exception):
    """Raised when AAP authentication fails."""

    pass

"""A thin, well-behaved client for the Newo.ai Customer API.

The client handles the two-step auth flow documented at
https://docs.newo.ai/reference/obtaintokenbyapikey :

1. Exchange the API key (``x-api-key`` header) for a short-lived JWT
   access token plus a refresh token.
2. Send the access token as ``Authorization: Bearer <token>`` on every
   subsequent call, transparently refreshing it when it nears expiry.

Only the endpoints needed for a typical integration are wrapped; the
generic :meth:`NewoClient.request` method covers everything else.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import requests

from .config import NewoConfig

# Renew the access token this many seconds before it actually expires so a
# long-running call never fails mid-flight. Tokens live 900s (15 min).
_TOKEN_REFRESH_MARGIN = 60


class NewoAPIError(RuntimeError):
    """Raised when the Newo API returns a non-2xx response."""

    def __init__(self, status: int, payload: Any):
        self.status = status
        self.payload = payload
        reason = ""
        if isinstance(payload, dict):
            reason = payload.get("reason") or payload.get("type") or ""
        super().__init__(f"Newo API error {status}: {reason or payload}")


class NewoClient:
    """Authenticated session against the Newo Customer API.

    Example::

        from newo import NewoClient
        client = NewoClient.from_env()
        client.connect()                 # obtains a token, verifies access
        actor = client.get_or_create_user_actor(
            name="Alice", external_id="crm-42",
            integration_idn="webchat", connector_idn="my_webchat",
        )
        client.send_message(actor["id"], "Hello from the API!")
    """

    def __init__(self, config: NewoConfig):
        self.config = config
        self._session = requests.Session()
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._expires_at: float = 0.0

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    @classmethod
    def from_env(cls, dotenv_path: str = ".env") -> "NewoClient":
        """Create a client from environment variables / ``.env``."""
        return cls(NewoConfig.from_env(dotenv_path))

    # ------------------------------------------------------------------ #
    # Authentication
    # ------------------------------------------------------------------ #
    def obtain_token(self) -> Dict[str, Any]:
        """Exchange the API key for an access + refresh token pair."""
        url = f"{self.config.base_url}/api/v1/auth/api-key/token"
        resp = self._session.post(
            url,
            headers={"x-api-key": self.config.api_key},
            timeout=self.config.timeout,
        )
        data = self._parse(resp)
        self._store_tokens(data)
        return data

    def refresh(self) -> Dict[str, Any]:
        """Renew the access token using the stored refresh token."""
        if not self._refresh_token:
            return self.obtain_token()
        url = f"{self.config.base_url}/api/v1/auth/refresh-token"
        resp = self._session.post(
            url,
            json={"refresh_token": self._refresh_token},
            timeout=self.config.timeout,
        )
        if resp.status_code >= 400:
            # Refresh token expired/revoked — fall back to a fresh login.
            return self.obtain_token()
        data = self._parse(resp)
        self._store_tokens(data)
        return data

    def _store_tokens(self, data: Dict[str, Any]) -> None:
        self._access_token = data.get("access_token")
        # Only overwrite the refresh token if the response supplied a new one.
        self._refresh_token = data.get("refresh_token", self._refresh_token)
        expires_in = float(data.get("expires_in", 900))
        self._expires_at = time.time() + expires_in

    def _valid_token(self) -> str:
        """Return a live access token, obtaining/refreshing as needed."""
        if not self._access_token:
            self.obtain_token()
        elif time.time() >= self._expires_at - _TOKEN_REFRESH_MARGIN:
            self.refresh()
        assert self._access_token is not None
        return self._access_token

    def connect(self) -> Dict[str, Any]:
        """Verify connectivity by obtaining a token.

        Returns a small dict describing the authenticated context (the
        ``customer_id`` decoded from the JWT and token expiry). Raises
        :class:`NewoAPIError` if the API key is rejected.
        """
        self.obtain_token()
        claims = _decode_jwt_claims(self._access_token or "")
        return {
            "connected": True,
            "base_url": self.config.base_url,
            "customer_id": claims.get("customer_id"),
            "source": claims.get("source"),
            "expires_in": int(max(0, self._expires_at - time.time())),
        }

    # ------------------------------------------------------------------ #
    # Generic request helper
    # ------------------------------------------------------------------ #
    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Any] = None,
    ) -> Any:
        """Make an authenticated request against ``path`` (e.g. ``/api/v1/...``)."""
        url = f"{self.config.base_url}{path}"
        headers = {"Authorization": f"Bearer {self._valid_token()}"}
        resp = self._session.request(
            method.upper(),
            url,
            headers=headers,
            params=params,
            json=json,
            timeout=self.config.timeout,
        )
        return self._parse(resp)

    # ------------------------------------------------------------------ #
    # Actors
    # ------------------------------------------------------------------ #
    def get_or_create_user_actor(
        self,
        *,
        name: str,
        external_id: str,
        integration_idn: str,
        connector_idn: str,
        time_zone_identifier: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get or create the user actor you send/receive messages as."""
        body: Dict[str, Any] = {
            "name": name,
            "external_id": external_id,
            "integration_idn": integration_idn,
            "connector_idn": connector_idn,
        }
        if time_zone_identifier:
            body["time_zone_identifier"] = time_zone_identifier
        return self.request("POST", "/api/v1/actors/user/get-or-create", json=body)

    def list_agent_actors(
        self, *, integration_idn: str, connector_idn: str
    ) -> List[Dict[str, Any]]:
        """List the agent actors reachable via a given integration/connector."""
        return self.request(
            "GET",
            "/api/v1/actors/agent",
            params={
                "integration_idn": integration_idn,
                "connector_idn": connector_idn,
            },
        )

    # ------------------------------------------------------------------ #
    # Messaging
    # ------------------------------------------------------------------ #
    def send_message(
        self,
        user_actor_id: str,
        text: str,
        *,
        external_event_id: Optional[str] = None,
        arguments: Optional[List[Dict[str, str]]] = None,
        uninterruptible: bool = False,
    ) -> Any:
        """Send a message as ``user_actor_id`` (asynchronous — returns on accept)."""
        body: Dict[str, Any] = {"text": text, "uninterruptible": uninterruptible}
        if external_event_id:
            body["external_event_id"] = external_event_id
        if arguments:
            body["arguments"] = arguments
        return self.request(
            "POST", f"/api/v1/chat/user/{user_actor_id}", json=body
        )

    def receive_messages(
        self, user_actor_id: str, *, is_streaming: bool = False
    ) -> Any:
        """Poll for new agent messages since the last call for this actor."""
        return self.request(
            "GET",
            f"/api/v1/chat/user/{user_actor_id}",
            params={"is_streaming": str(is_streaming).lower()},
        )

    def get_chat_history(
        self, user_actor_id: str, *, page: int = 1, per_page: int = 50
    ) -> Any:
        """Return paginated conversation history for a user actor."""
        return self.request(
            "GET",
            f"/api/v1/chat/user/{user_actor_id}/history",
            params={"page": page, "per_page": per_page},
        )

    # ------------------------------------------------------------------ #
    # Project resources (read-only inventory)
    # ------------------------------------------------------------------ #
    def list_webhooks(self) -> List[Dict[str, Any]]:
        """List outgoing webhooks configured in the project."""
        return self.request("GET", "/api/v1/webhooks")

    def list_incoming_webhooks(self) -> List[Dict[str, Any]]:
        """List incoming webhooks (external triggers) configured in the project."""
        return self.request("GET", "/api/v1/webhooks/incoming")

    def list_integrations(self) -> List[Dict[str, Any]]:
        """List integrations available in the account."""
        return self.request("GET", "/api/v1/integrations")

    # ------------------------------------------------------------------ #
    # Triggering an outbound task (e.g. ClickCredit outbound call)
    # ------------------------------------------------------------------ #
    def trigger_incoming_webhook(
        self, webhook: str, payload: Dict[str, Any]
    ) -> Any:
        """Fire an incoming webhook to trigger an agent event.

        ``webhook`` is either a full ``https://hooks.newo.ai/<id>`` URL or just
        the ``webhook_path_id``. Incoming webhooks are **not** part of the
        authenticated Customer API — they are public trigger endpoints, so this
        posts the payload directly (no bearer token).

        For ClickCredit this is how an automated outbound call is queued: post
        the caller's data (phone + the fields from the brief) to the
        ``outbound_call_webhook``. Callers should confirm the exact payload
        schema with their Newo Builder flow before firing real calls.
        """
        if webhook.startswith("http"):
            url = webhook
        else:
            url = f"https://hooks.newo.ai/{webhook}"
        resp = self._session.post(url, json=payload, timeout=self.config.timeout)
        return self._parse(resp)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _parse(self, resp: requests.Response) -> Any:
        if resp.status_code >= 400:
            try:
                payload: Any = resp.json()
            except ValueError:
                payload = resp.text
            raise NewoAPIError(resp.status_code, payload)
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text


def _decode_jwt_claims(token: str) -> Dict[str, Any]:
    """Decode a JWT payload without verifying the signature (read-only use)."""
    import base64
    import json

    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, json.JSONDecodeError):
        return {}

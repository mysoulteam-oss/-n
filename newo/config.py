"""Configuration for the Newo client.

Reads settings from environment variables (optionally from a local ``.env``
file if one is present). Nothing here is hard-coded — the API key must be
supplied by the environment, never committed to the repository.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Default public API host for the Newo Customer API.
DEFAULT_BASE_URL = "https://app.newo.ai"


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (no third-party dependency).

    Lines of the form ``KEY=value`` are loaded into ``os.environ`` unless the
    key is already set. Blank lines and ``#`` comments are ignored.
    """
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


@dataclass
class NewoConfig:
    """Resolved connection settings for :class:`~newo.client.NewoClient`."""

    api_key: str
    base_url: str = DEFAULT_BASE_URL
    timeout: float = 30.0

    @classmethod
    def from_env(cls, dotenv_path: str = ".env") -> "NewoConfig":
        """Build a config from environment variables.

        Recognised variables:
          * ``NEWO_API_KEY``  (required) — your key from Account → API Keys
          * ``NEWO_BASE_URL`` (optional) — override the API host
          * ``NEWO_TIMEOUT``  (optional) — request timeout in seconds
        """
        _load_dotenv(dotenv_path)
        api_key = os.environ.get("NEWO_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "NEWO_API_KEY is not set. Export it or add it to a .env file. "
                "Get your key from the Newo platform under Account → API Keys."
            )
        base_url = os.environ.get("NEWO_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        timeout = float(os.environ.get("NEWO_TIMEOUT", "30"))
        return cls(api_key=api_key, base_url=base_url, timeout=timeout)

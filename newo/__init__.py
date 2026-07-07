"""Lightweight Python client for the Newo.ai Customer API.

Docs: https://docs.newo.ai/  ·  API host: https://app.newo.ai
"""

from .brief import load_brief, pending_items
from .client import NewoClient, NewoAPIError
from .config import NewoConfig

__all__ = [
    "NewoClient",
    "NewoAPIError",
    "NewoConfig",
    "load_brief",
    "pending_items",
]
__version__ = "0.1.0"

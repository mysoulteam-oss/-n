"""Lightweight Python client for the Newo.ai Customer API.

Docs: https://docs.newo.ai/  ·  API host: https://app.newo.ai
"""

from .client import NewoClient, NewoAPIError
from .config import NewoConfig

__all__ = ["NewoClient", "NewoAPIError", "NewoConfig"]
__version__ = "0.1.0"

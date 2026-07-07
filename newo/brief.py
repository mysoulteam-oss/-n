"""Load a client agent brief/config from the ``config/`` tree.

The intake brief for an agent (company info, scripts, working hours, the
webhook/call data contract, etc.) lives as YAML under
``config/<client>/agent.yaml``. This helper loads and lightly validates it so
the rest of the integration can consume a single structured object instead of
re-parsing the brief.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise ImportError("PyYAML is required to load briefs: pip install pyyaml") from exc

_CONFIG_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")


def load_brief(client: str, config_root: str = _CONFIG_ROOT) -> Dict[str, Any]:
    """Load ``config/<client>/agent.yaml`` as a dict."""
    path = os.path.join(config_root, client, "agent.yaml")
    if not os.path.exists(path):
        raise FileNotFoundError(f"No agent config for client {client!r}: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def pending_items(brief: Dict[str, Any]) -> List[str]:
    """Return dotted paths of fields still awaiting client-supplied files.

    These are the brief answers that were "інформація у файлі" — flagged in the
    YAML with a ``pending_external_file: true`` marker.
    """
    found: List[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            if node.get("pending_external_file") is True:
                found.append(path or "<root>")
            for key, value in node.items():
                walk(value, f"{path}.{key}" if path else str(key))
        elif isinstance(node, list):
            for idx, value in enumerate(node):
                walk(value, f"{path}[{idx}]")

    walk(brief, "")
    return found

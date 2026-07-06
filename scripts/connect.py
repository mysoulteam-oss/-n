#!/usr/bin/env python3
"""Connect to your Newo.ai project and verify API access.

Usage:
    export NEWO_API_KEY=...        # or put it in a .env file
    python scripts/connect.py

The script obtains an access token from the Newo Customer API and prints the
authenticated context. Exit code is 0 on success, 1 on failure.
"""

from __future__ import annotations

import sys

# Allow running as `python scripts/connect.py` from the repo root.
sys.path.insert(0, ".")

from newo import NewoAPIError, NewoClient  # noqa: E402


def main() -> int:
    try:
        client = NewoClient.from_env()
    except RuntimeError as exc:
        print(f"✗ Configuration error: {exc}")
        return 1

    print(f"→ Connecting to {client.config.base_url} ...")
    try:
        info = client.connect()
    except NewoAPIError as exc:
        print(f"✗ Connection failed: {exc}")
        return 1
    except Exception as exc:  # network / TLS / unexpected
        print(f"✗ Connection failed: {exc}")
        return 1

    print("✓ Connected to Newo project")
    print(f"    customer_id : {info['customer_id']}")
    print(f"    source      : {info['source']}")
    print(f"    token valid : ~{info['expires_in']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

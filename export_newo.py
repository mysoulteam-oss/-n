#!/usr/bin/env python3
"""Export newo.ai project data (sessions + attributes) via the platform API.

Auth: exchange an API key for a short-lived JWT, then call the BFF endpoints.
The API key is read from the NEWO_API_KEY environment variable and is never
written to disk or printed.

Usage:
    NEWO_API_KEY=... python3 export_newo.py [--out export] [--per 100]

Endpoints (base https://app.newo.ai):
    POST /api/v1/auth/api-key/token        x-api-key -> {access_token, ...}
    GET  /api/v1/bff/sessions              paginated session records
    GET  /api/v1/bff/customer/attributes   customer attribute set
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("NEWO_BASE_URL", "https://app.newo.ai")


def _request(method, path, token=None, api_key=None, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if api_key:
        headers["x-api-key"] = api_key
    data = b"" if method == "POST" else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    last_err = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            # Retry transient 5xx/429; fail fast on other 4xx.
            if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                last_err = f"{e.code}: {body}"
                time.sleep(2 ** attempt)
                continue
            raise SystemExit(f"HTTP {e.code} on {method} {path}: {body}")
        except urllib.error.URLError as e:
            last_err = str(e)
            time.sleep(2 ** attempt)
    raise SystemExit(f"Request failed after retries: {method} {path}: {last_err}")


def get_token(api_key):
    tok = _request("POST", "/api/v1/auth/api-key/token", api_key=api_key)
    return tok["access_token"]


def export_sessions(token, per):
    items, page = [], 1
    total = None
    while True:
        d = _request("GET", "/api/v1/bff/sessions", token=token,
                     params={"page": page, "per": per})
        batch = d.get("items", [])
        items.extend(batch)
        total = d.get("metadata", {}).get("total", total)
        print(f"  sessions: page {page} -> {len(items)}"
              + (f"/{total}" if total is not None else ""), file=sys.stderr)
        if not batch or (total is not None and len(items) >= total):
            break
        page += 1
    return {"total": total, "count": len(items), "items": items}


def export_customer_attributes(token):
    return _request("GET", "/api/v1/bff/customer/attributes", token=token)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="export")
    ap.add_argument("--per", type=int, default=100)
    args = ap.parse_args()

    api_key = os.environ.get("NEWO_API_KEY")
    if not api_key:
        raise SystemExit("Set NEWO_API_KEY in the environment.")

    os.makedirs(args.out, exist_ok=True)
    print("Authenticating...", file=sys.stderr)
    token = get_token(api_key)

    print("Exporting sessions...", file=sys.stderr)
    sessions = export_sessions(token, args.per)
    with open(os.path.join(args.out, "sessions.json"), "w") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=2)

    print("Exporting customer attributes...", file=sys.stderr)
    attrs = export_customer_attributes(token)
    with open(os.path.join(args.out, "customer_attributes.json"), "w") as f:
        json.dump(attrs, f, ensure_ascii=False, indent=2)

    print(
        f"Done. sessions={sessions['count']} "
        f"attributes={len(attrs.get('attributes', []))} -> {args.out}/",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()

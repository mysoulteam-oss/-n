#!/usr/bin/env python3
"""Export newo.ai conversations for a given date.

Usage:
    NEWO_API_KEY=<key> python3 newo_export.py [YYYY-MM-DD] [--tz-offset HOURS] [--out DIR]

Defaults: date = yesterday in the given timezone, tz-offset = +3 (Europe/Kyiv), out = exports/.
The API returns acts with naive UTC timestamps; filtering is done in local time.

Produces:
    exports/conversations_<date>.md    - readable transcripts (client <-> agent)
    exports/conversations_<date>.json  - structured transcripts
    exports/acts_raw_<date>.json       - full raw act log for the day
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta

BASE_URL = "https://app.newo.ai"
PER_PAGE = 100
SESSION_GAP_MINUTES = 15


def get_token(api_key):
    req = urllib.request.Request(
        f"{BASE_URL}/api/v1/auth/api-key/token",
        method="POST",
        headers={"x-api-key": api_key},
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)["access_token"]


def fetch_acts_page(token, page):
    params = urllib.parse.urlencode({"page": page, "per": PER_PAGE})
    req = urllib.request.Request(
        f"{BASE_URL}/api/v1/conversations/acts?{params}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def collect_acts_for_day(api_key, day_start_utc, day_end_utc):
    """Acts come newest-first; walk pages until we pass the start boundary."""
    token = get_token(api_key)
    acts = []
    page = 1
    while True:
        data = fetch_acts_page(token, page)
        items = data.get("items", [])
        if not items:
            break
        for act in items:
            ts = datetime.fromisoformat(act["datetime"])
            if ts >= day_end_utc:
                continue
            if ts < day_start_utc:
                return acts
            acts.append(act)
        page += 1
    return acts


def get_arg(act, name):
    for a in act.get("arguments", []):
        if a.get("name") == name:
            return a.get("value")
    return None


def extract_messages(acts):
    """Keep only real dialogue turns between client and agent."""
    messages = []
    for act in acts:
        ref = act["reference_idn"]
        if ref == "user_message":
            text = get_arg(act, "text") or act.get("source_text") or ""
            role = "client"
        elif ref == "user_message_transcription_finished":
            text = get_arg(act, "transcript") or ""
            role = "client"
        elif ref == "agent_message" and act.get("to_integration_idn") is None:
            text = get_arg(act, "text") or act.get("source_text") or ""
            role = "agent"
        else:
            continue
        text = (text or "").strip()
        if not text:
            continue
        messages.append({
            "role": role,
            "text": text,
            "datetime": act["datetime"],
            "person_id": act["person_id"],
            "actor_id": act["actor_id"],
        })
    # The platform broadcasts the same utterance to several agent actors —
    # keep one copy per (person, role, text) within a few seconds.
    last_seen = {}
    deduped = []
    for m in sorted(messages, key=lambda m: m["datetime"]):
        key = (m["person_id"], m["role"], m["text"])
        ts = datetime.fromisoformat(m["datetime"])
        prev = last_seen.get(key)
        last_seen[key] = ts
        if prev is not None and ts - prev <= timedelta(seconds=5):
            continue
        deduped.append(m)
    return deduped


def extract_summaries(acts):
    """End-of-session summaries emitted by the agent's system log."""
    out = []
    for act in acts:
        if act["reference_idn"] != "agent_message" or act.get("to_integration_idn") != "system":
            continue
        text = get_arg(act, "text") or ""
        if "here is the summary" in text:
            out.append({"datetime": act["datetime"], "person_id": act["person_id"], "text": text.strip()})
    return out


def group_into_sessions(messages):
    """Group by client persona, then split on inactivity gaps."""
    by_person = defaultdict(list)
    for m in messages:
        by_person[m["person_id"]].append(m)
    sessions = []
    gap = timedelta(minutes=SESSION_GAP_MINUTES)
    for person_id, msgs in by_person.items():
        msgs.sort(key=lambda m: m["datetime"])
        current = [msgs[0]]
        for prev, cur in zip(msgs, msgs[1:]):
            if datetime.fromisoformat(cur["datetime"]) - datetime.fromisoformat(prev["datetime"]) > gap:
                sessions.append({"person_id": person_id, "messages": current})
                current = []
            current.append(cur)
        sessions.append({"person_id": person_id, "messages": current})
    sessions.sort(key=lambda s: s["messages"][0]["datetime"])
    return sessions


def attach_summaries(sessions, summaries):
    for s in sessions:
        start = s["messages"][0]["datetime"]
        end = s["messages"][-1]["datetime"]
        end_window = (datetime.fromisoformat(end) + timedelta(minutes=SESSION_GAP_MINUTES)).isoformat()
        s["summary"] = next(
            (x["text"] for x in summaries
             if x["person_id"] == s["person_id"] and start <= x["datetime"] <= end_window),
            None,
        )


def write_markdown(sessions, day_str, tz_offset, path):
    lines = [f"# Разговоры newo.ai за {day_str} (время UTC{tz_offset:+d})", "",
             f"Всего разговоров: {len(sessions)}", ""]
    role_names = {"client": "Клиент", "agent": "Агент"}
    for i, s in enumerate(sessions, 1):
        start = datetime.fromisoformat(s["messages"][0]["datetime"]) + timedelta(hours=tz_offset)
        end = datetime.fromisoformat(s["messages"][-1]["datetime"]) + timedelta(hours=tz_offset)
        lines.append(f"## {i}. {start:%H:%M}–{end:%H:%M} (клиент {s['person_id'][:8]})")
        lines.append("")
        for m in s["messages"]:
            ts = datetime.fromisoformat(m["datetime"]) + timedelta(hours=tz_offset)
            lines.append(f"**[{ts:%H:%M:%S}] {role_names[m['role']]}:** {m['text']}")
            lines.append("")
        if s.get("summary"):
            quoted = s["summary"].replace("\n", "\n> ")
            lines.append(f"> {quoted}")
            lines.append("")
        lines.append("---")
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("date", nargs="?", help="Local date YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--tz-offset", type=int, default=3, help="Local timezone offset in hours from UTC (default: +3)")
    parser.add_argument("--out", default="exports", help="Output directory")
    args = parser.parse_args()

    api_key = os.environ.get("NEWO_API_KEY")
    if not api_key:
        sys.exit("Set NEWO_API_KEY environment variable (see .env.example)")

    tz = timedelta(hours=args.tz_offset)
    if args.date:
        day_local = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        day_local = (datetime.utcnow() + tz).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    day_start_utc = day_local.replace(hour=0, minute=0, second=0, microsecond=0) - tz
    day_end_utc = day_start_utc + timedelta(days=1)
    day_str = day_local.strftime("%Y-%m-%d")

    print(f"Fetching acts for {day_str} local (UTC window {day_start_utc} .. {day_end_utc})")
    acts = collect_acts_for_day(api_key, day_start_utc, day_end_utc)
    print(f"Fetched {len(acts)} acts")

    messages = extract_messages(acts)
    sessions = group_into_sessions(messages)
    attach_summaries(sessions, extract_summaries(acts))

    os.makedirs(args.out, exist_ok=True)
    raw_path = os.path.join(args.out, f"acts_raw_{day_str}.json")
    json_path = os.path.join(args.out, f"conversations_{day_str}.json")
    md_path = os.path.join(args.out, f"conversations_{day_str}.md")
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(acts, f, ensure_ascii=False, indent=2)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"date": day_str, "tz_offset": args.tz_offset, "sessions": sessions}, f, ensure_ascii=False, indent=2)
    write_markdown(sessions, day_str, args.tz_offset, md_path)
    print(f"Wrote {md_path}, {json_path}, {raw_path} ({len(sessions)} conversations, {len(messages)} messages)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Standalone Newo outbound voice-call report generator.

Self-contained implementation of the newo-call-report spec: authenticate with a
Newo API key, pull voice sessions for a date range, reconstruct transcripts
(falling back to chat history), classify each call, and emit all.json, per-day
batch text files, and an HTML report.

The API key is read from --key or the NEWO_API_KEY env var; it is never written
to any output file.
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta

BASE = os.environ.get("NEWO_BASE_URL", "https://app.newo.ai")

VOICEMAIL_MARKERS = [
    "залиште ваше голосове", "після звукового сигналу", "натисніть нуль",
    "натисніть 0", "voice message after the beep", "recording this call",
    "вне зоны", "абонент", "залиште повідомлення", "автовідповідач",
    "голосову пошту", "голосова пошта",
]
REFUSAL_MARKERS = [
    "не треба", "не потрібно", "не актуально", "не цікаво", "нічого",
    "нічо", "ничего", "пізніше", "поки що", "не хочеться", "зайнята",
    "зайнятий", "не можу", "зараз ні", "не зараз", "передзвоніть",
]
SIMPLE_NO = {"ні", "нет", "нє", "ні, дякую", "ні дякую", "no", "no thanks"}
BOOKING_CONFIRM_RE = re.compile(
    r"бронюю для вас|забронював|забронювала|бронь підтвердж|"
    r"надішлю.{0,40}(sms|повідомлення|детал)|замовлення чекає|замовлення оформлен",
    re.IGNORECASE,
)
PHONE_RE = re.compile(r"\b(380\d{9})\b")


def http(method, path, token=None, api_key=None, params=None):
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
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(2 ** attempt)
                continue
            raise SystemExit(f"HTTP {e.code} on {method} {path}: {body}")
        except urllib.error.URLError:
            time.sleep(2 ** attempt)
    raise SystemExit(f"Request failed after retries: {method} {path}")


def auth(api_key):
    return http("POST", "/api/v1/auth/api-key/token", api_key=api_key)["access_token"]


def fix_mojibake(text):
    if not text:
        return text
    if any(ch in text for ch in ("Ð", "Ñ", "â", "Â", "ð")):
        try:
            return text.encode("latin1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return text
    return text


def pull_sessions(token, from_utc, to_utc, per=100):
    items, page = [], 1
    while True:
        d = http("GET", "/api/v1/bff/sessions", token=token, params={
            "page": page, "per": per,
            "from_datetime": from_utc, "to_datetime": to_utc,
        })
        batch = d.get("items", [])
        items.extend(batch)
        total = d.get("metadata", {}).get("total", 0)
        if not batch or len(items) >= total:
            break
        page += 1
    return items


def pull_detail(token, sid):
    return http("GET", f"/api/v1/bff/sessions/{sid}", token=token)


def reconstruct_chat(token, actor_id):
    lines, page = [], 1
    while True:
        d = http("GET", "/api/v1/chat/history", token=token, params={
            "user_actor_id": actor_id, "page": page, "per": 100,
        })
        batch = d.get("items", [])
        for m in batch:
            txt = (m.get("payload") or {}).get("text", "")
            if not txt:
                continue
            who = "ConvoAgent" if m.get("is_agent") else "User"
            lines.append(f"{who}: {fix_mojibake(txt)}")
        total = d.get("metadata", {}).get("total", 0)
        if not batch or len(lines) >= total or page > 50:
            break
        page += 1
    return "\n".join(lines)


def parse_transcript(raw):
    """Return (text, user_lines) from a 'ConvoAgent:/User:' transcript string."""
    text = fix_mojibake(raw or "").strip()
    user_lines = []
    for ln in text.splitlines():
        s = ln.strip()
        if s.lower().startswith("user:"):
            user_lines.append(s.split(":", 1)[1].strip())
    return text, user_lines


def is_refusal(user_lines, full_lines):
    for i, raw in enumerate(full_lines):
        if not raw.lower().startswith("user:"):
            continue
        u = raw.split(":", 1)[1].strip().lower()
        for m in REFUSAL_MARKERS:
            if m in u:
                return True
        if u.strip(" .!?") in SIMPLE_NO:
            # Not a refusal if the agent just asked whether the client has questions.
            prev = full_lines[i - 1].lower() if i > 0 else ""
            if any(q in prev for q in ("питанн", "запитанн", "questions", "ще щось")):
                continue
            return True
    return False


def classify(row, full_lines, booking_mode=False):
    u, a = row["u"], row["a"]
    text_l = row["text"].lower()
    if any(m in text_l for m in VOICEMAIL_MARKERS):
        return "voicemail"
    if u == 0 and a >= 2:
        return "silent"
    if u == 0:
        return "noanswer"
    if row["src"] == "empty":
        return "phantom"
    if is_refusal(row["user_lines"], full_lines):
        return "refusal"
    if booking_mode and BOOKING_CONFIRM_RE.search(row["text"]):
        return "booking"
    return "conversation"


def to_local(utc_str, tz_offset):
    if not utc_str:
        return "", ""
    s = utc_str.split(".")[0]
    try:
        dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return s, s
    loc = dt + timedelta(hours=tz_offset)
    return loc.strftime("%Y-%m-%dT%H:%M:%S"), dt.strftime("%Y-%m-%dT%H:%M:%S")


def build_rows(token, sessions, args):
    rows = []
    empty_transcripts = 0
    for s in sessions:
        sid = s["id"]
        det = pull_detail(token, sid)
        a_args = det.get("arguments") or {}
        persona = det.get("persona") or {}
        u = det.get("user_messages_count", 0) or 0
        a = det.get("agent_messages_count", 0) or 0
        raw = a_args.get("transcript") or ""
        text, user_lines = parse_transcript(raw)
        src = "transcript" if text else "empty"
        if not text and u > 0 and persona.get("actor_id"):
            text = reconstruct_chat(token, persona["actor_id"])
            if text:
                src = "chat_history"
                user_lines = [l.split(":", 1)[1].strip()
                              for l in text.splitlines() if l.lower().startswith("user:")]
        if u > 0 and src == "empty":
            empty_transcripts += 1
        phone = persona.get("external_id") or ""
        if not phone:
            m = PHONE_RE.search(text)
            phone = m.group(1) if m else ""
        if args.exclude and phone in args.exclude:
            continue
        time_local, time_utc = to_local(det.get("created_at", ""), args.tz_offset)
        full_lines = text.splitlines()
        row = {
            "id": sid,
            "day": time_local.split("T")[0] if time_local else "",
            "time_local": time_local,
            "time_utc": time_utc,
            "phone": phone or "—",
            "u": u, "a": a,
            "src": src,
            "ended": a_args.get("conversationEndedReason") or "",
            "is_voicemail": False,
            "is_opportunity": bool(det.get("is_opportunity")),
            "status": "",
            "user_lines": user_lines,
            "text": text,
        }
        row["status"] = classify(row, full_lines, args.booking)
        row["is_voicemail"] = row["status"] == "voicemail"
        rows.append(row)
    rows.sort(key=lambda r: r["time_local"])
    return rows, empty_transcripts


def write_all_json(rows, outdir):
    with open(os.path.join(outdir, "all.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def write_batches(rows, outdir, batch_size=25):
    by_day = {}
    for r in rows:
        by_day.setdefault(r["day"], []).append(r)
    for day, drows in by_day.items():
        for bi in range((len(drows) + batch_size - 1) // batch_size):
            chunk = drows[bi * batch_size:(bi + 1) * batch_size]
            path = os.path.join(outdir, f"{day}_b{bi + 1}.txt")
            with open(path, "w", encoding="utf-8") as f:
                for r in chunk:
                    f.write(
                        f"=== CALL day={r['day']} local_time={r['time_local']} "
                        f"phone={r['phone']} u={r['u']} a={r['a']} "
                        f"status={r['status']} ended={r['ended']} ===\n")
                    f.write(r["text"] + "\n\n")


STATUS_LABEL = {
    "conversation": "Розмова", "refusal": "Відмова/не актуально",
    "noanswer": "Не взяли", "silent": "Тиша", "voicemail": "Автовідповідач",
    "booking": "Бронь/замовлення", "phantom": "Порожній транскрипт",
}


def write_html(rows, outdir, client_label, date_from, date_to, tz_offset,
               empty_transcripts, booking_mode):
    c = Counter(r["status"] for r in rows)
    total = len(rows)
    noanswer = c.get("noanswer", 0)
    picked = total - noanswer
    pct = f"{(picked / total * 100):.0f}%" if total else "0%"
    conversations = c.get("conversation", 0)
    silence_vm = c.get("silent", 0) + c.get("voicemail", 0)
    refusals = c.get("refusal", 0)
    bookings = c.get("booking", 0)

    def esc(x):
        import html as _h
        return _h.escape(str(x))

    cards = [
        ("Всього дзвінків", total),
        ("Взяли слухавку", f"{picked} ({pct})"),
        ("Розмови з клієнтом", conversations),
        ("Не взяли", noanswer),
        ("Тиша / автовідповідач", silence_vm),
        ("Відмова / не актуально", refusals),
        ("Порожні транскрипти (u&gt;0)", empty_transcripts),
    ]
    if booking_mode:
        cards.append(("Бронь / замовлення", bookings))

    card_html = "".join(
        f'<div class="card"><div class="num">{esc(v)}</div>'
        f'<div class="lbl">{lbl}</div></div>' for lbl, v in cards)

    extra_cols = '<th>Бронь</th>' if booking_mode else ''
    rows_html = []
    for i, r in enumerate(rows):
        booking_cell = (f'<td>{"✅" if r["status"] == "booking" else ""}</td>'
                        if booking_mode else '')
        transcript = esc(r["text"]) or "—"
        rows_html.append(
            f'<tr class="row" data-status="{r["status"]}">'
            f'<td>{esc(r["time_local"])}</td>'
            f'<td>{esc(r["phone"])}</td>'
            f'<td><span class="badge s-{r["status"]}">{STATUS_LABEL.get(r["status"], r["status"])}</span></td>'
            f'<td>{r["u"]}</td><td>{r["a"]}</td>'
            f'<td>{esc(r["ended"]) or "—"}</td>'
            f'<td>{esc(r["src"])}</td>'
            f'{booking_cell}'
            f'<td><button onclick="t({i})">показати</button></td></tr>'
            f'<tr id="tr{i}" class="transcript" style="display:none">'
            f'<td colspan="{9 if booking_mode else 8}"><pre>{transcript}</pre></td></tr>')

    booking_warn = (
        '<p class="warn">⚠️ Кандидати на бронь/замовлення потребують ручної '
        'перевірки по транскрипту. is_opportunity НЕ використовується як підсумок.</p>'
        if booking_mode else '')

    period = date_from if date_from == date_to else f"{date_from} … {date_to}"
    html_doc = f"""<!doctype html>
<html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Звіт по дзвінках — {esc(client_label)} — {esc(period)}</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;background:#f5f6f8;color:#1a1a2e}}
 header{{background:#15233b;color:#fff;padding:20px 28px}}
 header h1{{margin:0;font-size:20px}} header p{{margin:4px 0 0;opacity:.8;font-size:13px}}
 .cards{{display:flex;flex-wrap:wrap;gap:14px;padding:20px 28px}}
 .card{{background:#fff;border-radius:12px;padding:16px 20px;min-width:140px;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
 .card .num{{font-size:26px;font-weight:700}} .card .lbl{{font-size:12px;color:#667;margin-top:4px}}
 .controls{{padding:0 28px 12px}} .controls button{{margin:3px;padding:6px 12px;border:1px solid #ccd;border-radius:8px;background:#fff;cursor:pointer}}
 .controls button.active{{background:#15233b;color:#fff}}
 table{{width:calc(100% - 56px);margin:0 28px 40px;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
 th,td{{padding:9px 12px;text-align:left;font-size:13px;border-bottom:1px solid #eef}}
 th{{background:#eef1f6}}
 pre{{white-space:pre-wrap;font-family:inherit;margin:0;font-size:13px;background:#fafbfd;padding:12px;border-radius:8px}}
 .badge{{padding:3px 8px;border-radius:20px;font-size:11px;color:#fff;white-space:nowrap}}
 .s-conversation{{background:#2e7d32}} .s-refusal{{background:#c62828}} .s-noanswer{{background:#9e9e9e}}
 .s-silent{{background:#ef6c00}} .s-voicemail{{background:#6a1b9a}} .s-booking{{background:#1565c0}} .s-phantom{{background:#455a64}}
 .warn{{margin:0 28px 16px;padding:12px 16px;background:#fff3cd;border:1px solid #ffe69c;border-radius:10px;font-size:13px}}
 button{{font-size:12px}}
</style></head>
<body>
<header><h1>Звіт по outbound voice-дзвінках — {esc(client_label)}</h1>
<p>Період: {esc(period)} · Час локальний (UTC+{tz_offset}) · Згенеровано автоматично з Newo API</p></header>
<div class="cards">{card_html}</div>
{booking_warn}
<div class="controls">
 <button class="active" onclick="f(this,'all')">Всі ({total})</button>
 <button onclick="f(this,'conversation')">Розмови ({conversations})</button>
 <button onclick="f(this,'refusal')">Відмови ({refusals})</button>
 <button onclick="f(this,'noanswer')">Не взяли ({noanswer})</button>
 <button onclick="f(this,'silent')">Тиша ({c.get('silent',0)})</button>
 <button onclick="f(this,'voicemail')">Автовідповідач ({c.get('voicemail',0)})</button>
 {'<button onclick="f(this,&quot;booking&quot;)">Бронь (' + str(bookings) + ')</button>' if booking_mode else ''}
</div>
<table><thead><tr><th>Час (локальний)</th><th>Телефон</th><th>Статус</th>
<th>U</th><th>A</th><th>Хто завершив</th><th>Джерело</th>{extra_cols}<th>Транскрипт</th></tr></thead>
<tbody>{''.join(rows_html)}</tbody></table>
<script>
 function t(i){{var e=document.getElementById('tr'+i);e.style.display=e.style.display==='none'?'table-row':'none';}}
 function f(btn,st){{document.querySelectorAll('.controls button').forEach(b=>b.classList.remove('active'));btn.classList.add('active');
  document.querySelectorAll('tr.row').forEach(r=>{{var show=(st==='all'||r.dataset.status===st);r.style.display=show?'table-row':'none';
   var tr=document.getElementById('tr'+[...document.querySelectorAll('tr.row')].indexOf(r));}});
  document.querySelectorAll('tr.transcript').forEach(tr=>tr.style.display='none');}}
</script>
</body></html>"""
    path = os.path.join(outdir, "report.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_doc)
    return path, {
        "total": total, "picked": picked, "pct": pct,
        "conversations": conversations, "noanswer": noanswer,
        "silence_vm": silence_vm, "refusals": refusals, "bookings": bookings,
        "empty_transcripts": empty_transcripts,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", help="client idn under ops/clients/<idn>")
    ap.add_argument("--client-label", default=None)
    ap.add_argument("--key", default=None, help="API key (else NEWO_API_KEY env)")
    ap.add_argument("--from", dest="date_from", required=True)
    ap.add_argument("--to", dest="date_to", default=None)
    ap.add_argument("--tz-offset", type=int, default=3)
    ap.add_argument("--exclude", default="")
    ap.add_argument("--booking", action="store_true")
    ap.add_argument("--copy-html", action="store_true")
    args = ap.parse_args()
    args.date_to = args.date_to or args.date_from
    args.exclude = set(x.strip() for x in args.exclude.split(",") if x.strip())

    api_key = args.key or os.environ.get("NEWO_API_KEY")
    if not api_key and args.client:
        env_path = os.path.join("newoedu_remote", "ops", "clients", args.client, ".env")
        if os.path.exists(env_path):
            for line in open(env_path):
                if line.startswith("NEWO_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
    if not api_key:
        raise SystemExit("No API key. Use --key or set NEWO_API_KEY.")

    client_label = args.client_label or (args.client or "Newo")
    # Local date range -> UTC naive window for the API filter.
    f_utc = (datetime.strptime(args.date_from, "%Y-%m-%d")
             - timedelta(hours=args.tz_offset)).strftime("%Y-%m-%dT%H:%M:%S")
    t_utc = (datetime.strptime(args.date_to, "%Y-%m-%d") + timedelta(days=1)
             - timedelta(hours=args.tz_offset)).strftime("%Y-%m-%dT%H:%M:%S")

    print(f"Auth + pulling sessions {args.date_from}..{args.date_to} "
          f"(UTC {f_utc}..{t_utc})", file=sys.stderr)
    token = auth(api_key)
    sessions = pull_sessions(token, f_utc, t_utc)
    voice = [s for s in sessions
             if s.get("connector_channel") == "voice"
             or "voice" in (s.get("connector_idn") or "")]
    print(f"sessions={len(sessions)} voice={len(voice)}", file=sys.stderr)

    rows, empty_transcripts = build_rows(token, voice, args)

    slug = args.client or re.sub(r"\W+", "_", client_label).strip("_").lower()
    outdir = f"_callreport_{slug}_{args.date_from}_{args.date_to}"
    os.makedirs(outdir, exist_ok=True)
    write_all_json(rows, outdir)
    write_batches(rows, outdir)
    path, stats = write_html(rows, outdir, client_label, args.date_from,
                             args.date_to, args.tz_offset, empty_transcripts,
                             args.booking)

    final = path
    if args.copy_html:
        suffix = args.date_from if args.date_from == args.date_to \
            else f"{args.date_from}_{args.date_to}"
        final = f"{slug}-calls-report-{suffix}.html"
        shutil.copy(path, final)

    print(json.dumps({
        "empty_transcripts": empty_transcripts, **stats,
        "html": os.path.abspath(final), "outdir": os.path.abspath(outdir),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

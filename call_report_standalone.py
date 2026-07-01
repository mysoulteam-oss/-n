#!/usr/bin/env python3
"""Standalone Newo outbound-voice call report (self-contained fallback).
Implements the "Universal Newo Call Report" spec: generic mode by default.
"""
import argparse, json, re, html, shutil, os, sys
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import requests

BASE = "https://app.newo.ai"
PHONE_RE = re.compile(r"\b(380\d{9})\b")

VOICEMAIL_MARKERS = [
    "залиште ваше голосове", "після звукового сигналу", "натисніть нуль",
    "натисніть 0", "voice message after the beep", "recording this call",
    "вне зоны", "абонент",
]
REFUSAL_MARKERS = [
    "не треба", "не потрібно", "не актуально", "не цікаво", "нічого", "нічо",
    "ничего", "пізніше", "поки що", "не хочеться", "зайнята", "зайнятий",
    "не можу", "зараз ні",
]

def auth(api_key):
    r = requests.post(f"{BASE}/api/v1/auth/api-key/token",
                      headers={"x-api-key": api_key, "Content-Type": "application/json"}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}

def fix_mojibake(text):
    if not text:
        return text
    if any(m in text for m in ("Ð", "Ñ", "â", "Â", "ð")):
        for enc in ("cp1252", "latin1"):
            try:
                return text.encode(enc).decode("utf-8")
            except Exception:
                continue
    return text

def pull_sessions(headers, from_dt, to_dt):
    out, page, per = [], 1, 200
    while True:
        r = requests.get(f"{BASE}/api/v1/bff/sessions", headers=headers, timeout=60,
                         params={"page": page, "per": per, "from_datetime": from_dt, "to_datetime": to_dt})
        r.raise_for_status()
        d = r.json()
        items = d.get("items") or d.get("data") or []
        out.extend(items)
        total = (d.get("metadata") or {}).get("total")
        if len(items) < per or (total is not None and len(out) >= total):
            break
        page += 1
    return out

def pull_details(headers, sid):
    r = requests.get(f"{BASE}/api/v1/bff/sessions/{sid}", headers=headers, timeout=60)
    r.raise_for_status()
    return r.json()

def parse_args_field(a):
    if isinstance(a, str):
        try:
            a = json.loads(a)
        except Exception:
            return {}
    return a if isinstance(a, dict) else {}

def reconstruct_chat_history(headers, actor_id, start_utc, end_utc):
    try:
        r = requests.get(f"{BASE}/api/v1/chat/history", headers=headers, timeout=60,
                         params={"user_actor_id": actor_id, "page": 1, "per": 250})
        r.raise_for_status()
        items = (r.json().get("items") or [])
    except Exception:
        return ""
    rows = []
    for m in items:
        dt = m.get("datetime", "")
        if dt and not (start_utc <= dt[:19] <= end_utc):
            continue
        payload = m.get("payload")
        txt = ""
        if isinstance(payload, dict):
            txt = payload.get("text") or payload.get("message") or payload.get("content") or ""
        elif isinstance(payload, str):
            txt = payload
        txt = (txt or "").strip()
        if not txt or txt.startswith(("System log:", "Debug log:", "THOUGHTS")):
            continue
        rows.append((dt, "ConvoAgent" if m.get("is_agent") else "User", txt))
    rows.sort(key=lambda x: x[0])
    return "\n".join(f"{who}: {t}" for _, who, t in rows)

def extract_phone(session, args, transcript):
    for cand in (
        (session.get("persona") or {}).get("external_id"),
        (session.get("persona") or {}).get("contact_information"),
        args.get("externalActorId"), args.get("phone"),
    ):
        if cand:
            m = PHONE_RE.search(str(cand))
            if m:
                return m.group(1)
    m = PHONE_RE.search(transcript or "")
    return m.group(1) if m else ""

def classify(u, a, transcript, ended, booking_mode=False):
    low = (transcript or "").lower()
    if u == 0 and a <= 1:
        return "noanswer"
    if any(mk in low for mk in VOICEMAIL_MARKERS):
        return "voicemail"
    if u == 0 and a >= 2:
        return "silent"
    # user spoke
    user_lines = [ln[5:].strip().lower() for ln in (transcript or "").split("\n") if ln.startswith("User:")]
    joined = " ".join(user_lines)
    if any(mk in joined for mk in REFUSAL_MARKERS):
        return "refusal"
    return "conversation"

def build(headers, args):
    tz = timedelta(hours=args.tz_offset)
    d_from = datetime.strptime(args.date_from, "%Y-%m-%d")
    d_to = datetime.strptime(args.date_to, "%Y-%m-%d")
    local_start = d_from
    local_end = d_to + timedelta(days=1) - timedelta(seconds=1)
    utc_start = (local_start - tz).strftime("%Y-%m-%dT%H:%M:%S")
    utc_end = (local_end - tz).strftime("%Y-%m-%dT%H:%M:%S")
    print(f"local window: {local_start} .. {local_end}  (UTC {utc_start} .. {utc_end})")

    sessions = pull_sessions(headers, utc_start, utc_end)
    voice = [s for s in sessions if s.get("integration_idn") == "newo_voice"
             or s.get("connector_idn") == "newo_voice_connector"]
    print(f"sessions total: {len(sessions)} | voice: {len(voice)}")

    exclude = set(x.strip() for x in (args.exclude or "").split(",") if x.strip())

    def work(s):
        sid = s.get("id") or s.get("session_id")
        u = s.get("user_messages_count") or 0
        a = s.get("agent_messages_count") or 0
        args_d, detail = {}, None
        # detail needed for transcript/endedReason whenever there was any agent turn
        if a >= 1:
            try:
                detail = pull_details(headers, sid)
                args_d = parse_args_field(detail.get("arguments"))
            except Exception:
                detail = None
        src = "transcript"
        transcript = fix_mojibake(args_d.get("transcript") or "")
        ended = args_d.get("conversationEndedReason") or ""
        persona = (detail or s).get("persona") or {}
        # reconstruct if needed
        if u > 0 and not transcript and persona.get("actor_id"):
            transcript = fix_mojibake(reconstruct_chat_history(headers, persona["actor_id"], utc_start, utc_end))
            src = "chat_history" if transcript else "empty"
        if not transcript:
            src = "empty"
        phone = extract_phone(detail or s, args_d, transcript)
        created = (s.get("created_at") or "")[:19]
        try:
            local_dt = (datetime.strptime(created, "%Y-%m-%dT%H:%M:%S") + tz).strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            local_dt = created
        status = classify(u, a, transcript, ended, args.booking)
        return {
            "id": sid, "day": local_dt[:10], "time_local": local_dt, "time_utc": created,
            "phone": phone, "u": u, "a": a, "src": src, "ended": ended,
            "is_voicemail": status == "voicemail",
            "is_opportunity": bool(s.get("is_opportunity")),
            "is_test": bool(s.get("is_test")),
            "status": status,
            "user_lines": [ln[5:].strip() for ln in transcript.split("\n") if ln.startswith("User:")],
            "text": transcript,
        }

    with ThreadPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(work, voice))

    # exclusions
    kept = []
    excluded = 0
    for r in rows:
        if r["is_test"] or (r["phone"] and r["phone"] in exclude):
            excluded += 1
            continue
        kept.append(r)
    kept.sort(key=lambda r: r["time_local"])
    print(f"excluded (test/exclude-list): {excluded} | kept: {len(kept)}")
    return kept, {"utc_start": utc_start, "utc_end": utc_end, "excluded": excluded, "total_voice": len(voice)}

def write_all_json(rows, outdir):
    (outdir / "all.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

def write_batches(rows, outdir):
    lines = []
    for r in rows:
        lines.append(f"=== CALL day={r['day']} local_time={r['time_local']} phone={r['phone']} "
                     f"u={r['u']} a={r['a']} status={r['status']} ended={r['ended']} ===")
        lines.append(r["text"] or "(no transcript)")
        lines.append("")
    (outdir / "b.txt").write_text("\n".join(lines), encoding="utf-8")

def write_html(rows, outdir, meta, label):
    n = len(rows)
    c = Counter(r["status"] for r in rows)
    picked = sum(1 for r in rows if r["status"] not in ("noanswer",))
    conv = c.get("conversation", 0)
    noans = c.get("noanswer", 0)
    silence_vm = c.get("silent", 0) + c.get("voicemail", 0)
    refus = c.get("refusal", 0)
    empty_u = sum(1 for r in rows if r["u"] > 0 and r["src"] == "empty")
    known_phone = sum(1 for r in rows if r["phone"])
    ended_c = Counter(r["ended"] for r in rows if r["ended"])
    pct = lambda x: f"{(100*x/n):.0f}%" if n else "0%"

    per_day = defaultdict(Counter)
    per_hour = defaultdict(Counter)
    for r in rows:
        per_day[r["day"]][r["status"]] += 1
        hr = r["time_local"][11:13]
        per_hour[hr][r["status"]] += 1

    def esc(x):
        return html.escape(str(x) if x is not None else "")

    STATUS_LABEL = {"conversation": "розмова", "refusal": "відмова", "noanswer": "не взяли",
                    "silent": "тиша", "voicemail": "автовідповідач"}

    kpi = [
        ("Всього дзвінків", n, ""),
        ("Взяли слухавку", picked, pct(picked)),
        ("Розмови з клієнтом", conv, pct(conv)),
        ("Не взяли", noans, pct(noans)),
        ("Тиша / автовідповідач", silence_vm, pct(silence_vm)),
        ("Відмова / не актуально", refus, pct(refus)),
        ("Порожні транскрипти (u>0)", empty_u, ""),
    ]
    kpi_html = "".join(
        f'<div class="card"><div class="v">{v}</div><div class="l">{esc(l)}</div>'
        f'<div class="p">{esc(p)}</div></div>' for l, v, p in kpi)

    def table(counter_map, header):
        head = sorted({s for cc in counter_map.values() for s in cc})
        rowshtml = ""
        for k in sorted(counter_map):
            cells = "".join(f"<td>{counter_map[k].get(s,0)}</td>" for s in head)
            tot = sum(counter_map[k].values())
            rowshtml += f"<tr><td>{esc(k)}</td>{cells}<td><b>{tot}</b></td></tr>"
        heads = "".join(f"<th>{esc(STATUS_LABEL.get(s,s))}</th>" for s in head)
        return (f"<h3>{esc(header)}</h3><table class=grid><tr><th>{esc(header)}</th>{heads}"
                f"<th>Разом</th></tr>{rowshtml}</table>")

    ended_html = "".join(f"<li>{esc(k)}: <b>{v}</b></li>" for k, v in ended_c.most_common())

    call_rows = ""
    for i, r in enumerate(rows):
        badge = STATUS_LABEL.get(r["status"], r["status"])
        tx = esc(r["text"]).replace("\n", "<br>")
        call_rows += (
            f'<tr class="crow" data-st="{esc(r["status"])}" onclick="tg({i})">'
            f'<td>{esc(r["time_local"][11:19])}</td><td>{esc(r["phone"] or "—")}</td>'
            f'<td><span class="badge b-{esc(r["status"])}">{esc(badge)}</span></td>'
            f'<td>{r["u"]}</td><td>{r["a"]}</td><td>{esc(r["ended"])}</td></tr>'
            f'<tr id="t{i}" class="tx" style="display:none"><td colspan=6><pre>{tx or "(немає транскрипту)"}</pre></td></tr>')

    doc = f"""<!doctype html><html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Newo Call Report — {esc(label)}</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;background:#0f172a;color:#e2e8f0}}
.wrap{{max-width:1100px;margin:0 auto;padding:24px}}
h1{{font-size:22px;margin:0 0 4px}} .sub{{color:#94a3b8;margin-bottom:20px;font-size:13px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:24px}}
.card{{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:14px}}
.card .v{{font-size:26px;font-weight:700}} .card .l{{font-size:12px;color:#94a3b8;margin-top:4px}}
.card .p{{font-size:12px;color:#38bdf8;margin-top:2px}}
.box{{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:16px;margin-bottom:20px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
.grid th,.grid td{{border:1px solid #334155;padding:6px 8px;text-align:center}}
.grid th{{background:#0b1220}}
.calltable td{{border-bottom:1px solid #1f2b3e;padding:7px 8px}}
.crow{{cursor:pointer}} .crow:hover{{background:#243049}}
.badge{{padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600}}
.b-conversation{{background:#064e3b;color:#6ee7b7}} .b-refusal{{background:#7c2d12;color:#fdba74}}
.b-noanswer{{background:#334155;color:#cbd5e1}} .b-silent{{background:#1e3a5f;color:#93c5fd}}
.b-voicemail{{background:#3b0764;color:#d8b4fe}}
pre{{white-space:pre-wrap;font-size:12px;color:#cbd5e1;margin:0;background:#0b1220;padding:10px;border-radius:8px}}
.filters button{{background:#1e293b;color:#e2e8f0;border:1px solid #334155;border-radius:8px;padding:5px 10px;margin:2px;cursor:pointer;font-size:12px}}
.filters button.on{{background:#38bdf8;color:#08131f;border-color:#38bdf8}}
h3{{margin:10px 0 6px;font-size:14px}}
</style></head><body><div class="wrap">
<h1>Newo Outbound Voice — {esc(label)}</h1>
<div class="sub">Період: {esc(rows[0]['day'] if rows else '')} (локальний час UTC+{meta['tz']}) ·
згенеровано з даних app.newo.ai · режим: generic (без booking)</div>
<div class="cards">{kpi_html}</div>
<div class="box"><h3>Якість даних</h3>
<ul><li>Порожні транскрипти при u&gt;0: <b>{empty_u}</b></li>
<li>Дзвінків з відомим номером: <b>{known_phone}</b> з {n}</li>
<li>Виключено тестових/зі списку: <b>{meta['excluded']}</b></li></ul>
<h3>Хто завершив дзвінок</h3><ul>{ended_html or '<li>—</li>'}</ul></div>
<div class="box">{table(per_day,'День')}</div>
<div class="box">{table(per_hour,'Година')}</div>
<div class="box"><h3>Усі дзвінки ({n})</h3>
<div class="filters">
<button class="on" onclick="fl('all',this)">Всі</button>
<button onclick="fl('conversation',this)">Розмови</button>
<button onclick="fl('refusal',this)">Відмови</button>
<button onclick="fl('noanswer',this)">Не взяли</button>
<button onclick="fl('silent',this)">Тиша</button>
<button onclick="fl('voicemail',this)">Автовідповідач</button></div>
<table class="calltable"><tr><th>Час</th><th>Телефон</th><th>Статус</th><th>u</th><th>a</th><th>Завершив</th></tr>
{call_rows}</table></div>
</div>
<script>
function tg(i){{var e=document.getElementById('t'+i);e.style.display=e.style.display==='none'?'':'none';}}
function fl(st,btn){{document.querySelectorAll('.filters button').forEach(b=>b.classList.remove('on'));btn.classList.add('on');
document.querySelectorAll('.crow').forEach(r=>{{var sh=st==='all'||r.dataset.st===st;r.style.display=sh?'':'none';
var tx=r.nextElementSibling;if(tx&&tx.classList.contains('tx'))tx.style.display='none';}});}}
</script></body></html>"""
    (outdir / "report.html").write_text(doc, encoding="utf-8")
    return {"n": n, "picked": picked, "conv": conv, "noans": noans,
            "silence_vm": silence_vm, "refus": refus, "empty_u": empty_u}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key")
    ap.add_argument("--client-label", default="Newo Client")
    ap.add_argument("--from", dest="date_from", required=True)
    ap.add_argument("--to", dest="date_to")
    ap.add_argument("--tz-offset", dest="tz_offset", type=int, default=3)
    ap.add_argument("--exclude", default="")
    ap.add_argument("--booking", action="store_true")
    ap.add_argument("--copy-html", action="store_true")
    ap.add_argument("--out", default="callreport")
    a = ap.parse_args()
    a.date_to = a.date_to or a.date_from
    key = a.key or os.environ.get("NEWO_API_KEY")
    if not key:
        print("ERROR: no API key (--key or NEWO_API_KEY)"); sys.exit(1)
    headers = auth(key)
    outdir = Path(a.out); outdir.mkdir(parents=True, exist_ok=True)
    rows, meta = build(headers, a)
    meta["tz"] = a.tz_offset
    write_all_json(rows, outdir)
    write_batches(rows, outdir)
    stats = write_html(rows, outdir, meta, a.client_label)
    html_path = outdir / "report.html"
    if a.copy_html:
        dest = Path(f"{a.date_from}-calls-report.html")
        shutil.copy(html_path, dest)
        print("copied html:", dest.resolve())
    print("HTML:", html_path.resolve())
    print("empty_transcripts:", stats["empty_u"])
    print("STATS:", json.dumps(stats, ensure_ascii=False))

if __name__ == "__main__":
    main()

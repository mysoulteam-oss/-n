# Newo.ai API integration

A small Python client for the [Newo.ai](https://newo.ai) Customer API, plus a
connection-test script for wiring your project up to Newo.

## What this connects to

| | |
|---|---|
| API host | `https://app.newo.ai` |
| Auth | API key (`x-api-key`) exchanged for a short-lived JWT bearer token |
| Docs | https://docs.newo.ai/ |

The auth flow is two steps (handled automatically by the client):

1. `POST /api/v1/auth/api-key/token` with an `x-api-key` header returns an
   `access_token` (valid ~15 min) and a `refresh_token`.
2. Every other call sends `Authorization: Bearer <access_token>`. The client
   refreshes the token transparently before it expires.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env and set NEWO_API_KEY (from the Newo platform: Account → API Keys)
```

`NEWO_API_KEY` can be provided either via a `.env` file or a real environment
variable. `.env` is git-ignored — the key is never committed.

## Connect / verify access

```bash
python scripts/connect.py
```

Expected output:

```
→ Connecting to https://app.newo.ai ...
✓ Connected to Newo project
    customer_id : 88f1a738-29db-44d1-8b17-46ba67c1e9d6
    source      : customer_api
    token valid : ~840s
```

## Using the client in code

```python
from newo import NewoClient

client = NewoClient.from_env()
client.connect()

# Get (or create) the user actor you converse as.
actor = client.get_or_create_user_actor(
    name="Alice",
    external_id="crm-42",
    integration_idn="webchat",     # your integration's identifying name
    connector_idn="my_webchat",    # your connector's identifying name
)

# Send a message and poll for the agent's reply (send is asynchronous).
client.send_message(actor["id"], "Hello from the API!")
replies = client.receive_messages(actor["id"])
```

`integration_idn` / `connector_idn` come from the integration you set up in the
[Newo Builder](https://builder.newo.ai). Any endpoint not wrapped explicitly is
reachable through `client.request(method, path, params=..., json=...)`.

### Implemented endpoints

| Method | Purpose | Newo endpoint |
|---|---|---|
| `connect()` / `obtain_token()` | Authenticate | `POST /api/v1/auth/api-key/token` |
| `refresh()` | Renew access token | `POST /api/v1/auth/refresh-token` |
| `get_or_create_user_actor()` | Resolve a user actor | `POST /api/v1/actors/user/get-or-create` |
| `list_agent_actors()` | List agent actors | `GET /api/v1/actors/agent` |
| `send_message()` | Send a message | `POST /api/v1/chat/user/{id}` |
| `receive_messages()` | Poll for replies | `GET /api/v1/chat/user/{id}` |
| `get_chat_history()` | Conversation history | `GET /api/v1/chat/user/{id}/history` |

## Client briefs (agent configuration)

Each client's intake brief is stored as structured configuration under
`config/<client>/`, ready to be transferred into the [Newo Builder](https://builder.newo.ai)
and consumed by this integration.

> **Note on scope.** The Newo *Customer API* used by this client is a runtime
> messaging API (auth, actors, chat, webhooks, sessions). It has **no endpoints
> for authoring an agent's persona, scripts, working hours or knowledge base** —
> that configuration is created in the Newo Builder. So a brief is captured here
> as the single source of truth and applied in Builder; the machine-readable
> parts (the call/webhook data contract) drive the code in `newo/`.

Current client: **ClickCredit** — Ukrainian online-lending outbound voice agent.

```
config/clickcredit/
  agent.yaml            structured agent config (persona, scripts, hours, data contract)
  knowledge_base.md     Active Knowledge Base content (products, FAQ, payments)
  newo-project.yaml     snapshot of the LIVE Newo project (webhooks, integrations)
  brief-clickcredit.md  full brief, verbatim
  brief-raw.csv         original form export
```

### Live project resources

The ClickCredit API key connects to a Newo project that already has a
**SuperAgent** configured. `config/clickcredit/newo-project.yaml` is a read-only
snapshot of it, discovered via the API:

- **`outbound_call_webhook`** (`https://hooks.newo.ai/…`, event `external_request`)
  — the incoming webhook that queues an automated **outbound call**. This is the
  mechanism behind the brief's "дзвінки будуть автоматизовані"; post the caller's
  phone plus the brief's call fields (ПІБ, дата народження, статус клієнта) to it.
- Outgoing webhooks `sa_send_hitl_report` and `sa_send_email` (agent → external).
- 21 available integrations, incl. `newo_voice`, `newo_sms`, `twilio_messenger`,
  `vapi`, `telegram`, `api`.

Inspect the live project from code:

```python
from newo import NewoClient

c = NewoClient.from_env(); c.connect()
c.list_incoming_webhooks()   # find outbound_call_webhook
c.list_webhooks()            # outgoing webhooks
c.list_integrations()        # available integrations

# Queue an outbound call (verify the payload schema in your Builder flow first):
# c.trigger_incoming_webhook("outbound_call_webhook_path_id", {
#     "phone": "+380...", "full_name": "...", "birth_date": "...", "status": "..."
# })
```

Load a brief in code:

```python
from newo import load_brief, pending_items

brief = load_brief("clickcredit")
print(brief["company"]["name"])                 # ClickCredit
print(brief["integration"]["outgoing_webhook_payload"])

# Fields the client still owes as a separate file ("інформація у файлі"):
for path in pending_items(brief):
    print("TODO:", path)
```

`pending_items()` lists every brief answer marked `pending_external_file: true`
(e.g. objection scripts, SMS templates) so nothing outstanding is forgotten.

## Project layout

```
newo/
  __init__.py     package exports
  config.py       env / .env configuration
  client.py       NewoClient + auth handling
  brief.py        load/validate client briefs from config/
scripts/
  connect.py      connection-test entry point
config/
  clickcredit/    ClickCredit agent brief + knowledge base
```

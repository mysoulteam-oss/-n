# newo.ai project export

Tooling to connect to a [newo.ai](https://newo.ai) project and export its
**sessions** and **attributes** via the platform API.

## Authentication

The API uses an API key (managed in the Newo platform under **Account → API Keys**)
which is exchanged for a short-lived (15 min) JWT access token:

```
POST https://app.newo.ai/api/v1/auth/api-key/token
     header: x-api-key: <your-api-key>
  -> { access_token, token_type, expires_in, refresh_token }
```

The `access_token` is then sent as `Authorization: Bearer <token>` on all
data requests.

> Note: the public docs list `https://api.newo.ai` as the base host, but that
> host only redirects; the working API base is `https://app.newo.ai`.

## Endpoints used

| Purpose             | Method & path                                   |
| ------------------- | ----------------------------------------------- |
| Get access token    | `POST /api/v1/auth/api-key/token`               |
| List sessions       | `GET  /api/v1/bff/sessions?page=&per=`          |
| Customer attributes | `GET  /api/v1/bff/customer/attributes`          |

## Usage

```bash
export NEWO_API_KEY=your-api-key-here   # never commit this
python3 export_newo.py --out export --per 100
```

Outputs:

- `export/sessions.json` — every session record (paginated through `metadata.total`)
- `export/customer_attributes.json` — all customer attributes grouped by section

## Security

- The API key is read only from the `NEWO_API_KEY` environment variable; it is
  never written to disk or logged.
- The `export/` directory is **git-ignored** because session records contain
  customer conversation data (PII) and the attribute values contain business
  configuration. Do not commit it to a shared/public repository.

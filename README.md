# nevo-project

A minimal project that connects to:

- the [Nevo AI](https://www.npmjs.com/package/nevo-ai) API (via the `nevo-ai` package), and
- a **SIP account (Zadarma)** for telephony (via the `sip` package).

All settings live in `config.js`, which reads secrets from a git-ignored `.env` file.

## Setup

1. Install dependencies:

   ```bash
   npm install
   ```

2. Provide your credentials. Copy the example env file and fill it in:

   ```bash
   cp .env.example .env
   # then edit .env
   ```

   The `.env` file is git-ignored, so nothing sensitive gets committed.

   `.env` keys:

   | Variable | Meaning |
   |----------|---------|
   | `NEVO_API_KEY` | Nevo AI API key |
   | `SIP_DOMAIN` | SIP server, e.g. `sip.zadarma.com` |
   | `SIP_USERNAME` | SIP login |
   | `SIP_PASSWORD` | SIP password |
   | `SIP_NUMBER` | Your phone number, e.g. `+380630207197` |
   | `SIP_EXPIRES` | (optional) registration lifetime, seconds |
   | `SIP_PORT` | (optional) local UDP port, default `5060` |

## Usage

### Nevo AI

Run with the default prompt (a connection check), or your own prompt:

```bash
npm start
node index.js "Tell me a joke."
```

### SIP (Zadarma)

Register the SIP account and keep it registered:

```bash
npm run sip
```

The client performs a digest-authenticated `REGISTER` to `SIP_DOMAIN` and
re-registers automatically before the registration expires. Press `Ctrl+C` to
de-register and exit.

> **Network note:** SIP uses outbound UDP (port 5060). It requires an
> environment that allows that traffic — it will not complete from a sandbox
> that only permits outbound HTTPS.

## Security note

Never commit real credentials. They belong only in the git-ignored `.env` file
or your environment. If a key or password is ever exposed, rotate it.

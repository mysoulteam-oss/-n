# nevo-project

A minimal client that connects to the [Nevo AI](https://www.npmjs.com/package/nevo-ai) API using the `nevo-ai` package.

## Setup

1. Install dependencies:

   ```bash
   npm install
   ```

2. Provide your API key. Copy the example env file and add your key:

   ```bash
   cp .env.example .env
   # then edit .env and set NEVO_API_KEY=...
   ```

   The `.env` file is git-ignored, so your key never gets committed. Alternatively,
   export it in your shell:

   ```bash
   export NEVO_API_KEY=your-key
   ```

## Usage

Run with the default prompt (a connection check):

```bash
npm start
```

Or pass your own prompt:

```bash
node index.js "Tell me a joke."
```

## Security note

Never commit your real API key. It belongs only in the git-ignored `.env` file
or your environment. If a key is ever exposed, rotate it.

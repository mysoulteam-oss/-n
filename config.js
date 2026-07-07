// Central project settings.
//
// All secrets (API keys, SIP password) are read from environment variables,
// loaded from a git-ignored .env file. Nothing sensitive is hard-coded here,
// so this file is safe to commit.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

// Minimal .env loader (no external dependency).
function loadDotEnv() {
  try {
    const raw = readFileSync(join(__dirname, ".env"), "utf8");
    for (const line of raw.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const eq = trimmed.indexOf("=");
      if (eq === -1) continue;
      const key = trimmed.slice(0, eq).trim();
      let value = trimmed.slice(eq + 1).trim();
      if (
        (value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'"))
      ) {
        value = value.slice(1, -1);
      }
      if (!(key in process.env)) process.env[key] = value;
    }
  } catch {
    // No .env file — rely on the real environment.
  }
}

loadDotEnv();

export const config = {
  nevo: {
    apiKey: process.env.NEVO_API_KEY || "",
  },

  // SIP / telephony account (Zadarma).
  sip: {
    domain: process.env.SIP_DOMAIN || "sip.zadarma.com",
    username: process.env.SIP_USERNAME || "",
    password: process.env.SIP_PASSWORD || "",
    number: process.env.SIP_NUMBER || "",
    // Registration lifetime in seconds; the client re-registers before it expires.
    expires: Number(process.env.SIP_EXPIRES || 300),
    // Local UDP port the SIP stack binds to.
    port: Number(process.env.SIP_PORT || 5060),
  },
};

export default config;

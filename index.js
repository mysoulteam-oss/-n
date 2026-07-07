// Minimal client that connects to the Nevo AI project.
//
// The API key is read from the NEVO_API_KEY environment variable so it never
// gets hard-coded into source control. Copy .env.example to .env and put your
// key there (the .env file is git-ignored), or export the variable in your shell.

import nevo from "nevo-ai";

// Load variables from a local .env file if present (no external dependency).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

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

const apiKey = process.env.NEVO_API_KEY;

if (!apiKey) {
  console.error(
    "Missing NEVO_API_KEY. Copy .env.example to .env and add your key, " +
      "or run: export NEVO_API_KEY=your-key"
  );
  process.exit(1);
}

// The prompt can be passed on the command line, otherwise a default is used.
const prompt = process.argv.slice(2).join(" ") || "Say hello and confirm the connection works.";

console.log(`Connecting to Nevo AI...`);
console.log(`Prompt: ${prompt}\n`);

nevo
  .ask({ apiKey, prompt })
  .then((response) => {
    console.log("Response:");
    console.log(response);
  })
  .catch((error) => {
    console.error("Nevo AI request failed:", error?.message || error);
    process.exit(1);
  });

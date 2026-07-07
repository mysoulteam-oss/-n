// Minimal client that connects to the Nevo AI project.
//
// The API key is read from the NEVO_API_KEY environment variable so it never
// gets hard-coded into source control. Copy .env.example to .env and put your
// key there (the .env file is git-ignored), or export the variable in your shell.

import nevo from "nevo-ai";

import { config } from "./config.js";

const apiKey = config.nevo.apiKey;

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

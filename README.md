# Newo project export

Attributes and scenarios (flows/skills) exported from the [Newo.ai](https://newo.ai) platform
using the official Newo CLI.

## Contents

- `newo_customers/default/attributes.yaml` — project **attributes**
- `newo_customers/default/projects/flows.yaml` — **scenarios** (agents → flows → skills index)
- `newo_customers/default/projects/<project>/<Agent>/<Flow>/<Skill>/` — skill source
  (`*.guidance` / `*.jinja`) plus `metadata.yaml`

## Re-exporting / pushing changes

1. Install the CLI: `npm install -g newo@latest`
2. Copy `.env.example` to `.env` and set your `NEWO_API_KEY`
3. Download: `newo pull`
4. Inspect local changes: `newo status`
5. Upload changes back: `newo push`

> `.env` (API key) and `.newo/` (cached JWT tokens / id-maps) are git-ignored — never commit them.

# usajobs-cli

CLI for searching **US federal government job postings** via the official USAJOBS Search API.

**Data source**: `data.usajobs.gov/api/search`.
**Authentication**: Required — free registered API key + the email you registered with.
**Dependencies**: None (plain `bun` + `fetch`). `bun install` is optional and only pulls dev type defs.

> **⚠️ Not yet live-verified.** This CLI was built from USAJOBS's published API
> documentation (developer.usajobs.gov), but every request — including a first
> smoke test — requires real credentials, which weren't available during
> scaffolding. The field paths in `src/helpers.ts` match the documented/standard
> response shape but have not been confirmed against an actual live response.
> **Run the live test below once you have an API key**, and fix any field-path
> mismatches in `helpers.ts` if something comes back `null` unexpectedly.

## Registration (required before first use)

1. Go to <https://developer.usajobs.gov> and submit an API request (free) with your email and an app name.
2. You'll receive an API key. Export both values in your shell (never pass them as CLI flags — that leaks into shell history):
   ```bash
   export USAJOBS_API_KEY="your-key-here"
   export USAJOBS_EMAIL="the-email-you-registered-with@example.com"
   ```

## Installation

```bash
cd .agents/skills/usajobs-search/cli
bun install   # optional — only installs TypeScript dev types
```

## Live verification (do this once you have credentials)

```bash
bun run typecheck
bun run src/cli.ts search -q "software engineer" --limit 5 --format table
bun run test   # live smoke tests run automatically once USAJOBS_API_KEY/USAJOBS_EMAIL are set
```

If `search` returns real titles/companies/locations and `detail` returns readable text, this skill is verified — otherwise report back what came back `null`/garbled so the field paths in `helpers.ts` can be corrected.

## Commands

| Command | Description |
|---------|-------------|
| `search` | Search federal job postings by keyword/location |
| `detail` | Fetch full detail for a single job listing |

`search` accepts `--format json|table|plain` (default `json`); `detail` accepts `--format json|plain`.
All errors are written to **stderr** as `{ "error": "...", "code": "..." }` with exit code `1`.

## Quick examples

```bash
# Electronics engineer roles, last 30 days
bun run src/cli.ts search -q "electronics engineer" --jobage 30 --format table

# Software engineer roles near DC, 50-mile radius
bun run src/cli.ts search -q "software engineer" -l "Washington, DC" --radius 50 --format table

# Full detail for one job
bun run src/cli.ts detail 797030800 --format plain
```

See `../SKILL.md` for the full flag reference.

## Search flags

| Flag | Alias | Description |
|------|-------|-------------|
| `--query` | `-q` | Keyword search (title, skill, agency). |
| `--location` | `-l` | City, state, or military installation. |
| `--radius` | | Expand location search by N miles (requires `--location`). |
| `--jobage` | | Posted within N days, 0-60 (USAJOBS's max window). |
| `--page` | | 1-indexed page (25 results/page). |
| `--limit` | `-n` | Cap results emitted. |
| `--format` | | `json` \| `table` \| `plain`. |

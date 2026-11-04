---
name: usajobs-search
version: 1.0.0
description: >
  Use this skill to search US federal government job postings via the official
  USAJOBS Search API (data.usajobs.gov). Covers agencies, national labs,
  defense contractors' government-side postings, and similar. Requires a free
  registered API key. Trigger phrases: federal jobs, government jobs,
  USAJOBS, GS positions, federal government careers, national lab jobs.
context: fork
allowed-tools: Bash(bun run .agents/skills/usajobs-search/cli/src/cli.ts *)
---

# USAJOBS Search Skill

Search live US federal job postings via the official **USAJOBS Search API**. Requires
free registered credentials (no anonymous access), and has **zero runtime dependencies**
beyond `bun`.

> ⚠️ **Not yet live-verified.** This skill was scaffolded from USAJOBS's published API
> docs, but could not be tested with a real request during setup (the API requires
> credentials for every call, including a first smoke test). See `cli/README.md` for the
> one-time verification steps to run once an API key is registered. Until that
> verification has run, treat `search`/`detail` output with a bit of skepticism and
> double-check a result or two against usajobs.gov directly.

## Access

This is an official, documented, registration-required developer API — not scraped HTML.
`developer.usajobs.gov` (the docs/registration host) has a permissive `robots.txt`; the
API host itself (`data.usajobs.gov`) has a blanket disallow, which is almost certainly
there to keep raw JSON API responses out of search-engine indexes rather than to block
the registered/authenticated use the API exists for. No personal-use warning beyond
normal rate-limit courtesy and keeping your API key out of shell history (set it via
environment variables, never a CLI flag).

## Setup (required before first use)

1. Register for a free API key at <https://developer.usajobs.gov> (email + app name).
2. Export credentials as environment variables:
   ```bash
   export USAJOBS_API_KEY="your-key-here"
   export USAJOBS_EMAIL="the-email-you-registered-with@example.com"
   ```

## When to use this skill

- Search federal agency, national lab, or defense-adjacent openings by keyword
- A strong complement to general boards for embedded systems / hardware / firmware
  backgrounds — agencies like NASA, DoD components, and national labs post on USAJOBS
  and don't show up as prominently on LinkedIn/Indeed
- Get the full description of a specific federal job listing

## Commands

### Search job listings

```bash
bun run .agents/skills/usajobs-search/cli/src/cli.ts search [flags]
```

Key flags:
- `--query <text>` / `-q <text>` — keyword search (title, skill, agency). Recommended.
- `--location <text>` / `-l <text>` — city, state, or military installation.
- `--radius <miles>` — expand location search by N miles (requires `--location`).
- `--jobage <days>` — posted within N days, 0-60 (USAJOBS's max window). Omit for all postings.
- `--page <n>` — page number (1-indexed, 25 results per page).
- `--limit <n>` / `-n <n>` — cap total results emitted (client-side).
- `--format json|table|plain` — default `json`.

### Fetch full job detail

```bash
bun run .agents/skills/usajobs-search/cli/src/cli.ts detail <id|url> [--format json|plain]
```

`id` is the job id (`MatchedObjectId`/`PositionID`) from `search` results. You may also
pass a full `usajobs.gov/job/<id>` URL.

## Usage examples

```bash
# Electronics engineer roles, last 30 days
bun run .agents/skills/usajobs-search/cli/src/cli.ts search -q "electronics engineer" --jobage 30 --format table

# Software engineer roles near Washington, DC
bun run .agents/skills/usajobs-search/cli/src/cli.ts search -q "software engineer" -l "Washington, DC" --radius 50 --format table

# Full detail for a specific job
bun run .agents/skills/usajobs-search/cli/src/cli.ts detail 797030800 --format plain
```

## Output formats

| Format | Best for |
|--------|----------|
| `json` | Default — programmatic use, passing IDs to `detail` |
| `table` | Quick human-readable scanning |
| `plain` | Reading a single job's full detail (`detail` command) |

All errors are written to **stderr** as `{ "error": "...", "code": "..." }` and the process exits with code `1`.

## Notes

- Requires `USAJOBS_API_KEY` and `USAJOBS_EMAIL` environment variables — the CLI exits
  with `NO_CREDENTIALS` if either is missing.
- Federal roles are almost always full-time/permanent by default (matches the candidate's
  full-time-only search preference), though internship-equivalent "Pathways" postings
  exist — check `PositionOfferingType` in results if that distinction matters.
- USAJOBS has no single-job-by-id endpoint; `detail` re-queries `search` filtered to one
  `PositionID` with `Fields=Full`.
- `--jobage` caps at 60 days (USAJOBS's own limit), unlike other portal skills here.

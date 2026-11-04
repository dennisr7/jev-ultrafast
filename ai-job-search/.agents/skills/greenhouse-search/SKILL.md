---
name: greenhouse-search
version: 1.0.0
description: >
  Use this skill to search job postings on Greenhouse-hosted company job boards
  (boards-api.greenhouse.io) - one company at a time, via Greenhouse's public
  Job Board API. Many tech, hardware, and AI companies (e.g. Anthropic, Scale AI,
  Databricks) post directly on Greenhouse. Trigger phrases: greenhouse jobs,
  company job board, search <company>'s openings, greenhouse.io jobs, check
  <company> careers page.
context: fork
allowed-tools: Bash(bun run .agents/skills/greenhouse-search/cli/src/cli.ts *)
---

# Greenhouse Job Board Search Skill

Search live job listings on individual companies' Greenhouse-hosted job boards, via
Greenhouse's public **Job Board API**. No authentication, no API key, and **zero runtime
dependencies** — it runs with just `bun`.

> Greenhouse does not offer a single cross-company search — there is no "search every
> company on Greenhouse" endpoint. Every call targets **one company token** (the slug in
> that company's job-board URL, e.g. `anthropic` for `job-boards.greenhouse.io/anthropic`).
> To cover several companies, call `search` once per company token.

## Access

This is a public, documented API that Greenhouse provides specifically so companies can
embed their job listings elsewhere — `robots.txt` only disallows `/embed/`, not the API
paths this skill uses. No personal-use warning is needed beyond normal rate-limit courtesy.

## When to use this skill

- Search a specific company's open roles by keyword, once you know (or suspect) they use Greenhouse
- Get the full description of a specific job listing
- Check a curated list of company tokens for hardware/embedded/agentic-AI-relevant openings (see Notes)

## Commands

### Search a company's job board

```bash
bun run .agents/skills/greenhouse-search/cli/src/cli.ts search --company <token> [flags]
```

Key flags:
- `--company <token>` / `-c <token>` — **required.** The company's Greenhouse slug, e.g. `anthropic`, `databricks`, `scaleai`.
- `--query <text>` / `-q <text>` — keyword filter on job title (all words must appear). Recommended.
- `--jobage <days>` — posted within N days (uses `first_published`). Omit for all postings.
- `--page <n>` — page number (1-indexed, 20 results per page).
- `--limit <n>` / `-n <n>` — cap total results emitted (client-side).
- `--format json|table|plain` — default `json`.

### Fetch full job detail

```bash
bun run .agents/skills/greenhouse-search/cli/src/cli.ts detail <id|url> [--company <token>] [--format json|plain]
```

Pass either a bare job `id` plus `--company <token>`, or a full job-board URL (e.g.
`https://job-boards.greenhouse.io/anthropic/jobs/5421031008`) — the company token and id
are parsed from the URL automatically.

## Usage examples

```bash
# Software engineer roles at Anthropic, last 30 days
bun run .agents/skills/greenhouse-search/cli/src/cli.ts search -c anthropic -q "software engineer" --jobage 30 --format table

# ML roles at Databricks
bun run .agents/skills/greenhouse-search/cli/src/cli.ts search -c databricks -q "machine learning" --format table

# All openings at Scale AI
bun run .agents/skills/greenhouse-search/cli/src/cli.ts search -c scaleai --format table

# Full detail by id + company
bun run .agents/skills/greenhouse-search/cli/src/cli.ts detail 5421031008 -c anthropic --format plain

# Full detail by URL
bun run .agents/skills/greenhouse-search/cli/src/cli.ts detail https://job-boards.greenhouse.io/anthropic/jobs/5421031008 --format plain
```

## Output formats

| Format | Best for |
|--------|----------|
| `json` | Default — programmatic use, passing IDs to `detail` |
| `table` | Quick human-readable scanning |
| `plain` | Reading a single job's full detail (`detail` command) |

All errors are written to **stderr** as `{ "error": "...", "code": "..." }` and the process exits with code `1`.

## Notes

- Not every company uses Greenhouse, and a 404 means that exact token has no public board —
  this is normal, not a bug (they may use a different ATS like Lever or Ashby, or a private board).
- Data is from Greenhouse's public Job Board API — no credentials required.
- Page size is fixed at 20 results per page (chosen by this CLI; Greenhouse itself returns
  a company's full job list in one response, filtered/paginated client-side).
- `--jobage` filtering uses `first_published`; undated postings are kept rather than dropped.
- Known company tokens confirmed live during setup (2026-09-22): `anthropic` (619 jobs),
  `scaleai`, `databricks`. `anduril`, `openai`, and `skydio` were tried and returned 404 on
  that exact token — they may use a different token, a different ATS, or a private board;
  don't assume 404 means "doesn't hire," verify via the company's careers page footer.

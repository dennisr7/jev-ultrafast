# greenhouse-cli

CLI for searching jobs on **Greenhouse-hosted company job boards**, one company at a time,
via Greenhouse's public Job Board API.

**Data source**: `boards-api.greenhouse.io/v1/boards/<company>/jobs` (and `/jobs/<id>` for detail).
**Authentication**: None required.
**Dependencies**: None (plain `bun` + `fetch`). `bun install` is optional and only pulls dev type defs.

> Greenhouse has no cross-company search — every call is scoped to one `--company` token
> (the slug in that company's job-board URL, e.g. `anthropic` for
> `job-boards.greenhouse.io/anthropic`). This is a public API Greenhouse provides for
> embedding job boards elsewhere; `robots.txt` only disallows `/embed/`, not this API.

## Installation

```bash
cd .agents/skills/greenhouse-search/cli
bun install   # optional — only installs TypeScript dev types
```

The CLI runs without any install because it has zero runtime dependencies.

## Commands

| Command | Description |
|---------|-------------|
| `search` | Search one company's job board (`--company` required) |
| `detail` | Fetch full detail for a single job listing |

`search` accepts `--format json|table|plain` (default `json`); `detail` accepts `--format json|plain`.
All errors are written to **stderr** as `{ "error": "...", "code": "..." }` with exit code `1`.

## Quick examples

```bash
# Software engineer roles at Anthropic, last 30 days
bun run src/cli.ts search -c anthropic -q "software engineer" --jobage 30 --format table

# Machine learning roles at Databricks
bun run src/cli.ts search -c databricks -q "machine learning" --format table

# Full detail by id + company
bun run src/cli.ts detail 5421031008 -c anthropic --format plain

# Full detail by URL (company token parsed automatically)
bun run src/cli.ts detail https://job-boards.greenhouse.io/anthropic/jobs/5421031008 --format plain
```

See `../SKILL.md` for the full flag reference and known company tokens.

## Search flags

| Flag | Alias | Description |
|------|-------|-------------|
| `--company` | `-c` | **Required.** Greenhouse company token, e.g. `anthropic`, `databricks`, `scaleai`. |
| `--query` | `-q` | Keywords (job title). All words must appear in the title. Recommended. |
| `--jobage` | | Posted within N days (uses `first_published`). |
| `--page` | | 1-indexed page (20 results/page). |
| `--limit` | `-n` | Cap results emitted. |
| `--format` | | `json` \| `table` \| `plain`. |

## Notes

- A 404 on `search` means that company token has no public Greenhouse board — try the
  company's careers page footer to confirm they use Greenhouse before assuming it's a bug.
- Greenhouse returns a company's full job list in one response (no server-side pagination);
  this CLI filters by `--query`/`--jobage` and paginates client-side at 20/page.

# workday-cli

CLI for searching jobs on a company's **Workday-hosted career site**
(`<tenant>.<wdN>.myworkdayjobs.com/<site>`).

**Data source**: Workday's CXS (candidate experience) job-search API — the same one the rendered career-site page itself calls.
**Authentication**: None required, for companies that expose it this way.
**Dependencies**: None (plain `bun` + `fetch`). `bun install` is optional and only pulls dev type defs.

> Only works for companies that expose Workday **directly** via a public
> `myworkdayjobs.com` URL. Some companies (Apple, notably) run Workday fully
> server-side behind a custom front-end with no discoverable client-side API —
> this tool can't reach those. See `../SKILL.md` for how to tell the difference.

## Installation

```bash
cd .agents/skills/workday-search/cli
bun install   # optional — only installs TypeScript dev types
```

## Commands

| Command | Description |
|---------|-------------|
| `search` | Search a company's Workday job board (`--tenant`, `--instance`, `--site` all required) |
| `detail` | Fetch full detail for a single job listing |

`search` accepts `--format json|table|plain` (default `json`); `detail` accepts `--format json|plain`.
All errors are written to **stderr** as `{ "error": "...", "code": "..." }` with exit code `1`.

## Quick examples

```bash
# Software engineer roles at GE Vernova
bun run src/cli.ts search -t gevernova -i wd5 -s Vernova_ExternalSite -q "software engineer" --company-name "GE Vernova" --format table

# Systems engineer roles at Boeing
bun run src/cli.ts search -t boeing -i wd1 -s EXTERNAL_CAREERS -q "systems engineer" --company-name Boeing --format table

# Full detail by URL (coordinates parsed automatically)
bun run src/cli.ts detail "https://gevernova.wd5.myworkdayjobs.com/Vernova_ExternalSite/job/2-Locations/Field-Service-Technician-1_R5049908-2" --format plain
```

See `../SKILL.md` for the full flag reference and how to find a company's tenant/instance/site.

## Search flags

| Flag | Alias | Description |
|------|-------|-------------|
| `--tenant` | `-t` | **Required.** Workday tenant slug, e.g. `boeing`. |
| `--instance` | `-i` | **Required.** Workday instance, e.g. `wd1`, `wd5`. |
| `--site` | `-s` | **Required.** Career site name, e.g. `EXTERNAL_CAREERS`. |
| `--company-name` | | Display name for output (defaults to `--tenant`). |
| `--query` | `-q` | Server-side full-text search (fuzzy, not exact-match — expect some noise). |
| `--page` | | 1-indexed page. Workday itself caps results at **20 per page**. |
| `--limit` | `-n` | Cap results emitted. |
| `--format` | | `json` \| `table` \| `plain`. |

## Notes

- **No bulk description fetch.** Unlike Greenhouse's `?content=true`, Workday's
  list endpoint never includes job descriptions — every `detail` call is a
  separate request. Scope searches with `--query` rather than paging through
  everything.
- **Detail needs the full path, not a bare id.** The `id` field in search
  results is a shortened display id (Workday's requisition number); pass the
  `url` a search result gave you to `detail`, not the bare id alone.
- A tenant that doesn't exist returns HTTP 422; a real tenant with a wrong
  site/instance returns 400 or 404 — both are mapped to `NOT_FOUND`.

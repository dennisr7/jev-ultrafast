---
name: workday-search
version: 1.0.0
description: >
  Use this skill to search job postings on a company's Workday-hosted career
  site (<tenant>.<wdN>.myworkdayjobs.com) - one company at a time, via
  Workday's public candidate-search API. Many large companies (Boeing, GE
  Vernova, and many others) expose this directly. Trigger phrases: workday
  jobs, company career site, search <company>'s openings on workday,
  myworkdayjobs.com.
context: fork
allowed-tools: Bash(bun run .agents/skills/workday-search/cli/src/cli.ts *)
---

# Workday Search Skill

Search live job listings on a company's Workday-hosted career site, via the
same public **CXS API** the rendered page itself calls. No authentication, no
API key, and **zero runtime dependencies** — it runs with just `bun`.

> Like Greenhouse, there's no cross-company search — every call needs one
> company's coordinates. Unlike Greenhouse, those coordinates are **three
> parts** (`--tenant`, `--instance`, `--site`), not one token, and the list
> endpoint doesn't include job descriptions (see Notes).

## Does this company even use Workday this way?

Not every Workday customer exposes it. Two different situations look similar
from the outside but aren't:

1. **Direct exposure** (this skill works): the company's careers link goes
   straight to (or embeds) a `<tenant>.<wdN>.myworkdayjobs.com/<site>` URL.
   Boeing and GE Vernova are both like this — confirmed live during setup
   (2026-09-22).
2. **Fully hidden** (this skill does NOT work): the company runs a custom
   front-end that talks to Workday server-side and never exposes a
   `myworkdayjobs.com` URL to the browser at all. **Apple is like this** —
   confirmed via browser network inspection (2026-09-22): `jobs.apple.com`
   returns fully server-rendered HTML with zero client-side API calls, and a
   direct guess at Workday's API returned `401 Unable to verify credentials
   for system account`. There is no workaround for this case with an API-based
   approach — it would need raw HTML scraping of the company's own site
   instead (a separate, per-company build, not this skill).

**To tell which one you're dealing with:** check the company's careers page
HTML/redirects for a `myworkdayjobs.com` reference (`curl -sL <careers-url> |
grep -io myworkdayjobs`), or WebSearch `site:myworkdayjobs.com "<company>"`.
If you find one, extract `tenant`/`instance`/`site` from the URL pattern
`https://<tenant>.<instance>.myworkdayjobs.com/<site>/...`. If you find
nothing, this skill doesn't apply to that company.

## Access

This is the same public API a job seeker's browser calls when they search the
company's own career site — no authentication for the companies that expose
it this way, and `robots.txt` on confirmed tenants explicitly `Allow`s the
career-site paths. No personal-use warning needed beyond normal rate-limit
courtesy.

## When to use this skill

- Search a specific company's open roles by keyword, once you've confirmed
  (per above) they expose Workday directly
- Get the full description of a specific job listing
- As the second-tier fallback in a multi-company sweep, after checking
  Greenhouse and before falling back to raw HTML scraping

## Commands

### Search a company's job board

```bash
bun run .agents/skills/workday-search/cli/src/cli.ts search --tenant <t> --instance <wdN> --site <s> [flags]
```

Key flags:
- `--tenant <name>` / `-t` — **required.** Workday tenant slug, e.g. `boeing`.
- `--instance <wdN>` / `-i` — **required.** e.g. `wd1`, `wd5`.
- `--site <name>` / `-s` — **required.** Career site name, e.g. `EXTERNAL_CAREERS`.
- `--company-name <text>` — display name for output (defaults to `--tenant`).
- `--query <text>` / `-q` — server-side full-text search (fuzzy, expect some noise in results — Workday's relevance ranking isn't a strict keyword filter).
- `--page <n>` — 1-indexed page. **Workday caps results at 20 per page** (a higher `limit` in the request itself returns HTTP 400).
- `--limit <n>` / `-n` — cap results emitted (client-side).
- `--format json|table|plain` — default `json`.

### Fetch full job detail

```bash
bun run .agents/skills/workday-search/cli/src/cli.ts detail <externalPath|url> [--tenant <t> --instance <wdN> --site <s>] [--format json|plain]
```

Pass the full job **URL** a search result gave you (coordinates are parsed
from it automatically), or a bare externalPath (starts with `/job/...`) plus
`--tenant`/`--instance`/`--site`. **A bare short id is not enough on its own**
— unlike Greenhouse/LinkedIn, Workday's routing needs the full path.

## Usage examples

```bash
# Software engineer roles at GE Vernova
bun run .agents/skills/workday-search/cli/src/cli.ts search -t gevernova -i wd5 -s Vernova_ExternalSite -q "software engineer" --company-name "GE Vernova" --format table

# Systems engineer roles at Boeing
bun run .agents/skills/workday-search/cli/src/cli.ts search -t boeing -i wd1 -s EXTERNAL_CAREERS -q "systems engineer" --company-name Boeing --format table

# Full detail by URL
bun run .agents/skills/workday-search/cli/src/cli.ts detail "https://gevernova.wd5.myworkdayjobs.com/Vernova_ExternalSite/job/2-Locations/Field-Service-Technician-1_R5049908-2" --format plain
```

## Output formats

| Format | Best for |
|--------|----------|
| `json` | Default — programmatic use |
| `table` | Quick human-readable scanning |
| `plain` | Reading a single job's full detail (`detail` command) |

All errors are written to **stderr** as `{ "error": "...", "code": "..." }` and the process exits with code `1`.

## Notes

- **No bulk description fetch, unlike Greenhouse.** The list endpoint returns
  title/location/postedOn/externalPath only — never the description. Getting
  a job's full text always costs one extra `detail` call. This matters a lot
  at scale: scope searches with `--query` per role-category rather than
  paging through a company's entire board (some Workday boards run into the
  thousands, same as Greenhouse's largest).
- A tenant that plain doesn't exist returns HTTP 422; a real tenant with the
  wrong site/instance returns 400 or 404 — both mapped to `NOT_FOUND`.
- `postedOn` in search results is a relative string ("Posted 3 Days Ago",
  "Posted 30+ Days Ago") — `detail` returns an exact `startDate` (ISO format)
  instead, which is more useful for date filtering.

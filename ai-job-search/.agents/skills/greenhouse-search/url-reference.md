# Greenhouse Job Board API Reference

Public, unauthenticated per-company Job Board API. No cross-company search exists — every
endpoint is scoped to one `--company` token.

> `robots.txt` at `boards-api.greenhouse.io` only disallows `/embed/`. The paths below are
> not disallowed — this is a public API Greenhouse provides for embedding job boards.

## List a company's jobs

```
GET https://boards-api.greenhouse.io/v1/boards/<company>/jobs
```

Returns `{ "jobs": [...], "meta": {...} }` — **all** of that company's open jobs in one
response (no pagination params). Each job object:

| Field | Meaning |
|-------|---------|
| `id` | Numeric job id |
| `title` | Job title |
| `company_name` | Company display name |
| `location.name` | Location string (may combine multiple offices, e.g. `"San Francisco, CA \| Seattle, WA"`) |
| `absolute_url` | Public posting URL (`job-boards.greenhouse.io/<company>/jobs/<id>`) |
| `first_published` | ISO timestamp, first publish date |
| `updated_at` | ISO timestamp, last update |

A 404 means that company token has no public Greenhouse board.

Optional `?content=true` includes the full job `content` (HTML-entity-escaped description)
for every job in the list response — not used by this CLI's `search` (keeps responses
light; `detail` fetches description on demand for one job at a time).

## Single job detail

```
GET https://boards-api.greenhouse.io/v1/boards/<company>/jobs/<id>
```

Same fields as above, plus `content` — the full job description as **HTML-entity-escaped
HTML** (e.g. the JSON string literally contains `&lt;div&gt;...&lt;/div&gt;`, not raw
`<div>`). The CLI decodes entities, converts block-level closing tags and `<br>` to
newlines, strips remaining tags, then decodes entities again for anything that was inside
the markup.

## Notes

- No authentication, no API key.
- Verified live (2026-09-22) against `anthropic` (619 jobs), `scaleai`, and `databricks`.
- `anduril`, `openai`, `skydio` returned 404 on this exact token — either a different
  token, a different ATS (e.g. Ashby, Lever), or no public board. Don't assume 404 means
  "company doesn't hire" — verify the token by checking the company's careers page footer
  for a Greenhouse link before concluding they're not on Greenhouse.
- If a company's markup or field names change, this file is the place to update the
  parsing notes above.

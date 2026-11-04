# Workday CXS API Reference

Public (for companies that expose it directly), unauthenticated per-company job
search API used by every Workday-hosted career site. No cross-company search —
every endpoint is scoped to one `--tenant`/`--instance`/`--site` combination.

> Confirmed live and `robots.txt`-permitted (2026-09-22) for `gevernova` (wd5,
> `Vernova_ExternalSite`) and `boeing` (wd1, `EXTERNAL_CAREERS`). Apple does
> **not** expose this at all — see SKILL.md's "Does this company even use
> Workday this way?" section.

## Finding a company's coordinates

A company's Workday-hosted career URL looks like:

```
https://<tenant>.<instance>.myworkdayjobs.com/<site>/...
```

e.g. `https://gevernova.wd5.myworkdayjobs.com/Vernova_ExternalSite/job/...`
gives `tenant=gevernova`, `instance=wd5`, `site=Vernova_ExternalSite`.

Find it via the company's own careers page (`curl -sL <careers-url> | grep -io
myworkdayjobs`) or `WebSearch site:myworkdayjobs.com "<company>"`.

## Search

```
POST https://<tenant>.<instance>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs
Content-Type: application/json

{"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "software engineer"}
```

- `limit`: **max 20** — anything higher returns `HTTP 400`.
- `offset`: pagination, increments of `limit`.
- `searchText`: server-side full-text search. Fuzzy/relevance-based, not an
  exact keyword filter — expect some tangentially-related results.
- `appliedFacets`: structured filters (e.g. `timeType`, `workerSubType`) —
  discoverable from the `facets` array in a response; not used by this CLI's
  default flags, but available for a future `--facet` flag if needed.

Response:

```json
{
  "total": 2185,
  "jobPostings": [
    {
      "title": "Senior O&M Station Manager",
      "externalPath": "/job/Noida/Senior-O-M-Station-Manager_R5051412-2",
      "locationsText": "Noida",
      "postedOn": "Posted Yesterday",
      "bulletFields": ["R5051412"]
    }
  ],
  "facets": [ ... ]
}
```

**No job description in this response** — that's the key asymmetry vs
Greenhouse. Every job needs a separate `detail` call for its text.

## Detail

```
GET https://<tenant>.<instance>.myworkdayjobs.com/wday/cxs/<tenant>/<site><externalPath>
```

(Just append the job's `externalPath` from a search result to the same base
URL used for search — no separate host or auth.)

```json
{
  "jobPostingInfo": {
    "id": "4d2a26e7680c10016006d8240d5c0001",
    "title": "Test Technician - 1st Shift",
    "jobDescription": "<h1>...</h1>...",
    "location": "Charleroi USA",
    "postedOn": "Posted 6 Days Ago",
    "startDate": "2026-09-16",
    "jobReqId": "R5053263"
  }
}
```

`jobDescription` is plain HTML (not double-escaped the way Greenhouse's
`content` field is) — decode standard entities and strip tags.

## Notes

- No authentication for tenants that expose this publicly.
- A nonexistent tenant returns `HTTP 422`; a real tenant with wrong
  site/instance returns `400` or `404`.
- `robots.txt` at a confirmed tenant (`https://<tenant>.<instance>.myworkdayjobs.com/robots.txt`)
  explicitly `Allow`s each configured career-site path and lists a sitemap —
  this is a public-facing feature, not an incidental exposure.
- Page size is hard-capped at 20 by the API itself, unlike Greenhouse (which
  returns everything in one call) or this CLI's own choices (which just pass
  the cap through).

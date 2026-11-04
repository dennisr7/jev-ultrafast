# USAJOBS Search API Reference

Official, registration-required developer API. Documented at
<https://developer.usajobs.gov>.

> ⚠️ **Field paths below are from published documentation, not a verified live
> response** — no live request could be made during scaffolding (the API requires
> credentials for every call). Confirm against a real response once credentials exist,
> and correct this file + `cli/src/helpers.ts` if anything doesn't match.

## Authentication

Every request requires three headers:

| Header | Value |
|--------|-------|
| `Host` | `data.usajobs.gov` (fixed) |
| `User-Agent` | The email address used when registering for the API key |
| `Authorization-Key` | Your registered API key |

Register at <https://developer.usajobs.gov> (API Request page) — free, requires email + app name.

## Search

```
GET https://data.usajobs.gov/api/search
```

Query params used by this CLI:

| Param | Meaning | Example |
|-------|---------|---------|
| `Keyword` | Free-text query | `software engineer` |
| `LocationName` | City, state, or military installation | `Washington, DC` |
| `Radius` | Expand location search by miles (requires `LocationName`) | `50` |
| `DatePosted` | Posted within N days, **0-60 max** | `30` |
| `Page` | 1-indexed page number | `1` |
| `ResultsPerPage` | Results per page (up to 500; this CLI uses 25) | `25` |
| `Fields` | `Min` (search) or `Full` (detail — includes full description) | `Min` |

Other documented params not currently used by this CLI: `PositionTitle`, `JobCategoryCode`,
`Organization`, `RemunerationMinimumAmount`/`RemunerationMaximumAmount`, `PayGradeLow`/`PayGradeHigh`,
`PositionScheduleTypeCode`, `SecurityClearanceRequired`, `WhoMayApply`, `SortField`/`SortDirection`.

### Response shape (documented, unverified live)

```
{
  "SearchResult": {
    "SearchResultCount": <number returned>,
    "SearchResultCountAll": <total matches>,
    "SearchResultItems": [
      {
        "MatchedObjectId": "<id>",
        "MatchedObjectDescriptor": {
          "PositionID": "...",
          "PositionTitle": "...",
          "PositionURI": "https://www.usajobs.gov/job/...",
          "OrganizationName": "...",
          "DepartmentName": "...",
          "PositionLocationDisplay": "...",
          "PositionLocation": [{ "LocationName": "..." }],
          "PositionRemuneration": [{ "MinimumRange": "...", "MaximumRange": "...", "RateIntervalCode": "Per Year" }],
          "PositionOfferingType": [{ "Name": "Permanent" }],
          "PublicationStartDate": "...",
          "ApplicationCloseDate": "...",
          "UserArea": {
            "Details": {
              "JobSummary": "...",
              "MajorDuties": ["..."],
              "Requirements": "...",
              "Education": "...",
              "HowToApply": "..."
            }
          }
        }
      }
    ]
  }
}
```

## Detail

No dedicated single-job endpoint exists. `detail` re-queries `search` with `PositionID=<id>`,
`Fields=Full`, `ResultsPerPage=1`, and reads the one matching item's `UserArea.Details`.

## Notes

- No anonymous/sandbox mode — every call, including a first smoke test, needs real credentials.
- `DatePosted` caps at 60 days (unlike other portal skills here, which often support 30).
- `PositionOfferingType` (e.g. `"Permanent"` vs Pathways internship types) is captured in
  the raw type but not yet surfaced as a CLI flag — worth adding if the full-time-vs-internship
  distinction needs to be automated here specifically, rather than left to the evaluation
  framework in `04-job-evaluation.md`.

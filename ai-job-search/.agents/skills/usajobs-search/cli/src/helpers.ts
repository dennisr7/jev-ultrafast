// Data source: the official USAJOBS Search API (data.usajobs.gov/api/search).
// This is a registered, authenticated developer API - every request requires
// three headers: Host (fixed), User-Agent (your registered email), and
// Authorization-Key (your API key). Register for free at developer.usajobs.gov.
//
// IMPORTANT: this CLI was built against USAJOBS's published API documentation
// (developer.usajobs.gov) but could NOT be live-tested during scaffolding - the
// API requires real credentials for every call, including a first smoke test.
// The field paths below (MatchedObjectDescriptor, UserArea.Details, etc.) match
// the documented/standard USAJOBS response shape, but have not been verified
// against a live response. Run the live test in cli/README.md once you have an
// API key, and fix any field-path mismatches you find in helpers.ts.

export const BASE_URL = "https://data.usajobs.gov/api/search"

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

export interface Credentials {
  apiKey: string
  email: string
}

/** Read credentials from environment. Never accept these as CLI flags (avoids leaking them into shell history / process lists). */
export function readCredentials(): Credentials | null {
  const apiKey = process.env.USAJOBS_API_KEY
  const email = process.env.USAJOBS_EMAIL
  if (!apiKey || !email) return null
  return { apiKey, email }
}

/** Fetch JSON with exponential backoff on 429/5xx. Returns null on a 404. */
export async function jsonFetch<T>(url: string, creds: Credentials): Promise<T | null> {
  const maxRetries = 6
  let delay = 500
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const response = await fetch(url, {
      headers: {
        Host: "data.usajobs.gov",
        "User-Agent": creds.email,
        "Authorization-Key": creds.apiKey,
        Accept: "application/json",
      },
    })
    if (response.status === 429 || response.status >= 500) {
      if (attempt === maxRetries) {
        throw new Error(`Request failed: ${response.status} ${response.statusText}`)
      }
      const jitter = Math.floor(Math.random() * 500)
      await new Promise((r) => setTimeout(r, delay + jitter))
      delay = Math.min(delay * 2, 8000)
      continue
    }
    if (response.status === 404) return null
    if (response.status === 401 || response.status === 403) {
      throw new Error(
        `Authentication failed (${response.status}). Check USAJOBS_API_KEY and USAJOBS_EMAIL match your registration at developer.usajobs.gov.`,
      )
    }
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status} ${response.statusText}`)
    }
    return (await response.json()) as T
  }
  throw new Error("Request failed after max retries")
}

// --- Documented response shape (unverified live - see file header) ---

export interface RawLocation {
  LocationName?: string
}

export interface RawRemuneration {
  MinimumRange?: string
  MaximumRange?: string
  RateIntervalCode?: string
}

export interface RawDescriptor {
  PositionID?: string
  PositionTitle: string
  PositionURI: string
  OrganizationName?: string
  DepartmentName?: string
  PositionLocationDisplay?: string
  PositionLocation?: RawLocation[]
  PositionRemuneration?: RawRemuneration[]
  PositionOfferingType?: { Name?: string }[]
  PublicationStartDate?: string
  ApplicationCloseDate?: string
  UserArea?: {
    Details?: {
      JobSummary?: string
      MajorDuties?: string[]
      Requirements?: string
      Education?: string
      HowToApply?: string
    }
  }
}

export interface RawSearchItem {
  MatchedObjectId: string
  MatchedObjectDescriptor: RawDescriptor
}

export interface RawSearchResponse {
  SearchResult: {
    SearchResultCount: number
    SearchResultCountAll: number
    SearchResultItems: RawSearchItem[]
  }
}

export interface JobCard {
  id: string
  title: string
  company: string | null
  location: string | null
  date: string | null
  url: string
}

export interface JobDetail extends JobCard {
  description: string | null
}

export function toJobCard(item: RawSearchItem): JobCard {
  const d = item.MatchedObjectDescriptor
  const location =
    d.PositionLocationDisplay ??
    (d.PositionLocation && d.PositionLocation.length > 0
      ? d.PositionLocation.map((l) => l.LocationName).filter(Boolean).join(" | ")
      : null)
  return {
    id: item.MatchedObjectId,
    title: d.PositionTitle,
    company: d.OrganizationName ?? d.DepartmentName ?? null,
    location: location || null,
    date: d.PublicationStartDate ?? null,
    url: d.PositionURI,
  }
}

export function toJobDetail(item: RawSearchItem): JobDetail {
  const card = toJobCard(item)
  const details = item.MatchedObjectDescriptor.UserArea?.Details
  const parts: string[] = []
  if (details?.JobSummary) parts.push(details.JobSummary)
  if (details?.MajorDuties?.length) parts.push("Duties:\n" + details.MajorDuties.join("\n"))
  if (details?.Requirements) parts.push("Requirements:\n" + details.Requirements)
  if (details?.Education) parts.push("Education:\n" + details.Education)
  if (details?.HowToApply) parts.push("How to Apply:\n" + details.HowToApply)
  return { ...card, description: parts.length ? parts.join("\n\n") : null }
}

/** Parse a USAJOBS job id out of a usajobs.gov/job/<id> URL. */
export function parseJobUrl(url: string): string | null {
  const m = url.match(/usajobs\.gov\/job\/(\d+)/)
  return m ? m[1] : null
}

/** Convert a job-age in days (0-60 per USAJOBS docs) into the DatePosted param. */
export function jobageToDatePosted(days: number): string | null {
  if (!days || days <= 0 || days >= 9999) return null
  return String(Math.min(days, 60))
}

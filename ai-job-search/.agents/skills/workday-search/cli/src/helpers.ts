// Data source: Workday's CXS (candidate experience) job-search API, used by
// every company that hosts its careers site directly at
// <tenant>.<wdN>.myworkdayjobs.com/<site>. This is NOT a single fixed host
// like Greenhouse - every call needs three coordinates: --tenant, --instance
// (the "wdN" number), and --site (the career-site name, e.g. "EXTERNAL_CAREERS").
//
// IMPORTANT ASYMMETRY vs other portal skills here: Workday's list endpoint
// does NOT include job descriptions (no Greenhouse-style ?content=true
// shortcut) - only title/location/externalPath. Getting a job's full
// description always costs one extra `detail` call. Plan searches
// accordingly (narrow with --query rather than pulling everything).
//
// Some companies (e.g. Apple) run Workday entirely server-side behind a
// custom front-end and never expose a myworkdayjobs.com URL at all - this
// skill only works for the subset that DOES expose a direct URL.

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

const UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

export interface WorkdayCoords {
  tenant: string
  instance: string // e.g. "wd1", "wd5"
  site: string // e.g. "EXTERNAL_CAREERS", "Vernova_ExternalSite"
}

/** Base URL for the CXS API (job-data calls) - distinct from the public browser URL. */
export function cxsBase(c: WorkdayCoords): string {
  return `https://${c.tenant}.${c.instance}.myworkdayjobs.com/wday/cxs/${c.tenant}/${c.site}`
}

/** Base URL for human-facing job links (what you'd paste in a browser). */
export function publicBase(c: WorkdayCoords): string {
  return `https://${c.tenant}.${c.instance}.myworkdayjobs.com/${c.site}`
}

/** Fetch JSON with exponential backoff on 429/5xx. Returns null on a 404. */
export async function jsonFetch<T>(
  url: string,
  opts: { method?: "GET" | "POST"; body?: unknown } = {},
): Promise<T | null> {
  const maxRetries = 6
  let delay = 500
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const response = await fetch(url, {
      method: opts.method ?? "GET",
      headers: {
        "User-Agent": UA,
        Accept: "application/json",
        ...(opts.body ? { "Content-Type": "application/json" } : {}),
      },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
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
    if (response.status === 400) return null // bad site/instance for a real tenant
    if (response.status === 422) return null // tenant itself doesn't exist
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status} ${response.statusText}`)
    }
    return (await response.json()) as T
  }
  throw new Error("Request failed after max retries")
}

export interface RawJobPosting {
  title: string
  externalPath: string
  locationsText?: string
  postedOn?: string
  bulletFields?: string[]
}

export interface RawSearchResponse {
  total: number
  jobPostings: RawJobPosting[]
}

export interface RawJobDetail {
  jobPostingInfo: {
    id: string
    title: string
    jobDescription: string
    location?: string
    postedOn?: string
    startDate?: string
    jobReqId?: string
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

/** Workday's externalPath ends in "..._<reqId>[-n]" - use that as a short display id. Full externalPath is required for detail lookups, not this id alone. */
export function shortId(externalPath: string): string {
  const parts = externalPath.split("_")
  return parts.length > 1 ? parts[parts.length - 1] : externalPath
}

export function toJobCard(job: RawJobPosting, coords: WorkdayCoords, companyName: string): JobCard {
  return {
    id: shortId(job.externalPath),
    title: job.title,
    company: companyName,
    location: job.locationsText ?? null,
    date: job.postedOn ?? null,
    url: `${publicBase(coords)}${job.externalPath}`,
  }
}

const NAMED_ENTITIES: Record<string, string> = {
  nbsp: " ", mdash: "—", ndash: "–", hellip: "…",
  lsquo: "‘", rsquo: "’", ldquo: "“", rdquo: "”",
  amp: "&", lt: "<", gt: ">", quot: '"', apos: "'",
}

function decodeHtmlEntities(text: string): string {
  return text
    .replace(/&#(\d+);/g, (_, dec) => String.fromCodePoint(parseInt(dec, 10)))
    .replace(/&#[xX]([0-9a-fA-F]+);/g, (_, hex) => String.fromCodePoint(parseInt(hex, 16)))
    .replace(/&([a-zA-Z]+);/g, (m, name) => NAMED_ENTITIES[name] ?? m)
}

function stripTags(html: string): string {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim()
}

/** Workday's jobDescription is plain HTML (not double-escaped like Greenhouse's content field). */
export function cleanDescription(html: string): string {
  return decodeHtmlEntities(stripTags(html)).replace(/\n{3,}/g, "\n\n").trim()
}

/** Parse a full myworkdayjobs.com URL into its tenant/instance/site/externalPath parts. */
export function parseWorkdayUrl(
  url: string,
): { tenant: string; instance: string; site: string; externalPath: string } | null {
  const m = url.match(/https?:\/\/([^.]+)\.([^.]+)\.myworkdayjobs\.com\/([^/]+)(\/.*)?$/)
  if (!m) return null
  return { tenant: m[1], instance: m[2], site: m[3], externalPath: m[4] ?? "" }
}

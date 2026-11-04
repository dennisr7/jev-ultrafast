// Data source: Greenhouse's public Job Board API (boards-api.greenhouse.io).
// This is a per-company JSON API - Greenhouse itself doesn't offer a single
// cross-company search, so every call needs a --company token. The API is
// designed for embedding company job boards publicly, so no auth is required
// and robots.txt only disallows /embed/ (not the API paths used here).

export const BASE_URL = "https://boards-api.greenhouse.io/v1/boards"

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

const UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

/** Fetch JSON with exponential backoff on 429/5xx. Returns null on a 404. */
export async function jsonFetch<T>(url: string): Promise<T | null> {
  const maxRetries = 6
  let delay = 500
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const response = await fetch(url, {
      headers: {
        "User-Agent": UA,
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
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status} ${response.statusText}`)
    }
    return (await response.json()) as T
  }
  throw new Error("Request failed after max retries")
}

export interface RawJob {
  id: number
  title: string
  company_name: string
  location: { name: string | null } | null
  absolute_url: string
  first_published: string | null
  updated_at: string | null
  content?: string
}

export interface RawBoard {
  jobs: RawJob[]
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

/**
 * Convert a Unicode code point to a string. Uses `fromCodePoint` (not
 * `fromCharCode`) so supplementary-plane code points decode correctly, and
 * drops out-of-range values instead of throwing.
 */
function numericEntity(cp: number): string {
  return cp >= 0 && cp <= 0x10ffff ? String.fromCodePoint(cp) : ""
}

// Common named entities that show up in real job-description prose (dashes,
// curly quotes, ellipsis, symbols). Not exhaustive, but covers what Greenhouse
// content actually contains beyond the handful of markup-escaping entities.
const NAMED_ENTITIES: Record<string, string> = {
  nbsp: " ",
  mdash: "—",
  ndash: "–",
  hellip: "…",
  lsquo: "‘",
  rsquo: "’",
  ldquo: "“",
  rdquo: "”",
  trade: "™",
  copy: "©",
  reg: "®",
  deg: "°",
  times: "×",
  bull: "•",
}

function decodeHtmlEntities(text: string): string {
  return text
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, dec) => numericEntity(parseInt(dec, 10)))
    .replace(/&#[xX]([0-9a-fA-F]+);/g, (_, hex) => numericEntity(parseInt(hex, 16)))
    .replace(/&([a-zA-Z]+);/g, (m, name) => NAMED_ENTITIES[name] ?? m)
}

function stripTags(html: string): string {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim()
}

/**
 * Greenhouse's `content` field is double-encoded: the JSON string contains
 * HTML-entity-escaped HTML (e.g. `&lt;div&gt;`). Decode entities first to
 * reveal real tags, convert block breaks to newlines, strip tags, then
 * decode entities again for anything that was inside the markup.
 */
export function cleanContent(raw: string): string {
  const html = decodeHtmlEntities(raw)
  const withBreaks = html
    .replace(/<\s*br\s*\/?>/gi, "\n")
    .replace(/<\/(p|li|ul|ol|div|h\d)>/gi, "\n")
  return decodeHtmlEntities(stripTags(withBreaks)).replace(/\n{3,}/g, "\n\n").trim()
}

export function toJobCard(job: RawJob): JobCard {
  return {
    id: String(job.id),
    title: job.title,
    company: job.company_name ?? null,
    location: job.location?.name ?? null,
    date: job.first_published ?? job.updated_at ?? null,
    url: job.absolute_url,
  }
}

/** Case-insensitive: every whitespace-separated term in the query must appear in the title. */
export function matchesQuery(title: string, query: string | undefined): boolean {
  if (!query) return true
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean)
  const hay = title.toLowerCase()
  return terms.every((t) => hay.includes(t))
}

/** Keep undated postings rather than silently dropping them. */
export function withinJobAge(dateStr: string | null, days: number): boolean {
  if (!days || days >= 9999) return true
  if (!dateStr) return true
  const posted = new Date(dateStr).getTime()
  if (isNaN(posted)) return true
  const cutoff = Date.now() - days * 86400000
  return posted >= cutoff
}

/** Parse a Greenhouse company token + job id out of a job-board URL. */
export function parseJobUrl(url: string): { company: string; id: string } | null {
  const m = url.match(/(?:job-boards|boards)\.greenhouse\.io\/([^/]+)\/jobs\/(\d+)/)
  if (!m) return null
  return { company: m[1], id: m[2] }
}

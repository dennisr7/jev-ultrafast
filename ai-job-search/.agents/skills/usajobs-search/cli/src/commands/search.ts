import {
  BASE_URL,
  jsonFetch,
  readCredentials,
  toJobCard,
  jobageToDatePosted,
  writeError,
  type RawSearchResponse,
  type JobCard,
} from "../helpers.js"

export interface SearchOpts {
  query?: string
  location?: string
  radius?: number
  jobage: number
  page: number
  limit?: number
  format: "json" | "table" | "plain"
}

function buildUrl(opts: SearchOpts): string {
  const params = new URLSearchParams()
  if (opts.query) params.set("Keyword", opts.query)
  if (opts.location) params.set("LocationName", opts.location)
  if (opts.radius) params.set("Radius", String(opts.radius))
  const datePosted = jobageToDatePosted(opts.jobage)
  if (datePosted) params.set("DatePosted", datePosted)
  params.set("Page", String(opts.page))
  params.set("ResultsPerPage", "25")
  params.set("Fields", "Min")
  return `${BASE_URL}?${params.toString()}`
}

function renderTable(cards: JobCard[]): string {
  if (cards.length === 0) return "No results."
  const rows = cards.map((c) => {
    const title = (c.title || "").slice(0, 42).padEnd(42)
    const company = (c.company || "—").slice(0, 26).padEnd(26)
    const loc = (c.location || "—").slice(0, 24).padEnd(24)
    const date = (c.date || "—").slice(0, 10)
    return `${c.id.padEnd(11)} ${title} ${company} ${loc} ${date}`
  })
  const header =
    "ID".padEnd(11) +
    " " +
    "TITLE".padEnd(42) +
    " " +
    "COMPANY".padEnd(26) +
    " " +
    "LOCATION".padEnd(24) +
    " DATE"
  return [header, "-".repeat(header.length), ...rows].join("\n")
}

export async function runSearch(opts: SearchOpts): Promise<number> {
  const creds = readCredentials()
  if (!creds) {
    writeError(
      "USAJOBS_API_KEY and USAJOBS_EMAIL environment variables are required. Register for free at developer.usajobs.gov.",
      "NO_CREDENTIALS",
    )
    return 1
  }
  try {
    const data = await jsonFetch<RawSearchResponse>(buildUrl(opts), creds)
    if (!data) {
      writeError("No response from USAJOBS API", "NOT_FOUND")
      return 1
    }
    let cards = data.SearchResult.SearchResultItems.map(toJobCard)
    if (opts.limit !== undefined && opts.limit >= 0) cards = cards.slice(0, opts.limit)

    if (opts.format === "table") {
      process.stdout.write(renderTable(cards) + "\n")
    } else if (opts.format === "plain") {
      process.stdout.write(
        cards
          .map(
            (c) =>
              `${c.title}\n  ${c.company || "—"} · ${c.location || "—"} · ${c.date || "—"}\n  id: ${c.id}\n  ${c.url}`,
          )
          .join("\n\n") + "\n",
      )
    } else {
      process.stdout.write(
        JSON.stringify(
          {
            meta: {
              count: cards.length,
              page: opts.page,
              totalMatches: data.SearchResult.SearchResultCountAll,
            },
            results: cards,
          },
          null,
          2,
        ) + "\n",
      )
    }
    return 0
  } catch (e) {
    writeError(e instanceof Error ? e.message : String(e), "SEARCH_FAILED")
    return 1
  }
}

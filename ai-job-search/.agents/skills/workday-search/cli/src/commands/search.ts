import {
  cxsBase,
  jsonFetch,
  toJobCard,
  writeError,
  type WorkdayCoords,
  type RawSearchResponse,
  type JobCard,
} from "../helpers.js"

const PAGE_SIZE = 20 // Workday's CXS API rejects limit > 20 with HTTP 400

export interface SearchOpts extends WorkdayCoords {
  companyName: string
  query?: string
  page: number
  limit?: number
  format: "json" | "table" | "plain"
}

function renderTable(cards: JobCard[]): string {
  if (cards.length === 0) return "No results."
  const rows = cards.map((c) => {
    const title = (c.title || "").slice(0, 42).padEnd(42)
    const loc = (c.location || "—").slice(0, 24).padEnd(24)
    const date = (c.date || "—").slice(0, 20)
    return `${c.id.padEnd(14)} ${title} ${loc} ${date}`
  })
  const header = "ID".padEnd(14) + " " + "TITLE".padEnd(42) + " " + "LOCATION".padEnd(24) + " POSTED"
  return [header, "-".repeat(header.length), ...rows].join("\n")
}

export async function runSearch(opts: SearchOpts): Promise<number> {
  try {
    const offset = (opts.page - 1) * PAGE_SIZE
    const data = await jsonFetch<RawSearchResponse>(`${cxsBase(opts)}/jobs`, {
      method: "POST",
      body: { appliedFacets: {}, limit: PAGE_SIZE, offset, searchText: opts.query ?? "" },
    })
    if (!data) {
      writeError(
        `No response for tenant="${opts.tenant}" instance="${opts.instance}" site="${opts.site}" - check the coordinates`,
        "NOT_FOUND",
      )
      return 1
    }

    let cards = data.jobPostings.map((j) => toJobCard(j, opts, opts.companyName))
    if (opts.limit !== undefined && opts.limit >= 0) cards = cards.slice(0, opts.limit)

    if (opts.format === "table") {
      process.stdout.write(renderTable(cards) + "\n")
    } else if (opts.format === "plain") {
      process.stdout.write(
        cards
          .map((c) => `${c.title}\n  ${c.location || "—"} · ${c.date || "—"}\n  id: ${c.id}\n  ${c.url}`)
          .join("\n\n") + "\n",
      )
    } else {
      process.stdout.write(
        JSON.stringify({ meta: { count: cards.length, page: opts.page, totalMatches: data.total }, results: cards }, null, 2) + "\n",
      )
    }
    return 0
  } catch (e) {
    writeError(e instanceof Error ? e.message : String(e), "SEARCH_FAILED")
    return 1
  }
}

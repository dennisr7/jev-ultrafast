import {
  BASE_URL,
  jsonFetch,
  readCredentials,
  toJobDetail,
  parseJobUrl,
  writeError,
  type RawSearchResponse,
} from "../helpers.js"

export interface DetailOpts {
  id: string
  format: "json" | "plain"
}

export async function runDetail(opts: DetailOpts): Promise<number> {
  const creds = readCredentials()
  if (!creds) {
    writeError(
      "USAJOBS_API_KEY and USAJOBS_EMAIL environment variables are required. Register for free at developer.usajobs.gov.",
      "NO_CREDENTIALS",
    )
    return 1
  }

  const fromUrl = parseJobUrl(opts.id)
  const id = fromUrl ?? opts.id
  if (!/^\d+$/.test(id)) {
    writeError(`Could not parse a job ID from "${opts.id}"`, "BAD_ID")
    return 1
  }

  try {
    // USAJOBS has no single-job-by-id endpoint - re-query search, filtered to
    // this PositionID, with Fields=Full to get the complete description.
    const params = new URLSearchParams()
    params.set("PositionID", id)
    params.set("Fields", "Full")
    params.set("ResultsPerPage", "1")
    const data = await jsonFetch<RawSearchResponse>(`${BASE_URL}?${params.toString()}`, creds)
    const item = data?.SearchResult.SearchResultItems[0]
    if (!item) {
      writeError("Job not found", "NOT_FOUND")
      return 1
    }
    const detail = toJobDetail(item)

    if (opts.format === "plain") {
      const lines = [
        detail.title,
        `${detail.company || "—"} · ${detail.location || "—"}`,
        "",
        detail.description || "(no description)",
        "",
        `URL: ${detail.url}`,
      ]
      process.stdout.write(lines.join("\n") + "\n")
    } else {
      process.stdout.write(JSON.stringify(detail, null, 2) + "\n")
    }
    return 0
  } catch (e) {
    writeError(e instanceof Error ? e.message : String(e), "DETAIL_FAILED")
    return 1
  }
}

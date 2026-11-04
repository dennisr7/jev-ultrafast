import {
  BASE_URL,
  jsonFetch,
  cleanContent,
  parseJobUrl,
  writeError,
  type RawJob,
  type JobDetail,
} from "../helpers.js"

export interface DetailOpts {
  id: string
  company?: string
  format: "json" | "plain"
}

export async function runDetail(opts: DetailOpts): Promise<number> {
  let company = opts.company
  let id = opts.id

  const parsed = parseJobUrl(opts.id)
  if (parsed) {
    company = parsed.company
    id = parsed.id
  }

  if (!company) {
    writeError(
      "detail requires --company <token> when given a bare job id (or pass the full job-board URL instead)",
      "NO_COMPANY",
    )
    return 1
  }
  if (!/^\d+$/.test(id)) {
    writeError(`Could not parse a job ID from "${opts.id}"`, "BAD_ID")
    return 1
  }

  try {
    const job = await jsonFetch<RawJob>(`${BASE_URL}/${company}/jobs/${id}`)
    if (!job) {
      writeError("Job not found", "NOT_FOUND")
      return 1
    }
    const detail: JobDetail = {
      id: String(job.id),
      title: job.title,
      company: job.company_name ?? null,
      location: job.location?.name ?? null,
      date: job.first_published ?? job.updated_at ?? null,
      url: job.absolute_url,
      description: job.content ? cleanContent(job.content) : null,
    }

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

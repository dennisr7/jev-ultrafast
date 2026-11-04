import {
  cxsBase,
  jsonFetch,
  cleanDescription,
  parseWorkdayUrl,
  writeError,
  type WorkdayCoords,
  type RawJobDetail,
  type JobDetail,
} from "../helpers.js"

export interface DetailOpts extends Partial<WorkdayCoords> {
  idOrUrl: string
  companyName?: string
  format: "json" | "plain"
}

export async function runDetail(opts: DetailOpts): Promise<number> {
  let coords: WorkdayCoords
  let externalPath: string

  const parsed = parseWorkdayUrl(opts.idOrUrl)
  if (parsed) {
    coords = { tenant: parsed.tenant, instance: parsed.instance, site: parsed.site }
    externalPath = parsed.externalPath
  } else if (opts.idOrUrl.startsWith("/")) {
    if (!opts.tenant || !opts.instance || !opts.site) {
      writeError(
        "detail requires --tenant, --instance, and --site when given a bare externalPath (or pass the full job URL instead)",
        "NO_COORDS",
      )
      return 1
    }
    coords = { tenant: opts.tenant, instance: opts.instance, site: opts.site }
    externalPath = opts.idOrUrl
  } else {
    writeError(
      `"${opts.idOrUrl}" is not a full Workday job URL or an externalPath starting with "/". ` +
        "Workday's routing needs the full path (unlike a bare numeric id) - pass the url a search result gave you.",
      "BAD_ID",
    )
    return 1
  }

  try {
    const data = await jsonFetch<RawJobDetail>(`${cxsBase(coords)}${externalPath}`)
    if (!data) {
      writeError("Job not found", "NOT_FOUND")
      return 1
    }
    const info = data.jobPostingInfo
    const detail: JobDetail = {
      id: info.jobReqId ?? info.id,
      title: info.title,
      company: opts.companyName ?? coords.tenant,
      location: info.location ?? null,
      date: info.startDate ?? info.postedOn ?? null,
      url: `https://${coords.tenant}.${coords.instance}.myworkdayjobs.com/${coords.site}${externalPath}`,
      description: info.jobDescription ? cleanDescription(info.jobDescription) : null,
    }

    if (opts.format === "plain") {
      const lines = [
        detail.title,
        `${detail.company || "—"} · ${detail.location || "—"} · ${detail.date || "—"}`,
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

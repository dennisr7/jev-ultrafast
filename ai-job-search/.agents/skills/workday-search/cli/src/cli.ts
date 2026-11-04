#!/usr/bin/env bun
// Self-contained CLI for searching jobs on a company's Workday-hosted career
// site (<tenant>.<wdN>.myworkdayjobs.com/<site>). No external CLI framework,
// so it runs anywhere `bun` is available with zero install beyond the repo clone.
//
// Every call needs three coordinates identifying the company's Workday
// instance: --tenant, --instance (the "wdN" number), --site. Find these by
// locating the company's public myworkdayjobs.com career-site URL (e.g. via
// WebSearch for "<company> careers myworkdayjobs.com") and reading them off
// the URL: https://<tenant>.<instance>.myworkdayjobs.com/<site>/...
//
// Only works for companies that expose Workday directly this way. Some
// companies (e.g. Apple) run Workday fully server-side behind a custom
// front-end with no discoverable public URL - this tool can't reach those.

import { runSearch, type SearchOpts } from "./commands/search.js"
import { runDetail, type DetailOpts } from "./commands/detail.js"

interface Flags {
  _: string[]
  [k: string]: string | boolean | string[]
}

function parseFlags(argv: string[]): Flags {
  const flags: Flags = { _: [] }
  const alias: Record<string, string> = { q: "query", n: "limit", t: "tenant", i: "instance", s: "site" }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a.startsWith("--") || a.startsWith("-")) {
      const key = alias[a.replace(/^-+/, "")] ?? a.replace(/^-+/, "")
      const next = argv[i + 1]
      if (next === undefined || next.startsWith("-")) {
        flags[key] = true
      } else {
        flags[key] = next
        i++
      }
    } else {
      ;(flags._ as string[]).push(a)
    }
  }
  return flags
}

const HELP = `workday-cli — search jobs on a company's Workday career site

USAGE
  bun run src/cli.ts search --tenant <t> --instance <wdN> --site <s> [flags]
  bun run src/cli.ts detail <externalPath|url> [--tenant <t> --instance <wdN> --site <s>] [--format json|plain]

SEARCH FLAGS
  --tenant, -t <name>     Workday tenant slug, e.g. "boeing". REQUIRED.
  --instance, -i <wdN>    Workday instance, e.g. "wd1", "wd5". REQUIRED.
  --site, -s <name>       Career site name, e.g. "EXTERNAL_CAREERS". REQUIRED.
  --company-name <text>   Display name for output (defaults to --tenant).
  --query, -q <text>      Keyword search (server-side full-text, not exact-match).
  --page <n>              1-indexed page (20 results/page max - Workday's own limit). Default 1.
  --limit, -n <n>         Cap results emitted (client-side).
  --format <fmt>          json (default) | table | plain.

DETAIL
  <externalPath|url>      A full job URL (from search results), OR a bare
                           externalPath starting with "/" (requires --tenant/
                           --instance/--site too). A bare numeric id is NOT
                           enough on its own - Workday's routing needs the
                           full path, unlike Greenhouse or LinkedIn ids.

EXAMPLES
  bun run src/cli.ts search -t boeing -i wd1 -s EXTERNAL_CAREERS -q "software engineer" --format table
  bun run src/cli.ts search -t gevernova -i wd5 -s Vernova_ExternalSite -q "controls engineer" --company-name "GE Vernova" --format table
  bun run src/cli.ts detail "https://boeing.wd1.myworkdayjobs.com/EXTERNAL_CAREERS/job/USA---Saint-Charles-MO/Experienced-Systems-Engineer_JR2026525017-2" --format plain

No authentication required for a company's public Workday career site - this is
the standard candidate-facing search API, same one the rendered page itself calls.
`

async function main(): Promise<number> {
  const argv = process.argv.slice(2)
  const flags = parseFlags(argv)
  const cmd = (flags._ as string[])[0]

  if (!cmd || flags.help || flags.h) {
    process.stdout.write(HELP)
    return cmd ? 0 : 1
  }

  const need = (name: string): string | null => {
    const v = flags[name]
    return typeof v === "string" ? v : null
  }

  if (cmd === "search") {
    const tenant = need("tenant")
    const instance = need("instance")
    const site = need("site")
    if (!tenant || !instance || !site) {
      process.stderr.write(
        JSON.stringify({
          error: "--tenant, --instance, and --site are all required",
          code: "NO_COORDS",
        }) + "\n",
      )
      return 1
    }
    const fmt = (flags.format as string) || "json"

    const parseIntFlag = (name: string, raw: string | boolean | string[]): number | null => {
      const val = parseInt(raw as string, 10)
      if (isNaN(val)) {
        process.stderr.write(JSON.stringify({ error: `--${name} must be a number, got "${raw}"`, code: "BAD_ARG" }) + "\n")
        return null
      }
      return val
    }
    if (flags.page !== undefined) {
      const v = parseIntFlag("page", flags.page)
      if (v === null) return 1
      flags.page = String(v)
    }
    if (flags.limit !== undefined) {
      const v = parseIntFlag("limit", flags.limit)
      if (v === null) return 1
      flags.limit = String(v)
    }

    const opts: SearchOpts = {
      tenant,
      instance,
      site,
      companyName: need("company-name") ?? tenant,
      query: typeof flags.query === "string" ? flags.query : undefined,
      page: flags.page ? Math.max(1, parseInt(flags.page as string, 10)) : 1,
      limit: flags.limit ? parseInt(flags.limit as string, 10) : undefined,
      format: (["json", "table", "plain"].includes(fmt) ? fmt : "json") as SearchOpts["format"],
    }
    return runSearch(opts)
  }

  if (cmd === "detail") {
    const idOrUrl = (flags._ as string[])[1]
    if (!idOrUrl) {
      process.stderr.write(JSON.stringify({ error: "detail requires an <externalPath|url>", code: "NO_ID" }) + "\n")
      return 1
    }
    const fmt = (flags.format as string) || "json"
    const opts: DetailOpts = {
      idOrUrl,
      tenant: need("tenant") ?? undefined,
      instance: need("instance") ?? undefined,
      site: need("site") ?? undefined,
      companyName: need("company-name") ?? undefined,
      format: (fmt === "plain" ? "plain" : "json") as DetailOpts["format"],
    }
    return runDetail(opts)
  }

  process.stderr.write(JSON.stringify({ error: `Unknown command "${cmd}"`, code: "BAD_CMD" }) + "\n")
  return 1
}

main().then((code) => process.exit(code))

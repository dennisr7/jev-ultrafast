#!/usr/bin/env bun
// Self-contained CLI for searching jobs on Greenhouse's public Job Board API
// (boards-api.greenhouse.io), one company at a time. No external CLI framework,
// so it runs anywhere `bun` is available with zero install beyond the repo clone.
//
// Greenhouse doesn't offer a single cross-company search - every call needs a
// --company token (the slug in a company's job-board URL, e.g. "anthropic" for
// job-boards.greenhouse.io/anthropic). This is a public, documented API meant
// for embedding company job boards, so no authentication or ToS warning applies
// beyond normal rate-limit courtesy.

import { runSearch, type SearchOpts } from "./commands/search.js"
import { runDetail, type DetailOpts } from "./commands/detail.js"

interface Flags {
  _: string[]
  [k: string]: string | boolean | string[]
}

function parseFlags(argv: string[]): Flags {
  const flags: Flags = { _: [] }
  const alias: Record<string, string> = { q: "query", c: "company", n: "limit" }
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

const HELP = `greenhouse-cli — search jobs on Greenhouse company job boards (per company)

USAGE
  bun run src/cli.ts search --company <token> [flags]
  bun run src/cli.ts detail <id|url> [--company <token>] [--format json|plain]

SEARCH FLAGS
  --company, -c <token>   Greenhouse company token (the slug in job-boards.greenhouse.io/<token>). REQUIRED.
  --query, -q <text>      Keywords (job title). All words must appear in the title. Recommended.
  --jobage <days>         Posted within N days (uses first_published). Default: all.
  --page <n>              1-indexed page (20 results/page). Default 1.
  --limit, -n <n>         Cap results emitted (client-side).
  --format <fmt>          json (default) | table | plain.

DETAIL
  <id|url>                A job id from search results, OR a full job-board URL
                           (e.g. https://job-boards.greenhouse.io/anthropic/jobs/5421031008).
  --company, -c <token>   Required if <id> is bare (not needed when a full URL is given).

EXAMPLES
  bun run src/cli.ts search -c anthropic -q "software engineer" --jobage 30 --format table
  bun run src/cli.ts search -c databricks -q "machine learning" --format table
  bun run src/cli.ts detail 5421031008 -c anthropic --format plain
  bun run src/cli.ts detail https://job-boards.greenhouse.io/anthropic/jobs/5421031008 --format plain

Public Greenhouse Job Board API - no authentication required. Not every company uses
Greenhouse; a 404 means that company token has no public board.
`

async function main(): Promise<number> {
  const argv = process.argv.slice(2)
  const flags = parseFlags(argv)
  const cmd = (flags._ as string[])[0]

  if (!cmd || flags.help || flags.h) {
    process.stdout.write(HELP)
    return cmd ? 0 : 1
  }

  if (cmd === "search") {
    const company = typeof flags.company === "string" ? flags.company : undefined
    if (!company) {
      process.stderr.write(
        JSON.stringify({
          error: "--company/-c is required (the token in job-boards.greenhouse.io/<token>)",
          code: "NO_COMPANY",
        }) + "\n",
      )
      return 1
    }
    const fmt = (flags.format as string) || "json"

    const parseIntFlag = (name: string, raw: string | boolean | string[]): number | null => {
      const val = parseInt(raw as string, 10)
      if (isNaN(val)) {
        process.stderr.write(
          JSON.stringify({ error: `--${name} must be a number, got "${raw}"`, code: "BAD_ARG" }) + "\n",
        )
        return null
      }
      return val
    }

    if (flags.jobage !== undefined) {
      const v = parseIntFlag("jobage", flags.jobage)
      if (v === null) return 1
      flags.jobage = String(v)
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
      company,
      query: typeof flags.query === "string" ? flags.query : undefined,
      jobage: flags.jobage ? parseInt(flags.jobage as string, 10) : 9999,
      page: flags.page ? Math.max(1, parseInt(flags.page as string, 10)) : 1,
      limit: flags.limit ? parseInt(flags.limit as string, 10) : undefined,
      format: (["json", "table", "plain"].includes(fmt) ? fmt : "json") as SearchOpts["format"],
    }
    return runSearch(opts)
  }

  if (cmd === "detail") {
    const id = (flags._ as string[])[1]
    if (!id) {
      process.stderr.write(JSON.stringify({ error: "detail requires an <id|url>", code: "NO_ID" }) + "\n")
      return 1
    }
    const fmt = (flags.format as string) || "json"
    const opts: DetailOpts = {
      id,
      company: typeof flags.company === "string" ? flags.company : undefined,
      format: (fmt === "plain" ? "plain" : "json") as DetailOpts["format"],
    }
    return runDetail(opts)
  }

  process.stderr.write(JSON.stringify({ error: `Unknown command "${cmd}"`, code: "BAD_CMD" }) + "\n")
  return 1
}

main().then((code) => process.exit(code))

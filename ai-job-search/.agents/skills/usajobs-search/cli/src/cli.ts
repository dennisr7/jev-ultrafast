#!/usr/bin/env bun
// Self-contained CLI for searching the official USAJOBS Search API
// (data.usajobs.gov/api/search) - US federal government job postings.
// No external CLI framework, so it runs anywhere `bun` is available with
// zero install beyond the repo clone.
//
// Requires free registered credentials: set USAJOBS_API_KEY and USAJOBS_EMAIL
// as environment variables (never pass them as CLI flags - that would leak
// them into shell history and process listings). Register at
// https://developer.usajobs.gov.
//
// NOTE: built from USAJOBS's published API docs but not live-tested during
// scaffolding (every request, including a first smoke test, requires real
// credentials). See helpers.ts header and cli/README.md.

import { runSearch, type SearchOpts } from "./commands/search.js"
import { runDetail, type DetailOpts } from "./commands/detail.js"

interface Flags {
  _: string[]
  [k: string]: string | boolean | string[]
}

function parseFlags(argv: string[]): Flags {
  const flags: Flags = { _: [] }
  const alias: Record<string, string> = { q: "query", l: "location", n: "limit" }
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

const HELP = `usajobs-cli — search US federal job postings via the official USAJOBS Search API

USAGE
  bun run src/cli.ts search [flags]
  bun run src/cli.ts detail <id|url> [--format json|plain]

REQUIRED ENVIRONMENT
  USAJOBS_API_KEY   Your registered API key (developer.usajobs.gov)
  USAJOBS_EMAIL     The email address you registered with

SEARCH FLAGS
  --query, -q <text>      Keyword search (title, skill, agency, etc).
  --location, -l <text>   City, state, or military installation.
  --radius <miles>        Expand location search by N miles (requires --location).
  --jobage <days>         Posted within N days, 0-60 (USAJOBS max window). Default: all.
  --page <n>              1-indexed page (25 results/page). Default 1.
  --limit, -n <n>         Cap results emitted (client-side).
  --format <fmt>          json (default) | table | plain.

DETAIL
  <id|url>                A job id (PositionID/MatchedObjectId) from search results,
                           OR a full usajobs.gov/job/<id> URL.

EXAMPLES
  bun run src/cli.ts search -q "electronics engineer" --jobage 30 --format table
  bun run src/cli.ts search -q "software engineer" -l "Washington, DC" --radius 50 --format table
  bun run src/cli.ts detail 797030800 --format plain

Official government API — no ToS restriction on registered/authenticated use.
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
    if (flags.radius !== undefined) {
      const v = parseIntFlag("radius", flags.radius)
      if (v === null) return 1
      flags.radius = String(v)
    }

    const opts: SearchOpts = {
      query: typeof flags.query === "string" ? flags.query : undefined,
      location: typeof flags.location === "string" ? flags.location : undefined,
      radius: flags.radius ? parseInt(flags.radius as string, 10) : undefined,
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
      format: (fmt === "plain" ? "plain" : "json") as DetailOpts["format"],
    }
    return runDetail(opts)
  }

  process.stderr.write(JSON.stringify({ error: `Unknown command "${cmd}"`, code: "BAD_CMD" }) + "\n")
  return 1
}

main().then((code) => process.exit(code))

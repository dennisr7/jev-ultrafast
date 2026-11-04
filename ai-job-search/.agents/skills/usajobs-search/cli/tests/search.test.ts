import { describe, test, expect } from "bun:test";
import { runCLI, parseJSON } from "./helpers";

// Live smoke tests against the real USAJOBS Search API. Require
// USAJOBS_API_KEY and USAJOBS_EMAIL in the environment - skipped entirely
// (not failed) when absent, since this API has no anonymous/sandbox mode.
// Run these for real once you've registered at developer.usajobs.gov and
// exported both variables in your shell.

const HAS_CREDS = Boolean(process.env.USAJOBS_API_KEY && process.env.USAJOBS_EMAIL);
const TEST_QUERY = "software engineer";

interface SearchResult {
  meta: { count: number; page: number; totalMatches: number };
  results: { id: string; title: string; company: string | null; location: string | null; date: string | null; url: string }[];
}

describe.skipIf(!HAS_CREDS)("USAJOBS CLI live smoke tests (requires USAJOBS_API_KEY/USAJOBS_EMAIL)", () => {
  test("search returns real results with non-null id/title/url", async () => {
    const result = await runCLI(["search", "-q", TEST_QUERY, "--limit", "5"]);
    expect(result.exitCode).toBe(0);
    const parsed = parseJSON<SearchResult>(result);
    expect(parsed.results.length).toBeGreaterThan(0);
    for (const job of parsed.results) {
      expect(job.id).toBeTruthy();
      expect(job.title).toBeTruthy();
      expect(job.url).toMatch(/^https:\/\//);
    }
  });

  test("detail on the first search result returns readable description", async () => {
    const searchResult = await runCLI(["search", "-q", TEST_QUERY, "--limit", "1"]);
    const parsed = parseJSON<SearchResult>(searchResult);
    expect(parsed.results.length).toBeGreaterThan(0);
    const id = parsed.results[0].id;

    const detailResult = await runCLI(["detail", id, "--format", "plain"]);
    expect(detailResult.exitCode).toBe(0);
    expect(detailResult.stdout.length).toBeGreaterThan(20);
  });
});

if (!HAS_CREDS) {
  // eslint-disable-next-line no-console
  console.log(
    "\n[usajobs-search] Skipped live smoke tests: set USAJOBS_API_KEY and USAJOBS_EMAIL to run them for real.\n",
  );
}

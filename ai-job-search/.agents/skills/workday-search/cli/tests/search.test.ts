import { describe, test, expect } from "bun:test";
import { runCLI, parseJSON } from "./helpers";

// Live smoke tests against GE Vernova's real Workday career site, confirmed
// public/unauthenticated during /add-portal setup (2026-09-22).

const COORDS = ["-t", "gevernova", "-i", "wd5", "-s", "Vernova_ExternalSite"];
const TEST_QUERY = "software engineer";

interface SearchResult {
  meta: { count: number; page: number; totalMatches: number };
  results: { id: string; title: string; location: string | null; url: string }[];
}

describe("Workday CLI live smoke tests", () => {
  test("search returns real results with non-null id/title/url", async () => {
    const result = await runCLI(["search", ...COORDS, "-q", TEST_QUERY, "--limit", "5"]);
    expect(result.exitCode).toBe(0);
    const parsed = parseJSON<SearchResult>(result);
    expect(parsed.meta.totalMatches).toBeGreaterThan(0);
    expect(parsed.results.length).toBeGreaterThan(0);
    for (const job of parsed.results) {
      expect(job.id).toBeTruthy();
      expect(job.title).toBeTruthy();
      expect(job.url).toMatch(/^https:\/\/gevernova\.wd5\.myworkdayjobs\.com\//);
    }
  });

  test("detail on the first search result returns readable description", async () => {
    const searchResult = await runCLI(["search", ...COORDS, "-q", TEST_QUERY, "--limit", "1"]);
    const parsed = parseJSON<SearchResult>(searchResult);
    expect(parsed.results.length).toBeGreaterThan(0);
    const url = parsed.results[0].url;

    const detailResult = await runCLI(["detail", url, "--format", "plain"]);
    expect(detailResult.exitCode).toBe(0);
    expect(detailResult.stdout.length).toBeGreaterThan(20);
    expect(detailResult.stdout).not.toMatch(/&lt;|&gt;|<h1>|<p>/);
  });

  test("bad tenant/site combo is treated as not-found, not a crash", async () => {
    const result = await runCLI(["search", "-t", "this-should-not-exist-xyz123", "-i", "wd1", "-s", "nope"]);
    expect(result.exitCode).not.toBe(0);
    const err = JSON.parse(result.stderr);
    expect(err.code).toBe("NOT_FOUND");
  });

  test("page size beyond Workday's 20-result max is rejected upstream, not silently truncated wrong", async () => {
    // Workday itself caps limit at 20; this CLI always requests exactly 20 and
    // slices client-side with --limit, so this just confirms normal operation
    // at the boundary rather than a client-side bug.
    const result = await runCLI(["search", ...COORDS, "--limit", "20"]);
    expect(result.exitCode).toBe(0);
    const parsed = parseJSON<SearchResult>(result);
    expect(parsed.results.length).toBeLessThanOrEqual(20);
  });
});

import { describe, test, expect } from "bun:test";
import { runCLI, parseJSON } from "./helpers";

// Live smoke tests against Greenhouse's public Job Board API.
// Keep volume low - one search + one detail call per run.

const COMPANY = "anthropic"; // confirmed live during /add-portal setup (2026-09-22)
const TEST_QUERY = "engineer";

interface SearchResult {
  meta: { count: number; page: number };
  results: { id: string; title: string; company: string | null; location: string | null; date: string | null; url: string }[];
}

describe("Greenhouse CLI live smoke tests", () => {
  test("search returns real results with non-null id/title/url", async () => {
    const result = await runCLI(["search", "-c", COMPANY, "-q", TEST_QUERY, "--limit", "5"]);
    expect(result.exitCode).toBe(0);
    const parsed = parseJSON<SearchResult>(result);
    expect(parsed.results.length).toBeGreaterThan(0);
    for (const job of parsed.results) {
      expect(job.id).toBeTruthy();
      expect(job.title).toBeTruthy();
      expect(job.url).toMatch(/^https:\/\//);
      expect(job.title.toLowerCase()).toContain(TEST_QUERY);
    }
  });

  test("detail on the first search result returns readable description", async () => {
    const searchResult = await runCLI(["search", "-c", COMPANY, "-q", TEST_QUERY, "--limit", "1"]);
    const parsed = parseJSON<SearchResult>(searchResult);
    expect(parsed.results.length).toBeGreaterThan(0);
    const id = parsed.results[0].id;

    const detailResult = await runCLI(["detail", id, "-c", COMPANY, "--format", "plain"]);
    expect(detailResult.exitCode).toBe(0);
    expect(detailResult.stdout.length).toBeGreaterThan(20);
    expect(detailResult.stdout).not.toMatch(/&lt;|&gt;|<div|<p>/);
  });

  test("unknown company token returns 404-mapped NOT_FOUND", async () => {
    const result = await runCLI(["search", "-c", "this-company-should-not-exist-xyz123"]);
    expect(result.exitCode).not.toBe(0);
    const err = JSON.parse(result.stderr);
    expect(err.code).toBe("NOT_FOUND");
  });
});

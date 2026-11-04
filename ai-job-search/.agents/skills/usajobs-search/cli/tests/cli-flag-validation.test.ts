import { describe, test, expect } from "bun:test";
import { runCLI } from "./helpers";

// These tests exercise flag parsing/validation, which happens before credential
// checks - so they pass whether or not USAJOBS_API_KEY/USAJOBS_EMAIL are set.
// A dedicated NO_CREDENTIALS test explicitly clears them. No real API call is
// made in this file (see search.test.ts for the live smoke tests, which
// require real credentials and are skipped without them).

function parsedStderr(stderr: string): { error?: string; code?: string } {
  try {
    return JSON.parse(stderr);
  } catch {
    return {};
  }
}

describe("USAJOBS CLI flag validation", () => {
  describe("--jobage NaN validation", () => {
    test("non-numeric string exits 1 with BAD_ARG", async () => {
      const result = await runCLI(["search", "--jobage", "foo"]);
      expect(result.exitCode).not.toBe(0);
      const err = parsedStderr(result.stderr);
      expect(err.code).toBe("BAD_ARG");
      expect(err.error).toMatch(/jobage/);
    });
  });

  describe("--page NaN validation", () => {
    test("non-numeric string exits 1 with BAD_ARG", async () => {
      const result = await runCLI(["search", "--page", "abc"]);
      expect(result.exitCode).not.toBe(0);
      const err = parsedStderr(result.stderr);
      expect(err.code).toBe("BAD_ARG");
      expect(err.error).toMatch(/page/);
    });
  });

  describe("--limit NaN validation", () => {
    test("non-numeric string exits 1 with BAD_ARG", async () => {
      const result = await runCLI(["search", "--limit", "xyz"]);
      expect(result.exitCode).not.toBe(0);
      const err = parsedStderr(result.stderr);
      expect(err.code).toBe("BAD_ARG");
      expect(err.error).toMatch(/limit/);
    });
  });

  describe("--radius NaN validation", () => {
    test("non-numeric string exits 1 with BAD_ARG", async () => {
      const result = await runCLI(["search", "--radius", "far"]);
      expect(result.exitCode).not.toBe(0);
      const err = parsedStderr(result.stderr);
      expect(err.code).toBe("BAD_ARG");
      expect(err.error).toMatch(/radius/);
    });
  });

  describe("detail requires an id", () => {
    test("missing id exits 1 with NO_ID", async () => {
      const result = await runCLI(["detail"]);
      expect(result.exitCode).not.toBe(0);
      const err = parsedStderr(result.stderr);
      expect(err.code).toBe("NO_ID");
    });
  });

  describe("credentials", () => {
    test("missing USAJOBS_API_KEY/USAJOBS_EMAIL exits 1 with NO_CREDENTIALS", async () => {
      const result = await runCLI(["search", "-q", "engineer"], {
        USAJOBS_API_KEY: "",
        USAJOBS_EMAIL: "",
      });
      expect(result.exitCode).not.toBe(0);
      const err = parsedStderr(result.stderr);
      expect(err.code).toBe("NO_CREDENTIALS");
    });
  });
});

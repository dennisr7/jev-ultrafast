import { describe, test, expect } from "bun:test";
import { runCLI } from "./helpers";

function parsedStderr(stderr: string): { error?: string; code?: string } {
  try {
    return JSON.parse(stderr);
  } catch {
    return {};
  }
}

describe("Workday CLI flag validation", () => {
  describe("required coordinates", () => {
    test("search with no flags exits 1 with NO_COORDS", async () => {
      const result = await runCLI(["search"]);
      expect(result.exitCode).not.toBe(0);
      const err = parsedStderr(result.stderr);
      expect(err.code).toBe("NO_COORDS");
    });

    test("search missing --site exits 1 with NO_COORDS", async () => {
      const result = await runCLI(["search", "-t", "boeing", "-i", "wd1"]);
      expect(result.exitCode).not.toBe(0);
      const err = parsedStderr(result.stderr);
      expect(err.code).toBe("NO_COORDS");
    });

    test("detail with bare externalPath and no coords exits 1 with NO_COORDS", async () => {
      const result = await runCLI(["detail", "/job/some-role_R123"]);
      expect(result.exitCode).not.toBe(0);
      const err = parsedStderr(result.stderr);
      expect(err.code).toBe("NO_COORDS");
    });

    test("detail with a non-path non-url id exits 1 with BAD_ID", async () => {
      const result = await runCLI(["detail", "R123"]);
      expect(result.exitCode).not.toBe(0);
      const err = parsedStderr(result.stderr);
      expect(err.code).toBe("BAD_ID");
    });

    test("detail with no id exits 1 with NO_ID", async () => {
      const result = await runCLI(["detail"]);
      expect(result.exitCode).not.toBe(0);
      const err = parsedStderr(result.stderr);
      expect(err.code).toBe("NO_ID");
    });
  });

  describe("--page / --limit validation", () => {
    test("non-numeric --page exits 1 with BAD_ARG", async () => {
      const result = await runCLI(["search", "-t", "boeing", "-i", "wd1", "-s", "EXTERNAL_CAREERS", "--page", "abc"]);
      expect(result.exitCode).not.toBe(0);
      const err = parsedStderr(result.stderr);
      expect(err.code).toBe("BAD_ARG");
    });

    test("non-numeric --limit exits 1 with BAD_ARG", async () => {
      const result = await runCLI(["search", "-t", "boeing", "-i", "wd1", "-s", "EXTERNAL_CAREERS", "--limit", "xyz"]);
      expect(result.exitCode).not.toBe(0);
      const err = parsedStderr(result.stderr);
      expect(err.code).toBe("BAD_ARG");
    });
  });
});

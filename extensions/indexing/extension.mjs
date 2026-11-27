import { execFile } from "node:child_process";
import { readFile } from "node:fs/promises";
import { homedir } from "node:os";
import { basename, isAbsolute, join } from "node:path";
import { fileURLToPath } from "node:url";
import { joinSession } from "@github/copilot-sdk/extension";

const engine = fileURLToPath(new URL("./engine.py", import.meta.url));

async function search(request) {
  const directory = process.env.COPILOT_INDEXING_HOME || join(homedir(), ".config", "copilot-indexing");
  if (!isAbsolute(directory)) {
    throw new Error("COPILOT_INDEXING_HOME must be absolute.");
  }
  const config = JSON.parse(await readFile(join(directory, "config.json"), "utf8"));
  if (typeof config.python !== "string" || !isAbsolute(config.python) || basename(config.python) !== "python") {
    throw new Error("Run copilot-indexing setup to configure the Python environment.");
  }
  const env = { COPILOT_INDEXING_HOME: directory };
  for (const key of ["HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE"]) {
    if (process.env[key] !== undefined) {
      env[key] = process.env[key];
    }
  }

  return new Promise((resolve, reject) => {
    const child = execFile(config.python, ["-I", engine], {
      cwd: process.cwd(),
      env,
      timeout: 35_000,
      maxBuffer: 96_000,
    }, (error, stdout, stderr) => {
      if (error) {
        reject(new Error(stderr.trim().slice(0, 1_000) || "CocoIndex search timed out or could not start."));
      } else {
        resolve(stdout.trim());
      }
    });
    child.stdin.on("error", () => {});
    child.stdin.end(JSON.stringify(request));
  });
}

await joinSession({
  tools: [{
    name: "search_codebase",
    description: "Find relevant code or documentation by meaning in the current checkout's local CocoIndex index.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        query: { type: "string", minLength: 1, maxLength: 2000, description: "What to find." },
        limit: { type: "integer", minimum: 1, maximum: 10, description: "Maximum snippets, default 5." },
        lang: { type: "string", description: "Optional language filter, such as python." },
        path: { type: "string", description: "Optional checkout-relative glob." },
      },
      required: ["query"],
    },
    handler: async (request) => {
      try {
        return await search(request);
      } catch (error) {
        const message = error.code === "ENOENT"
          ? "CocoIndex has not been configured. Run copilot-indexing setup with --workspace."
          : error.message;
        return { textResultForLlm: message, resultType: "failure" };
      }
    },
  }],
});

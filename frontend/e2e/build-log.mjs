import { execFileSync } from "node:child_process";
import { closeSync, mkdirSync, openSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

// Capture stdout/stderr while building, so even a timeout leaves an artifact.
// Environment variable values are never logged by this wrapper.
export function runLoggedCommand({ command, args, cwd, env, logFile, shell = false, echo = true }) {
  mkdirSync(path.dirname(logFile), { recursive: true });
  writeFileSync(logFile, `Build started: ${new Date().toISOString()}\n`, "utf8");
  const descriptor = openSync(logFile, "a");
  let failure;
  try {
    execFileSync(command, args, {
      cwd,
      env,
      shell,
      windowsHide: true,
      stdio: ["ignore", descriptor, descriptor],
    });
  } catch (error) {
    failure = error;
  } finally {
    closeSync(descriptor);
  }
  if (echo) process.stdout.write(readFileSync(logFile, "utf8").slice(-64000));
  if (failure) {
    const status = Number.isInteger(failure.status)
      ? failure.status
      : failure.signal
        ? `signal:${failure.signal}`
        : "not-started";
    const error = new Error(`E2E build failed (${status}); see ${logFile}`);
    error.buildStatus = status;
    throw error;
  }
}

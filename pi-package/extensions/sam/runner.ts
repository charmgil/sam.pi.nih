/**
 * Runs the deterministic core (`python -m samkit ...`) from the harness's pixi
 * environment. stdout carries one JSON result; stderr lines are progress.
 *
 * Each call runs in its own process group so that cancelling a tool stops the
 * whole tree (samkit and the plink2/regenie/PRS-CS processes it started).
 */

import { type ChildProcess, spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

export interface SamConfig {
	home: string;
	input?: string;
	resource?: string;
	output: string;
	build?: string;
	threads?: string;
	privacy: "auto" | "on" | "off";
	approve: "ask" | "allow" | "deny";
	consultant?: string;
}

export interface SamResult {
	ok: boolean;
	error?: string;
	hint?: string;
	[key: string]: unknown;
}

const running = new Set<ChildProcess>();

function killGroup(child: ChildProcess, signal: NodeJS.Signals): void {
	if (child.pid === undefined) return;
	try {
		process.kill(-child.pid, signal);
	} catch {
		try {
			child.kill(signal);
		} catch {
			/* already gone */
		}
	}
}

/** Stop every samkit process tree started by this extension (session shutdown). */
export function stopAll(): void {
	for (const child of running) killGroup(child, "SIGTERM");
	setTimeout(() => {
		for (const child of running) killGroup(child, "SIGKILL");
	}, 5000).unref();
}

export function pythonPath(cfg: SamConfig): string {
	return path.join(cfg.home, ".pixi", "envs", "default", "bin", "python");
}

export function globalArgs(cfg: SamConfig): string[] {
	const a: string[] = [];
	if (cfg.input) a.push("--input", cfg.input);
	if (cfg.resource) a.push("--resource", cfg.resource);
	a.push("--output", cfg.output);
	if (cfg.build) a.push("--build", cfg.build);
	if (cfg.threads) a.push("--threads", cfg.threads);
	return a;
}

export async function runSamkit(
	cfg: SamConfig,
	args: string[],
	opts: { signal?: AbortSignal; onProgress?: (lines: string[]) => void; needsInput?: boolean } = {},
): Promise<SamResult> {
	if (opts.signal?.aborted) return { ok: false, error: "cancelled by the user" };
	if (opts.needsInput !== false && !cfg.input)
		return {
			ok: false,
			error: "input directory is not set",
			hint: "start with `./sam agent --input DIR --resource DIR`, or run /sam-data <input> [resource]",
		};
	const py = pythonPath(cfg);
	if (!fs.existsSync(py))
		return { ok: false, error: `harness Python not found at ${py}`, hint: "ask the user to run `./sam bootstrap` in the harness directory" };

	return new Promise((resolve) => {
		const child = spawn(py, ["-B", "-m", "samkit", ...globalArgs(cfg), ...args], {
			cwd: process.cwd(),
			env: { ...process.env, PYTHONPATH: path.join(cfg.home, "src"), SAM_HOME: cfg.home, PYTHONUNBUFFERED: "1" },
			stdio: ["ignore", "pipe", "pipe"],
			detached: true, // own process group: cancelling kills the whole tree
		});
		running.add(child);
		let stdout = "";
		const recent: string[] = [];
		let lastEmit = 0;
		let partial = "";
		let settled = false;
		const finish = (r: SamResult) => {
			if (settled) return;
			settled = true;
			running.delete(child);
			opts.signal?.removeEventListener("abort", onAbort);
			resolve(r);
		};
		child.stdout?.on("data", (d: Buffer) => {
			stdout += d.toString("utf8");
		});
		child.stderr?.on("data", (d: Buffer) => {
			partial += d.toString("utf8");
			const lines = partial.split(/\r?\n/);
			partial = lines.pop() ?? "";
			for (const l of lines) if (l.trim()) recent.push(l.slice(0, 300));
			if (recent.length > 12) recent.splice(0, recent.length - 12);
			const now = Date.now();
			if (opts.onProgress && now - lastEmit > 1000) {
				lastEmit = now;
				opts.onProgress([...recent]);
			}
		});
		const onAbort = () => {
			killGroup(child, "SIGTERM");
			setTimeout(() => killGroup(child, "SIGKILL"), 5000).unref();
		};
		opts.signal?.addEventListener("abort", onAbort, { once: true });
		child.on("exit", () => {
			if (opts.signal?.aborted) finish({ ok: false, error: "cancelled by the user" });
		});
		child.on("close", (code) => {
			if (opts.signal?.aborted) return finish({ ok: false, error: "cancelled by the user" });
			try {
				finish(JSON.parse(stdout) as SamResult);
			} catch {
				finish({
					ok: false,
					error: `samkit exited with code ${code} without a JSON result`,
					hint: recent.slice(-8).join("\n"),
				});
			}
		});
		child.on("error", (err) => finish({ ok: false, error: `cannot start samkit: ${err.message}` }));
	});
}

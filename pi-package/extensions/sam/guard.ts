/**
 * Guards for pi's built-in tools (bash, read, write, edit, grep).
 *
 * These are mistake guards, not a security boundary: a determined command can
 * always evade pattern checks. They enforce the harness rules in code so that
 * every model (cloud or local) gets the same limits:
 *   - input/resource directories are read-only
 *   - files are written only inside the working directory or the output directory
 *   - installs and file downloads go through sam_setup / sam_pheweb (with approval)
 *   - with privacy on, individual-level files cannot be read into the model context
 */

import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export interface GuardConfig {
	cwd: string;
	output: string;
	input?: string;
	resource?: string;
	privacy: boolean;
}

export interface Verdict {
	block: boolean;
	reason?: string;
}

const ALLOW: Verdict = { block: false };

/** Summary-level files that may sit in the input directory. Everything else there is treated as individual-level. */
const INPUT_SUMMARY_LEVEL = [
	/\.bim$/i,
	/\.pvar(\.zst)?$/i,
	/\.log$/i,
	/\.md$/i,
	/readme/i,
	/phenocode-.*\.tsv(\.gz)?$/i,
	/sumstat/i,
	/prs_weight/i,
	/\.meta\.json$/i,
];

/** Individual-level artifacts anywhere (mostly under output/). */
const INDIVIDUAL_LEVEL = [
	/\.fam$/i,
	/\.psam$/i,
	/\.(bed|pgen|bgen|bcf)$/i,
	/\.vcf(\.gz)?$/i,
	/(^|\/)pheno\.tsv$/i,
	/\.eigenvec$/i,
	/\.sscore$/i,
	/\.loco(\.gz)?$/i,
	/_pred\.list$/i,
	/(^|\/)samples(_qc)?\.(id|keep)$/i,
	/\.(smiss|scount|king|kin0)$/i,
	/(^|\/)gwas\/[^/]+\/step1\//i,
	/(^|\/)\.pi-sessions(\/|$)/i, // transcripts of earlier sessions may hold data read with privacy off
];

/** Normalize like pi's own tools (leading @, file://), expand SAM_* variables, resolve symlinks when possible. */
export function expandPath(p: string, cfg: GuardConfig): string {
	let s = p.trim().replace(/^['"]|['"]$/g, "");
	if (s.startsWith("@")) s = s.slice(1);
	if (s.startsWith("file://")) s = s.slice("file://".length);
	s = s
		.replace(/\$\{?SAM_INPUT\}?/g, cfg.input ?? "$SAM_INPUT")
		.replace(/\$\{?SAM_RESOURCE\}?/g, cfg.resource ?? "$SAM_RESOURCE")
		.replace(/\$\{?SAM_OUTPUT\}?/g, cfg.output)
		.replace(/\$\{?(HOME)\}?/g, os.homedir());
	if (s === "~" || s.startsWith("~/")) s = path.join(os.homedir(), s.slice(1));
	const abs = path.resolve(cfg.cwd, s);
	try {
		return fs.realpathSync(abs);
	} catch {
		return abs;
	}
}

export function within(p: string, dir?: string): boolean {
	if (!dir) return false;
	const rel = path.relative(dir, p);
	return rel === "" || (!rel.startsWith("..") && !path.isAbsolute(rel));
}

export function isProtected(abs: string, cfg: GuardConfig): boolean {
	return within(abs, cfg.input) || within(abs, cfg.resource);
}

export function isIndividualLevel(abs: string, cfg: GuardConfig): boolean {
	if (INDIVIDUAL_LEVEL.some((re) => re.test(abs))) return true;
	if (cfg.input && within(abs, cfg.input) && abs !== path.resolve(cfg.input)) {
		const name = path.basename(abs);
		return !INPUT_SUMMARY_LEVEL.some((re) => re.test(name));
	}
	return false;
}

function writable(abs: string, cfg: GuardConfig): Verdict {
	if (isProtected(abs, cfg)) return { block: true, reason: `${abs} is in a read-only data directory (input/resource)` };
	if (!within(abs, cfg.cwd) && !within(abs, cfg.output))
		return { block: true, reason: `writes are limited to the working directory ${cfg.cwd} and the output directory (target: ${abs})` };
	return ALLOW;
}

// ── built-in file tools ──────────────────────────────────────────────────────
export function checkWritePath(p: string | undefined, cfg: GuardConfig): Verdict {
	if (!p) return ALLOW;
	return writable(expandPath(p, cfg), cfg);
}

export function checkReadPath(p: string | undefined, cfg: GuardConfig): Verdict {
	if (!p || !cfg.privacy) return ALLOW;
	const abs = expandPath(p, cfg);
	if (isIndividualLevel(abs, cfg))
		return {
			block: true,
			reason:
				`privacy mode: ${path.basename(abs)} holds individual-level data and cannot be read into the model context. ` +
				"Use the sam_* tools, which return aggregate summaries only.",
		};
	return ALLOW;
}

/** Output subtrees that contain individual-level files (phenotype tables, step-1 predictions, scores). */
const INDIVIDUAL_SUBTREES = ["gwas", "prs", ".pi-sessions"];

/** grep reads file contents: with privacy on, refuse targets that are (or contain) individual-level data. */
export function checkSearchPath(p: string | undefined, cfg: GuardConfig): Verdict {
	if (!cfg.privacy) return ALLOW;
	const abs = expandPath(p || ".", cfg);
	const file = checkReadPath(abs, cfg);
	if (file.block) return file;
	const holds =
		(cfg.input && (within(cfg.input, abs) || within(abs, cfg.input))) ||
		within(cfg.output, abs) ||
		INDIVIDUAL_SUBTREES.some((d) => within(abs, path.join(cfg.output, d)) || within(path.join(cfg.output, d), abs));
	if (holds && !/\.(json|log|png|md|regenie\.gz|tsv\.gz)$/i.test(abs))
		return {
			block: true,
			reason:
				"privacy mode: searching this directory could print lines from individual-level files. " +
				"Search a specific summary file (e.g. a summary.json or log) instead.",
		};
	return ALLOW;
}

// ── bash ─────────────────────────────────────────────────────────────────────
const INSTALL_RE = [
	/\b(pip3?|uv\s+pip|pipx|conda|mamba|micromamba)\s+(install|add|create)\b/,
	/\bconda\s+env\s+(create|update)\b/,
	/\bpixi\s+(install|add|global|init|run\s+--manifest)\b/,
	/\buv\s+(tool\s+install|add|sync)\b/,
	/\b(apt|apt-get|yum|dnf|zypper|brew|port|snap)\s+(install|add)\b/,
	/\b(npm|pnpm|yarn|bun)\s+(i|install|add)\b/,
	/\bcargo\s+install\b/,
	/\binstall\.packages\s*\(/,
	/\b(BiocManager|remotes|devtools|pak)::\w*install/,
	/\bR\s+CMD\s+INSTALL\b/,
	/\bgit\s+clone\b/,
	/\b(curl|wget)\b[^|;&\n]*\|\s*(ba|z)?sh\b/,
	/(^|[\s;&|(])(\S*\/)?sam\s+(setup|bootstrap|llm\s+(pull|vllm-install))\b/,
	/\bsamkit(\.llm)?\s+(setup|pull)\b/,
	/\bollama\s+(pull|create|rm)\b/,
];
const DOWNLOAD_RE = [
	/(^|[\s;&|(])wget\b/,
	/\bcurl\b[^|;&\n]*(\s-[a-zA-Z]*[oO][a-zA-Z]*(\s|$)|\s--output\b|\s--remote-name\b|>\s*\S)/,
	/\baria2c\b/,
	/\b(rsync|scp)\b[^|;&\n]*\s\S+:\S*/,
];
const LOOKUP_ONLY_RE = /^\s*(which|type|command\s+-v|whereis)\s/;

/** Commands that modify every path argument they get. */
const MODIFY_ALL = new Set(["rm", "rmdir", "touch", "mkdir", "truncate", "chmod", "chown", "chgrp", "shred", "unlink", "tee"]);
/** Commands whose last path argument (or -t DIR) is the destination. */
const MODIFY_DEST = new Set(["cp", "mv", "ln", "install", "rsync"]);
/** Commands that rewrite their file arguments in place unless asked to write to stdout. */
const IN_PLACE = new Set(["gzip", "gunzip", "bgzip", "zstd", "unzstd", "xz", "unxz", "bzip2", "bunzip2"]);

const METADATA_CMDS = /^(ls|du|stat|file|wc|md5sum|sha256sum|sha1sum|realpath|readlink|test|\[|basename|dirname|find)$/;
const STREAM_FILTERS = /^(wc|sort|uniq|head|tail|grep|cut|awk|sed|tr|column|nl|cat)$/;
const RECURSIVE_SEARCH_RE = /^(grep|zgrep|egrep|fgrep)\b.*\s(-[a-zA-Z]*[rR][a-zA-Z]*|--recursive)\b|^(rg|ag|ack)\b/;

/** Split a command line into `;` / `&&` / `||` / newline separated segments (pipes stay inside a segment). */
function segments(command: string): string[] {
	return command
		.replace(/\\\n/g, " ")
		.split(/\n|;|&&|\|\|/)
		.map((s) => s.trim().replace(/^[({]\s*/, "").replace(/\s*[)}]$/, ""))
		.filter(Boolean);
}

/** Words of one simple command, quotes removed; leading VAR=value assignments dropped. */
function words(stage: string): string[] {
	const raw = stage.match(/'[^']*'|"[^"]*"|[^\s<>]+/g) ?? [];
	const out = raw.map((w) => w.replace(/^['"]|['"]$/g, ""));
	while (out.length && /^[A-Za-z_]\w*=/.test(out[0])) out.shift();
	return out;
}

/**
 * Path-like pieces of a command. Quoted strings are unwrapped and split again, so paths
 * embedded in inline code (`python -c 'open("/x/y.fam")'`) are found too.
 */
export function pathTokens(command: string): string[] {
	const ws = command.match(/'[^']*'|"[^"]*"|[^\s;&|<>()]+/g) ?? [];
	const pieces = ws.flatMap((w) => w.replace(/^['"]|['"]$/g, "").split(/[\s'"`(),;=]+/));
	return pieces
		.map((w) => w.replace(/^--?[\w-]+=/, ""))
		.filter((w) => w.includes("/") || w.includes("$SAM_") || w.includes("${SAM_") || w.startsWith("~") || w.startsWith("@"));
}

/** Commands that print their arguments instead of reading them. */
const PRINT_ONLY = /^(echo|printf|true|false|:)$/;

/** Path-like pieces plus bare file names (`pheno.tsv`, `x.fam`) that only make sense relative to a directory. */
function candidateTokens(segment: string): string[] {
	const stages = segment.split("|").filter((st) => !PRINT_ONLY.test(path.basename(words(st)[0] ?? "")));
	const reading = stages.join(" | ");
	const ws = (reading.match(/'[^']*'|"[^"]*"|[^\s;&|<>()]+/g) ?? []).flatMap((w) =>
		w.replace(/^['"]|['"]$/g, "").split(/[\s'"`(),;=]+/),
	);
	const files = ws.filter((w) => /^[\w.+-]+\.[A-Za-z0-9]{1,8}(\.gz|\.zst)?$/.test(w) && !/^\d+(\.\d+)?$/.test(w));
	return [...pathTokens(reading), ...files];
}

/** Redirect / output-option targets: `> f`, `>> f`, `--out f`, `-o f`, `--out_dir=f`, `of=f`. */
export function writeTargets(command: string): string[] {
	const out: string[] = [];
	const patterns = [
		/(?:^|[^0-9&<])>{1,2}\|?\s*([^\s;&|<>()]+)/g,
		/(?:^|\s)--(?:out|output|out[-_]dir|out[-_]prefix)[=\s]+([^\s;&|<>()]+)/g,
		/(?:^|\s)-o\s+([^\s;&|<>()]+)/g,
		/(?:^|\s)of=([^\s;&|<>()]+)/g,
	];
	for (const re of patterns) for (const m of command.matchAll(re)) out.push(m[1]);
	return out.filter((t) => !/^\/dev\/(null|stderr|stdout|fd\/\d+)$/.test(t) && !t.startsWith("&"));
}

/** Paths a single pipeline stage would modify, according to its command word. */
function modifiedPaths(stage: string): string[] {
	const w = words(stage);
	if (!w.length) return [];
	const cmd = path.basename(w[0]);
	const args = w.slice(1);
	const operands = args.filter((a) => !a.startsWith("-"));
	if (MODIFY_ALL.has(cmd)) return operands;
	if (MODIFY_DEST.has(cmd)) {
		const t = args.indexOf("-t");
		if (t >= 0 && args[t + 1]) return [args[t + 1]];
		return operands.length > 1 ? [operands[operands.length - 1]] : [];
	}
	if (cmd === "sed" && args.some((a) => /^-[a-zA-Z]*i/.test(a) || a.startsWith("--in-place"))) return operands.slice(1);
	if (IN_PLACE.has(cmd) && !args.some((a) => /^-[a-zA-Z]*c/.test(a) || a === "--stdout" || a === "-l" || a === "-t"))
		return operands;
	if (cmd === "tar" && args.some((a) => /^-?[a-zA-Z]*x/.test(a))) {
		const c = args.findIndex((a) => a === "-C" || a === "--directory");
		return [c >= 0 && args[c + 1] ? args[c + 1] : "."];
	}
	if (cmd === "unzip") {
		const d = args.indexOf("-d");
		return [d >= 0 && args[d + 1] ? args[d + 1] : "."];
	}
	return [];
}

/** True when a pipeline only produces metadata about files (names, sizes, counts, a header line). */
function metadataOnly(segment: string, cfg: GuardConfig): boolean {
	if (/`|\$\(/.test(segment)) return false;
	const expanded = segment
		.replace(/\$\{?SAM_INPUT\}?/g, cfg.input ?? "")
		.replace(/\$\{?SAM_RESOURCE\}?/g, cfg.resource ?? "")
		.replace(/\$\{?SAM_OUTPUT\}?/g, cfg.output);
	const stages = expanded.split("|").map((s) => s.trim());
	const first = words(stages[0]);
	if (!first.length) return false;
	const cmd = path.basename(first[0]);
	let ok = false;
	if (cmd === "find") ok = !first.some((a) => /^-(exec|execdir|ok|okdir|fprint|fprintf|fls|delete)$/.test(a));
	else if (cmd === "wc") ok = first.some((a) => /^-[lcmw]+$/.test(a));
	else if (cmd === "head") ok = /\s-(n\s*)?1(\s|$)/.test(stages[0]);
	else if (/^(z|gz)?cat$/.test(cmd) || (cmd === "gzip" && first.some((a) => /^-[a-z]*d/.test(a))))
		return stages.length > 1 && /^head\s+-(n\s*)?1(\s|$)/.test(stages[1]);
	else ok = METADATA_CMDS.test(cmd);
	return ok && stages.slice(1).every((s) => STREAM_FILTERS.test(path.basename(words(s)[0] ?? "")) && !/\bxargs\b/.test(s));
}

export function checkBash(command: string, cfg: GuardConfig): Verdict {
	const cmd = command.replace(/\\\n/g, " ");
	if (/(^|[;&|\s(])sudo\b/.test(cmd)) return { block: true, reason: "sudo is not allowed in this harness" };
	if (INSTALL_RE.some((re) => re.test(cmd)))
		return {
			block: true,
			reason:
				"installing software or models from bash is disabled; use the sam_setup tool (it asks the user and installs " +
				"into the harness environments), or ask the user to run it",
		};
	if (!segments(cmd).every((s) => LOOKUP_ONLY_RE.test(s)) && DOWNLOAD_RE.some((re) => re.test(cmd)))
		return {
			block: true,
			reason:
				"downloading files from bash is disabled; use sam_pheweb for KNIH PheWeb data, or ask the user to place files in the input/resource directory",
		};

	let dir = cfg.cwd;
	const stack: string[] = [];
	for (const seg of segments(cmd)) {
		const cd = seg.match(/^(cd|pushd)(?:\s+(\S+))?\s*$/);
		if (cd) {
			if (cd[1] === "pushd") stack.push(dir);
			dir = cd[2] ? expandPath(cd[2], { ...cfg, cwd: dir }) : os.homedir();
			continue;
		}
		if (/^popd\b/.test(seg)) {
			dir = stack.pop() ?? dir;
			continue;
		}
		const here = { ...cfg, cwd: dir };
		const targets = [...writeTargets(` ${seg}`), ...seg.split("|").flatMap((stage) => modifiedPaths(stage))];
		for (const t of targets) {
			const v = writable(expandPath(t, here), cfg);
			if (v.block) return v;
		}
		if (cfg.privacy) {
			for (const stage of seg.split("|"))
				if (RECURSIVE_SEARCH_RE.test(stage.trim()))
					return {
						block: true,
						reason:
							"privacy mode: recursive content search could print lines from individual-level files; " +
							"search specific summary files (summary.json, logs, results) instead",
					};
			const touched = candidateTokens(seg).map((t) => expandPath(t, here));
			const dataDirs = touched.some(
				(t) => within(t, cfg.input) || INDIVIDUAL_SUBTREES.some((d) => within(t, path.join(cfg.output, d))),
			);
			if (dataDirs && /(^|\s)(-exec|-execdir|-ok|-okdir)\s|\bxargs\b|\bparallel\b/.test(seg))
				return {
					block: true,
					reason: "privacy mode: running commands over files found in data directories could print individual-level data",
				};
			const individual = touched.filter((t) => isIndividualLevel(t, cfg));
			if (individual.length && !metadataOnly(seg, cfg))
				return {
					block: true,
					reason:
						`privacy mode: the command reads individual-level data (${[...new Set(individual.map((p) => path.basename(p)))].join(", ")}). ` +
						"Only metadata (ls, wc -l, du, head -1 for column names) is allowed; use the sam_* tools for analysis.",
				};
		}
	}
	return ALLOW;
}

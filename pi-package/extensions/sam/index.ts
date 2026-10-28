/**
 * SAM — pi extension for the merged GWAS + PRS harness.
 *
 * Thin skills, thick tools: the model decides what to run and how to read the
 * results; paths, parameters, preconditions, provenance and privacy are handled
 * by code (samkit) and by the guards below.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { Type } from "@earendil-works/pi-ai";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

import { checkBash, checkReadPath, checkSearchPath, checkWritePath, type GuardConfig, within } from "./guard.ts";
import { runSamkit, type SamConfig, type SamResult, stopAll } from "./runner.ts";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const HOME = process.env.SAM_HOME ? path.resolve(process.env.SAM_HOME) : path.resolve(HERE, "..", "..", "..");
const PKG = path.join(HOME, "pi-package");
const LOCAL_PROVIDERS = new Set(["ollama", "vllm", "llama-cpp", "llamacpp", "llama.cpp", "lmstudio", "sglang", "local"]);
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"]);
const MAX_RESULT_CHARS = 14000;
/** Directories the kernel keeps read-only for this whole process tree (src/samkit/sandbox.py, started by ./sam agent). */
const KERNEL_RO = (process.env.SAM_SANDBOX ?? "").startsWith("landlock")
	? (process.env.SAM_SANDBOX_RO ?? "").split(path.delimiter).filter(Boolean)
	: [];
const kernelReadOnly = (dir?: string): boolean => {
	if (!dir) return true;
	let real = path.resolve(dir);
	try {
		real = fs.realpathSync(real);
	} catch {}
	return KERNEL_RO.some((d) => within(real, d));
};
/** The catalog's default consultant as an Ollama `sam-*` variant (models/catalog.json "defaults"). */
const catalogConsultant = (): string | undefined => {
	try {
		const cat = JSON.parse(fs.readFileSync(path.join(HOME, "models", "catalog.json"), "utf8")) as {
			defaults?: { consultant?: string };
		};
		return cat.defaults?.consultant ? `ollama/sam-${cat.defaults.consultant}` : undefined;
	} catch {
		return undefined;
	}
};
const READ_ONLY_NOTE =
	"kernel protection covers only the directories given to ./sam agent at start; restart with --input/--resource " +
	"for it (the command checks still apply)";

type Ctx = ExtensionContext;

export default function sam(pi: ExtensionAPI) {
	pi.registerFlag("sam-input", { type: "string", description: "SAM: input data directory (read-only)" });
	pi.registerFlag("sam-resource", { type: "string", description: "SAM: reference resource directory (read-only)" });
	pi.registerFlag("sam-output", { type: "string", description: "SAM: output directory (default ./output)" });
	pi.registerFlag("sam-build", { type: "string", description: "SAM: genome build hg19|hg38 (default hg19)" });
	pi.registerFlag("sam-threads", { type: "string", description: "SAM: threads for analysis tools" });
	pi.registerFlag("sam-privacy", {
		type: "string",
		description: "SAM: block reading individual-level files: auto (cloud models only, default) | on | off",
	});
	pi.registerFlag("sam-approve", {
		type: "string",
		description: "SAM: installs/downloads/partial PRS: ask (default) | allow | deny (headless 'ask' = deny)",
	});
	pi.registerFlag("sam-consultant", {
		type: "string",
		description: "SAM: provider/model used by sam_consult (default: models/catalog.json defaults.consultant; 'none' turns it off)",
	});

	const flag = (name: string, env: string): string | undefined => {
		const v = pi.getFlag(name);
		return typeof v === "string" && v ? v : process.env[env] || undefined;
	};

	const cfg: SamConfig = { home: HOME, output: path.resolve(process.cwd(), "output"), privacy: "auto", approve: "ask" };
	let rules = "";
	let configWarnings: string[] = [];
	// set once individual-level data has entered this session's transcript (privacy was off when it was read)
	let tainted = false;

	/** Unknown privacy values fail safe (on); unknown approval values fall back to ask. */
	const parsePrivacy = (v: string | undefined): SamConfig["privacy"] => {
		const x = (v ?? "auto").trim().toLowerCase();
		if (x === "auto" || x === "on" || x === "off") return x;
		configWarnings.push(`unknown privacy value '${v}'; using 'on'`);
		return "on";
	};
	const parseApprove = (v: string | undefined): SamConfig["approve"] => {
		const x = (v ?? "ask").trim().toLowerCase();
		if (x === "ask" || x === "allow" || x === "deny") return x;
		configWarnings.push(`unknown approval value '${v}'; using 'ask'`);
		return "ask";
	};

	const resolveConfig = () => {
		const input = flag("sam-input", "SAM_INPUT");
		const resource = flag("sam-resource", "SAM_RESOURCE");
		cfg.input = input ? path.resolve(input) : cfg.input;
		cfg.resource = resource ? path.resolve(resource) : cfg.resource;
		cfg.output = path.resolve(flag("sam-output", "SAM_OUTPUT") ?? path.join(process.cwd(), "output"));
		cfg.build = flag("sam-build", "SAM_BUILD");
		cfg.threads = flag("sam-threads", "SAM_THREADS");
		configWarnings = [];
		cfg.privacy = parsePrivacy(flag("sam-privacy", "SAM_PRIVACY"));
		cfg.approve = parseApprove(flag("sam-approve", "SAM_APPROVE"));
		const consultant = flag("sam-consultant", "SAM_CONSULTANT");
		cfg.consultant = consultant?.toLowerCase() === "none" ? undefined : (consultant ?? catalogConsultant());
		exportEnv();
	};

	const exportEnv = () => {
		// lets the model write `$SAM_INPUT` etc. in shell commands (the guard expands them too)
		if (cfg.input) process.env.SAM_INPUT = cfg.input;
		if (cfg.resource) process.env.SAM_RESOURCE = cfg.resource;
		process.env.SAM_OUTPUT = cfg.output;
		process.env.SAM_HOME = HOME;
	};

	const isLocalModel = (ctx: Ctx): boolean => {
		const m = ctx.model;
		if (!m) return false;
		if (LOCAL_PROVIDERS.has(String(m.provider).toLowerCase())) return true;
		try {
			return LOCAL_HOSTS.has(new URL(m.baseUrl).hostname);
		} catch {
			return false;
		}
	};

	const privacyActive = (ctx: Ctx): boolean =>
		cfg.privacy === "on" || (cfg.privacy === "auto" && !isLocalModel(ctx));

	const guardConfig = (ctx: Ctx): GuardConfig => ({
		cwd: ctx.cwd,
		output: cfg.output,
		input: cfg.input,
		resource: cfg.resource,
		privacy: privacyActive(ctx),
	});

	const updateStatus = (ctx: Ctx) => {
		if (!ctx.hasUI) return;
		const data = cfg.input ? path.basename(cfg.input) : "no input (/sam-data)";
		ctx.ui.setStatus("sam", `SAM ▸ ${data} │ privacy ${privacyActive(ctx) ? "on" : "off"}${tainted ? " │ local-only session" : ""}`);
	};

	/** A tainted session must not be continued with a cloud model (its transcript holds individual-level data). */
	const cloudBlocked = (ctx: Ctx): boolean => tainted && !isLocalModel(ctx) && cfg.privacy !== "off";
	const TAINT_MSG =
		"SAM: this session's transcript contains individual-level data read with a local model, so it cannot be " +
		"continued with a cloud model. Switch back to a local model (/model) or start a new session (/new).";

	/** Would this allowed call read individual-level data? (checked as if privacy were on) */
	const readsIndividualData = (toolName: string, input: Record<string, unknown>, g: GuardConfig): boolean => {
		const strict = { ...g, privacy: true };
		let v: { block: boolean; reason?: string } = { block: false };
		if (toolName === "bash") v = checkBash(String(input.command ?? ""), strict);
		else if (toolName === "read") v = checkReadPath(String(input.path ?? ""), strict);
		else if (toolName === "grep") v = checkSearchPath(input.path ? String(input.path) : undefined, strict);
		return v.block && String(v.reason).startsWith("privacy mode");
	};

	// ── lifecycle ──────────────────────────────────────────────────────────────
	pi.on("session_start", async (_event, ctx) => {
		resolveConfig();
		// restore per-session state recorded on this branch (survives /resume, /fork, /reload)
		tainted = false;
		for (const e of ctx.sessionManager.getBranch()) {
			if (e.type !== "custom") continue;
			const data = (e as { data?: Record<string, unknown> }).data ?? {};
			if (e.customType === "sam-taint") tainted = true;
			if (e.customType === "sam-privacy" && typeof data.mode === "string") cfg.privacy = parsePrivacy(data.mode);
			if (e.customType === "sam-data" && typeof data.input === "string") {
				cfg.input = data.input;
				if (typeof data.resource === "string") cfg.resource = data.resource;
			}
		}
		exportEnv();
		const rulesFile = path.join(PKG, "RULES.md");
		rules = fs.existsSync(rulesFile) ? fs.readFileSync(rulesFile, "utf8") : "";
		updateStatus(ctx);
		if (ctx.hasUI) {
			for (const w of configWarnings) ctx.ui.notify(`SAM: ${w}`, "warning");
			if (!cfg.input) ctx.ui.notify("SAM: input directory not set. Use /sam-data <input-dir> [resource-dir].", "warning");
			if (process.env.SAM_SANDBOX === "none")
				ctx.ui.notify("SAM: Landlock is not available here; input/resource are protected by command checks only.", "warning");
			if (cloudBlocked(ctx)) ctx.ui.notify(TAINT_MSG, "error");
		}
	});

	pi.on("model_select", async (_event, ctx) => {
		updateStatus(ctx);
		if (cloudBlocked(ctx) && ctx.hasUI) ctx.ui.notify(TAINT_MSG, "error");
	});

	pi.on("input", async (_event, ctx) => {
		if (!cloudBlocked(ctx)) return { action: "continue" as const };
		if (ctx.hasUI) ctx.ui.notify(TAINT_MSG, "error");
		else process.stderr.write(`${TAINT_MSG}\n`);
		return { action: "handled" as const };
	});

	pi.on("user_bash", async (event, ctx) => {
		// the user's own `!command` output also enters the model context (unless `!!` is used)
		if (event.excludeFromContext || !privacyActive(ctx)) return undefined;
		const v = checkBash(event.command, guardConfig(ctx));
		if (!v.block || !String(v.reason).startsWith("privacy mode")) return undefined;
		return {
			result: {
				output: `SAM privacy: ${v.reason}\nUse !!command to run it without sending the output to the model.`,
				exitCode: 1,
				cancelled: false,
				truncated: false,
			},
		};
	});

	pi.on("session_shutdown", async () => stopAll());

	pi.on("resources_discover", async () => ({
		skillPaths: [path.join(PKG, "skills")],
		promptPaths: [path.join(PKG, "prompts")],
	}));

	pi.on("before_agent_start", async (event, ctx) => {
		const runtime = [
			"## Current SAM session",
			`- input directory (read-only): ${cfg.input ?? "NOT SET — ask the user, then they run /sam-data"}`,
			`- resource directory (read-only): ${cfg.resource ?? "not set"}`,
			`- output directory: ${cfg.output}`,
			`- privacy mode: ${privacyActive(ctx) ? "ON — individual-level files are blocked for you" : cfg.privacy === "off" ? "off (turned off by the user)" : "off (local model)"}`,
			`- approvals (installs, downloads, partial PRS): ${cfg.approve}${cfg.approve === "ask" && !ctx.hasUI ? " (no UI: behaves as deny)" : ""}`,
			...(KERNEL_RO.length && kernelReadOnly(cfg.input) && kernelReadOnly(cfg.resource)
				? ["- the operating system refuses writes into the input/resource directories (Permission denied); do not look for another way, write under the output directory"]
				: []),
		].join("\n");
		event.systemPromptOptions.sections.sam_harness = `${rules}\n\n${runtime}`;
	});

	// ── guards on built-in tools ───────────────────────────────────────────────
	pi.on("tool_call", async (event, ctx) => {
		const g = guardConfig(ctx);
		const input = event.input as Record<string, unknown>;
		let v = { block: false } as { block: boolean; reason?: string };
		switch (event.toolName) {
			case "bash":
				v = checkBash(String(input.command ?? ""), g);
				break;
			case "write":
			case "edit":
				v = checkWritePath(String(input.path ?? input.file_path ?? ""), g);
				break;
			case "read":
				v = checkReadPath(String(input.path ?? input.file_path ?? ""), g);
				break;
			case "grep":
				v = checkSearchPath(input.path ? String(input.path) : undefined, g);
				break;
		}
		if (v.block) {
			if (ctx.hasUI) ctx.ui.notify(`SAM guard: ${v.reason}`, "warning");
			return { block: true, reason: v.reason };
		}
		if (!g.privacy && !tainted && readsIndividualData(event.toolName, input, g)) {
			tainted = true;
			pi.appendEntry("sam-taint", { tool: event.toolName, at: new Date().toISOString() });
			updateStatus(ctx);
		}
		return undefined;
	});

	// ── helpers for tools ──────────────────────────────────────────────────────
	const approve = async (ctx: Ctx, title: string, message: string): Promise<boolean> => {
		if (cfg.approve === "allow") return true;
		if (cfg.approve === "deny" || !ctx.hasUI) return false;
		return ctx.ui.confirm(title, message);
	};

	const asText = (r: SamResult): string => {
		const { tools: _tools, ...rest } = r as Record<string, unknown>;
		let s = JSON.stringify(rest, null, 1);
		if (s.length > MAX_RESULT_CHARS) s = `${s.slice(0, MAX_RESULT_CHARS)}\n… (truncated; full summary in the step's summary.json)`;
		return s;
	};

	const images = (ctx: Ctx, r: SamResult) => {
		const out: { type: "image"; data: string; mimeType: string }[] = [];
		const supports = (ctx.model as unknown as { input?: string[] } | undefined)?.input?.includes("image");
		if (!supports) return out;
		const outputs = (r.outputs ?? {}) as Record<string, string>;
		for (const rel of Object.values(outputs)) {
			if (!rel.endsWith(".png")) continue;
			const abs = path.isAbsolute(rel) ? rel : path.resolve(ctx.cwd, rel);
			if (fs.existsSync(abs) && fs.statSync(abs).size < 3_000_000)
				out.push({ type: "image", data: fs.readFileSync(abs).toString("base64"), mimeType: "image/png" });
		}
		return out.slice(0, 2);
	};

	const call = async (
		args: string[],
		signal: AbortSignal | undefined,
		onUpdate: ((r: { content: { type: "text"; text: string }[]; details: unknown }) => void) | undefined,
		ctx: Ctx,
		opts: { needsInput?: boolean; withImages?: boolean } = {},
	) => {
		const r = await runSamkit(cfg, args, {
			signal,
			needsInput: opts.needsInput,
			onProgress: (lines) => onUpdate?.({ content: [{ type: "text", text: lines.join("\n") }], details: { progress: true } }),
		});
		if (!r.ok) throw new Error(`${r.error}${r.hint ? `\nhint: ${r.hint}` : ""}`);
		return {
			content: [{ type: "text" as const, text: asText(r) }, ...(opts.withImages ? images(ctx, r) : [])],
			details: { step: r.step, key: r.key, outputs: r.outputs, warnings: r.warnings },
		};
	};

	const opt = (flagName: string, value: unknown): string[] =>
		value === undefined || value === null || value === "" ? [] : [flagName, String(value)];
	const oneOf = <T extends string>(desc: string, values: readonly T[]) =>
		Type.String({ description: `${desc} (one of: ${values.join(", ")})`, enum: [...values] });

	// ── tools ───────────────────────────────────────────────────────────────────
	pi.registerTool({
		name: "sam_status",
		label: "SAM status",
		description:
			"Show the SAM session: input/resource/output directories, genotype filesets and tables found in the input " +
			"directory (column names and row counts only), reference resources (LDSC panel, genetic map, dbSNP map, " +
			"PRS-CS LD reference with chromosomes), installed tools, and completed steps. Read-only; run it first.",
		promptSnippet: "sam_status — what data, resources, tools and finished steps exist",
		parameters: Type.Object({}),
		async execute(_id, _p, signal, onUpdate, ctx) {
			return call(["status"], signal, onUpdate, ctx);
		},
	});

	pi.registerTool({
		name: "sam_doctor",
		label: "SAM doctor",
		description:
			"Check only the tools and resources needed by the given step(s): gwas, plots, peaks, ldsc, regional, finemap, prs, pheweb. " +
			"Reports versions and which pixi environment would need installing. Read-only.",
		promptSnippet: "sam_doctor — check the tools/resources of one step before running it",
		parameters: Type.Object({
			steps: Type.Array(oneOf("step", ["gwas", "plots", "peaks", "ldsc", "regional", "finemap", "prs", "pheweb"] as const)),
		}),
		async execute(_id, p, signal, onUpdate, ctx) {
			// tools and resources only: works before /sam-data sets an input directory
			return call(["doctor", ...p.steps.flatMap((s) => ["--step", s])], signal, onUpdate, ctx, { needsInput: false });
		},
	});

	pi.registerTool({
		name: "sam_setup",
		executionMode: "sequential", // analyses share output folders and CPUs
		label: "SAM setup",
		description:
			"Install the analysis environments needed by the given steps into the harness (pixi; no system changes). " +
			"Asks the user first. Install only what the requested step needs (see sam_doctor).",
		promptSnippet: "sam_setup — install missing tools for a step (user approval)",
		parameters: Type.Object({
			steps: Type.Array(oneOf("step", ["gwas", "plots", "peaks", "ldsc", "regional", "finemap", "prs", "pheweb"] as const)),
		}),
		async execute(_id, p, signal, onUpdate, ctx) {
			const ok = await approve(ctx, "SAM: install tools?", `Install the environments needed for: ${p.steps.join(", ")}`);
			if (!ok) throw new Error("installation was not approved by the user");
			return call(["setup", ...p.steps.flatMap((s) => ["--step", s])], signal, onUpdate, ctx, { needsInput: false });
		},
	});

	pi.registerTool({
		name: "sam_gwas",
		executionMode: "sequential", // analyses share output folders and CPUs
		label: "SAM GWAS (regenie)",
		description:
			"Run a GWAS with regenie. stage=prepare: sample QC, step-1 variant set, PCA, and the phenotype/covariate table " +
			"(matches the phenotype file's ID column to the genotype samples; adds PCs). stage=step1 / step2: regenie whole-genome " +
			"regression and association tests (binary traits use Firth). stage=all runs the three in order. " +
			"Returns sample counts, λGC, number of genome-wide significant variants/loci and top hits. Long-running (minutes to an hour).",
		promptSnippet: "sam_gwas — regenie GWAS (prepare → step1 → step2)",
		parameters: Type.Object({
			stage: oneOf("which stage", ["prepare", "step1", "step2", "all"] as const),
			phenotype: Type.String({ description: "phenotype column name, e.g. HDL" }),
			phenotype_file: Type.Optional(Type.String({ description: "phenotype table in the input directory (prepare/all)" })),
			genotype: Type.Optional(Type.String({ description: "genotype fileset name if there are several" })),
			vcf: Type.Optional(Type.String({ description: "VCF to convert when no PLINK fileset exists" })),
			trait: Type.Optional(oneOf("trait type; omit to auto-detect", ["qt", "bt"] as const)),
			covariates: Type.Optional(Type.Array(Type.String(), { description: "covariate columns; default AGE,SEX if present" })),
			n_pc: Type.Optional(Type.Integer({ description: "number of PCs used as covariates (default 4)" })),
			chromosomes: Type.Optional(Type.String({ description: "step2 only: restrict, e.g. '11' or '1-3,11' (partial genome)" })),
		}),
		async execute(_id, p, signal, onUpdate, ctx) {
			const args = ["gwas", p.stage, "--pheno", p.phenotype, ...opt("--pheno-file", p.phenotype_file), ...opt("--geno", p.genotype),
				...opt("--vcf", p.vcf), ...opt("--trait", p.trait), ...opt("--n-pc", p.n_pc), ...opt("--chroms", p.chromosomes),
				...(p.covariates ? ["--covars", p.covariates.join(",")] : [])];
			return call(args, signal, onUpdate, ctx);
		},
	});

	pi.registerTool({
		name: "sam_plots",
		executionMode: "sequential", // analyses share output folders and CPUs
		label: "SAM Manhattan/QQ",
		description: "Draw Manhattan and QQ plots for a finished GWAS and report λGC. Output: output/plots/<phenotype>/.",
		promptSnippet: "sam_plots — Manhattan + QQ plots",
		parameters: Type.Object({ phenotype: Type.String() }),
		async execute(_id, p, signal, onUpdate, ctx) {
			return call(["plots", "--pheno", p.phenotype], signal, onUpdate, ctx, { withImages: true });
		},
	});

	pi.registerTool({
		name: "sam_peaks",
		executionMode: "sequential", // analyses share output folders and CPUs
		label: "SAM peaks",
		description:
			"List independent genome-wide significant loci (distance clumping) with lead variant ID, position, alleles, beta and −log10P. " +
			"Use it to let the user pick a locus for regional plots / fine-mapping.",
		promptSnippet: "sam_peaks — independent significant loci (for choosing a locus)",
		parameters: Type.Object({
			phenotype: Type.String(),
			p_threshold: Type.Optional(Type.Number({ description: "default 5e-8" })),
			window_kb: Type.Optional(Type.Integer({ description: "clumping distance, default 500" })),
		}),
		async execute(_id, p, signal, onUpdate, ctx) {
			return call(["peaks", "--pheno", p.phenotype, ...opt("--p", p.p_threshold), ...opt("--window-kb", p.window_kb)], signal, onUpdate, ctx);
		},
	});

	pi.registerTool({
		name: "sam_ldsc",
		executionMode: "sequential", // analyses share output folders and CPUs
		label: "SAM LDSC",
		description:
			"LD score regression SNP heritability (Python 3 ldsc). Needs genome-wide GWAS results and the LDSC reference panel. " +
			"Returns h2 (SE), intercept, ratio, λGC, mean χ², number of regression SNPs, and sanity warnings.",
		promptSnippet: "sam_ldsc — SNP heritability with LDSC",
		parameters: Type.Object({
			phenotype: Type.String(),
			population_prevalence: Type.Optional(Type.Number({ description: "binary traits: for liability-scale h2" })),
			model: Type.Optional(
				oneOf("base = standard univariate h2 (default); baseline = stratified LDSC with all panel annotations", [
					"base",
					"baseline",
				] as const),
			),
		}),
		async execute(_id, p, signal, onUpdate, ctx) {
			return call(["ldsc", "--pheno", p.phenotype, ...opt("--pop-prev", p.population_prevalence), ...opt("--model", p.model)], signal, onUpdate, ctx, {
				withImages: true,
			});
		},
	});

	const locusParams = {
		phenotype: Type.String(),
		locus: Type.String({ description: "lead variant: 'CHR:POS', a variant ID, or a rank from sam_peaks (e.g. '1')" }),
		window_kb: Type.Optional(Type.Integer({ description: "± window in kb (default 500)" })),
	};

	pi.registerTool({
		name: "sam_regional",
		executionMode: "sequential", // analyses share output folders and CPUs
		label: "SAM regional plot",
		description:
			"Regional association plot around a lead variant: LD r² with the lead (computed in the GWAS samples), recombination " +
			"rate, build-matched gene track, and SuSiE credible sets if fine-mapping was done. The locus should be chosen by the user.",
		promptSnippet: "sam_regional — regional association plot for a chosen locus",
		parameters: Type.Object(locusParams),
		async execute(_id, p, signal, onUpdate, ctx) {
			return call(["regional", "--pheno", p.phenotype, "--locus", p.locus, ...opt("--window-kb", p.window_kb)], signal, onUpdate, ctx, {
				withImages: true,
			});
		},
	});

	pi.registerTool({
		name: "sam_finemap",
		executionMode: "sequential", // analyses share output folders and CPUs
		label: "SAM fine-mapping (SuSiE)",
		description:
			"SuSiE-RSS fine-mapping of a locus with in-sample LD (alleles aligned to the LD matrix). Returns credible sets " +
			"(size, purity, top variant/PIP), top PIPs, convergence and an LD-consistency diagnostic.",
		promptSnippet: "sam_finemap — SuSiE fine-mapping for a chosen locus",
		parameters: Type.Object({
			...locusParams,
			L: Type.Optional(Type.Integer({ description: "max number of causal signals (default 10)" })),
			coverage: Type.Optional(Type.Number({ description: "credible set coverage (default 0.95)" })),
			min_abs_corr: Type.Optional(Type.Number({ description: "purity threshold (default 0.5, susieR default)" })),
		}),
		async execute(_id, p, signal, onUpdate, ctx) {
			const args = ["finemap", "--pheno", p.phenotype, "--locus", p.locus, ...opt("--window-kb", p.window_kb), ...opt("--L", p.L),
				...opt("--coverage", p.coverage), ...opt("--min-abs-corr", p.min_abs_corr)];
			return call(args, signal, onUpdate, ctx, { withImages: true });
		},
	});

	pi.registerTool({
		name: "sam_pheweb",
		executionMode: "sequential", // analyses share output folders and CPUs
		label: "SAM KNIH PheWeb",
		description:
			"KNIH PheWeb (Korean GWAS summary statistics and PRS weights). action=search: find phenotypes by name/code across " +
			"cohorts (KBA+BBJ, KBA_126K, KBA_187K, ...) and PRS weights; returns codes and GWAS N. action=download: download one " +
			"code into output/downloads/pheweb (asks the user, showing URL and size). An interrupted download resumes from " +
			"the partial file when the same code is downloaded again.",
		promptSnippet: "sam_pheweb — search/download KNIH PheWeb sumstats or PRS weights",
		parameters: Type.Object({
			action: oneOf("action", ["search", "download"] as const),
			query: Type.Optional(Type.String({ description: "search words, e.g. 'hypertension'" })),
			code: Type.Optional(Type.String({ description: "download: code from search, e.g. KBA_187K_HTN or HTN_PRS_weight" })),
			kind: Type.Optional(oneOf("filter", ["sumstats", "prs_weight"] as const)),
		}),
		async execute(_id, p, signal, onUpdate, ctx) {
			if (p.action === "search") {
				if (!p.query) throw new Error("query is required for search");
				return call(["pheweb", "search", ...p.query.split(/\s+/), ...opt("--kind", p.kind)], signal, onUpdate, ctx);
			}
			if (!p.code) throw new Error("code is required for download");
			const head = await runSamkit(cfg, ["pheweb", "head", "--code", p.code], { signal });
			if (!head.ok) throw new Error(`${head.error}${head.hint ? `\nhint: ${head.hint}` : ""}`);
			if (!head.exists) {
				const ok = await approve(
					ctx,
					"SAM: download from KNIH PheWeb?",
					`${head.phenotype} (${head.cohort})\nURL: ${head.url}\nsize: ${head.size_mb ?? "?"} MB\nto: ${head.destination}`,
				);
				if (!ok) throw new Error("download was not approved by the user");
			}
			return call(["pheweb", "download", "--code", p.code], signal, onUpdate, ctx);
		},
	});

	pi.registerTool({
		name: "sam_prs",
		executionMode: "sequential", // analyses share output folders and CPUs
		label: "SAM PRS",
		description:
			"Polygenic risk scores on the target genotypes (plink2 --score). method=weights: score with an existing weight file " +
			"(e.g. KNIH PheWeb *_PRS_weight). method=prscs: build weights with PRS-CS from EXTERNAL GWAS summary statistics " +
			"(PheWeb format, or columns SNP A1 A2 BETA with SE or P) and an LD reference, then score. Target variants are linked to rsIDs and alleles are checked " +
			"automatically. Returns match rates, chromosomes covered and the score distribution (no individual scores). " +
			"Results from this harness's own GWAS are not accepted as PRS-CS input.",
		promptSnippet: "sam_prs — PRS from weights or PRS-CS (external sumstats)",
		parameters: Type.Object({
			method: oneOf("method", ["weights", "prscs"] as const),
			weights_file: Type.Optional(Type.String({ description: "weights: file in input dir or output/downloads/..." })),
			sumstats_file: Type.Optional(Type.String({ description: "prscs: external summary statistics file" })),
			n_gwas: Type.Optional(Type.Integer({ description: "prscs: GWAS sample size (auto for PheWeb downloads)" })),
			chromosomes: Type.Optional(Type.String({ description: "prscs: subset, e.g. '16' (partial score; user must agree)" })),
			ancestry: Type.Optional(Type.String({ description: "prscs: LD reference ancestry, default EAS" })),
			name: Type.Optional(Type.String({ description: "result name (folder under output/prs/)" })),
			genotype: Type.Optional(Type.String()),
		}),
		async execute(_id, p, signal, onUpdate, ctx) {
			if (p.method === "weights") {
				if (!p.weights_file) throw new Error("weights_file is required for method=weights");
				return call(["prs", "score", "--weights", p.weights_file, ...opt("--name", p.name), ...opt("--geno", p.genotype)], signal, onUpdate, ctx);
			}
			if (!p.sumstats_file) throw new Error("sumstats_file is required for method=prscs");
			const base = ["prs", "prscs", "--sumstats", p.sumstats_file, ...opt("--n-gwas", p.n_gwas), ...opt("--chroms", p.chromosomes),
				...opt("--ancestry", p.ancestry), ...opt("--name", p.name), ...opt("--geno", p.genotype)];
			const first = await runSamkit(cfg, base, {
				signal,
				onProgress: (l) => onUpdate?.({ content: [{ type: "text", text: l.join("\n") }], details: { progress: true } }),
			});
			if (first.ok) return { content: [{ type: "text" as const, text: asText(first) }], details: { step: first.step, outputs: first.outputs } };
			if (!String(first.error).includes("not genome-wide")) throw new Error(`${first.error}${first.hint ? `\nhint: ${first.hint}` : ""}`);
			const ok = await approve(ctx, "SAM: partial PRS?", `${first.error}\n\nA partial score is not a genome-wide PRS. Continue?`);
			if (!ok) throw new Error(`${first.error} — the user did not approve a partial score`);
			return call([...base, "--allow-partial"], signal, onUpdate, ctx);
		},
	});

	pi.registerTool({
		name: "sam_report",
		executionMode: "sequential", // analyses share output folders and CPUs
		label: "SAM report",
		description: "Collect the latest summary of every finished step into output/report.md (summary-level numbers and plot links).",
		promptSnippet: "sam_report — write output/report.md",
		parameters: Type.Object({}),
		async execute(_id, _p, signal, onUpdate, ctx) {
			return call(["report"], signal, onUpdate, ctx);
		},
	});

	pi.registerTool({
		name: "sam_consult",
		label: "SAM consult (domain model)",
		description:
			"Ask the configured biomedical/genomics consultant model (usually a local model, see --sam-consultant) a domain " +
			"question, e.g. about known biology of a locus or how to interpret a result. Send only summary-level facts. " +
			"Treat the answer as a second opinion: verify claims, and do not present it as a tool-computed result. " +
			"When the question is about a locus, pass `region` (e.g. the ±500 kb window) so the answer is grounded in the real gene list.",
		promptSnippet: "sam_consult — second opinion from a genomics/biomedical domain model",
		parameters: Type.Object({
			question: Type.String({ description: "self-contained question with the relevant summary numbers" }),
			region: Type.Optional(
				Type.String({
					description:
						"genomic region the question is about, CHR:START-END in the analysis build (e.g. the ±500 kb window " +
						"of a locus). The harness then adds the actual gene list from Ensembl so the answer is grounded.",
				}),
			),
		}),
		async execute(_id, p, signal, _onUpdate, ctx) {
			const spec = cfg.consultant;
			if (!spec) throw new Error("no consultant model configured; start with --sam-consultant provider/model (see docs/MODELS.md)");
			const slash = spec.indexOf("/");
			const model = slash > 0 ? ctx.modelRegistry.find(spec.slice(0, slash), spec.slice(slash + 1)) : undefined;
			if (!model) throw new Error(`consultant model ${spec} not found; check models.json (./sam llm models-json)`);
			const consultantLocal = LOCAL_PROVIDERS.has(String(model.provider).toLowerCase()) ||
				(() => {
					try {
						return LOCAL_HOSTS.has(new URL(model.baseUrl).hostname);
					} catch {
						return false;
					}
				})();
			if (tainted && !consultantLocal && cfg.privacy !== "off")
				throw new Error("this session holds individual-level data; a cloud consultant model cannot be used");
			let facts = "";
			if (p.region) {
				const g = await runSamkit(cfg, ["genes", "--region", p.region], { signal });
				facts = g.ok
					? `Facts from the analysis harness (${g.source}, build ${g.build}): protein-coding genes overlapping ` +
						`${g.region}: ${(g.protein_coding_genes as string[]).join(", ") || "none"}. ` +
						"Discuss only genes in this list for this region; if your memory disagrees with it, say so.\n\n"
					: "";
			}
			const stream = ctx.modelRegistry.streamSimple(
				model,
				{
					systemPrompt:
						"You are a statistical genetics and genomic medicine consultant. Answer concisely and precisely. " +
						"State uncertainty explicitly. Do not invent citations, gene functions or numbers; say when you do not know.",
					messages: [{ role: "user", content: facts + p.question, timestamp: Date.now() }],
				},
				// explicit budget: reasoning models otherwise spend the default output budget on thinking
				{ signal, maxTokens: 4096, ...(model.reasoning ? { reasoning: "low" as const } : {}) },
			);
			const msg = await stream.result();
			const text = msg.content
				.filter((c): c is { type: "text"; text: string } => c.type === "text")
				.map((c) => c.text)
				.join("\n")
				.trim();
			if (!text)
				throw new Error(`consultant returned no text (${msg.stopReason}${msg.errorMessage ? `: ${msg.errorMessage}` : ""})`);
			return {
				content: [
					{
						type: "text" as const,
						text:
							`[UNVERIFIED second opinion from ${spec}${facts ? ", grounded with the Ensembl gene list" : ""}. ` +
							"Present it as such, check it against the harness results, and flag anything that contradicts them.]\n" +
							text,
					},
				],
				details: { consultant: spec },
				usage: msg.usage,
			};
		},
	});

	// ── commands ────────────────────────────────────────────────────────────────
	pi.registerCommand("sam", {
		description: "Show SAM settings (data directories, privacy, approvals)",
		handler: async (_args, ctx) => {
			ctx.ui.notify(
				[
					`input:     ${cfg.input ?? "(not set)"}`,
					`resource:  ${cfg.resource ?? "(not set)"}`,
					`output:    ${cfg.output}`,
					`privacy:   ${cfg.privacy} → ${privacyActive(ctx) ? "on" : "off"} for ${ctx.model?.provider ?? "?"}/${ctx.model?.id ?? "?"}`,
					`approvals: ${cfg.approve}`,
					`consultant: ${cfg.consultant ?? "(none)"}`,
					`read-only: ${KERNEL_RO.length ? (kernelReadOnly(cfg.input) && kernelReadOnly(cfg.resource) ? "kernel (Landlock) + command checks" : `command checks; ${READ_ONLY_NOTE}`) : "command checks only"}`,
				].join("\n"),
				"info",
			);
		},
	});

	pi.registerCommand("sam-data", {
		description: "Set data directories: /sam-data <input-dir> [resource-dir] (quote paths with spaces)",
		handler: async (args, ctx) => {
			const parts = ((args ?? "").match(/"[^"]*"|'[^']*'|\S+/g) ?? []).map((a) => a.replace(/^["']|["']$/g, ""));
			const [inp, res] = parts;
			if (!inp) return ctx.ui.notify("usage: /sam-data <input-dir> [resource-dir]", "warning");
			for (const d of [inp, res].filter(Boolean) as string[])
				if (!fs.existsSync(d) || !fs.statSync(d).isDirectory()) return ctx.ui.notify(`not a directory: ${d}`, "error");
			const input = path.resolve(inp);
			const resource = res ? path.resolve(res) : cfg.resource;
			// one output directory belongs to one dataset (samkit refuses to mix them)
			const bound = path.join(cfg.output, "sam.json");
			if (fs.existsSync(bound)) {
				const meta = JSON.parse(fs.readFileSync(bound, "utf8")) as { input?: string; resource?: string };
				if ((meta.input && meta.input !== input) || (res && meta.resource && meta.resource !== resource))
					return ctx.ui.notify(
						`${cfg.output} already holds results for ${meta.input}. Start pi in another directory for other data.`,
						"error",
					);
			}
			cfg.input = input;
			cfg.resource = resource;
			pi.appendEntry("sam-data", { input: cfg.input, resource: cfg.resource });
			exportEnv();
			updateStatus(ctx);
			ctx.ui.notify(`SAM data: input=${cfg.input}${cfg.resource ? ` resource=${cfg.resource}` : ""}`, "info");
			if (KERNEL_RO.length && !(kernelReadOnly(cfg.input) && kernelReadOnly(cfg.resource)))
				ctx.ui.notify(`SAM: ${READ_ONLY_NOTE}`, "warning");
		},
	});

	pi.registerCommand("sam-privacy", {
		description: "Privacy mode for individual-level files: /sam-privacy auto|on|off",
		handler: async (args, ctx) => {
			const v = (args ?? "").trim().toLowerCase();
			if (!["auto", "on", "off"].includes(v)) return ctx.ui.notify("usage: /sam-privacy auto|on|off", "warning");
			if (v === "off" && !isLocalModel(ctx)) {
				const ok = await ctx.ui.confirm(
					"Turn privacy off for a cloud model?",
					"Individual-level data could then be sent to the model provider. Check your data use agreement.",
				);
				if (!ok) return;
			}
			cfg.privacy = v as SamConfig["privacy"];
			pi.appendEntry("sam-privacy", { mode: v });
			updateStatus(ctx);
			ctx.ui.notify(`SAM privacy: ${v} → ${privacyActive(ctx) ? "on" : "off"}`, "info");
		},
	});
}

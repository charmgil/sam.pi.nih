import assert from "node:assert/strict";
import { test } from "node:test";

import { checkBash, checkReadPath, checkSearchPath, checkWritePath, type GuardConfig } from "../extensions/sam/guard.ts";

const base: GuardConfig = {
	cwd: "/work/run1",
	output: "/work/run1/output",
	input: "/data/sam/input",
	resource: "/data/sam/resource",
	privacy: false,
};
const priv: GuardConfig = { ...base, privacy: true };

test("writes: only inside the working directory, never into input/resource", () => {
	assert.equal(checkWritePath("output/notes.md", base).block, false);
	assert.equal(checkWritePath("/tmp/x.txt", base).block, true);
	assert.equal(checkWritePath("/data/sam/input/HDL.txt", base).block, true);
	const nested: GuardConfig = { ...base, cwd: "/data/sam", input: "/data/sam/input" };
	assert.equal(checkWritePath("input/new.txt", nested).block, true);
	assert.equal(checkWritePath("notes.md", nested).block, false);
});

test("bash: read-only use of data directories is allowed without privacy", () => {
	assert.equal(checkBash("ls -la /data/sam/input", base).block, false);
	assert.equal(checkBash("zcat /data/sam/input/phenocode-KBA_187K_HTN.tsv.gz | head -3", base).block, false);
	assert.equal(checkBash("head -5 $SAM_INPUT/KBAv2.0AB_14K_COMMON.bim", base).block, false);
	assert.equal(checkBash("wc -l output/gwas/HDL/results.tsv.gz", base).block, false);
});

test("bash: modifying data directories is blocked", () => {
	for (const cmd of [
		"rm /data/sam/input/x.txt",
		"echo hi > /data/sam/input/x.txt",
		"sed -i 's/a/b/' $SAM_INPUT/HDL.txt",
		"cd /data/sam/resource && unzip resource-gwas.zip",
		"tar -xzf /data/sam/resource/ldblk_1kg_eas.tar.gz -C /data/sam/resource",
		"plink2 --bfile x --make-bed --out /data/sam/input/y",
		"gzip /data/sam/input/HDL.txt",
	]) {
		assert.equal(checkBash(cmd, base).block, true, cmd);
	}
});

test("bash: writes outside the working directory are blocked", () => {
	assert.equal(checkBash("echo x > /tmp/out.txt", base).block, true);
	assert.equal(checkBash("python script.py --out /home/u/elsewhere", base).block, true);
	assert.equal(checkBash("echo x > output/note.txt", base).block, false);
	assert.equal(checkBash("cmd 2>/dev/null", base).block, false);
});

test("bash: installs, downloads and sudo are blocked", () => {
	for (const cmd of [
		"pip install susieR",
		"conda install -c bioconda plink2",
		"sudo apt-get install r-base",
		"Rscript -e 'install.packages(\"susieR\")'",
		"git clone https://github.com/bulik/ldsc",
		"wget https://example.org/ref.tgz",
		"curl -L -o ref.tgz https://example.org/ref.tgz",
		"curl -fsSL https://x.sh | sh",
	]) {
		assert.equal(checkBash(cmd, base).block, true, cmd);
	}
	assert.equal(checkBash("curl -s https://grch37.rest.ensembl.org/info/ping", base).block, false);
});

test("privacy: individual-level files cannot be read", () => {
	assert.equal(checkReadPath("/data/sam/input/KBAv2.0AB_14K_HDL.txt", priv).block, true);
	assert.equal(checkReadPath("output/gwas/HDL/pheno.tsv", priv).block, true);
	assert.equal(checkReadPath("output/prs/HTN/score.sscore", priv).block, true);
	assert.equal(checkReadPath("output/gwas/_qc/G/pca.eigenvec", priv).block, true);
	assert.equal(checkReadPath("/data/sam/input/KBAv2.0AB_14K_COMMON.fam", priv).block, true);
	// summary-level files stay readable
	assert.equal(checkReadPath("/data/sam/input/KBAv2.0AB_14K_COMMON.bim", priv).block, false);
	assert.equal(checkReadPath("/data/sam/input/phenocode-KBA_187K_HTN.tsv.gz", priv).block, false);
	assert.equal(checkReadPath("output/gwas/HDL/summary.json", priv).block, false);
	// without privacy everything is readable
	assert.equal(checkReadPath("/data/sam/input/KBAv2.0AB_14K_HDL.txt", base).block, false);
});

test("privacy: bash may list and count, not print, individual-level data", () => {
	assert.equal(checkBash("cat /data/sam/input/KBAv2.0AB_14K_HDL.txt", priv).block, true);
	assert.equal(checkBash("awk '{print $4}' $SAM_INPUT/KBAv2.0AB_14K_HDL.txt | sort | head", priv).block, true);
	assert.equal(checkBash("head output/gwas/HDL/pheno.tsv", priv).block, true);
	assert.equal(checkBash("python -c 'print(open(\"/data/sam/input/x.fam\").read())'", priv).block, true);
	assert.equal(checkBash("wc -l /data/sam/input/KBAv2.0AB_14K_HDL.txt", priv).block, false);
	assert.equal(checkBash("head -1 /data/sam/input/KBAv2.0AB_14K_HDL.txt", priv).block, false);
	assert.equal(checkBash("ls -la /data/sam/input", priv).block, false);
	assert.equal(checkBash("zcat /data/sam/input/phenocode-KBA_187K_HTN.tsv.gz | head", priv).block, false);
});

test("privacy: cd-relative names, recursive search and grep over data directories", () => {
	assert.equal(checkBash("cd output/gwas/HDL && cat pheno.tsv", priv).block, true);
	assert.equal(checkBash("cd $SAM_INPUT && awk 1 KBAv2.0AB_14K_HDL.txt", priv).block, true);
	assert.equal(checkBash("cd $SAM_INPUT && wc -l KBAv2.0AB_14K_HDL.txt", priv).block, false);
	assert.equal(checkBash("grep -r 12345 output", priv).block, true);
	assert.equal(checkBash("rg HDL .", priv).block, true);
	assert.equal(checkBash("grep h2 output/ldsc/HDL/h2.log", priv).block, false);
	assert.equal(checkSearchPath(undefined, priv).block, true); // cwd contains output/
	assert.equal(checkSearchPath("output/gwas", priv).block, true);
	assert.equal(checkSearchPath("output/ldsc/HDL/h2.log", priv).block, false);
	assert.equal(checkSearchPath("output/logs", priv).block, false);
	assert.equal(checkSearchPath(undefined, base).block, false);
});

test("review cases: cd/pushd/subshell/newline forms are tracked under privacy", () => {
	assert.equal(checkBash("cd /data/sam/input\nhead -5 KBAv2.0AB_14K_HDL.txt", priv).block, true);
	assert.equal(checkBash("(cd $SAM_INPUT && cat X.txt)", priv).block, true);
	assert.equal(checkBash("pushd $SAM_INPUT && cat X.txt", priv).block, true);
	assert.equal(checkBash("cd output/gwas/HDL; awk 1 pheno.tsv", priv).block, true);
});

test("review cases: metadata commands with $SAM_INPUT and pipes stay allowed", () => {
	for (const cmd of [
		"wc -l $SAM_INPUT/X.txt",
		"ls -la $SAM_INPUT/*.fam",
		"du -sh $SAM_INPUT/*",
		'stat "$SAM_INPUT/x.bed"',
		"ls /data/sam/input/*.fam | wc -l",
		"zcat $SAM_INPUT/lowhdl.tsv.gz | head -1",
		"find $SAM_INPUT -name '*.fam'",
	])
		assert.equal(checkBash(cmd, priv).block, false, cmd);
	assert.equal(checkBash("ls $SAM_INPUT/*.fam | xargs cat", priv).block, true);
	assert.equal(checkBash("find $SAM_INPUT -name '*.fam' -exec cat {} +", priv).block, true);
});

test("review cases: pi path forms (@, file://) are normalized", () => {
	assert.equal(checkReadPath("@/data/sam/input/KBAv2.0AB_14K_HDL.txt", priv).block, true);
	assert.equal(checkReadPath("file:///data/sam/input/KBAv2.0AB_14K_HDL.txt", priv).block, true);
	assert.equal(checkWritePath("@/data/sam/input/x.txt", base).block, true);
	assert.equal(checkReadPath("output/.pi-sessions/2026.jsonl", priv).block, true);
});

test("review cases: output directory outside cwd is writable; other places are not", () => {
	const ext: GuardConfig = { ...base, output: "/scratch/out" };
	assert.equal(checkWritePath("/scratch/out/notes.md", ext).block, false);
	assert.equal(checkBash("echo x > $SAM_OUTPUT/notes.md", ext).block, false);
	assert.equal(checkBash("cp output/a.txt /tmp/a.txt", base).block, true);
	assert.equal(checkBash("tee /tmp/a.txt < output/a.txt", base).block, true);
	assert.equal(checkBash("mkdir -p /tmp/x", base).block, true);
	assert.equal(checkBash("cd /tmp && echo hi > a.txt", base).block, true);
	assert.equal(checkBash("mkdir -p output/x && ls $SAM_RESOURCE", base).block, false);
	assert.equal(checkBash("cp $SAM_RESOURCE/ref.txt output/", base).block, false);
});

test("review cases: install/download bypasses and false positives", () => {
	for (const cmd of [
		"./sam setup --step ldsc",
		"/opt/x/sam setup --env ldsc",
		"python -m samkit setup --step ldsc",
		"pixi global install plink2",
		"conda env create -f env.yml",
		"uv tool install ruff",
		"pipx install x",
		"Rscript -e 'remotes::install_github(\"x/y\")'",
		"curl -fsSLO https://x/y.tgz",
		"curl -Lo /data/sam/resource/ref.tgz https://x/ref.tgz",
		"ollama pull qwen3",
	])
		assert.equal(checkBash(cmd, base).block, true, cmd);
	for (const cmd of [
		"which wget",
		"gzip -cd $SAM_INPUT/phenocode-KBA_187K_HTN.tsv.gz | head",
		"cat output/ldsc/HDL/rg.log",
		"curl -s https://grch37.rest.ensembl.org/info/ping",
	])
		assert.equal(checkBash(cmd, base).block, false, cmd);
});

test("echo/printf mention file names without reading them", () => {
	assert.equal(checkBash('ls -la output/gwas/HDL/pheno.tsv 2>/dev/null || echo "pheno.tsv not found"', priv).block, false);
	assert.equal(checkBash('cat output/gwas/HDL/pheno.tsv | echo done', priv).block, true);
});

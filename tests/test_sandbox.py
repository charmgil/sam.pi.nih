"""Kernel read-only enforcement (samkit/sandbox.py): writes into --ro directories fail, the rest work."""

import subprocess
import sys
from pathlib import Path

import pytest

from samkit import sandbox

SANDBOX = Path(sandbox.__file__)
pytestmark = pytest.mark.skipif(sandbox.abi_version() < 1, reason="Landlock not available on this kernel")


def run_in_sandbox(tmp_path: Path, script: str, *ro: Path) -> subprocess.CompletedProcess:
    args = [sys.executable, "-I", str(SANDBOX)]
    for d in ro:
        args += ["--ro", str(d)]
    args += ["--tmpdir", str(tmp_path / "run" / "_tmp"), "--", "bash", "-c", script]
    return subprocess.run(args, cwd=tmp_path / "run", capture_output=True, text=True)


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "data" / "input").mkdir(parents=True)
    (tmp_path / "data" / "resource").mkdir()
    (tmp_path / "run" / "output").mkdir(parents=True)
    pheno = tmp_path / "data" / "input" / "pheno.txt"
    pheno.write_text("FID\tIID\tHDL\nA\tA\t40\nB\tB\t\n")
    (tmp_path / "data" / "resource" / "ref.txt").write_text("ref\n")
    return tmp_path


# each must fail: the two first are what a local model ran in the 2026-10-28 benchmark
DENIED = [
    'F="$IN/pheno.txt"; awk -F"\\t" \'NR==1||$3!=""\' "$F" > "$F.tmp" && mv "$F.tmp" "$F"',
    'python3 -c "import shutil,sys; p=sys.argv[1]; open(p+\'.tmp\',\'w\').write(\'x\'); shutil.move(p+\'.tmp\',p)" '
    '"$IN/pheno.txt"',
    'echo x >> "$IN/pheno.txt"',
    'sed -i s/A/Z/ "$IN/pheno.txt"',
    'truncate -s0 "$IN/pheno.txt"',
    'mv "$IN/pheno.txt" output/',
    'unlink "$IN/pheno.txt"',
    'mkdir "$IN/sub"',
    'ln -s /etc/hostname "$IN/link"',
    'echo x > "$RES/ref.txt"',
]


@pytest.mark.parametrize("script", DENIED)
def test_writes_into_protected_dirs_fail(tree, script):
    inp, res = tree / "data" / "input", tree / "data" / "resource"
    before = {p.name: p.read_bytes() for p in inp.iterdir()}
    r = run_in_sandbox(tree, f'IN="{inp}"; RES="{res}"; {script}', inp, res)
    assert r.returncode != 0, r.stdout + r.stderr
    assert {p.name: p.read_bytes() for p in inp.iterdir()} == before
    assert (res / "ref.txt").read_text() == "ref\n"


def test_reads_and_other_writes_work(tree):
    inp = tree / "data" / "input"
    r = run_in_sandbox(
        tree,
        f'cat "{inp}/pheno.txt" > output/copy.txt && mv output/copy.txt output/c2.txt && '
        'f=$(mktemp) && echo 1 > "$f" && echo "$SAM_SANDBOX $TMPDIR"',
        inp,
    )
    assert r.returncode == 0, r.stderr
    assert (tree / "run" / "output" / "c2.txt").read_text() == (inp / "pheno.txt").read_text()
    assert r.stdout.startswith("landlock-")


def test_tmpdir_moves_when_temp_is_an_ancestor(tree):
    # tmp_path lives under the temp directory, so the protected dir is inside $TMPDIR
    inp = tree / "data" / "input"
    r = run_in_sandbox(tree, 'f=$(mktemp) && echo "$f"', inp)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().startswith(str(tree / "run" / "_tmp"))


def test_without_protected_dirs_nothing_is_restricted(tree):
    r = run_in_sandbox(tree, 'echo "$SAM_SANDBOX"')
    assert r.returncode == 0 and r.stdout.strip() == "none"

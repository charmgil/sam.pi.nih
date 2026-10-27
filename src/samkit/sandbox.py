"""Kernel-enforced read-only data directories (Linux Landlock).

    python sandbox.py --ro DIR [--ro DIR ...] [--tmpdir DIR] -- COMMAND [ARGS ...]

Runs COMMAND so that it and every process it starts cannot create, modify, rename,
truncate or delete anything under the --ro directories; everything else keeps its
normal permissions. `./sam agent` starts pi this way. The pi guard
(pi-package/extensions/sam/guard.ts) still runs first and explains refusals; this is
the boundary behind it for writes no command pattern can see (a path held in a shell
variable, built inside a script, ...).

Landlock only grants rights, so "everything except DIR" is built from rules on every
sibling of DIR and of each of its ancestors. Consequences:
  - new entries cannot be created directly in an ancestor of DIR (e.g. the harness
    folder when the input sits inside it); existing files and subfolders there stay
    writable. If the temp directory is such an ancestor, TMPDIR moves to --tmpdir.
  - metadata changes (chmod, chown, touch) are outside Landlock's scope
  - another mount of the same files, or a hard link outside DIR, is not covered
Without Landlock (not Linux, kernel < 5.13, or Landlock not enabled) COMMAND runs
unchanged; SAM_SANDBOX in its environment tells which case applied.

Standard library only: the launcher runs this file with `python -I`.
"""

from __future__ import annotations

import ctypes
import os
import sys

SYS_CREATE_RULESET, SYS_ADD_RULE, SYS_RESTRICT_SELF = 444, 445, 446  # same numbers on every architecture
CREATE_RULESET_VERSION = 1
RULE_PATH_BENEATH = 1
PR_SET_NO_NEW_PRIVS = 38

WRITE_FILE = 1 << 1
REMOVE_DIR, REMOVE_FILE = 1 << 4, 1 << 5
MAKE_ANY = sum(1 << b for b in range(6, 13))  # char, dir, reg, sock, fifo, block, sym
REFER = 1 << 13  # ABI 2: rename/link across directories
TRUNCATE = 1 << 14  # ABI 3
FILE_RIGHTS = WRITE_FILE | TRUNCATE  # the only write rights a rule on a non-directory may carry


class _RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class _PathBeneath(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


def _libc():
    lib = ctypes.CDLL(None, use_errno=True)
    lib.syscall.restype = ctypes.c_long
    return lib


def abi_version() -> int:
    """Landlock ABI of the running kernel; 0 when Landlock is unavailable."""
    if not sys.platform.startswith("linux"):
        return 0
    v = _libc().syscall(ctypes.c_long(SYS_CREATE_RULESET), None, ctypes.c_size_t(0),
                        ctypes.c_uint32(CREATE_RULESET_VERSION))
    return max(int(v), 0)


def _within(p: str, d: str) -> bool:
    return p == d or p.startswith(d.rstrip("/") + "/")


def writable_roots(protected: list[str]) -> list[str]:
    """Every path whose subtree stays writable: siblings of the protected dirs and of their ancestors."""
    ancestors: set[str] = set()
    for p in protected:
        a = p
        while a != "/":
            a = os.path.dirname(a)
            ancestors.add(a)
    roots: set[str] = set()
    for a in sorted(ancestors):
        try:
            names = os.listdir(a)
        except OSError:
            continue
        for name in names:
            entry = os.path.join(a, name)
            if entry in ancestors or entry in protected:
                continue
            real = os.path.realpath(entry)
            # a symlink pointing into (or above) a protected dir must not open it up
            if any(_within(real, p) or _within(p, real) for p in protected):
                continue
            roots.add(real)
    return sorted(roots)


def restrict(protected: list[str]) -> int:
    """Make the protected dirs read-only for this process and its future children.

    Returns the Landlock ABI used, or 0 when nothing was applied. Call it before the
    process starts threads: Landlock restricts the calling thread (and what it spawns).
    """
    abi = abi_version()
    protected = sorted({os.path.realpath(p) for p in protected if p})
    if abi < 1 or not protected:
        return 0
    lib = _libc()
    handled = WRITE_FILE | REMOVE_DIR | REMOVE_FILE | MAKE_ANY
    if abi >= 2:
        handled |= REFER
    if abi >= 3:
        handled |= TRUNCATE
    attr = _RulesetAttr(handled)
    fd = lib.syscall(ctypes.c_long(SYS_CREATE_RULESET), ctypes.byref(attr), ctypes.c_size_t(ctypes.sizeof(attr)),
                     ctypes.c_uint32(0))
    if fd < 0:
        return 0
    try:
        for root in writable_roots(protected):
            try:
                pfd = os.open(root, os.O_PATH | os.O_CLOEXEC)
            except OSError:
                continue
            try:
                rights = handled if os.path.isdir(root) else handled & FILE_RIGHTS
                rule = _PathBeneath(rights, pfd)
                # a rule the kernel refuses only leaves that path read-only too
                lib.syscall(ctypes.c_long(SYS_ADD_RULE), ctypes.c_int(fd), ctypes.c_int(RULE_PATH_BENEATH),
                            ctypes.byref(rule), ctypes.c_uint32(0))
            finally:
                os.close(pfd)
        if lib.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            return 0
        if lib.syscall(ctypes.c_long(SYS_RESTRICT_SELF), ctypes.c_int(fd), ctypes.c_uint32(0)) != 0:
            return 0
    finally:
        os.close(fd)
    return abi


def status() -> dict:
    """For `sam doctor`: is kernel enforcement available here, and is this process under it?"""
    abi = abi_version()
    return {
        "landlock_abi": abi,
        "enforced_here": os.environ.get("SAM_SANDBOX", "none"),
        "note": "input/resource are read-only at kernel level under ./sam agent" if abi else
                "Landlock unavailable (needs Linux >= 5.13 with landlock in the LSM list); "
                "input/resource are protected by the agent's command checks only",
    }


def main(argv: list[str]) -> None:
    ro: list[str] = []
    tmpdir = ""
    while argv and argv[0] != "--":
        if argv[0] in ("--ro", "--tmpdir") and len(argv) > 1:
            if argv[0] == "--tmpdir":
                tmpdir = argv[1]
            elif argv[1]:
                ro.append(argv[1])
            argv = argv[2:]
        else:
            sys.exit(f"sandbox: unexpected argument {argv[0]!r} (usage: --ro DIR ... [--tmpdir DIR] -- COMMAND ...)")
    cmd = argv[1:]
    if not cmd:
        sys.exit("sandbox: no command given")
    protected = [os.path.realpath(p) for p in ro]
    tmp = os.path.realpath(os.environ.get("TMPDIR") or "/tmp")
    if tmpdir and any(_within(p, tmp) for p in protected):
        os.makedirs(tmpdir, exist_ok=True)
        os.environ["TMPDIR"] = tmpdir
    abi = restrict(protected)
    os.environ["SAM_SANDBOX"] = f"landlock-{abi}" if abi else "none"
    os.environ["SAM_SANDBOX_RO"] = os.pathsep.join(protected) if abi else ""
    os.execvp(cmd[0], cmd)


if __name__ == "__main__":
    main(sys.argv[1:])

#!/usr/bin/env python3
"""OS-level isolation check (rule R04 §31; acceptance criteria AC-09, AC-26, AC-27).

Verifies, from file ownership and mode bits, that protected storage is not readable or writable
by the sandbox/agent uid, and that only the kernel uid owns it. Run as the kernel user in the
deployment environment:

    python tools/check_os_isolation.py --root . --kernel-uid $(id -u) --sandbox-uid <uid of the test/agent user>

Exit code 0 = all checks pass; 1 = at least one failure. The check is deterministic and does not
attempt to switch users; it inspects the permission bits that the OS will enforce. On Windows
without WSL the POSIX bits are not meaningful and the script reports NOT_APPLICABLE.
"""
from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

PROTECTED = ["state/twe", "state/approvals", "state/audit.jsonl", "state/police.jsonl", "permissions.toml", "constitution.toml", "kernel", "state"]


def check(path: Path, kernel_uid: int, sandbox_uid: int) -> tuple[str, str]:
    if not path.exists():
        return "SKIP", "absent"
    st = path.stat()
    mode = st.st_mode
    if st.st_uid != kernel_uid:
        return "FAIL", f"owner uid {st.st_uid} != kernel uid {kernel_uid}"
    if st.st_uid == sandbox_uid:
        return "FAIL", "owned by the sandbox uid"
    if mode & (stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH):
        return "FAIL", f"world-accessible mode {oct(mode & 0o777)}"
    if mode & (stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP):
        return "WARN", f"group-accessible mode {oct(mode & 0o777)}; verify the sandbox uid is not in gid {st.st_gid}"
    return "PASS", oct(mode & 0o777)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--kernel-uid", type=int, default=os.getuid() if hasattr(os, "getuid") else -1)
    ap.add_argument("--sandbox-uid", type=int, required=True)
    a = ap.parse_args()
    if os.name != "posix":
        print("NOT_APPLICABLE: POSIX permission bits are not enforced on this platform; use WSL, a Linux VM or the Docker wrapper.")
        return 1
    root = Path(a.root).resolve()
    failures = 0
    for rel in PROTECTED:
        status, detail = check(root / rel, a.kernel_uid, a.sandbox_uid)
        print(f"{status:5} {rel:22} {detail}")
        failures += status == "FAIL"
    ws = root / "workspace"
    if ws.exists():
        st = ws.stat()
        print(f"INFO  workspace              owner uid {st.st_uid}, mode {oct(st.st_mode & 0o777)} (tests run here under the sandbox uid or wrapper)")
    print("RESULT:", "PASS" if failures == 0 else f"FAIL ({failures})")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

"""Policy engine: decides whether a proposal is even eligible for human review.

The policy engine is a pure function of (constitution, proposal). It has no
access to the model and the model has no access to it. Its decisions are:

  BLOCK    - violates a constraint; not presented to the human for approval
             (reported as a violation instead).
  ESCALATE - permitted by the path rules but matches an escalation flag; shown to the
             human with a HIGH RISK banner and the list of flags.
  REVIEW   - no flags; shown to the human for approval.

There is no "AUTO" decision in the seed kernel. Autonomy level 1 means a human
approves every mutation.
"""
from __future__ import annotations

import fnmatch
import posixpath
import re
from dataclasses import dataclass, field

from .constitution import Constitution
from .model import Proposal


@dataclass
class Decision:
    verdict: str                      # BLOCK | ESCALATE | REVIEW
    flags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return self.verdict == "BLOCK"


def _norm(path: str) -> str:
    p = path.replace("\\", "/").lstrip("/")
    p = posixpath.normpath(p)
    return p


def _matches_any(path: str, globs) -> bool:
    for g in globs:
        if fnmatch.fnmatchcase(path, g):
            return True
        # fnmatch's "*" matches "/" so "src/**" already covers nested paths; also
        # handle patterns like "**/conftest.py" against bare file names.
        if g.startswith("**/") and fnmatch.fnmatchcase(path, g[3:]):
            return True
    return False


def path_is_safe(path: str) -> bool:
    """Reject absolute paths, drive letters, traversal and hidden control files."""
    if not path or len(path) > 400:
        return False
    if path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", path):
        return False
    norm = _norm(path)
    if norm.startswith("..") or "/../" in f"/{norm}/":
        return False
    if any(part in ("", ".", "..") for part in norm.split("/")):
        return False
    return True


def evaluate(c: Constitution, proposal: Proposal) -> Decision:
    d = Decision(verdict="REVIEW")
    paths = c.section("paths")
    budget = c.section("budget")
    monitor = c.section("monitor")

    if proposal.abstain:
        d.verdict = "REVIEW"
        d.reasons.append("model abstained; nothing to apply")
        return d

    # --- size limits --------------------------------------------------------
    if len(proposal.files) == 0:
        return Decision(verdict="BLOCK", flags=["empty"], reasons=["proposal contains no files and did not abstain"])
    if len(proposal.files) > int(budget["max_patch_files"]):
        d.verdict = "BLOCK"; d.flags.append("too_many_files")
        d.reasons.append(f"{len(proposal.files)} files > max_patch_files={budget['max_patch_files']}")
    total = sum(len(v or "") for v in proposal.files.values())
    if total > int(budget["max_patch_total_chars"]):
        d.verdict = "BLOCK"; d.flags.append("patch_too_large")
        d.reasons.append(f"{total} chars > max_patch_total_chars={budget['max_patch_total_chars']}")

    # --- path rules ---------------------------------------------------------
    for raw in proposal.files:
        if not path_is_safe(raw):
            d.verdict = "BLOCK"; d.flags.append("unsafe_path"); d.reasons.append(f"unsafe path: {raw!r}")
            continue
        p = _norm(raw)
        if _matches_any(p, paths["denied_globs"]):
            d.verdict = "BLOCK"; d.flags.append("denied_path"); d.reasons.append(f"denied path: {p}")
            if p.startswith(("kernel/", "state/")) or p == "constitution.toml":
                d.flags.append("self_modification")
            continue
        if not _matches_any(p, paths["allowed_write_globs"]):
            d.verdict = "BLOCK"; d.flags.append("path_not_allowed"); d.reasons.append(f"path not in allowed_write_globs: {p}")
        if _matches_any(p, paths.get("protected_test_globs", ())):
            d.flags.append("protected_test_change"); d.reasons.append(f"touches protected test file: {p}")

    # --- content rules ------------------------------------------------------
    for p, content in proposal.files.items():
        text = content or ""
        low = text.lower()
        if re.search(r"(api[_-]?key|secret|password|BEGIN (RSA|EC|OPENSSH) PRIVATE KEY)\s*[:=]", text, re.I):
            d.verdict = "BLOCK"; d.flags.append("secret_material"); d.reasons.append(f"secret-looking material in {p}")
        if re.search(r"\b(STOP|FREEZE)\b", text) and ("state" in low or "halt" in low):
            d.flags.append("halt_control_reference"); d.verdict = "BLOCK"
            d.reasons.append(f"references halt controls in {p}")
        for pat in monitor["review_patterns"]:
            if pat in text:
                d.flags.append("review_pattern_match"); d.reasons.append(f"'{pat}' in {p}")
        if re.search(r"[A-Za-z0-9+/]{200,}={0,2}", text):
            d.flags.append("encoded_blob"); d.reasons.append(f"long base64-like blob in {p}")
        if re.search(r"(https?://|socket\.|urlopen|\.connect\()", text):
            d.flags.append("network_call"); d.reasons.append(f"network-looking code in {p}")

    # --- final verdict ------------------------------------------------------
    d.flags = sorted(set(d.flags))
    block_on = set(monitor["block_on_flags"])
    escalate_on = set(monitor["escalate_on_flags"])
    if d.verdict != "BLOCK" and (block_on & set(d.flags)):
        d.verdict = "BLOCK"
    if d.verdict != "BLOCK" and (escalate_on & set(d.flags)):
        d.verdict = "ESCALATE"
    return d

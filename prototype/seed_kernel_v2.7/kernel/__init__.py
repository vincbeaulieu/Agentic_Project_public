"""Seed kernel: a minimal, human-governed loop for agent-proposed code changes.

Design rule: no safety property in this package depends on model output conforming
to instructions. Every safety property is enforced by code, files and OS permissions;
none is enforced by a prompt.
"""

__version__ = "2.7.0"


class KernelError(Exception):
    """Base class for kernel errors."""


class Halted(KernelError):
    """Raised whenever the kernel must stop immediately (STOP file, signal, budget)."""


class PolicyViolation(KernelError):
    """Raised when a proposal violates the constitution."""


class ApprovalError(KernelError):
    """Raised when an approval is missing, malformed, expired, or fails integrity or ownership checks."""

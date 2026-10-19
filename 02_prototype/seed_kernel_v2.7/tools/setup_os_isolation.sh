#!/usr/bin/env bash
# Sets the two-user layout for the seed kernel (rule R04 §31). Run as root once, in the kernel root.
#   KERNEL_USER  owns kernel/, constitution.toml, permissions.toml, state/ (mode 700/600); runs `python -m kernel`
#   SANDBOX_USER runs the workspace tests (via `sandbox_wrapper`, e.g. docker --user or sudo -u); can read/write workspace/ only
# The proposer LLM is an HTTP endpoint and has no OS identity on this machine; the only agent-controlled code that
# executes locally is the test command, under SANDBOX_USER or the wrapper.
set -euo pipefail
KERNEL_USER="${KERNEL_USER:-aopkernel}"
SANDBOX_USER="${SANDBOX_USER:-aopsandbox}"
ROOT="${1:-.}"
id "$KERNEL_USER" >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin "$KERNEL_USER"
id "$SANDBOX_USER" >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin "$SANDBOX_USER"
chown -R "$KERNEL_USER":"$KERNEL_USER" "$ROOT/kernel" "$ROOT/constitution.toml" "$ROOT/permissions.toml"
mkdir -p "$ROOT/state" && chown -R "$KERNEL_USER":"$KERNEL_USER" "$ROOT/state"
chmod 700 "$ROOT/kernel" "$ROOT/state"; chmod 600 "$ROOT/constitution.toml" "$ROOT/permissions.toml"
find "$ROOT/state" -type d -exec chmod 700 {} + ; find "$ROOT/state" -type f -exec chmod 600 {} +
mkdir -p "$ROOT/workspace" && chown -R "$KERNEL_USER":"$SANDBOX_USER" "$ROOT/workspace" && chmod -R 770 "$ROOT/workspace"
echo "done. verify with: sudo -u $KERNEL_USER python3 tools/check_os_isolation.py --root $ROOT --sandbox-uid $(id -u $SANDBOX_USER)"

#!/bin/bash
# chain_after.sh <pgrep pattern to wait for> -- <command...>
# Waits (0.2 s polls) until no process matches the pattern, then runs the command immediately,
# so a guarded step follows the previous one without leaving the experiment lock idle.
pat="$1"; shift; [ "$1" = "--" ] && shift
while pgrep -f "$pat" >/dev/null; do sleep 0.2; done
exec "$@"

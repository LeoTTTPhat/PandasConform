#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$ROOT/06_pandas_conformance"
for ENGINE in "${@:-ref}"; do
  PYTHON_VERSION=3.12
  [ "$ENGINE" != p15 ] || PYTHON_VERSION=3.11
  test -f "$PROJECT/requirements/$ENGINE.txt"
  uv venv --python "$PYTHON_VERSION" "$PROJECT/envs/$ENGINE"
  uv pip install --python "$PROJECT/envs/$ENGINE/bin/python" -r "$PROJECT/requirements/$ENGINE.txt"
done

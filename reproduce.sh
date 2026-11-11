#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$ROOT/06_pandas_conformance"
PY="${ARTIFACT_PYTHON:-$ROOT/.venv/bin/python}"
[ -x "$PY" ] || { echo "Run bash setup.sh first, or set ARTIFACT_PYTHON." >&2; exit 2; }
export ARTIFACT_PYTHON="$PY" PYTHONPATH="$PROJECT/src:$PROJECT:${PYTHONPATH:-}" MPLBACKEND=Agg
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
cd "$PROJECT"
case "${1:-analysis}" in
 analysis)
  "$PY" icde27/analysis/r5_corpus.py
  "$PY" icde27/analysis/r5_evidence.py
 ;;
 test)
  if [ -x "$PROJECT/envs/ref/bin/python" ]; then
    "$PROJECT/envs/ref/bin/python" -m unittest discover -s tests -p test_dfeq.py -v
  else
    "$PY" -m unittest discover -s tests -p test_nbsource.py -v
  fi
 ;;
 test-all)
  "$PY" -m unittest discover -s tests -v
 ;;
 run)
 shift
 [ "$#" -gt 0 ] || { echo "Usage: bash reproduce.sh run <script.py> [arguments]" >&2; exit 2; }
 exec "$PY" "$@"
 ;;
 *) echo "Usage: bash reproduce.sh [analysis|test|test-all|run <script.py> ...]" >&2; exit 2 ;;
esac

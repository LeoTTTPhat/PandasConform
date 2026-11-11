#!/usr/bin/env bash
# Create one uv virtual environment per engine configuration under envs/ and pin them in
# envs.lock.json (plan.md Section 4). Idempotent: an existing env is left alone unless
# FORCE=1. Usage: scripts/make_envs.sh [env ...]   (default: all)
#
# pyarrow_backend reuses envs/ref (the shim lives in src/pconf/engines.py).
# pandas-on-Spark is out of scope (Spark 4 needs Java 17/21; only JDK 26 is installed).
set -uo pipefail
PROJ="$(cd "$(dirname "$0")/.." && pwd)"
ENVS="$PROJ/envs"
mkdir -p "$ENVS"
export UV_PYTHON_PREFERENCE=only-managed

# Packages every env needs: the harness (pyarrow, psutil) and the few non-pandas modules the
# PandasBench notebooks import (numpy, tqdm, seaborn/matplotlib, openpyxl for read_excel).
COMMON_312="pyarrow psutil tqdm seaborn matplotlib openpyxl nbformat"

spec() {  # prints "<python> <packages...>" for an env name
  case "$1" in
    ref)       echo "3.12 pandas==2.3.3 numpy==2.3.5 $COMMON_312" ;;
    p15)       echo "3.11 pandas==1.5.3 numpy<2 pyarrow<18 psutil tqdm seaborn<0.14 matplotlib<3.10 openpyxl nbformat" ;;
    p30)       echo "3.12 pandas>=3.0,<3.1 numpy>=2 $COMMON_312" ;;
    modin)     echo "3.12 modin[ray]>=0.37,<0.38 pandas==2.3.3 numpy==2.3.5 $COMMON_312" ;;
    fireducks) echo "3.12 fireducks>=1.4,<1.5 pandas==2.3.3 numpy==2.3.5 $COMMON_312" ;;
    bodo)      echo "3.12 bodo==2026.8 pandas==2.3.3 numpy==2.3.5 $COMMON_312" ;;
    dask)      echo "3.12 dask[dataframe] pandas==2.3.3 numpy==2.3.5 $COMMON_312" ;;
    *)         echo "" ;;
  esac
}
ALL="ref p15 p30 modin fireducks bodo dask"

TARGETS="${*:-$ALL}"
STATUS=0
for e in $TARGETS; do
  d="$ENVS/$e"
  if [ -x "$d/bin/python" ] && [ -f "$d/.pconf_ok" ] && [ "${FORCE:-0}" != "1" ]; then
    echo "[make_envs] $e exists"; continue
  fi
  S="$(spec "$e")"
  if [ -z "$S" ]; then echo "[make_envs] unknown env $e"; STATUS=1; continue; fi
  PYV="${S%% *}"; PKGS="${S#* }"
  echo "[make_envs] creating $e (python $PYV): $PKGS"
  rm -rf "$d"
  uv venv --quiet --python "$PYV" "$d" || { echo "[make_envs] $e: venv failed"; STATUS=1; continue; }
  # shellcheck disable=SC2086
  if uv pip install --python "$d/bin/python" $PKGS > "$ENVS/$e.install.log" 2>&1; then
    touch "$d/.pconf_ok"
    echo "[make_envs] $e ok"
  else
    echo "[make_envs] $e: install FAILED (see envs/$e.install.log)"; tail -5 "$ENVS/$e.install.log"; STATUS=1
  fi
done

$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/.venv/bin/python "$PROJ/scripts/lock_envs.py" --envs "$ENVS" --out "$PROJ/envs.lock.json"
exit $STATUS

#!/usr/bin/env bash
# Smoke campaign (plan.md Section 6): all engines, 3 notebooks, scale 1x.
# Proves the full path data -> engine under test -> capture -> dfeq oracle -> checkpoint -> resume.
# Run ONLY through the memory guard:
#   cd $(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd) && python3 tools/memory_guard.py --limit-gb 120 --wait-lock 14400 \
#     --state runs/06_pandas_conformance_implement_smoke.json -- bash 06_pandas_conformance/scripts/run_smoke.sh
set -euo pipefail
PROJ="$(cd "$(dirname "$0")/.." && pwd)"
PY=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/.venv/bin/python
export PYTHONPATH="$PROJ/src"
cd "$PROJ"
CAMPAIGN="${CAMPAIGN:-smoke}"
ENGINES="${ENGINES:-ref,ref#2,pyarrow_backend,p15,p30,fireducks,bodo,bodo_dw,modin,dask}"
CMP="${CMP:-pyarrow_backend,p15,p30,fireducks,bodo,bodo_dw,modin,dask}"
T0=$(date +%s)
echo "== phase 1: first 2 notebooks per engine (checkpointed records)"
$PY -m pconf.orchestrate run --campaign "$CAMPAIGN" --set smoke --engines "$ENGINES" --limit 2
echo "== phase 2: all 3 notebooks (resume: completed fingerprints are skipped)"
$PY -m pconf.orchestrate run --campaign "$CAMPAIGN" --set smoke --engines "$ENGINES"
echo "== phase 3: oracle comparison (dfeq + classify in the ref env; ref#2 marks non-determinism)"
$PY -m pconf.orchestrate compare --campaign "$CAMPAIGN" --set smoke --engines "$CMP" --ref2 'ref#2'
$PY -m pconf.orchestrate summarize --campaign "$CAMPAIGN"
echo "== phase 4: resume check (all runs and comparisons already checkpointed)"
$PY -m pconf.orchestrate run --campaign "$CAMPAIGN" --set smoke --engines "$ENGINES"
$PY -m pconf.orchestrate compare --campaign "$CAMPAIGN" --set smoke --engines "$CMP" --ref2 'ref#2'
if [ "${TIMING:-0}" = "1" ]; then
  echo "== phase 5: timing path (no capture, repr of displayed values, matched CPU budget 8)"
  $PY -m pconf.timing run --campaign "${CAMPAIGN}_timing" --set smoke --engines ref,modin,fireducks,bodo,dask --reps 1 --cpus 8
  $PY -m pconf.timing report --campaign "${CAMPAIGN}_timing"
fi
echo "== smoke wall seconds: $(( $(date +%s) - T0 ))"

#!/bin/bash
# Engine non-determinism in the pilot: each parallel engine compared with its own replicate
# (engine#2 against engine), with ref#2 as the reference replicate. Run ONLY through the guard:
#   python3 tools/memory_guard.py --limit-gb 120 --wait-lock 14400 \
#     --state runs/06_pandas_conformance_experiment_pilot_replicates.json -- bash 06_pandas_conformance/scripts/pilot_replicate_compare.sh
set -u
cd $(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
export PYTHONPATH=06_pandas_conformance/src
for e in modin fireducks bodo dask; do
  .venv/bin/python -m pconf.orchestrate compare --campaign pilot --set pilot --ref "$e" --engines "$e#2" --ref2 'ref#2'
done

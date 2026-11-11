#!/bin/bash
# C2 guarded job (review round R5, agent B1): the adversarial corpus through (1) the unmodified harness of the paper
# (src/pconf) and (2) the C1 harness copy (exact encoder), each with ref, ref#2, p30, fireducks (dask on c2_dask),
# then the comparisons. Run only through the workspace memory guard:
#   cd $(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd) && python3 tools/memory_guard.py --start-if-fits --wait-lock 3600 \
#     --limit-gb 60 --max-restarts 1 --state runs/06_pandas_conformance_r5_capture_c2.json -- \
#     bash 06_pandas_conformance-ICDE/icde27/analysis/r5_capture/c2_job.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJ="$(cd "$HERE/../../.." && pwd)"
PY=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)/.venv/bin/python
C2="$PROJ/work/r5_capture/c2"
export PYTHONDONTWRITEBYTECODE=1 OMPI_MCA_btl_tcp_if_include=lo0
echo "[c2_job] start $(date '+%F %T')"; uptime
rc=0
for H in orig exact; do
  if [ "$H" = orig ]; then SRC="$PROJ/src"; else SRC="$HERE/harness"; fi
  export PCONF_WORK="$C2/work" PCONF_RESULTS="$C2/results_$H" PCONF_CAPTURES="$C2/captures_$H" PYTHONPATH="$SRC"
  cd "$PROJ" || exit 2
  echo "[c2_job] harness $H src=$SRC"
  nice "$PY" -m pconf.orchestrate run --campaign c2 --set "$C2/c2_set.json" --engines 'ref,ref#2,p30,fireducks' \
      --scale 1 --max-concurrency 4 || rc=$?
  nice "$PY" -m pconf.orchestrate run --campaign c2 --set "$C2/c2_set_dask.json" --engines 'ref,ref#2,p30,fireducks,dask' \
      --scale 1 --max-concurrency 4 || rc=$?
  nice "$PY" -m pconf.orchestrate compare --campaign c2 --set "$C2/c2_set.json" --engines p30,fireducks \
      --ref2 'ref#2' --scale 1 --workers 2 || rc=$?
  nice "$PY" -m pconf.orchestrate compare --campaign c2 --set "$C2/c2_set_dask.json" --engines p30,fireducks,dask \
      --ref2 'ref#2' --scale 1 --workers 2 || rc=$?
done
echo "[c2_job] end $(date '+%F %T') rc=$rc"; uptime
exit $rc

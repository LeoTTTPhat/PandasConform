#!/bin/bash
# C1 guarded job (review round R5, agent B1): one orchestrator per stream of c1_streams/<job>_*, all in parallel,
# waits for every stream (nothing is left running). Run only through the workspace memory guard:
#   cd $(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd) && python3 tools/memory_guard.py --start-if-fits --wait-lock 3600 \
#     --limit-gb 190 --max-restarts 1 --state runs/06_pandas_conformance_r5_capture_c1a.json -- \
#     bash 06_pandas_conformance-ICDE/icde27/analysis/r5_capture/c1_job.sh job1 2100 2580
# Arguments: job name (job1|job2), --deadline seconds (no new notebook after it), --hard-budget seconds.
set -u
JOB="$1"; DEADLINE="$2"; HARD="$3"
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJ="$(cd "$HERE/../../.." && pwd)"
PY=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)/.venv/bin/python
LOGS="$PROJ/work/r5_capture/logs"
mkdir -p "$LOGS"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$HERE/harness" OMPI_MCA_btl_tcp_if_include=lo0
echo "[c1_job] $JOB start $(date '+%F %T') deadline=$DEADLINE hard=$HARD"; uptime
pids=()
if [ "$JOB" = job2 ]; then
  # pairs of job 1 whose comparison did not fit job 1's compare budget: classify them while job 2 runs
  ( cd "$PROJ" && nice "$PY" "$HERE/c1_compare_all.py" --workers 3 --budget-s 1500 > "$LOGS/compare_${JOB}_leftover.log" 2>&1 ) &
  pid=$!
  pids+=("$pid")
  echo "[c1_job] leftover compare pid $pid"
fi
for setf in "$HERE"/c1_streams/${JOB}_*_set.json; do
  name="$(basename "$setf" _set.json)"
  stop="$HERE/c1_streams/${name}_stop.json"
  eng="$(python3 -c "import json,sys; print(next(iter(json.load(open(sys.argv[1])))).split('|')[0])" "$stop")"
  conc=2; [ "$eng" = ref ] && conc=3   # every configuration needs the new reference: give it more room
  ( cd "$PROJ" && nice "$PY" -m pconf.orchestrate run --campaign "r5c1_${name}" --set "$setf" --engines "$eng" \
      --scale 1 --stop-plan "$stop" --max-concurrency "$conc" --big-input-gb 100 --deadline "$DEADLINE" \
      --hard-budget "$HARD" > "$LOGS/${name}.log" 2>&1 ) &
  pid=$!
  pids+=("$pid")
  echo "[c1_job] stream $name engine $eng pid $pid"
done
rc=0
for p in "${pids[@]}"; do wait "$p" || rc=$?; done
echo "[c1_job] $JOB runs end $(date '+%F %T') rc=$rc"; uptime
# classify every new pair whose records exist, in both encodings (existing outputs are kept)
( cd "$PROJ" && nice "$PY" "$HERE/c1_compare_all.py" --workers 6 --budget-s 900 > "$LOGS/compare_${JOB}.log" 2>&1 ) || rc=$?
echo "[c1_job] $JOB compare end $(date '+%F %T') rc=$rc"; uptime
exit $rc

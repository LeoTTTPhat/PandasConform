#!/usr/bin/env python3
"""D3 check N2 (serial-execution counterfactual): captured runs of the notebooks in d3_plan.json n2_runs with the
UNCHANGED harness (src/pconf, harness d1c421ecb5ee) and the conf_1x run configuration, but each engine in a serial
variant registered at run time in this process (engines.ENGINES is extended in memory; no file is edited; the child
receives the variant's setup code in its job file, as for any engine). Records and blobs go to work/r5_replay/.

Run ONLY under the memory guard, from the workspace root, with the shared venv:
    OMPI_MCA_btl_tcp_if_include=lo0 python3 tools/memory_guard.py --start-if-fits --wait-lock 7200 --limit-gb 150 \
      --state runs/06_pandas_conformance_r5_replay_d3n2.json -- \
      .venv/bin/python 06_pandas_conformance-ICDE/icde27/analysis/r5_replay/d3_run.py
"""
import argparse
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import r5common as R  # noqa: E402

os.environ["PCONF_RESULTS"] = R.REPLAY_RESULTS
os.environ["PCONF_CAPTURES"] = R.REPLAY_STORE
os.environ["PCONF_WORK"] = R.REPLAY_PWORK
sys.path.insert(0, R.SRC)
from pconf import datasets, engines, orchestrate as O, util  # noqa: E402

CAMPAIGN = "r5_serial"
CFG = {"cell_timeout": 600, "nb_timeout": 3600, "seed": 0, "capture_inputs": True, "limits": None, "cpus": None}

MODIN_SERIAL = r'''
import modin.config as _mc
_mc.Engine.put("Python")      # in-process, serial execution engine (no Ray workers)
_mc.NPartitions.put(1)        # one partition: no partition-order or per-partition effects
import modin.pandas as pd
'''

DASK_SERIAL = r'''
import types as _types
import dask
dask.config.set(scheduler="synchronous")     # no threads
import dask.dataframe as _dd
class _DaskSerial(_types.ModuleType):
    def __getattr__(self, name):
        return getattr(_dd, name)
pd = _DaskSerial("dask.dataframe")
def _read_csv(*a, **k):
    k.setdefault("blocksize", None)          # one partition per file
    return _dd.read_csv(*a, **k)
pd.read_csv = _read_csv
'''

BODO_EXACTQ = r'''
import bodo.pandas as pd
import pandas as _rp
def _plain_series(x):
    try:
        x.execute_plan()
    except Exception:
        pass
    return _rp.Series(x.array, index=x.index, name=x.name, copy=False)
def _plain_frame(x):
    try:
        x.execute_plan()
    except Exception:
        pass
    arrays = [x.iloc[:, j].array for j in range(x.shape[1])]
    out = _rp.DataFrame(dict(zip(range(len(arrays)), arrays)), index=x.index, copy=False)
    out.columns = x.columns
    return out
# a failed patch must not pass silently as plain Bodo: any error here is an engine setup error (all cells SETUP_ERR)
_BS = type(pd.Series([1.0, 2.0]))
_BD = type(pd.DataFrame({"a": [1.0, 2.0]}))
assert _BS.__module__.startswith("bodo") and _BD.__module__.startswith("bodo"), (_BS, _BD)
_BS.quantile = lambda self, *a, **k: _plain_series(self).quantile(*a, **k)        # exact (pandas) quantiles
_BD.quantile = lambda self, *a, **k: _plain_frame(self).quantile(*a, **k)
_BD.describe = lambda self, *a, **k: _plain_frame(self).describe(*a, **k)
print("[bodo_exactq] patched", _BS.__name__, _BD.__name__)
'''

VARIANTS = {
    "modin_serial": {"env": "modin", "setup": MODIN_SERIAL, "class": "parallel", "threads": "default",
                     "env_vars": {"MODIN_ENGINE": "python", "MODIN_NPARTITIONS": "1"},
                     "doc": "Modin 0.37, Python engine (serial, in process), 1 partition"},
    "dask_serial": {"env": "dask", "setup": DASK_SERIAL, "class": "parallel", "threads": "default",
                    "evaluate_lazy": "return lazy.compute() if hasattr(lazy, 'compute') else lazy",
                    "doc": "dask.dataframe, synchronous scheduler, read_csv(blocksize=None)"},
    "fireducks_1t": {"env": "fireducks", "setup": "import fireducks.pandas as pd", "class": "parallel", "threads": "default",
                     "env_vars": {"FIREDUCKS_FLAGS": "-Wfallback", "OMP_NUM_THREADS": "1"},
                     "doc": "FireDucks 1.4 with OMP_NUM_THREADS=1 (its thread pool follows it, engines.py)"},
    "pyarrow_1t": {"env": "ref", "setup": engines.PYARROW_SHIM + "\nimport pyarrow as _pa\n_pa.set_cpu_count(1)\n_pa.set_io_thread_count(1)\n",
                   "class": "single", "doc": "pyarrow backend with one Arrow CPU and IO thread"},
    "bodo_exactq": {"env": "bodo", "setup": BODO_EXACTQ, "class": "parallel", "threads": "default",
                    "env_vars": {"BODO_NUM_WORKERS": "1"},
                    "doc": "Bodo 2026.8, 1 worker, Series/DataFrame quantile and describe computed exactly by pandas"},
}
LANES = 8
LOG_DIR = os.path.join(R.WORK, "logs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deadline", type=float, default=24 * 60)
    ap.add_argument("--hard-budget", type=float, default=29 * 60)
    ap.add_argument("--no-post", action="store_true", help="skip the comparisons and checks after the runs")
    ap.add_argument("--plan-file", default="d3_plan.json", help="JSON with n2_runs [{variant, engine, nb}]")
    ap.add_argument("--tag", default="d3n2")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    engines.ENGINES.update(VARIANTS)
    plan = R.read_json(os.path.join(HERE, a.plan_file))
    tasks = []
    for r in plan["n2_runs"]:
        orig = R.original_record(r["engine"], r["nb"])
        rec = R.read_json(orig)
        tasks.append({"variant": r["variant"], "engine": r["engine"], "nb": r["nb"],
                      "orig_wall_s": rec.get("orchestrator_wall_s") or 0, "orig_record": os.path.relpath(orig, R.PROJ)})
    tasks.sort(key=lambda t: -t["orig_wall_s"])
    if a.dry_run:
        for t in tasks:
            print(t["variant"], t["nb"], O.fingerprint(t["variant"], t["nb"], 1.0, dict(CFG))[:12])
        return 0
    os.makedirs(LOG_DIR, exist_ok=True)
    O._install_signal_handlers()
    t0 = time.time()
    O.HARD_DEADLINE[0] = t0 + a.hard_budget
    results, lock = [], threading.Lock()
    summary_path = os.path.join(HERE, "d3_run_%s.json" % a.tag)
    queue = list(tasks)

    def worker():
        while True:
            with lock:
                if not queue:
                    return
                t = queue.pop(0)
            if O.STOP.is_set():
                st, path = "interrupted", None
            elif time.time() - t0 > a.deadline:
                st, path = "deferred", None
            else:
                ts = time.time()
                st, path = O.run_one(CAMPAIGN, t["variant"], t["nb"], 1.0, dict(CFG), "capture", 1, ())
                t["run_wall_s"] = round(time.time() - ts, 1)
            rec = util.read_json(path) if path else None
            out = dict(t, status=st, record=os.path.relpath(path, R.PROJ) if path else None,
                       record_status=rec.get("status") if rec else None, log_tail=(rec or {}).get("log_tail", "")[-600:])
            print("[d3n2] %-13s %-62s -> %s (%s s, %s)" % (t["variant"], t["nb"], st, t.get("run_wall_s"),
                  out["record_status"]), flush=True)
            with lock:
                results.append(out)
                R.write_json(summary_path, {"campaign": CAMPAIGN, "cfg": CFG, "variants": {k: v["doc"] for k, v in VARIANTS.items()},
                                            "variant_setup": {k: v["setup"] for k, v in VARIANTS.items()},
                                            "variant_env_vars": {k: v.get("env_vars", {}) for k, v in VARIANTS.items()},
                                            "tag": a.tag, "started": t0, "results": results,
                                            "loadavg": [round(x, 2) for x in os.getloadavg()]})

    ths = [threading.Thread(target=worker) for _ in range(LANES)]
    for th in ths:
        th.start()
    for th in ths:
        th.join()
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(json.dumps({"counts": counts, "seconds": round(time.time() - t0, 1)}), flush=True)
    if O.STOP.is_set():
        return 130
    if not a.no_post:
        # post-processing inside the same guarded job (comparator work decodes large frames):
        # (1) serial records vs the original reference, (2) checks N3, N1, N6 on existing records
        import subprocess
        env = dict(os.environ, PYTHONPATH=R.SRC)
        py = os.path.join(R.ENVS, "ref", "bin", "python")
        for args, tmo in (([os.path.join(HERE, "d1_compare.py"), "--d3", "--workers", "2"], 11 * 60),
                          ([os.path.join(HERE, "d3_checks.py")], 6 * 60)):
            ts = time.time()
            try:
                p = subprocess.run([py] + args, env=env, timeout=tmo, capture_output=True, text=True)
                print("[d3post] %s rc=%s %.0fs\n%s" % (os.path.basename(args[0]), p.returncode, time.time() - ts,
                      (p.stdout or "")[-1500:] + (p.stderr or "")[-800:]), flush=True)
            except subprocess.TimeoutExpired:
                print("[d3post] %s timeout after %ds" % (os.path.basename(args[0]), tmo), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

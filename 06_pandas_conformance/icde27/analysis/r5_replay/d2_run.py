#!/usr/bin/env python3
"""D2 driver: run the uncaptured replays of d2_cases.py (pandas once per notebook, each engine REPS times) and write
d2_raw.json. Run ONLY under the memory guard, from the workspace root, with the shared venv:
    OMPI_MCA_btl_tcp_if_include=lo0 python3 tools/memory_guard.py --start-if-fits --wait-lock 3600 --limit-gb 120 \
      --state runs/06_pandas_conformance_r5_replay_d2.json -- \
      .venv/bin/python 06_pandas_conformance-ICDE/icde27/analysis/r5_replay/d2_run.py
Each run is a fresh process (own process group, killed with its Ray or MPI helpers after the run) in a scratch working
directory under work/r5_replay/d2_cwd/ whose `input` links to the prepared inputs used by the captured runs.
Engine setup code and environment variables come from src/pconf/engines.py (read only), as in the captured runs:
Modin 8 Ray CPUs and 16 GB object store, FireDucks -Wfallback, Bodo BODO_NUM_WORKERS=1, bodo_dw default workers.
"""
import concurrent.futures as cf
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import r5common as R  # noqa: E402
import d2_cases as DC  # noqa: E402

sys.path.insert(0, R.SRC)
from pconf import datasets, engines  # noqa: E402

OUT = os.path.join(HERE, "d2_raw.json")
CWD_ROOT = os.path.join(R.WORK, "d2_cwd")
LOG = os.path.join(R.WORK, "logs", "d2_children.log")
RUN_TIMEOUT_S = 1500
LIMITS = {"modin": 1, "bodo": 2, "bodo_dw": 1, "fireducks": 2, "pandas": 3}
POOL = 5


def build_jobs(cases=None, configs=None, with_pandas=True):
    groups = {}
    for case in DC.CASES:
        if cases and case["id"] not in cases:
            continue
        for cfg in (["pandas"] if with_pandas else []) + case["configs"]:
            if configs and cfg not in configs and cfg != "pandas":
                continue
            key = (cfg, case["nb"])
            g = groups.setdefault(key, {"config": cfg, "nb": case["nb"], "targets": []})
            g["targets"].append({"case": case["id"], "cell": case["cell"], "values": case["values"]})
    jobs = []
    for (cfg, nb), g in sorted(groups.items()):
        reps = 1 if cfg == "pandas" else DC.REPS
        for rep in range(1, reps + 1):
            jobs.append(dict(g, rep=rep))
    return jobs


def run_job(j):
    eng = DC.CONFIGS[j["config"]]
    spec = engines.engine_spec(eng)
    py = engines.engine_python(eng)
    env = engines.child_env(eng)
    env["PYTHONPATH"] = R.SRC
    if j["config"] == "bodo_dw":
        env.pop("BODO_NUM_WORKERS", None)   # default worker count, as the harness's bodo_dw runs
    scratch = os.path.join(CWD_ROOT, j["config"], R.nb_key(j["nb"]), "rep%d" % j["rep"])
    shutil.rmtree(scratch, ignore_errors=True)
    cwd = os.path.join(scratch, "cwd")
    os.makedirs(cwd)
    in_dir = os.path.join(datasets.scaled_dir(j["nb"], 1.0), "input")
    os.symlink(in_dir, os.path.join(cwd, "input"))
    job = {"nb_file": datasets.notebook_file(j["nb"]), "cwd": cwd, "setup": spec["setup"],
           "evaluate_lazy": spec["evaluate_lazy"], "teardown": spec["teardown"], "seed": 0,
           "skip_cells": datasets.setup_cells(j["nb"]), "targets": j["targets"], "cell_timeout": 600}
    jpath = os.path.join(scratch, "job.json")
    with open(jpath, "w") as f:
        json.dump(job, f)
    t0 = time.time()
    p = subprocess.Popen([py, os.path.join(HERE, "d2_child.py"), jpath], cwd=cwd, env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, errors="replace", start_new_session=True)
    try:
        out, _ = p.communicate(timeout=RUN_TIMEOUT_S)
        status = "ok" if p.returncode == 0 else "rc=%s" % p.returncode
    except subprocess.TimeoutExpired:
        status = "timeout"
        os.killpg(p.pid, signal.SIGKILL)
        out, _ = p.communicate()
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    events = []
    for line in (out or "").splitlines():
        if line.startswith("D2RESULT "):
            try:
                events.append(json.loads(line[len("D2RESULT "):]))
            except ValueError:
                pass
    with open(LOG, "a") as f:
        f.write("===== %s %s rep%d %s %.1fs %s\n%s\n" % (j["config"], j["nb"], j["rep"], time.strftime("%H:%M:%S"),
                                                     time.time() - t0, status, (out or "")[-6000:]))
    shutil.rmtree(scratch, ignore_errors=True)
    return dict(config=j["config"], nb=j["nb"], rep=j["rep"], status=status, seconds=round(time.time() - t0, 1),
                events=events, env_bodo_workers=env.get("BODO_NUM_WORKERS"))


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="", help="rerun only these case ids (comma separated)")
    ap.add_argument("--configs", default="", help="with --cases: only these engine configurations")
    ap.add_argument("--no-pandas", action="store_true", help="with --cases: skip the pandas baseline runs")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    cases = {c for c in a.cases.split(",") if c}
    jobs = build_jobs(cases or None, {c for c in a.configs.split(",") if c} or None, not a.no_pandas)
    sems = {k: threading.Semaphore(v) for k, v in LIMITS.items()}
    results, lock = [], threading.Lock()
    t0 = time.time()
    loads = []

    def guarded(j):
        with sems[j["config"]]:
            r = run_job(j)
        with lock:
            results.append(r)
            loads.append({"t": time.strftime("%H:%M:%S"), "loadavg": [round(x, 2) for x in os.getloadavg()]})
        print("[d2] %-9s %-60s rep%d %s %.1fs" % (r["config"], r["nb"], r["rep"], r["status"], r["seconds"]), flush=True)
        return r

    # longest groups first: notebooks with the most cells before the target
    jobs.sort(key=lambda j: -max(t["cell"] for t in j["targets"]))
    with cf.ThreadPoolExecutor(POOL) as ex:
        list(ex.map(guarded, jobs))
    R.write_json(a.out, {"item": "D2", "cases": DC.CASES, "rerun_of": sorted(cases) or None, "reps": DC.REPS, "run_timeout_s": RUN_TIMEOUT_S,
                       "seconds": round(time.time() - t0, 1), "host_load": loads,
                       "results": sorted(results, key=lambda r: (r["nb"], r["config"], r["rep"]))})
    print("wrote", a.out, round(time.time() - t0, 1), "s", flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""D1 replay driver: re-run the notebooks of d1_plan.json with the UNCHANGED harness (src/pconf, harness d1c421ecb5ee)
and the conf_1x run configuration, writing records and blobs only under work/r5_replay/.

Run ONLY under the memory guard, from the workspace root, with the shared venv:
    OMPI_MCA_btl_tcp_if_include=lo0 python3 tools/memory_guard.py --start-if-fits --wait-lock 3600 --limit-gb 180 \
      --state runs/06_pandas_conformance_r5_replay_d1.json -- \
      .venv/bin/python 06_pandas_conformance-ICDE/icde27/analysis/r5_replay/d1_run.py --engines bodo,dask,modin,fireducks,pyarrow_backend

Same settings as conf_1x: run config {cell_timeout 600, nb_timeout 3600, seed 0, capture_inputs True, limits None,
cpus None} (the input-capture rule of orchestrate.nb_cfg applies as before), same environments and scaled inputs.
Each replay record's fingerprint is checked against the original record's fingerprint (identical engine, env freeze,
notebook, inputs, harness and run config). Deviation from conf_1x (declared): several notebooks run at once (lanes
below), whereas conf_1x ran parallel engines one notebook at a time; CPU contention can change timing, not settings.
"""
import argparse
import concurrent.futures as cf
import json
import os
import shutil
import subprocess
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
from pconf import datasets, orchestrate as O, util  # noqa: E402

CAMPAIGN = "r5_replay"
CFG = {"cell_timeout": 600, "nb_timeout": 3600, "seed": 0, "capture_inputs": True, "limits": None, "cpus": None}
LANES = {"bodo": 3, "dask": 2, "modin": 2, "fireducks": 2, "pyarrow_backend": 3}
BIG_INPUT_GB = 0.5
MAX_BIG = 5
MIN_FREE_DISK_GB = 60
LOG_DIR = os.path.join(R.WORK, "logs")


def host_sample():
    s = {"t": time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        s["loadavg"] = [round(x, 2) for x in os.getloadavg()]
    except OSError:
        pass
    try:
        import psutil
        vm = psutil.virtual_memory()
        s["host_used_gb"] = round((vm.total - vm.available) / 1e9, 1)
    except Exception:
        pass
    st = shutil.disk_usage(R.WORK)
    s["disk_free_gb"] = round(st.free / 1e9, 1)
    return s


def monitor(stop_evt, path):
    while not stop_evt.is_set():
        s = host_sample()
        with open(path, "a") as f:
            f.write(json.dumps(s) + "\n")
        if s.get("disk_free_gb", 1e9) < MIN_FREE_DISK_GB:
            print("[d1] disk free %.1f GB below %d GB: stopping" % (s["disk_free_gb"], MIN_FREE_DISK_GB), flush=True)
            O.STOP.set()
        stop_evt.wait(30)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engines", default="bodo,dask,modin,fireducks,pyarrow_backend")
    ap.add_argument("--deadline", type=float, default=38 * 60, help="stop launching notebooks after this many s")
    ap.add_argument("--hard-budget", type=float, default=44 * 60, help="interrupt running notebooks after this")
    ap.add_argument("--tag", default="d1")
    ap.add_argument("--dry-run", action="store_true", help="only check that replay fingerprints equal the originals")
    a = ap.parse_args()
    plan = R.read_json(os.path.join(HERE, "d1_plan.json"))
    os.makedirs(LOG_DIR, exist_ok=True)
    O._install_signal_handlers()
    t0 = time.time()
    O.HARD_DEADLINE[0] = t0 + a.hard_budget
    mon_stop = threading.Event()
    mon = threading.Thread(target=monitor, args=(mon_stop, os.path.join(LOG_DIR, "host_%s.jsonl" % a.tag)), daemon=True)
    mon.start()
    tasks = []
    for eng in a.engines.split(","):
        e = plan["engines"][eng]
        for role, lst in (("disputed", e["notebooks"]), ("control", e["controls"])):
            for nbe in lst:
                tasks.append({"engine": eng, "nb": nbe["nb"], "role": role, "orig_wall_s": nbe["orig_wall_s"],
                              "orig_fingerprint": nbe["orig_fingerprint"],
                              "big": datasets.input_bytes(nbe["nb"]) > BIG_INPUT_GB * 1e9})
    tasks.sort(key=lambda t: -t["orig_wall_s"])          # longest first within each engine (makespan)
    if a.dry_run:
        bad = 0
        for t in tasks:
            fp = O.fingerprint(t["engine"], t["nb"], 1.0, dict(CFG))
            ok = fp == t["orig_fingerprint"]
            bad += not ok
            print("[dry] %-16s %-62s fp match %s" % (t["engine"], t["nb"], ok))
        print("[dry] %d tasks, %d fingerprint mismatches" % (len(tasks), bad))
        mon_stop.set()
        return 0
    queues = {}
    for t in tasks:
        queues.setdefault(t["engine"], []).append(t)
    big_sem = threading.Semaphore(MAX_BIG)
    results = []
    res_lock = threading.Lock()
    summary_path = os.path.join(R.HERE, "d1_run_%s.json" % a.tag)

    def job(t):
        if O.STOP.is_set():
            st, path = "interrupted", None
        elif time.time() - t0 > a.deadline:
            st, path = "deferred", None
        else:
            if t["big"]:
                big_sem.acquire()
            try:
                ts = time.time()
                st, path = O.run_one(CAMPAIGN, t["engine"], t["nb"], 1.0, dict(CFG), "capture", 1, ())
                t["replay_wall_s"] = round(time.time() - ts, 1)
            finally:
                if t["big"]:
                    big_sem.release()
        rec = util.read_json(path) if path else None
        out = dict(t, status=st, record=os.path.relpath(path, R.PROJ) if path else None,
                   replay_fingerprint=rec.get("fingerprint") if rec else None,
                   fingerprint_matches_original=(rec.get("fingerprint") == t["orig_fingerprint"]) if rec else None,
                   replay_record_status=rec.get("status") if rec else None,
                   peak_tree_rss_gb=rec.get("peak_tree_rss_gb") if rec else None)
        print("[d1] %-16s %-62s %-8s -> %s (%s s, fp match %s)" % (t["engine"], t["nb"], t["role"], st,
              out.get("replay_wall_s"), out["fingerprint_matches_original"]), flush=True)
        with res_lock:
            results.append(out)
            R.write_json(summary_path, {"campaign": CAMPAIGN, "cfg": CFG, "lanes": LANES, "tag": a.tag,
                                        "started": t0, "results": results})
        return out

    qlock = threading.Lock()

    def lane(eng):
        while True:
            with qlock:
                if not queues[eng]:
                    return
                t = queues[eng].pop(0)
            job(t)

    threads = []
    for eng in queues:
        for _ in range(LANES.get(eng, 1)):
            th = threading.Thread(target=lane, args=(eng,))
            th.start()
            threads.append(th)
    for th in threads:
        th.join()
    mon_stop.set()
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    R.write_json(summary_path, {"campaign": CAMPAIGN, "cfg": CFG, "lanes": LANES, "tag": a.tag, "started": t0,
                                "seconds": round(time.time() - t0, 1), "counts": counts, "results": results,
                                "host_end": host_sample()})
    print(json.dumps({"counts": counts, "seconds": round(time.time() - t0, 1)}), flush=True)
    return 130 if O.STOP.is_set() else 0


if __name__ == "__main__":
    sys.exit(main())

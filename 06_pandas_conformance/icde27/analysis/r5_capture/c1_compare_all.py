#!/usr/bin/env python3
"""Pair the new C1 runs and classify them in both encodings (review round R5, agent B1).

Parent side (shared venv). For every configuration and notebook of c1_selection.json whose new run and new reference
run exist (campaign manifests of results/r5c1_*), writes a job and runs c1_compare.py in the `ref` environment with
WORKERS processes; outputs go to work/r5_capture/compare/{orig,exact}/<label>/<nb>.json (existing outputs are kept).

    python c1_compare_all.py [--workers 4]
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
R5 = os.path.join(PROJ, "work", "r5_capture")
REF_PY = os.path.join(PROJ, "envs", "ref", "bin", "python")


def manifest_records():
    """(engine, nb) -> (status, absolute record path) over all r5c1 campaigns."""
    out = {}
    for p in glob.glob(os.path.join(R5, "results", "r5c1_*", "raw", "campaign_h*.json")):
        m = json.load(open(p))
        for key, v in (m.get("runs") or {}).items():
            mode, eng, nb, scale, rep = key.split("|")
            if mode != "capture" or not v.get("record"):
                continue
            out[(eng, nb)] = (v.get("status"), os.path.join(PROJ, v["record"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--budget-s", type=float, default=0, help="workers start no new pair after this many seconds")
    a = ap.parse_args()
    sel = json.load(open(os.path.join(HERE, "c1_selection.json")))
    recs = manifest_records()
    jobs, missing = [], []
    for label, S in sorted(sel["by_label"].items()):
        for nb, v in sorted(S["notebooks"].items()):
            ref = recs.get(("ref", nb))
            eng = recs.get((label, nb))
            if not ref or not eng or not os.path.exists(ref[1]) or not os.path.exists(eng[1]):
                missing.append([label, nb, bool(ref), bool(eng)])
                continue
            done = all(os.path.exists(os.path.join(R5, "compare", var, label, nb.replace("/", "__") + ".json"))
                       for var in ("orig", "exact", "graded"))
            if not done:
                jobs.append({"label": label, "nb": nb, "ref": ref[1], "eng": eng[1], "last_cell": v["stop"],
                             "store": os.path.join(R5, "captures")})
    print(json.dumps({"jobs": len(jobs), "missing_records": len(missing)}), flush=True)
    for m in missing:
        print("missing", m, flush=True)
    if not jobs:
        return 0
    jdir = os.path.join(R5, "compare_jobs")
    os.makedirs(jdir, exist_ok=True)
    n = max(1, min(a.workers, len(jobs)))
    procs = []
    env = dict(os.environ)
    for k in list(env):
        if k.startswith("PYTHON") and k != "PYTHONDONTWRITEBYTECODE":
            env.pop(k)
    env.update({"PYTHONPATH": os.path.join(HERE, "harness"), "PCONF_DECODE_CACHE_GB": "2", "PYTHONHASHSEED": "0"})
    for k in range(n):
        jp = os.path.join(jdir, "chunk_%d_%d.json" % (os.getpid(), k))
        with open(jp, "w") as f:
            json.dump(jobs[k::n], f)
        cmd = [REF_PY, "-B", os.path.join(HERE, "c1_compare.py"), "--jobs", jp, "--out-root", os.path.join(R5, "compare")]
        if a.budget_s:
            cmd += ["--deadline-epoch", str(time.time() + a.budget_s)]
        procs.append(subprocess.Popen(cmd, env=env))
    rc = 0
    for p in procs:
        rc |= p.wait()
    return rc


if __name__ == "__main__":
    sys.exit(main())

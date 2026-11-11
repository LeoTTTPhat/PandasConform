"""Comparison worker (runs in the `ref` environment, plan.md: dfeq runs in ref).

    <envs/ref/bin/python> -m pconf.compare_worker --jobs jobs.jsonl

Each job line: {"ref": path, "eng": path, "ref2": path|null, "out": path, "store": dir, "meta": {...}}.
Outputs are written atomically; existing outputs are skipped (checkpoint/resume).
"""
import argparse
import json
import os
import sys
import time

from pconf import classify, util


def run_job(job):
    if os.path.exists(job["out"]):
        return "skipped"
    t0 = time.time()
    ref = util.read_json(job["ref"])
    eng = util.read_json(job["eng"])
    ref2 = util.read_json(job["ref2"]) if job.get("ref2") else None
    if ref is None or eng is None:
        return "missing_input"
    res = classify.classify_run(ref, eng, job["store"], ref2=ref2)
    res["meta"] = dict(job.get("meta", {}))
    res["meta"].update({"ref_record": os.path.relpath(job["ref"], util.PROJ),
                        "eng_record": os.path.relpath(job["eng"], util.PROJ),
                        "ref2_record": os.path.relpath(job["ref2"], util.PROJ) if job.get("ref2") else None,
                        "compare_sha": util.compare_sha(), "seconds": round(time.time() - t0, 3),
                        "ref_status": ref.get("status"), "eng_status": eng.get("status"),
                        "eng_engine_setup_error": eng.get("error") if eng.get("status") == "engine_setup_error" else None})
    util.atomic_write_json(job["out"], res)
    return "done"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    a = ap.parse_args(argv)
    delay = float(os.environ.get("MEMGUARD_DELAY_SECONDS", "0") or 0)
    counts = {}
    with open(a.jobs) as f:
        jobs = [json.loads(l) for l in f if l.strip()]
    for job in jobs:
        try:
            st = run_job(job)
        except Exception as e:
            st = "error"
            print("compare error %s: %s: %s" % (job.get("out"), type(e).__name__, e), file=sys.stderr)
        counts[st] = counts.get(st, 0) + 1
        if delay:
            time.sleep(delay)
    print(json.dumps(counts))


if __name__ == "__main__":
    main()

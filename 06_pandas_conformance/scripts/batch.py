#!/usr/bin/env python3
"""Run several orchestrate steps inside ONE memory-guarded invocation (fewer races for the shared
experiment lock), sharing a time budget (2026-10-03).

    python3 06_pandas_conformance/scripts/batch.py --budget 5300 --steps <steps.json>

steps.json: {"name": "...", "steps": [{"name": "...", "args": [orchestrate args ...]}, ...]}
Steps run in order. A step is complete when its orchestrate summary reports nothing deferred,
interrupted or killed (run) or done == compare_jobs (compare); completion is recorded in
work/batch/<batch>/<step>.done together with the summary, so a rerun skips it. `run` steps get
--deadline (remaining - 600 s) and --hard-budget (remaining - 60 s); `compare` steps get
--hard-budget (remaining - 60 s). The batch stops when a step is incomplete (budget spent) and
prints one JSON line {"batch": "complete"|"incomplete", ...} for the driver.
"""
import argparse
import json
import os
import subprocess
import sys
import time

ROOT = str(__import__('pathlib').Path(__file__).resolve().parents[2] / '')
PROJ = os.path.join(ROOT, "06_pandas_conformance")
INCOMPLETE = ("deferred", "interrupted", "killed_external")


def last_json(text):
    for line in reversed(text.strip().splitlines()):
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=5300)
    ap.add_argument("--steps", required=True)
    a = ap.parse_args()
    spec = json.load(open(a.steps))
    mark_dir = os.path.join(PROJ, "work", "batch", spec["name"])
    os.makedirs(mark_dir, exist_ok=True)
    t0 = time.time()
    env = dict(os.environ, PYTHONPATH=os.path.join(PROJ, "src"))
    done_steps, status = [], "complete"
    for st in spec["steps"]:
        mark = os.path.join(mark_dir, st["name"] + ".done")
        if os.path.exists(mark):
            done_steps.append(st["name"])
            continue
        remaining = a.budget - (time.time() - t0)
        if remaining < 300:
            status = "incomplete"
            break
        args = list(st["args"])
        if args[0] == "run":
            args += ["--deadline", str(int(max(60, remaining - 600))), "--hard-budget", str(int(remaining - 60))]
        elif args[0] == "compare":
            args += ["--hard-budget", str(int(remaining - 60))]
        print("[batch] step %s (%.0f s left): %s" % (st["name"], remaining, " ".join(args)), flush=True)
        p = subprocess.run([os.path.join(ROOT, ".venv", "bin", "python"), "-m", "pconf.orchestrate"] + args,
                           cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        sys.stdout.write(p.stdout)
        sys.stdout.flush()
        res = last_json(p.stdout)
        ok = res is not None and (
            ("counts" in res and not any(c in res["counts"] for c in INCOMPLETE)) or
            ("compare_jobs" in res and res["done"] == res["compare_jobs"]))
        if ok:
            with open(mark, "w") as f:
                json.dump({"finished": time.strftime("%Y-%m-%dT%H:%M:%S"), "result": res, "rc": p.returncode}, f)
            done_steps.append(st["name"])
            print("[batch] step %s complete" % st["name"], flush=True)
        else:
            status = "incomplete"
            print("[batch] step %s incomplete (rc %d)" % (st["name"], p.returncode), flush=True)
            break
    print(json.dumps({"batch": status, "name": spec["name"], "done_steps": done_steps,
                      "seconds": round(time.time() - t0, 1)}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

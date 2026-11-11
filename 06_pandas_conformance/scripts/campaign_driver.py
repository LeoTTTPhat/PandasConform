#!/usr/bin/env python3
"""Repeat a guarded pconf command until the campaign step is complete (2026-10-02).

Each iteration is ONE memory-guarded invocation (tools/memory_guard.py --limit-gb 120
--wait-lock 14400) with its own state file runs/06_pandas_conformance_<name>_i<k>.json, so every
invocation stays within ~90 min (use --deadline 1800 with nb_timeout 3600 for `run`) and the
experiment lock is released between invocations. The step is complete when the orchestrator's
final JSON line reports no deferred / interrupted / killed_external notebooks (run) or
done == compare_jobs (compare). Exit 75 from the guard (lock timeout / memory not recovered)
waits 5 minutes and retries.

    python3 06_pandas_conformance/scripts/campaign_driver.py --name pilot_run --max-iters 8 -- \\
        run --campaign pilot --set pilot --engines ref,ref#2 --deadline 1800
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
LOCK_PATH = os.path.join(ROOT, "runs", "experiment.lock")


def wait_until_lock_free(max_wait=14400, poll=0.02):
    """Poll (every 20 ms) until the shared experiment lock is free, without holding it: take it
    non-blocking and release it at once. The guard is launched right after, so this driver is not
    disadvantaged against projects that chain guarded invocations back to back. The guard still
    does the real locking (--wait-lock), so losing the race only means waiting again."""
    import fcntl
    t0 = time.time()
    while time.time() - t0 < max_wait:
        with open(LOCK_PATH, "a") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(f, fcntl.LOCK_UN)
                return True
            except BlockingIOError:
                pass
        time.sleep(poll)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--max-iters", type=int, default=8)
    ap.add_argument("--start-iter", type=int, default=1)
    ap.add_argument("--batch", default=None, help="steps JSON for scripts/batch.py (instead of one orchestrate command)")
    ap.add_argument("--budget", type=float, default=5300)
    ap.add_argument("--guard-limit-gb", default="120", help="memory_guard --limit-gb for every iteration")
    ap.add_argument("--guard-start-if-fits", action="store_true",
                    help="pass memory_guard --start-if-fits (user rule 2026-10-26): start when machine use "
                         "plus --guard-limit-gb stays under 490 GB")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    log_path = os.path.join(PROJ, "work", "logs", "%s.log" % a.name)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    k = a.start_iter
    while k < a.start_iter + a.max_iters:
        state = "runs/06_pandas_conformance_%s_i%d.json" % (a.name, k)
        guard = ["python3", "tools/memory_guard.py", "--limit-gb", a.guard_limit_gb, "--wait-lock", "14400", "--state", state]
        guard += (["--start-if-fits"] if a.guard_start_if_fits else []) + ["--"]
        if a.batch:
            full = guard + ["python3", "06_pandas_conformance/scripts/batch.py", "--budget", str(a.budget), "--steps", a.batch]
        else:
            full = guard + ["env", "PYTHONPATH=06_pandas_conformance/src", ".venv/bin/python", "-m", "pconf.orchestrate"] + cmd
        # 2026-10-04: no pre-wait here any more. The guard now queues waiters first-come-first-served
        # (runs/lock_queue), and polling the lock before joining that queue would only delay this driver.
        t0 = time.time()
        with open(log_path, "a") as log:
            log.write("\n=== iteration %d %s\n$ %s\n" % (k, time.strftime("%Y-%m-%d %H:%M:%S"), " ".join(full)))
            log.flush()
            p = subprocess.run(full, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            log.write(p.stdout)
            log.write("\n=== iteration %d rc=%d wall=%.0fs\n" % (k, p.returncode, time.time() - t0))
        last = None
        for line in reversed(p.stdout.strip().splitlines()):
            if line.startswith("{"):
                try:
                    last = json.loads(line)
                    break
                except ValueError:
                    pass
        print("[driver] %s iteration %d rc=%d wall=%.0fs last=%s" % (a.name, k, p.returncode, time.time() - t0,
                                                                      json.dumps(last)), flush=True)
        if p.returncode == 75:
            time.sleep(300)
            k += 1
            continue
        if last is not None:
            if "counts" in last and not any(c in last["counts"] for c in INCOMPLETE) and p.returncode == 0:
                print("[driver] %s complete" % a.name, flush=True)
                return 0
            if "compare_jobs" in last and last["done"] == last["compare_jobs"]:
                print("[driver] %s complete" % a.name, flush=True)
                return 0
            if last.get("batch") == "complete":
                print("[driver] %s complete" % a.name, flush=True)
                return 0
        k += 1
    print("[driver] %s NOT complete after %d iterations" % (a.name, a.max_iters), flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())

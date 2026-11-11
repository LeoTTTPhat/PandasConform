#!/usr/bin/env python3
"""D3 follow-up guarded job: (1) the exploratory Modin serial extension (d3_ext_plan.json, d3_run.py --tag ext),
(2) comparisons of all serial records with the original reference (d1_compare.py --d3; existing outputs are kept),
(3) checks N3/N1/N6 (d3_checks.py, parallel and resumable; the first attempt timed out inside the N2 job).
Run ONLY under the memory guard, from the workspace root, with the shared venv:
    python3 tools/memory_guard.py --start-if-fits --wait-lock 7200 --limit-gb 150 \
      --state runs/06_pandas_conformance_r5_replay_d3post.json -- \
      .venv/bin/python 06_pandas_conformance-ICDE/icde27/analysis/r5_replay/d3_post.py
"""
import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import r5common as R  # noqa: E402

REF_PY = os.path.join(R.ENVS, "ref", "bin", "python")
CAP_S = 120 * 60                       # guarded wall-time cap of this agent's jobs together (round brief)
RUNS = os.path.join(R.WS, "runs")
OTHER_STATES = ["d1", "d1b", "d2", "d1cmp", "d3n2b", "d2b", "d1cmp2"]
# guard states that ended without finished_utc (stopped jobs): end times observed by B2's watch loops
KNOWN_END = {"d1cmp": "2026-11-10T15:30:34Z", "d1cmp2": "2026-11-10T19:23:55Z"}


def used_seconds():
    import datetime
    import json
    tot = 0.0
    for name in OTHER_STATES:
        try:
            s = json.load(open(os.path.join(RUNS, "06_pandas_conformance_r5_replay_%s.json" % name)))
        except (OSError, ValueError):
            continue
        st = datetime.datetime.fromisoformat(s["started_utc"].replace("Z", "+00:00"))
        en = s.get("finished_utc") or KNOWN_END.get(name)
        en = datetime.datetime.fromisoformat(en.replace("Z", "+00:00")) if en else datetime.datetime.now(datetime.timezone.utc)
        tot += (en - st).total_seconds()
    return tot


def steps(remaining):
    ext = [sys.executable, os.path.join(HERE, "d3_run.py"), "--plan-file", "d3_ext_plan.json", "--tag", "ext",
           "--no-post", "--deadline", "200", "--hard-budget", "290"]
    cmp_ = [REF_PY, os.path.join(HERE, "d1_compare.py"), "--d3", "--workers", "2"]
    chk = [REF_PY, os.path.join(HERE, "d3_checks.py"), "--workers", "3"]
    if remaining >= 17.5 * 60:      # extension 5 + comparisons 4 + checks 8 minutes at most
        return [("modin serial extension", ext, 300, None), ("serial comparisons", cmp_, 240, R.SRC),
                ("checks N3/N1/N6", chk, 480, R.SRC)]
    if remaining >= 6 * 60:         # checks only
        return [("checks N3/N1/N6", chk, int(remaining - 60), R.SRC)]
    return []


def main():
    remaining = CAP_S - used_seconds()
    plan = steps(remaining)
    print("[d3post2] remaining guarded budget %.1f min -> steps %s" % (remaining / 60, [p[0] for p in plan]), flush=True)
    for name, cmd, tmo, pypath in plan:
        env = dict(os.environ)
        if pypath:
            env["PYTHONPATH"] = pypath
        ts = time.time()
        p = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             start_new_session=True)
        try:
            out, _ = p.communicate(timeout=tmo)
            print("[d3post2] %s rc=%s %.0fs\n%s" % (name, p.returncode, time.time() - ts, (out or "")[-3000:]), flush=True)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGTERM)
            time.sleep(5)
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            out, _ = p.communicate()
            print("[d3post2] %s timeout after %ds\n%s" % (name, tmo, (out or "")[-1500:]), flush=True)


if __name__ == "__main__":
    main()

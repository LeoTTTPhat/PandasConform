"""Timing runs (plan.md Sections 4 and 7: timing excludes capture; conformance excludes timing).

Same child runner with capture disabled, one notebook at a time, `--reps` repetitions, engine
defaults (FireDucks fallback logging off). Engine start-up (Ray init, MPI spawn) is recorded
separately (engine_setup_s) and excluded from notebook time. Each cell's last value and display()
arguments are rendered (repr) inside the timed region (review T1); every parallel engine gets the
same CPU budget `--cpus N` (review T2; `--cpus default` gives the engine-defaults row).

    python -m pconf.timing run    --campaign timing --set timing30 --engines ref,modin,fireducks,bodo --reps 3
    python -m pconf.timing report --campaign timing
"""
import argparse
import os
import statistics
import sys

from pconf import orchestrate, util


def report(campaign):
    root = os.path.join(orchestrate.raw_dir(campaign), "timing__" + orchestrate.harness_tag())
    rows = {}
    for dp, _, fn in os.walk(root):
        for n in fn:
            if not n.endswith(".json"):
                continue
            r = util.read_json(os.path.join(dp, n))
            if not r:
                continue
            key = (r["engine"], r["nb"], r.get("scale"), str((r.get("cfg") or {}).get("cpus")))
            ok = r.get("status") == "completed" and all(c.get("status") in ("ok", "setup", "empty", "skipped")
                                                         for c in r.get("cells", []))
            t = sum(c.get("wall_s", 0.0) for c in r.get("cells", []) if c.get("status") == "ok")
            rows.setdefault(key, []).append({"rep": r.get("rep"), "cells_wall_s": t, "all_ok": ok,
                                             "status": r.get("status"), "setup_s": r.get("engine_setup_s")})
    out = []
    for (e, nb, sc, cpus), reps in sorted(rows.items()):
        ts = [x["cells_wall_s"] for x in reps]
        out.append({"engine": e, "nb": nb, "scale": sc, "cpus": cpus, "reps": len(reps), "median_s": statistics.median(ts),
                    "min_s": min(ts), "max_s": max(ts), "all_ok": all(x["all_ok"] for x in reps),
                    "statuses": sorted({x["status"] for x in reps})})
    path = os.path.join(util.RESULTS, campaign, "timing_report__%s.json" % orchestrate.harness_tag())
    util.atomic_write_json(path, out, indent=1)
    print("wrote %s (%d rows)" % (path, len(out)))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--campaign", required=True)
    r.add_argument("--set", required=True)
    r.add_argument("--engines", required=True)
    r.add_argument("--scale", default="1.0")
    r.add_argument("--reps", default="3")
    r.add_argument("--nb-timeout", default="3600")
    r.add_argument("--cell-timeout", default="1200")
    r.add_argument("--limit", default="0")
    r.add_argument("--cpus", default="8", help="matched CPU budget for every parallel engine, or 'default'")
    p = sub.add_parser("report")
    p.add_argument("--campaign", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        return orchestrate.main(["run", "--campaign", a.campaign, "--set", a.set, "--engines", a.engines,
                                 "--scale", a.scale, "--mode", "timing", "--reps", a.reps, "--max-concurrency", "1",
                                 "--nb-timeout", a.nb_timeout, "--cell-timeout", a.cell_timeout, "--limit", a.limit,
                                 "--cpus", a.cpus])
    report(a.campaign)
    return 0


if __name__ == "__main__":
    sys.exit(main())

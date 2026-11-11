#!/usr/bin/env python3
"""Per-configuration resource metrics of a campaign's run records (reads only):
wall clock (orchestrator), cell time, input/output capture time, peak RSS (sampled after each
cell incl. children; child maxrss), statuses, cell statuses, fallback-flagged cells, capped columns,
bytes written to the store. Writes results/<campaign>/metrics__<harness>.json.

    .venv/bin/python 06_pandas_conformance/scripts/campaign_metrics.py --campaign pilot
"""
import argparse
import collections
import glob
import json
import os
import sys

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJ, "src"))
from pconf import orchestrate, util  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--mode", default="runs", choices=["runs", "timing"])
    a = ap.parse_args()
    root = os.path.join(orchestrate.raw_dir(a.campaign), "%s__%s" % (a.mode, orchestrate.harness_tag()))
    per = collections.defaultdict(lambda: collections.defaultdict(float))
    per_nb = {}
    for p in sorted(glob.glob(os.path.join(root, "*", "*", "*.json"))):
        r = util.read_json(p)
        if not r or "fingerprint" not in r:
            continue
        e = r["engine"]
        g = per[e]
        g["records"] += 1
        g["status:" + str(r.get("status"))] += 1
        g["wall_s"] += r.get("orchestrator_wall_s") or 0
        cells = r.get("cells", [])
        cw = sum(c.get("wall_s", 0) for c in cells)
        ci = sum(c.get("t_capture_in", 0) for c in cells)
        co = sum(c.get("t_capture_out", 0) for c in cells)
        g["cell_s"] += cw
        g["capture_in_s"] += ci
        g["capture_out_s"] += co
        rss = max([c.get("rss_after") or 0 for c in cells] + [0])
        g["peak_rss_gb"] = max(g["peak_rss_gb"], rss / 1e9)
        g["peak_maxrss_self_gb"] = max(g["peak_maxrss_self_gb"], (r.get("maxrss_self") or 0) / 1e9)
        for c in cells:
            g["cellstatus:" + str(c.get("status"))] += 1
            if any("fallback" in f or "default_to_pandas" in f for f in c.get("flags", [])):
                g["fallback_cells"] += 1
        cs = r.get("capture_stats") or {}
        g["capped_columns"] += cs.get("capped_columns", 0)
        g["bytes_written_gb"] += (cs.get("bytes_written", 0) or 0) / 1e9
        if r.get("reused_from"):
            g["reused"] += 1
        per_nb[e + "|" + r["nb"]] = {"status": r.get("status"), "wall_s": r.get("orchestrator_wall_s"),
                                     "cell_s": round(cw, 2), "capture_s": round(ci + co, 2),
                                     "peak_rss_gb": round(rss / 1e9, 2), "n_cells": len(cells),
                                     "capped_columns": cs.get("capped_columns", 0), "reused": bool(r.get("reused_from"))}
    out = {"campaign": a.campaign, "harness_tag": orchestrate.harness_tag(),
           "per_engine": {e: {k: (round(v, 3) if isinstance(v, float) else v) for k, v in sorted(g.items())}
                          for e, g in sorted(per.items())},
           "per_notebook": per_nb}
    path = os.path.join(util.RESULTS, a.campaign, "metrics__%s__%s.json" % (a.mode, orchestrate.harness_tag()))
    util.atomic_write_json(path, out, indent=1)
    for e, g in sorted(out["per_engine"].items()):
        print("%-14s rec=%d wall=%.0fs cell=%.0fs capture=%.0fs peakRSS=%.1fGB statuses=%s fallback=%d capped=%d" % (
            e, g["records"], g["wall_s"], g["cell_s"], g["capture_in_s"] + g["capture_out_s"], g["peak_rss_gb"],
            {k[7:]: int(v) for k, v in g.items() if k.startswith("status:")}, g.get("fallback_cells", 0),
            g.get("capped_columns", 0)))
    print("wrote", path)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Summary of the C1 runs (review round R5, agent B1): per stream, the run statuses from the campaign manifests and the
stream logs, compared with c1_selection.json; and the guard records of the C1 jobs. Read-only; writes
icde27/analysis/r5_capture/c1_runlog.json.

    python3 06_pandas_conformance-ICDE/icde27/analysis/r5_capture/c1_runlog.py
"""
import collections
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
WS = os.path.dirname(PROJ)
R5 = os.path.join(PROJ, "work", "r5_capture")


def main():
    sel = json.load(open(os.path.join(HERE, "c1_selection.json")))
    out = {"streams": {}, "guards": {}}
    for name, st in sorted(sel["streams"].items()):
        want = [o[0] for o in st["order"]]
        m = {}
        for p in glob.glob(os.path.join(R5, "results", "r5c1_" + name, "raw", "campaign_h*.json")):
            for k, v in (json.load(open(p)).get("runs") or {}).items():
                m[k.split("|")[2]] = v.get("status")
        log = os.path.join(R5, "logs", name + ".log")
        logst = collections.Counter()
        if os.path.exists(log):
            for line in open(log, errors="replace"):
                mm = re.search(r"->\s+(\S+)\s*$", line)
                if line.startswith("[run]") and mm:
                    logst[mm.group(1)] += 1
        out["streams"][name] = {"engine": st["engine"], "selected": len(want),
                                "statuses": dict(collections.Counter(m.get(nb, "no record") for nb in want)),
                                "log_statuses": dict(logst),
                                "not_completed": sorted(nb for nb in want if m.get(nb) != "completed")}
    for p in sorted(glob.glob(os.path.join(WS, "runs", "06_pandas_conformance_r5_capture_*.json"))):
        d = json.load(open(p))
        att = d.get("attempts") or [{}]
        out["guards"][os.path.basename(p)] = {k: d.get(k) for k in ("status", "started_utc", "finished_utc", "returncode",
                                                                      "lock_wait_seconds", "limit_bytes")}
        out["guards"][os.path.basename(p)].update({"peak_tree_rss_gb": round((att[-1].get("peak_tree_rss_bytes") or 0) / 1e9, 1),
                                                   "peak_host_used_gb": round((att[-1].get("peak_host_used_bytes") or 0) / 1e9, 1),
                                                   "attempts": len(d.get("attempts") or [])})
    with open(os.path.join(HERE, "c1_runlog.json"), "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    for name, v in out["streams"].items():
        print("%-22s %-16s selected %3d statuses %s" % (name, v["engine"], v["selected"], v["statuses"]))
    for g, v in out["guards"].items():
        print(g, v)


if __name__ == "__main__":
    main()

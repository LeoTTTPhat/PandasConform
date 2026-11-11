#!/usr/bin/env python3
"""C1 re-execution selection (review round R5, agent B1): which notebooks run, to which cell, in which stream.

Reads c1_plan.json and the original compare outputs (read-only); writes icde27/analysis/r5_capture/c1_selection.json
and the per-stream notebook sets and stop plans under icde27/analysis/r5_capture/c1_streams/.

Pre-declared rule (RESULTS.md, C1 design):
  tier 1  printed-form cells (pf_out or pf_in) that are in the clean@E2 view, or that read a printed-form value and
          whose other inputs agree at E2 or finer (they can enter clean@E2);
  tier 2  every other printed-form cell (scored).
  For each configuration and notebook the run stops at the last printed-form cell, unless that costs more than
  EXTEND_S seconds of recorded execution and capture time beyond the last tier-1 cell, in which case it stops at
  the last tier-1 cell; a notebook with only tier-2 cells runs only if its cost is at most EXTEND_S.
  Runs costing more than HEAVY_S (recorded time to the stop cell) form the second guarded job, ordered by the number
  of tier-1 cells per second; for the guarded-time budget only the first of each stream runs (JOB2_PER_STREAM).
  Job-1 streams run longest first, except for memory: in the modin stream runs whose
  original peak exceeded MEM_HEAVY_GB go first, in the other engine streams such runs go last. The new reference
  run covers every selected notebook up to the largest stop cell.
"""
import collections
import importlib.util
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
OUTDIR = os.path.join(HERE, "c1_streams")
EXTEND_S = 120.0
HEAVY_S = 1000.0
JOB2_PER_STREAM = 1   # guarded-time budget: job 2 runs only the first (best tier-1 cells per second) heavy run per stream
MEM_HEAVY_GB = 50.0   # original peak_tree_rss_gb above this: ordered so that two such runs do not overlap in job 1
LABEL_ENGINE = {"pyarrow_backend": "pyarrow_backend", "modin": "modin", "fireducks": "fireducks", "bodo": "bodo",
                "dask": "dask", "p15": "p15", "p30": "p30"}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    T = load_module("rootcause_taxonomy", os.path.join(PROJ, "scripts", "rootcause_taxonomy.py"))
    plan = json.load(open(os.path.join(HERE, "c1_plan.json")))
    full = {}
    for camp in ("conf_1x", "drift"):
        _, best = T.select_outputs(camp, T.COMPARE)
        for (lab, nb, sc), (_, r, p) in best.items():
            full[(lab, nb)] = {c["i"]: c for c in r["cells"]}
    sel = {"rule": {"EXTEND_S": EXTEND_S, "HEAVY_S": HEAVY_S}, "by_label": {}, "streams": {}}
    runs = []          # (label, nb, stop, cost, n_tier1, ref cost)
    peak = {}          # (label, nb) -> original peak_tree_rss_gb of the configuration's run
    for label, L in plan["by_label"].items():
        S = sel["by_label"].setdefault(label, {"notebooks": {}, "not_run": {}})
        for nb, N in sorted(L["notebooks"].items()):
            t1, t2 = [], []
            for c in N["cells"]:
                fc = full[(label, nb)][c["i"]]
                il = fc.get("input_levels") or {}
                others_ok = all(v in ("E0", "E1", "E2") for n, v in il.items() if n not in c["pf_in"])
                enter = (not c["in_clean_E2"]) and bool(c["pf_in"]) and others_ok and not c["post_timeout"]
                (t1 if (c["in_clean_E2"] or enter) else t2).append(dict(c, can_enter=enter))
            last_all = N["cells"][-1]
            if t1:
                last1 = t1[-1]
                stop = last_all if last_all["cum_eng_s"] - last1["cum_eng_s"] <= EXTEND_S else last1
            else:
                stop = last_all if last_all["cum_eng_s"] <= EXTEND_S else None
            if stop is None:
                S["not_run"][nb] = {"tier2_cells": [c["i"] for c in t2], "cost_s": last_all["cum_eng_s"]}
                continue
            cov2 = [c["i"] for c in t2 if c["i"] <= stop["i"]]
            unc2 = [c["i"] for c in t2 if c["i"] > stop["i"]]
            S["notebooks"][nb] = {"stop": stop["i"], "cost_s": stop["cum_eng_s"], "ref_cost_s": stop["cum_ref_s"],
                                  "tier1_cells": [c["i"] for c in t1], "tier1_can_enter": [c["i"] for c in t1 if c["can_enter"]],
                                  "tier2_covered": cov2, "tier2_uncovered": unc2}
            runs.append((label, nb, stop["i"], stop["cum_eng_s"], len(t1), stop["cum_ref_s"]))
            peak[(label, nb)] = json.load(open(os.path.join(PROJ, N["eng_record"]))).get("peak_tree_rss_gb") or 0.0
    # streams
    single = ("p15", "p30", "pyarrow_backend")
    streams = collections.defaultdict(list)
    for label, nb, stop, cost, n1, rcost in runs:
        if label in single:
            streams["job1_" + label].append((nb, stop, cost, n1))
        elif cost > HEAVY_S:
            streams["job2_" + label].append((nb, stop, cost, n1))
        else:
            streams["job1_" + label].append((nb, stop, cost, n1))
    # reference: every selected notebook, up to the largest stop cell over configurations
    ref_stop = {}
    for label, nb, stop, cost, n1, rcost in runs:
        ref_stop[nb] = max(ref_stop.get(nb, -1), stop)
    ref_cost = {nb: max(rc for (l, n, s, c, k, rc) in runs if n == nb) for nb in ref_stop}
    streams["job1_ref"] = [(nb, ref_stop[nb], ref_cost[nb], 0) for nb in sorted(ref_stop)]
    os.makedirs(OUTDIR, exist_ok=True)
    for name, lst in sorted(streams.items()):
        label = name.split("_", 1)[1]
        eng = "ref" if label == "ref" else LABEL_ENGINE[label]
        if name.startswith("job2"):
            lst.sort(key=lambda r: -r[3] / max(r[2], 1.0))   # tier-1 cells per second, best first
            for r in lst[JOB2_PER_STREAM:]:                   # not run: over the guarded-time budget
                sel["by_label"][label]["not_run"][r[0]] = {"budget": True, "cost_s": round(r[2], 1),
                                                           "tier1_cells": sel["by_label"][label]["notebooks"][r[0]]["tier1_cells"]}
                del sel["by_label"][label]["notebooks"][r[0]]
            del lst[JOB2_PER_STREAM:]
        else:
            lst.sort(key=lambda r: -r[2])                     # longest first (better packing)
            heavy = [r for r in lst if peak.get((label, r[0]), 0.0) > MEM_HEAVY_GB]
            rest = [r for r in lst if r not in heavy]
            lst[:] = (heavy + rest) if label == "modin" else (rest + heavy)
        nbs = [r[0] for r in lst]
        with open(os.path.join(OUTDIR, name + "_set.json"), "w") as f:
            json.dump({"notebooks": nbs}, f, indent=1)
        with open(os.path.join(OUTDIR, name + "_stop.json"), "w") as f:
            json.dump({"%s|%s" % (eng, r[0]): r[1] for r in lst}, f, indent=1, sort_keys=True)
        sel["streams"][name] = {"engine": eng, "notebooks": len(lst), "recorded_cost_s": round(sum(r[2] for r in lst), 1),
                                "max_notebook_s": round(max(r[2] for r in lst), 1), "tier1_cells": sum(r[3] for r in lst),
                                "order": [[r[0], r[1], round(r[2], 1), r[3]] for r in lst]}
    tot = collections.Counter()
    for label, S in sel["by_label"].items():
        tot["tier1"] += sum(len(v["tier1_cells"]) for v in S["notebooks"].values())
        tot["tier2_covered"] += sum(len(v["tier2_covered"]) for v in S["notebooks"].values())
        tot["tier2_uncovered"] += sum(len(v["tier2_uncovered"]) for v in S["notebooks"].values()) + \
            sum(len(v.get("tier2_cells", [])) for v in S["not_run"].values())
        tot["tier1_not_run_budget"] += sum(len(v.get("tier1_cells", [])) for v in S["not_run"].values())
    sel["totals"] = dict(tot)
    with open(os.path.join(HERE, "c1_selection.json"), "w") as f:
        json.dump(sel, f, indent=1, sort_keys=True)
    for name, v in sorted(sel["streams"].items()):
        print("%-22s %-16s nbs %3d cost %7.1f s max %7.1f tier1 %3d" % (name, v["engine"], v["notebooks"], v["recorded_cost_s"],
                                                                     v["max_notebook_s"], v["tier1_cells"]))
    print("totals", dict(tot))


if __name__ == "__main__":
    main()

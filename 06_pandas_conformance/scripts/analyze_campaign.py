#!/usr/bin/env python3
"""Aggregate a campaign's compare outputs (reads only; shared venv):

    .venv/bin/python 06_pandas_conformance/scripts/analyze_campaign.py --campaign pilot

Uses the same output selection as `orchestrate summarize` (one output per engine/notebook/scale:
with ref#2 first, newest first). Cell populations per engine:
  all        comparable cells: every cell except REF_ERR, NONDET, NOOUT and SETUP_ERR
  clean_E0   comparable and strictly clean-input (plan definition)
  clean_E2   comparable and clean at E2 (inputs equal modulo widening/tolerance)
For each population: class shares (E0..E4, DIFF, ERR, TIMEOUT, CRASH, KILLED, NOTRUN, UNCOMPARABLE)
with 95% bootstrap intervals over notebooks (1,000 resamples, seed 0), cumulative "conformant at
<= Ek" shares, fallback-flagged share; operation family x engine finest-level table (clean_E2);
first divergent cell per notebook; per-notebook engine status. Output:
results/<campaign>/analysis__<compare_tag>.json
"""
import argparse
import collections
import os
import sys

import numpy as np

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJ, "src"))
from pconf import orchestrate, util  # noqa: E402

LEVELS = ["E0", "E1", "E2", "E3", "E4"]
CLASSES = LEVELS + ["DIFF", "UNCOMPARABLE", "ERR", "TIMEOUT", "CRASH", "KILLED", "MEMORY", "NOTRUN"]
EXCLUDED = {"REF_ERR", "NONDET", "NOOUT", "SETUP_ERR"}


def select_outputs(campaign):
    root = os.path.join(orchestrate.raw_dir(campaign), "compare__" + orchestrate.compare_tag())
    best = {}
    for dp, _, fn in os.walk(root):
        for n in fn:
            if not n.endswith(".json") or n.startswith(".tmp"):
                continue
            p = os.path.join(dp, n)
            r = util.read_json(p)
            if not r:
                continue
            ref = r["meta"].get("ref") or "ref"
            label = r["meta"]["engine"] if ref == "ref" else "%s~vs~%s" % (r["meta"]["engine"], ref)
            key = (label, r["meta"]["nb"], r["meta"].get("scale"))
            rank = (r["meta"].get("ref2_record") is not None, os.path.getmtime(p))
            if key not in best or rank > best[key][0]:
                best[key] = (rank, r)
    return {k: v[1] for k, v in best.items()}


def shares_with_ci(per_nb_counts, rng, reps=1000):
    """per_nb_counts: list of Counter (one per notebook). Shares pooled over cells; CI by
    resampling notebooks."""
    tot = collections.Counter()
    for c in per_nb_counts:
        tot.update(c)
    n = sum(tot.values())
    out = {"cells": n, "notebooks": len(per_nb_counts), "share": {}, "ci95": {}, "cum_share": {}}
    if not n:
        return out
    arr = np.array([[c.get(k, 0) for k in CLASSES] for c in per_nb_counts], dtype=float)
    idx = rng.integers(0, len(per_nb_counts), size=(reps, len(per_nb_counts)))
    boot = arr[idx].sum(axis=1)
    denom = boot.sum(axis=1, keepdims=True)
    denom[denom == 0] = 1
    bs = boot / denom
    for j, k in enumerate(CLASSES):
        out["share"][k] = round(tot.get(k, 0) / n, 4)
        out["ci95"][k] = [round(float(np.percentile(bs[:, j], 2.5)), 4), round(float(np.percentile(bs[:, j], 97.5)), 4)]
    run = 0
    for L in LEVELS:
        run += tot.get(L, 0)
        out["cum_share"]["<=" + L] = round(run / n, 4)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", required=True)
    a = ap.parse_args()
    outs = select_outputs(a.campaign)
    rng = np.random.default_rng(0)
    engines = sorted({k[0] for k in outs})
    res = {"campaign": a.campaign, "compare_tag": orchestrate.compare_tag(), "engines": {}, "families": {},
           "first_divergent": {}, "eng_status": {}}
    for e in engines:
        pops = {"all": [], "clean_E0": [], "clean_E2": []}
        fam = collections.defaultdict(collections.Counter)
        excluded = collections.Counter()
        fallback = collections.Counter()
        for (eng, nb, sc), r in sorted(outs.items()):
            if eng != e:
                continue
            res["first_divergent"].setdefault(e, {})[nb] = r["first_divergent"]
            res["eng_status"].setdefault(e, {})[nb] = r["meta"].get("eng_status")
            cnt = {k: collections.Counter() for k in pops}
            for c in r["cells"]:
                cls = c["cls"]
                if cls in EXCLUDED:
                    excluded[cls] += 1
                    continue
                cnt["all"][cls] += 1
                fallback["all"] += bool(c.get("fallback"))
                if c.get("clean_input"):
                    cnt["clean_E0"][cls] += 1
                lv = c.get("clean_level")
                if lv in ("E0", "E1", "E2"):
                    cnt["clean_E2"][cls] += 1
                    fallback["clean_E2"] += bool(c.get("fallback"))
                    for f in c.get("families", ["other"]):
                        fam[f][cls] += 1
            for k in pops:
                pops[k].append(cnt[k])
        res["engines"][e] = {k: shares_with_ci(v, rng) for k, v in pops.items()}
        res["engines"][e]["excluded_cells"] = dict(excluded)
        res["engines"][e]["fallback_cells"] = dict(fallback)
        res["families"][e] = {f: dict(c) for f, c in sorted(fam.items())}
    path = os.path.join(util.RESULTS, a.campaign, "analysis__%s.json" % orchestrate.compare_tag())
    util.atomic_write_json(path, res, indent=1)
    for e in engines:
        g = res["engines"][e]
        for pop in ("all", "clean_E0", "clean_E2"):
            s = g[pop]
            if not s["cells"]:
                continue
            top = ", ".join("%s %.1f%%" % (k, 100 * s["share"][k]) for k in CLASSES if s["share"].get(k))
            print("%-14s %-8s nb=%d cells=%d  %s" % (e, pop, s["notebooks"], s["cells"], top))
    print("wrote", path)


if __name__ == "__main__":
    main()

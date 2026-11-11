#!/usr/bin/env python3
"""D1 (targeted second execution): write the pre-declared replay plan d1_plan.json BEFORE any run.

Disputed cells: every conf_1x engine cell that is an introduced DIFF under the pure criterion (class DIFF, coarser
than its clean level; r4_cell_flags.csv kind_exception_off == introduced). This is a superset of the paper's
exception-on counts; both views are reported. Notebooks: every notebook with a disputed cell whose original conf_1x
engine run took at most MAX_WALL_S (longer ones are listed as not replayed). Controls: per engine CONTROLS notebooks
without any disputed cell, original run completed in at most CONTROL_MAX_WALL_S, drawn with random.Random(SEED).
Stdlib only.  Usage: python3 d1_plan.py
"""
import collections
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r5common as R  # noqa: E402

MAX_WALL_S = 900
CONTROLS = 3
CONTROL_MAX_WALL_S = 300
SEED = 20261110
OUT = os.path.join(R.HERE, "d1_plan.json")


def compare_outputs(engine):
    d = os.path.join(R.CONF1X_COMPARE, engine, "sf1")
    out = {}
    for n in sorted(os.listdir(d)):
        if n.endswith(".json"):
            c = R.read_json(os.path.join(d, n))
            out[c["meta"]["nb"]] = (os.path.join(d, n), c)
    return out


def main():
    flags = R.cell_flags()
    plan = {"item": "D1", "created_before_any_run": True, "max_wall_s": MAX_WALL_S, "controls_per_engine": CONTROLS,
            "control_max_wall_s": CONTROL_MAX_WALL_S, "seed": SEED, "engines": {}}
    for eng in R.ENGINES:
        cmp_ = compare_outputs(eng)
        disputed = []
        for r in flags:
            if r["campaign"] != "conf_1x" or r["configuration"] != eng or r["cls"] != "DIFF":
                continue
            if r["kind_exception_off"] != "introduced":
                continue
            disputed.append({"nb": r["nb"], "cell": int(r["cell"]), "clean_level": r["clean_level"],
                             "kind_exception_on": r["kind_exception_on"], "assigned_by": r["assigned_by"],
                             "cause": r["cause"] or (r["single_rater_cause"] and "single_rater:" + r["single_rater_cause"]),
                             "printed_form_artifact": r["printed_form_artifact"] == "True",
                             "reduced_capture_notebook": r["reduced_capture_notebook"] == "True"})
        by_nb = collections.defaultdict(list)
        for d in disputed:
            by_nb[d["nb"]].append(d)
        nbs, skipped = [], []
        for nb in sorted(by_nb):
            path, c = cmp_[nb]
            rec = R.read_json(os.path.join(R.PROJ, c["meta"]["eng_record"]))
            w = rec.get("orchestrator_wall_s") or rec.get("wall_s") or 0
            entry = {"nb": nb, "orig_wall_s": w, "orig_status": rec.get("status"), "n_disputed": len(by_nb[nb]),
                     "orig_fingerprint": rec.get("fingerprint"), "compare_output": os.path.relpath(path, R.PROJ),
                     "eng_record": c["meta"]["eng_record"], "ref_record": c["meta"]["ref_record"],
                     "ref2_record": c["meta"]["ref2_record"], "peak_tree_rss_gb": rec.get("peak_tree_rss_gb")}
            (nbs if w <= MAX_WALL_S else skipped).append(entry)
        pool = []
        for nb, (path, c) in sorted(cmp_.items()):
            if nb in by_nb:
                continue
            rec = R.read_json(os.path.join(R.PROJ, c["meta"]["eng_record"]))
            w = rec.get("orchestrator_wall_s") or 0
            if rec.get("status") == "completed" and w <= CONTROL_MAX_WALL_S:
                pool.append({"nb": nb, "orig_wall_s": w, "orig_status": rec.get("status"), "n_disputed": 0,
                             "orig_fingerprint": rec.get("fingerprint"), "compare_output": os.path.relpath(path, R.PROJ),
                             "eng_record": c["meta"]["eng_record"], "ref_record": c["meta"]["ref_record"],
                             "ref2_record": c["meta"]["ref2_record"], "peak_tree_rss_gb": rec.get("peak_tree_rss_gb")})
        rng = random.Random("%d|%s" % (SEED, eng))
        controls = sorted(rng.sample(pool, CONTROLS), key=lambda e: e["nb"])
        plan["engines"][eng] = {
            "disputed_cells": disputed, "n_disputed": len(disputed),
            "n_disputed_exception_on": sum(1 for d in disputed if d["kind_exception_on"] == "introduced"),
            "notebooks": nbs, "not_replayed_long": skipped, "controls": controls, "control_pool_size": len(pool),
            "est_seconds": round(sum(e["orig_wall_s"] for e in nbs + controls), 1)}
        print("%-16s disputed %3d (exception on %3d) notebooks %2d (+%d long not replayed: %d cells) controls %s est %.1f min"
              % (eng, len(disputed), plan["engines"][eng]["n_disputed_exception_on"], len(nbs), len(skipped),
                 sum(e["n_disputed"] for e in skipped), [c["nb"] for c in controls],
                 plan["engines"][eng]["est_seconds"] / 60))
    if os.path.exists(OUT):
        print("d1_plan.json exists; not overwritten (pre-declared)")
        return
    R.write_json(OUT, plan)
    print("wrote", OUT, R.sha256_file(OUT))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Print the C1 tables for RESULTS.md from c1_results.json (review round R5, agent B1). Read-only.

    python3 06_pandas_conformance-ICDE/icde27/analysis/r5_capture/c1_report.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = ["p15", "p30", "pyarrow_backend", "modin", "fireducks", "bodo", "dask"]
ENG = ["pyarrow_backend", "modin", "fireducks", "bodo", "dask"]


def pct(x):
    return "%.1f" % (100 * x)


def main():
    d = json.load(open(os.path.join(HERE, "c1_results.json")))
    print("## census categories (graded / primary)")
    for g in ("matching", "DIFF", "other"):
        print("*", g, json.dumps(d["census_categories"][g], sort_keys=True))
    print("## census categories (nested E0 / strict)")
    for g in ("matching", "DIFF", "other"):
        print("*", g, json.dumps(d["census_categories_nested_e0"][g], sort_keys=True))
    print("## census categories, clean@E2 cells (graded)")
    for g in ("matching", "DIFF", "other"):
        print("*", g, json.dumps(d["census_categories_clean_E2"][g], sort_keys=True))
    print("## by label (graded)")
    for lab in LAB:
        v = d["census_categories_by_label"].get(lab, {})
        print("*", lab, json.dumps(v, sort_keys=True))
    print("## run-to-run (all cells up to the stop cells)")
    for lab, v in sorted(d["run_to_run_all_cells"].items()):
        print("*", lab, json.dumps(v, sort_keys=True))
    print("## object hash determinism")
    for k, v in sorted(d["object_hash_determinism"].items()):
        print("*", k, json.dumps(v, sort_keys=True))
    print("## readers (graded)")
    for lab, v in sorted(d["readers"].items()):
        print("*", lab, json.dumps(v, sort_keys=True))
    print("## outputs that change (orig -> graded, nested-E0)")
    for k, v in sorted(d["exact_mismatch_outputs_graded"].items(), key=lambda kv: -kv[1]):
        print("*", k, v)
    P = d["principal"]
    variants = [v for v in ("published", "exact_graded", "exact_nested_e0", "exact_graded_strict", "exclude_all_pf") if v in P]
    print("## clean@E2 DIFF share (%) [cells]")
    print("| config | " + " | ".join(variants) + " |")
    print("|---|" + "---:|" * len(variants))
    for lab in LAB:
        print("| %s | " % lab + " | ".join("%s [%d]" % (pct(P[v]["by_label"][lab]["clean_E2_DIFF"]["share"]),
                                                   P[v]["by_label"][lab]["clean_E2_DIFF"]["den"]) for v in variants) + " |")
    print("## paired DIFF difference, points [95% interval] (cells), reading")
    print("| pair | " + " | ".join(variants) + " |")
    print("|---|" + "---|" * len(variants))
    for e in ENG:
        for p in ("p15", "p30"):
            k = "%s-%s" % (e, p)
            cells = []
            for v in variants:
                q = P[v]["pairs"][k]
                r = {"not distinguishable": "n.d.", "more often": "more", "less often": "less"}[q["reading"]]
                cells.append("%+.1f [%+.1f, %+.1f] (%d) %s%s" % (q["diff_pp"], q["ci95_pp"][0], q["ci95_pp"][1], q["cells"], r,
                                                               "" if q["within_2pp"] else " out2"))
            print("| %s | " % k + " | ".join(cells) + " |")
    print("## notebooks with an introduced DIFF: pure / heuristic")
    print("| config | " + " | ".join(variants) + " |")
    print("|---|" + "---|" * len(variants))
    for lab in LAB:
        print("| %s | " % lab + " | ".join("%d / %d" % (P[v]["by_label"][lab]["notebooks_introduced_DIFF_pure"]["num"],
                                                    P[v]["by_label"][lab]["notebooks_introduced_DIFF_heuristic"]["num"]) for v in variants) + " |")


if __name__ == "__main__":
    main()

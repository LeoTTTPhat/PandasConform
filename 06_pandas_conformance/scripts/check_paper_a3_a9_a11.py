#!/usr/bin/env python3
"""Recheck the numbers behind the paper's A3, A9 and A11 statements against results/summary.json (2026-10-05).

A3  (Findings, Section 6, abstract, Conclusion): clean@E2 DIFF shares of the five core engines and of both
    pandas versions; notebooks diverging at E4.
A9  (Section 8): class of the first E4-divergent cell per notebook (pandas 3.0.6 and 1.5.3).
A11 (Section 6): composition of the unpaired clean@E2 sets (reading cells) and the paired common-cell view
    (summary.json common_clean_E2: cells, DIFF shares, paired DIFF-share differences and their readings).
Each expected value is the number printed in paper/main.tex (percent with one decimal, round half up; counts
exact). Read-only; prints one line per check and exits 1 on any mismatch.

Usage (from the project folder): ../.venv/bin/python scripts/check_paper_a3_a9_a11.py
"""
import decimal
import json
import os
import sys

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def p1(x):
    """100*x with one decimal, round half up (paper precision)."""
    q = decimal.Decimal(repr(x)) * 100
    return float(q.quantize(decimal.Decimal("0.1"), rounding=decimal.ROUND_HALF_UP))


def main():
    s = json.load(open(os.path.join(PROJ, "results", "summary.json")))
    c1 = s["campaigns"]["conf_1x"]["engines"]
    dr = s["campaigns"]["drift"]["engines"]
    cc = s.get("common_clean_E2") or {}
    checks = []

    def chk(name, expected, got):
        checks.append((name, expected, got, expected == got))

    # A3
    for e, v in (("modin", 2.0), ("pyarrow_backend", 2.6), ("fireducks", 2.7), ("bodo", 6.0), ("dask", 6.2)):
        chk("A3 conf_1x.%s clean_E2 DIFF %%" % e, v, p1(c1[e]["views"]["clean_E2"]["share"]["DIFF"]))
    for e, v in (("p15", 2.3), ("p30", 2.5)):
        chk("A3 drift.%s clean_E2 DIFF %%" % e, v, p1(dr[e]["views"]["clean_E2"]["share"]["DIFF"]))
    for e, v in (("modin", 57), ("pyarrow_backend", 60), ("fireducks", 67), ("bodo", 94), ("dask", 100)):
        chk("A3 conf_1x.%s notebooks diverging at E4" % e, v, c1[e]["first_divergence"]["E4"]["notebooks_diverged"])
    for e, v in (("p15", 43), ("p30", 53)):
        chk("A3 drift.%s notebooks diverging at E4" % e, v, dr[e]["first_divergence"]["E4"]["notebooks_diverged"])
    # A9
    for e, exp in (("p30", {"DIFF": 29, "ERR": 17, "UNCOMPARABLE": 7}), ("p15", {"DIFF": 38, "ERR": 1, "UNCOMPARABLE": 4})):
        got = dr[e]["first_divergence"]["E4"]["class_at_first_divergence"]
        for k, v in exp.items():
            chk("A9 drift.%s first E4 divergence class %s" % (e, k), v, got.get(k, 0))
    # A11, unpaired composition
    fam = s["campaigns"]["conf_1x"]["families"]
    chk("A11 conf_1x.dask clean_E2 cells", 545, c1["dask"]["views"]["clean_E2"]["cells"])
    chk("A11 conf_1x.modin clean_E2 cells", 2332, c1["modin"]["views"]["clean_E2"]["cells"])
    chk("A11 conf_1x.dask read cells (clean_E2)", 134, fam["dask"]["read"]["cells"])
    chk("A11 conf_1x.modin read cells (clean_E2)", 132, fam["modin"]["read"]["cells"])
    # A11, paired common-cell view
    chk("A11 common_clean_E2 status", "complete", cc.get("status"))
    if cc.get("status") == "complete":
        chk("A11 common cells", 461, cc["cells"])
        chk("A11 common notebooks with cells", 102, cc["notebooks_with_common_cells"])
        chk("A11 common cells held by the 5 largest notebooks %", 26.9,
            p1(cc["cells_per_notebook"]["largest_5_notebooks_share"]))
        for l, v in (("p30", 2.0), ("p15", 3.7), ("modin", 2.8), ("pyarrow_backend", 3.0), ("fireducks", 3.7),
                     ("bodo", 5.0), ("dask", 5.0)):
            chk("A11 common %s DIFF %%" % l, v, p1(cc["per_label"][l]["share"]["DIFF"]))
        for base, rows in (("p30", (("modin", 0.9, -0.9, 2.8, "about as often"),
                                    ("pyarrow_backend", 1.1, -0.4, 2.7, "about as often"),
                                    ("fireducks", 1.7, -0.5, 4.5, "about as often"),
                                    ("bodo", 3.0, 1.5, 4.9, "more often"), ("dask", 3.0, 0.8, 5.2, "more often"))),
                           ("p15", (("modin", None, None, None, "about as often"),
                                    ("pyarrow_backend", None, None, None, "about as often"),
                                    ("fireducks", None, None, None, "about as often"),
                                    ("bodo", 1.3, -1.6, 4.2, "about as often"),
                                    ("dask", 1.3, -2.0, 4.2, "about as often")))):
            for e, d, lo, hi, reading in rows:
                p = cc["paired_DIFF_vs_" + base][e]
                if d is not None:
                    chk("A11 paired %s-%s diff pp" % (e, base), d, p1(p["diff"]))
                    chk("A11 paired %s-%s ci95 pp" % (e, base), [lo, hi], [p1(p["ci95"][0]), p1(p["ci95"][1])])
                chk("A11 paired %s-%s reading" % (e, base), reading, p["reading"])
    bad = [c for c in checks if not c[3]]
    for name, exp, got, ok in checks:
        print("%-8s %-48s paper %-16s summary %s" % ("ok" if ok else "MISMATCH", name, exp, got))
    print("%d checks, %d mismatches" % (len(checks), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

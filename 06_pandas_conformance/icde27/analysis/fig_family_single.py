#!/usr/bin/env python3
"""Figure 2 of the ICDE copy: DIFF share per operation family and configuration (redesigned 2026-11-10).

Reads results/summary.json (campaigns.{drift,conf_1x}.families.<label>.<family>.{cells,counts.DIFF}: the clean@E2
cells of each operation family) and writes icde27/figures/fig2_opfamily_single.pdf in the figure style
of figstyle.py, beside this script: one row per configuration (the two pandas versions, then the
five engine configurations, as in Figure 1), one column per family (analyze.FAMILIES order), and
each cell coloured by the share of its clean@E2 cells that are DIFF, in four classes (below 5%, 5-10%, 10-20%, 20% or
more) on a one-hue red ramp built from the style's red arm, so that DIFF keeps the red of Figures 1, 3 and 4; the
share is printed (rounded half up to an integer) in the cells of the two upper classes. Families with fewer than
analyze.MIN_FAMILY_CELLS cells are left blank with a dash. Prints the plotted shares as JSON.

The previous version of this figure showed the finest level reached by at least half of each family's cells; that
statistic stays in summary.json (finest_level_majority) and in the text.

    cd <project folder>        (the artifact's repository root)
    ../.venv/bin/python icde27/analysis/fig_family_single.py
"""
import bisect
import decimal
import importlib.util
import json
import os

import figstyle as fs

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(os.path.dirname(HERE), "figures", "fig2_opfamily_single.pdf")
ROWS = [("drift", "p15", "pandas 1.5.3"), ("drift", "p30", "pandas 3.0.6"),
        ("conf_1x", "pyarrow_backend", "pyarrow backend"), ("conf_1x", "modin", "Modin"),
        ("conf_1x", "fireducks", "FireDucks"), ("conf_1x", "bodo", "Bodo (one worker)"), ("conf_1x", "dask", "Dask")]
GAP = 0.35                                    # extra space between the pandas baselines and the engines (row units)
FAMILY_NAME = {"read": "reading", "merge_join": "merge, join", "groupby_agg": "group-by agg.", "sort": "sorting",
               "string": "string", "datetime": "datetime", "apply_map": "apply, map", "pivot_reshape": "pivot, reshape",
               "describe_stats": "descriptive stats", "missing": "missing values", "dedup_unique": "dedup, unique",
               "indexing": "indexing", "dtype_conv": "dtype conversion", "other": "other"}
# DIFF-share classes (percent): lower edges and fills, light to dark (the style's red arm without its lightest step,
# which is below 2:1 against white); shares in the classes from LABEL_FROM on are printed
EDGES = [0.0, 5.0, 10.0, 20.0]
FILLS = fs.RED[1:]
CLASS_LABEL = ["<5%", "5\u201310%", "10\u201320%", "\u226520%"]
LABEL_FROM = 2


def half_up(x):
    """x rounded half up to an integer, as a string (the paper's rounding rule)."""
    return str(decimal.Decimal(repr(float(x))).quantize(decimal.Decimal(1), rounding=decimal.ROUND_HALF_UP))


def load_analyze():
    spec = importlib.util.spec_from_file_location("pconf_analyze", os.path.join(PROJ, "analyze.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    A = load_analyze()
    fs.setup()
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch, Rectangle
    with open(os.path.join(PROJ, "results", "summary.json")) as f:
        s = json.load(f)
    fams = list(A.FAMILIES)
    ys = [i + (GAP if camp == "conf_1x" else 0.0) for i, (camp, _, _) in enumerate(ROWS)]
    fig, ax = fs.figure(height_in=1.92)
    printed = {}
    for y, (camp, lab, _) in zip(ys, ROWS):
        fd = s["campaigns"][camp]["families"][lab]
        for x, fam in enumerate(fams):
            d = fd.get(fam) or {"cells": 0, "counts": {}}
            n, k = d["cells"], d["counts"].get("DIFF", 0)
            if n < A.MIN_FAMILY_CELLS:
                ax.text(x, y, "\u2013", ha="center", va="center", color=fs.MUTED)
                printed["%s|%s" % (lab, fam)] = {"cells": n, "DIFF": k, "pct": None}
                continue
            pct = 100.0 * k / n
            cls = bisect.bisect_right(EDGES, pct) - 1
            ax.add_patch(Rectangle((x - 0.5, y - 0.5), 1.0, 1.0, facecolor=FILLS[cls], edgecolor=fs.SURFACE,
                                   linewidth=0.8))
            if cls >= LABEL_FROM:
                ax.text(x, y, half_up(pct), ha="center", va="center", color=fs.SURFACE,
                        fontsize=plt.rcParams["xtick.labelsize"])
            printed["%s|%s" % (lab, fam)] = {"cells": n, "DIFF": k, "pct": round(pct, 1)}
    ax.set_xlim(-0.5, len(fams) - 0.5)
    ax.set_ylim(ys[-1] + 0.5, -0.5)
    ax.set_yticks(ys, [r[2] for r in ROWS])
    ax.set_xticks(range(len(fams)), [FAMILY_NAME.get(f, f) for f in fams], rotation=40, ha="right",
                  rotation_mode="anchor")
    ax.tick_params(length=0, labelcolor=fs.INK)
    ax.tick_params(axis="x", pad=2)
    for sp in ax.spines.values():
        sp.set_visible(False)
    handles = [Patch(facecolor=c, edgecolor="none", label=l) for c, l in zip(FILLS, CLASS_LABEL)]
    handles.append(Patch(facecolor=fs.SURFACE, edgecolor="none",
                         label="\u2013 fewer than %d cells" % A.MIN_FAMILY_CELLS))
    fig.legend(handles=handles, loc="outside upper center", ncol=5, handlelength=1.0, handleheight=0.8,
               columnspacing=0.9, handletextpad=0.35)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fs.save(fig, OUT)
    print("wrote", OUT)
    print(json.dumps(printed))


if __name__ == "__main__":
    main()

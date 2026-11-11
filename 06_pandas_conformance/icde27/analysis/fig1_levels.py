#!/usr/bin/env python3
"""Figure 1 of the ICDE copy: level reached per configuration, and the paired DIFF comparison (redesigned 2026-11-10).

Reads results/summary.json (campaigns.{drift,conf_1x}.engines.<label>.views.all.{cells,counts,cum_share}) and
icde27/analysis/r1_cells.json (pairwise_vs_pandas_clean_E2.<engine>-{p15,p30}.{diff_pp,ci90_pp,ci95_pp}) and writes
icde27/figures/fig1_levels.pdf in the figure style of figstyle.py, beside this script:
  top     one stacked bar per configuration (the two pandas versions, then the five engine configurations) of the
          level or class that each scored cell reaches: E0-E4 on the style's ordinal ramp, then DIFF, UNCOMPARABLE,
          ERR, "stopped" (TIMEOUT, CRASH, KILLED or MEMORY: the engine stopped in that cell) and "not run" (NOTRUN:
          later cells of a notebook whose engine stopped); a tick and the number at the right mark the share equal
          at E2 or finer;
  bottom  per engine, the paired difference of DIFF shares (engine minus pandas 1.5.3 or 3.0.6, percentage points)
          on the cells clean@E2 under both, with the 90% (thick) and 95% (thin) bootstrap intervals over notebooks
          and the +-2-point equivalence margin (dashed).
Every plotted value is read from these two files; prints the plotted numbers as JSON.

    cd <project folder>        (the artifact's repository root)
    ../.venv/bin/python icde27/analysis/fig1_levels.py
"""
import json
import os

import figstyle as fs

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(os.path.dirname(HERE), "figures", "fig1_levels.pdf")
ROWS = [("drift", "p15", "pandas 1.5.3"), ("drift", "p30", "pandas 3.0.6"),
        ("conf_1x", "pyarrow_backend", "pyarrow backend"), ("conf_1x", "modin", "Modin"),
        ("conf_1x", "fireducks", "FireDucks"), ("conf_1x", "bodo", "Bodo (one worker)"), ("conf_1x", "dask", "Dask")]
GAP = 0.35                                    # extra space between the pandas baselines and the engines (row units)
# (legend label, classes merged into the segment, fill); E0-E4 take the ordinal ramp (dark = finest level)
SEGMENTS = [("E0", ("E0",), fs.ORD[0]), ("E1", ("E1",), fs.ORD[1]), ("E2", ("E2",), fs.ORD[2]),
            ("E3", ("E3",), fs.ORD[3]), ("E4", ("E4",), fs.ORD[4]),
            ("DIFF", ("DIFF",), fs.CAT[7]), ("UNCOMP.", ("UNCOMPARABLE",), fs.MUTED), ("ERR", ("ERR",), fs.CAT[3]),
            ("stopped", ("TIMEOUT", "CRASH", "KILLED", "MEMORY"), fs.INK2), ("not run", ("NOTRUN",), fs.GRAY)]
BAR_H = 0.66
BOTTOM_XLIM = (-2.6, 6.6)                     # percentage points; checked to hold every interval
LE2 = "\u2264E2"                              # "<=E2" with the less-than-or-equal sign


def load(*p):
    with open(os.path.join(PROJ, *p)) as f:
        return json.load(f)


def main():
    fs.setup()
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    s = load("results", "summary.json")
    pw = load("icde27", "analysis", "r1_cells.json")["pairwise_vs_pandas_clean_E2"]
    printed = {"top": {}, "bottom": {}}
    eng_rows = [r for r in ROWS if r[0] == "conf_1x"]
    fig, (ax, bx) = fs.figure(height_in=2.78, nrows=2, gridspec_kw={"height_ratios": [7 + GAP + 1.25, 5 + 1.0]})

    # ---- top: level reached over all scored cells
    ys = [i + (GAP if camp == "conf_1x" else 0.0) for i, (camp, _, _) in enumerate(ROWS)]
    total_classes = {k for _, ks, _ in SEGMENTS for k in ks}
    for y, (camp, lab, _) in zip(ys, ROWS):
        vv = s["campaigns"][camp]["engines"][lab]["views"]["all"]
        n, c = vv["cells"], vv["counts"]
        if set(c) - total_classes or sum(c.values()) != n:
            raise SystemExit("counts of %s do not add up to its scored cells" % lab)
        left = 0.0
        for _, ks, col in SEGMENTS:
            w = 100.0 * sum(c.get(k, 0) for k in ks) / n
            if w > 0:
                ax.barh(y, w, left=left, height=BAR_H, color=col, edgecolor=fs.SURFACE, linewidth=0.45)
            left += w
        le2 = 100.0 * vv["cum_share"]["<=E2"]
        ax.plot([le2, le2], [y - 0.47, y + 0.47], color=fs.INK, linewidth=0.9, solid_capstyle="butt", zorder=4)
        printed["top"][lab] = {"cells": n, "le_E2_pct": round(le2, 1), "E0_pct": round(100.0 * c["E0"] / n, 1)}
    ax.set_xlim(0, 100)
    ax.set_ylim(ys[-1] + 0.55, -0.62)
    ax.set_yticks(ys, [r[2] for r in ROWS])
    ax.tick_params(axis="y", length=0, labelcolor=fs.INK)
    ax.set_xticks(range(0, 101, 20))
    ax.spines["left"].set_visible(False)
    fs.grid(ax, axis="x")
    ax.set_xlabel("share of scored cells (%)", labelpad=1.5)
    ax.set_title("All scored cells: level reached", loc="left", pad=3)
    right = ax.secondary_yaxis("right")
    right.set_yticks(ys, ["%.1f" % printed["top"][lab]["le_E2_pct"] for _, lab, _ in ROWS])
    right.tick_params(length=0, pad=2, labelcolor=fs.INK)
    right.spines["right"].set_visible(False)
    ax.text(1.0, 1.0, " " + LE2, transform=ax.transAxes, ha="left", va="bottom", color=fs.INK2,
            fontsize=plt.rcParams["xtick.labelsize"])
    patches = [Patch(facecolor=col, edgecolor="none", label=lab) for lab, _, col in SEGMENTS]
    tick = Line2D([], [], color=fs.INK, linewidth=0.9, label=LE2 + " share")
    # legend rows: the five levels and the tick, then the other classes (matplotlib fills legend columns first)
    order = [h for pair in zip(patches[:5], patches[5:]) for h in pair] + [tick]
    fig.legend(handles=order, loc="outside upper center", ncol=6, handlelength=1.0, handleheight=0.8,
               columnspacing=0.8, handletextpad=0.35)

    # ---- bottom: paired DIFF difference against each pandas version on cells clean@E2 under both
    by = list(range(len(eng_rows)))
    for y, (_, lab, _) in zip(by, eng_rows):
        for base, dy, face in (("p15", -0.17, fs.SURFACE), ("p30", 0.17, fs.INK)):
            r = pw["%s-%s" % (lab, base)]
            bx.plot(r["ci95_pp"], [y + dy] * 2, color=fs.INK2, linewidth=0.6, solid_capstyle="butt", zorder=2)
            bx.plot(r["ci90_pp"], [y + dy] * 2, color=fs.INK2, linewidth=1.8, solid_capstyle="butt", zorder=3)
            bx.plot([r["diff_pp"]], [y + dy], marker="o", markersize=3.6, markerfacecolor=face, markeredgecolor=fs.INK,
                    markeredgewidth=0.7, linestyle="none", zorder=4)
            printed["bottom"]["%s-%s" % (lab, base)] = {"diff_pp": r["diff_pp"], "ci90_pp": r["ci90_pp"],
                                                        "ci95_pp": r["ci95_pp"]}
    lo, hi = BOTTOM_XLIM
    if not all(lo < v < hi for r in printed["bottom"].values() for v in r["ci95_pp"]):
        raise SystemExit("an interval falls outside the bottom panel's x range %s" % (BOTTOM_XLIM,))
    for x in (-2, 2):
        bx.axvline(x, **fs.REFLINE, zorder=1)
    bx.axvline(0, color=fs.AXIS, linewidth=0.6, zorder=1)
    bx.set_ylim(by[-1] + 0.55, -0.55)
    bx.set_yticks(by, [r[2] for r in eng_rows])
    bx.tick_params(axis="y", length=0, labelcolor=fs.INK)
    bx.spines["left"].set_visible(False)
    bx.set_xlim(*BOTTOM_XLIM)
    bx.set_xticks(range(-2, 7, 2))
    bx.xaxis.set_major_formatter(lambda v, _: "%+d" % v if v else "0")
    fs.grid(bx, axis="x")
    bx.set_xlabel("engine minus pandas (percentage points)", labelpad=1.5)
    bx.set_title("Cells clean at E2 under both: paired DIFF difference", loc="left", pad=3)
    h2 = [Line2D([], [], marker="o", markersize=3.6, markerfacecolor=fs.SURFACE, markeredgecolor=fs.INK,
                 markeredgewidth=0.7, linestyle="none", label="vs 1.5.3"),
          Line2D([], [], marker="o", markersize=3.6, markerfacecolor=fs.INK, markeredgecolor=fs.INK,
                 markeredgewidth=0.7, linestyle="none", label="vs 3.0.6"),
          Line2D([], [], color=fs.INK2, linewidth=1.8, label="90%"),
          Line2D([], [], color=fs.INK2, linewidth=0.6, label="95%")]
    bx.legend(handles=h2, loc="upper right", ncol=2, handlelength=1.2, columnspacing=0.9, borderaxespad=0.15,
              borderpad=0.2, labelspacing=0.25)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fs.save(fig, OUT)
    print("wrote", OUT)
    print(json.dumps(printed))


if __name__ == "__main__":
    main()

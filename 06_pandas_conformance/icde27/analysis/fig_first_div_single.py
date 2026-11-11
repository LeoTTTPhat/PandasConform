#!/usr/bin/env python3
"""Figure 3 of the ICDE copy: where in each notebook the first cell not equal at E4 lies (redesigned 2026-11-10).

Reads results/summary.json (campaigns.{drift,conf_1x}.engines.<label>.first_divergence_per_notebook.<nb>.E4.{rel,cls}
and first_divergence.E4.{notebooks_diverged,rel_position_quantiles.p50}) and writes
icde27/figures/fig3_first_divergence_single.pdf in the figure style of figstyle.py, beside this
script: one row per configuration (the two pandas versions, then the five engine configurations, as in Figure
1); one dot per notebook with a cell not equal at E4, at the relative position of the first such cell, coloured by
that cell's class as in Figure 1 (DIFF and ERR as circles; UNCOMPARABLE and "stopped", that is TIMEOUT, CRASH, KILLED
or MEMORY, as squares); a tick at the median position over these notebooks; at the right, the number of such
notebooks of the 102. Dots are spread over lanes by rank (deterministic). The script checks that the medians and
counts it plots equal summary.json's first_divergence.E4 entries. Prints the plotted numbers as JSON.

The previous version showed cumulative curves of the first cell not equal at E2 and at E4.

    cd <project folder>        (the artifact's repository root)
    ../.venv/bin/python icde27/analysis/fig_first_div_single.py
"""
import json
import os
import statistics

import figstyle as fs

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(os.path.dirname(HERE), "figures", "fig3_first_divergence_single.pdf")
ROWS = [("drift", "p15", "pandas 1.5.3"), ("drift", "p30", "pandas 3.0.6"),
        ("conf_1x", "pyarrow_backend", "pyarrow backend"), ("conf_1x", "modin", "Modin"),
        ("conf_1x", "fireducks", "FireDucks"), ("conf_1x", "bodo", "Bodo (one worker)"), ("conf_1x", "dask", "Dask")]
GAP = 0.35                                    # extra space between the pandas baselines and the engines (row units)
LEVEL = "E4"
# class of the first cell not equal at E4 -> (legend label, colour as in Figure 1, marker, drawing order: DIFF on top);
# the rare classes are squares, so that they stay apart from DIFF in greyscale
CLASSES = {"ERR": ("ERR", fs.CAT[3], "o", 1), "UNCOMPARABLE": ("UNCOMP.", fs.MUTED, "s", 2),
           "TIMEOUT": ("stopped", fs.INK2, "s", 3), "CRASH": ("stopped", fs.INK2, "s", 3),
           "KILLED": ("stopped", fs.INK2, "s", 3), "MEMORY": ("stopped", fs.INK2, "s", 3),
           "DIFF": ("DIFF", fs.CAT[7], "o", 4)}
LEGEND = ("DIFF", "UNCOMPARABLE", "ERR", "TIMEOUT")
LANES = 7                                     # vertical lanes for the dots of one row
LANE_STRIDE = 3                               # the k-th dot (by position) goes to lane 3k mod 7: no diagonal stripes
LANE_STEP = 0.095                             # row units between lanes


def main():
    fs.setup()
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    with open(os.path.join(PROJ, "results", "summary.json")) as f:
        s = json.load(f)
    ys = [i + (GAP if camp == "conf_1x" else 0.0) for i, (camp, _, _) in enumerate(ROWS)]
    fig, ax = fs.figure(height_in=1.72)
    printed = {}
    for y, (camp, lab, _) in zip(ys, ROWS):
        e = s["campaigns"][camp]["engines"][lab]
        per = e["first_divergence_per_notebook"]
        pts = sorted((h[LEVEL]["rel"], h[LEVEL]["cls"], nb) for nb, h in per.items() if h[LEVEL] is not None)
        unknown = {c for _, c, _ in pts} - set(CLASSES)
        if unknown:
            raise SystemExit("unexpected first-divergence classes for %s: %s" % (lab, sorted(unknown)))
        med = statistics.median(r for r, _, _ in pts)
        ref = e["first_divergence"][LEVEL]
        if len(pts) != ref["notebooks_diverged"] or abs(med - ref["rel_position_quantiles"]["p50"]) > 5e-7:
            raise SystemExit("%s: %d notebooks, median %.6f; summary.json says %s, %s" % (
                lab, len(pts), med, ref["notebooks_diverged"], ref["rel_position_quantiles"]["p50"]))
        lanes = [y + (LANE_STRIDE * k % LANES - (LANES - 1) / 2.0) * LANE_STEP for k in range(len(pts))]
        for cls in sorted({c for _, c, _ in pts}, key=lambda c: (CLASSES[c][3], c)):     # fixed order (no set order)
            xs = [r for (r, c, _) in pts if c == cls]
            yy = [ly for (r, c, _), ly in zip(pts, lanes) if c == cls]
            ax.scatter(xs, yy, s=7 if CLASSES[cls][2] == "o" else 5.5, marker=CLASSES[cls][2], color=CLASSES[cls][1],
                       edgecolors=fs.SURFACE, linewidths=0.3, clip_on=False, zorder=2 + CLASSES[cls][3])
        ax.plot([med, med], [y - 0.42, y + 0.42], color=fs.INK, linewidth=1.0, solid_capstyle="butt", zorder=8)
        by_cls = {}
        for _, c, _ in pts:
            by_cls[CLASSES[c][0]] = by_cls.get(CLASSES[c][0], 0) + 1
        printed[lab] = {"notebooks": len(pts), "median_rel": round(med, 6), "first_class": by_cls}
    ax.set_xlim(0, 1)
    ax.set_ylim(ys[-1] + 0.55, -0.55)
    ax.set_yticks(ys, [r[2] for r in ROWS])
    ax.tick_params(axis="y", length=0, labelcolor=fs.INK)
    ax.spines["left"].set_visible(False)
    ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0], ["0", "0.2", "0.4", "0.6", "0.8", "1"])
    fs.grid(ax, axis="x")
    # "earliest", not "first": with Helvetica, matplotlib 3.11 sets "fi" and "fl" as ligature glyphs from a second
    # embedded font whose bytes change with the hash seed, which would make the PDF differ from run to run
    ax.set_xlabel("relative position in the notebook of the earliest cell not equal at E4", labelpad=1.5)
    right = ax.secondary_yaxis("right")
    right.set_yticks(ys, ["%d" % printed[lab]["notebooks"] for _, lab, _ in ROWS])
    right.tick_params(length=0, pad=3, labelcolor=fs.INK)
    right.spines["right"].set_visible(False)
    ax.text(1.0, 1.0, " NB", transform=ax.transAxes, ha="left", va="bottom", color=fs.INK2,
            fontsize=plt.rcParams["xtick.labelsize"])
    handles = []
    for key in LEGEND:                        # legend in Figure 1's class order
        lab_, col, mk, _ = CLASSES[key]
        handles.append(Line2D([], [], marker=mk, markersize=3.6 if mk == "o" else 3.2, markerfacecolor=col,
                              markeredgecolor=fs.SURFACE, markeredgewidth=0.3, linestyle="none", label=lab_))
    handles.append(Line2D([], [], color=fs.INK, linewidth=1.0, label="median"))
    fig.legend(handles=handles, loc="outside upper center", ncol=5, handlelength=1.0, columnspacing=1.0,
               handletextpad=0.3)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fs.save(fig, OUT)
    print("wrote", OUT)
    print(json.dumps(printed))


if __name__ == "__main__":
    main()

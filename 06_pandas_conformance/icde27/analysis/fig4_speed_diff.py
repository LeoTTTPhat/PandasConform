#!/usr/bin/env python3
"""Figure 4 of the ICDE copy: per-notebook speed-up over pandas and introduced DIFF cells (written 2026-11-10).

Plotting only; it changes no number. Reads
  icde27/analysis/rq4_timing.json   figure.rows (per engine and CPU budget: geometric mean, its 95% interval, both-ok
                                    count, timeouts with their speed-up upper bounds) and per_notebook."<cpus>|<engine>"
                                    .notebooks (the speed-up of every both-ok notebook), as written by rq4_timing.py;
  results/rootcause/taxonomy_conf1x.json   causes.*.cells of the introduced causes: the conf_1x cells that introduce a
                                    divergence, to count per engine and notebook the introduced DIFF cells;
  icde27/analysis/r1_cells.json     by_label.<engine>.{notebooks.introduced_DIFF.num,
                                    introduced_DIFF_by_mechanism_with_hand} (consistency checks of these counts only);
and writes icde27/figures/fig4_speed_vs_diff.pdf in the figure style of figstyle.py, beside this
script: one row per engine and CPU budget (the rows of rq4_timing.json figure.rows); one dot per notebook in
which both pandas and the engine ran every cell, at its speed-up (log scale), red if the engine introduces at least
one DIFF cell in that notebook in the conformance run (conf_1x settings), grey otherwise; left triangles for timeouts
at their speed-up upper bound (filled red with an introduced DIFF, hollow grey without); a diamond and a bar for the
geometric mean and its 95% interval; a dashed line at speed-up 1; at the right, the both-ok notebooks of the 30
(generated_from.notebooks_expected).
rq4_timing.py still writes the earlier version of this figure (fig4_speed_vs_conformance.pdf) and rq4_timing.json,
which this script only reads. Prints the plotted values as JSON.

    cd <project folder>        (the artifact's repository root)
    ../.venv/bin/python icde27/analysis/fig4_speed_diff.py
"""
import collections
import json
import math
import os

import figstyle as fs

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(os.path.dirname(HERE), "figures", "fig4_speed_vs_diff.pdf")
LABEL = {"modin": "Modin", "fireducks": "FireDucks", "bodo": "Bodo"}
BUDGET = {"8": "8 CPUs", "default": "default"}
GAP = 0.35                                    # extra space between engines (row units)
LANES = 5                                     # vertical lanes for the dots of one row
LANE_STEP = 0.11                              # row units between lanes
TO_STEP = 0.17                                # row units between the timeouts of one row
XLIM = (0.001, 12)                            # speed-up axis; checked to hold every plotted value
NO_DIFF, HAS_DIFF = fs.GRAY, fs.CAT[7]        # grey: no introduced DIFF cell; red: DIFF as in Figures 1-3


def load(*p):
    with open(os.path.join(PROJ, *p)) as f:
        return json.load(f)


def introduced_diff_by_notebook(tax, r1, engines):
    """{engine: Counter(notebook -> introduced DIFF cells in conf_1x)}, checked against r1_cells.json."""
    intro = {k.split(":", 1)[1] for d in tax["per_engine"].values() for k in d if k.startswith("introduced:")}
    out = {e: collections.Counter() for e in engines}
    for cause in intro:
        for camp, eng, nb, _cell, cls in tax["causes"][cause]["cells"]:
            if camp == "conf_1x" and eng in out and cls == "DIFF":
                out[eng][nb] += 1
    for e in engines:
        b = r1["by_label"][e]
        if (sum(out[e].values()), len(out[e])) != (sum(b["introduced_DIFF_by_mechanism_with_hand"].values()),
                                                   b["notebooks"]["introduced_DIFF"]["num"]):
            raise SystemExit("introduced DIFF counts of %s disagree with r1_cells.json" % e)
    return out


def main():
    fs.setup()
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FixedLocator, NullFormatter
    rq = load("icde27", "analysis", "rq4_timing.json")
    rows = rq["figure"]["rows"]
    diff = introduced_diff_by_notebook(load("results", "rootcause", "taxonomy_conf1x.json"),
                                       load("icde27", "analysis", "r1_cells.json"), sorted({r["engine"] for r in rows}))
    ys, y, prev = [], 0.0, None
    for r in rows:
        if prev is not None:
            y += 1.0 + (GAP if r["engine"] != prev else 0.0)
        ys.append(y)
        prev = r["engine"]
    fig, ax = fs.figure(height_in=1.62)
    printed = []
    for y, r in zip(ys, rows):
        key = "%s|%s" % (r["cpus"], r["engine"])
        nbs = sorted(rq["per_notebook"][key]["notebooks"], key=lambda x: x["speedup"])
        gm = math.exp(sum(math.log(x["speedup"]) for x in nbs) / len(nbs))
        if len(nbs) != r["n_both_ok"] or abs(gm - r["geomean"]) > 2e-6:
            raise SystemExit("%s: per-notebook speed-ups disagree with figure.rows" % key)
        d = diff[r["engine"]]
        for k, x in enumerate(nbs):
            has = d[x["nb"]] > 0
            ax.scatter([x["speedup"]], [y + (k % LANES - (LANES - 1) / 2.0) * LANE_STEP], s=11,
                       color=HAS_DIFF if has else NO_DIFF, edgecolors=fs.SURFACE, linewidths=0.35,
                       zorder=4 if has else 3)
        tos = sorted(r["timeouts"], key=lambda t: t["speedup_upper_bound"])
        for k, t in enumerate(tos):
            has = d[t["nb"]] > 0
            ax.scatter([t["speedup_upper_bound"]], [y + (k - (len(tos) - 1) / 2.0) * TO_STEP], s=14, marker="<",
                       facecolors=HAS_DIFF if has else fs.SURFACE, edgecolors=HAS_DIFF if has else fs.MUTED,
                       linewidths=0.8, zorder=4)
        lo, hi = r["ci95"]
        ax.plot([lo, hi], [y, y], color=fs.INK, linewidth=1.2, solid_capstyle="butt", zorder=5)
        ax.plot([r["geomean"]], [y], marker="D", markersize=4.0, markerfacecolor=fs.INK, markeredgecolor=fs.SURFACE,
                markeredgewidth=0.6, linestyle="none", zorder=6)
        printed.append({"row": key, "n_both_ok": r["n_both_ok"], "geomean": r["geomean"], "ci95": r["ci95"],
                        "both_ok_with_introduced_DIFF": sum(1 for x in nbs if d[x["nb"]] > 0),
                        "faster_than_pandas": sum(1 for x in nbs if x["speedup"] > 1),
                        "faster_with_introduced_DIFF": sum(1 for x in nbs if x["speedup"] > 1 and d[x["nb"]] > 0),
                        "timeouts": len(tos), "timeouts_with_introduced_DIFF": sum(1 for t in tos if d[t["nb"]] > 0)})
    xs = [v for r in rows for v in r["ci95"] + [t["speedup_upper_bound"] for t in r["timeouts"]]] + \
        [x["speedup"] for r in rows for x in rq["per_notebook"]["%s|%s" % (r["cpus"], r["engine"])]["notebooks"]]
    if not all(XLIM[0] < v < XLIM[1] for v in xs):
        raise SystemExit("a plotted speed-up falls outside the x range %s" % (XLIM,))
    ax.axvline(1.0, **fs.REFLINE, zorder=1)
    ax.set_xscale("log")
    ax.set_xlim(*XLIM)
    ax.xaxis.set_major_locator(FixedLocator([0.001, 0.01, 0.1, 1, 10]))
    ax.xaxis.set_major_formatter(lambda v, _: "%g" % v)
    ax.xaxis.set_minor_formatter(NullFormatter())
    fs.grid(ax, axis="x")
    ax.set_ylim(ys[-1] + 0.6, -0.6)
    ax.set_yticks(ys, ["%s, %s" % (LABEL[r["engine"]], BUDGET[r["cpus"]]) for r in rows])
    ax.tick_params(axis="y", length=0, labelcolor=fs.INK)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("speed-up over pandas 2.3.3 per notebook (log scale)", labelpad=1.5)
    right = ax.secondary_yaxis("right")
    right.set_yticks(ys, ["%d/%d" % (r["n_both_ok"], rq["generated_from"]["notebooks_expected"]) for r in rows])
    right.tick_params(length=0, pad=2, labelcolor=fs.INK)
    right.spines["right"].set_visible(False)
    ax.text(1.0, 1.0, " ok", transform=ax.transAxes, ha="left", va="bottom", color=fs.INK2,
            fontsize=plt.rcParams["xtick.labelsize"])
    h = [Line2D([], [], marker="o", markersize=3.8, markerfacecolor=NO_DIFF, markeredgecolor=fs.SURFACE,
                markeredgewidth=0.35, linestyle="none", label="no introduced DIFF"),
         Line2D([], [], marker="o", markersize=3.8, markerfacecolor=HAS_DIFF, markeredgecolor=fs.SURFACE,
                markeredgewidth=0.35, linestyle="none", label="introduced DIFF in conf_1x"),
         Line2D([], [], marker="<", markersize=4.0, markerfacecolor=fs.SURFACE, markeredgecolor=fs.MUTED,
                markeredgewidth=0.8, linestyle="none", label="timeout: at most"),
         Line2D([], [], color=fs.INK, linewidth=1.2, marker="D", markersize=3.6, markerfacecolor=fs.INK,
                markeredgecolor=fs.INK, markeredgewidth=0.6, label="geometric mean, 95% interval")]
    fig.legend(handles=[h[0], h[2], h[1], h[3]], loc="outside upper center", ncol=2, handlelength=1.8,
               columnspacing=1.2, handletextpad=0.4, numpoints=1)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fs.save(fig, OUT)
    print("wrote", OUT)
    print(json.dumps(printed))


if __name__ == "__main__":
    main()

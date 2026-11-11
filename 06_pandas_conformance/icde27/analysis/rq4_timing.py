#!/usr/bin/env python3
"""RQ4 (speed versus conformance) numbers and figure for the ICDE 2027 copy (written 2026-10-26).

Read-only on results/ and runs/; writes only results/summary.json and results/analysis.md (through
analyze.py, with --run-analyze), icde27/analysis/rq4_timing.json and icde27/figures/fig4_speed_vs_conformance.pdf.

    cd ..
    /usr/bin/time -l .venv/bin/python 06_pandas_conformance/icde27/analysis/rq4_timing.py --run-analyze

--run-analyze runs analyze.analyze() unchanged except for two things:
  * figures are written to icde27/figures instead of paper/figures (the SIGMOD copy in paper/ is frozen);
  * the batch markers are the union of work/batch/experiment_main (analyze.py's BATCH) and every --extra-batch
    (default: icde27_remaining). The 2026-10-26 queue `pandas_icde27` writes its step markers to
    work/batch/icde27_remaining, which plain analyze.py never reads, so without the union the timing, conf_5x and
    bodo_dw groups would stay "partial" in summary.json even after their steps finish.
Then this script reads results/summary.json (key `timing`) and the raw timing records of the campaigns `timing`
and `timing_bodo_r2` and writes
  * icde27/analysis/rq4_timing.json: per (cpus, engine) record completeness; within-period repetition spread
    (plan.md F2.5(iv)); the Bodo cpus-8 rerun `timing_bodo_r2` against its same-period reference, with its host
    load and the drift of that reference against the first cpus-8 reference period; the points of the figure and
    the groups left out of it, with the reason;
  * Bodo at engine defaults against a same-period pandas reference (per notebook the closer of the 5-6 October
    cpus=default reference and the timing_bodo_r2 reference), key `bodo_default_same_period` (added 2026-10-27);
  * icde27/figures/fig4_speed_vs_conformance.pdf from COMPLETE groups only (all records of the group present).
    A group whose runs are still pending (for example Bodo at engine defaults while `timing_default` runs) is
    listed under `figure.left_out` and never plotted from partial data. Bodo at cpus 8 is plotted only from
    `timing_bodo_r2` (complete), because all 90 cpus-8 records of campaign `timing` are host-configuration crashes.
Numbers printed in the paper come from summary.json `timing` where they exist there, and from rq4_timing.json
otherwise (repetition spread, timing_bodo_r2, Bodo at engine defaults against its same-period reference).
"""
import argparse
import collections
import datetime
import glob
import importlib.util
import json
import math
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ICDE = os.path.dirname(HERE)
PROJ = os.path.dirname(ICDE)
FIGDIR = os.path.join(ICDE, "figures")
OUT = os.path.join(HERE, "rq4_timing.json")
FIG = os.path.join(FIGDIR, "fig4_speed_vs_conformance.pdf")
R2 = "timing_bodo_r2"
R2_MARKER = ("icde27_remaining", "timing_bodo_r2_cpu8")
REPS = {"8": 3, "default": 1}
ENGINES = ("modin", "fireducks", "bodo")


def load_analyze():
    spec = importlib.util.spec_from_file_location("pconf_analyze", os.path.join(PROJ, "analyze.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def batch_markers(batch):
    return sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(PROJ, "work", "batch", batch, "*.done")))


def run_analyze(A, extra_batches):
    orig_init, orig_markers = A.Paths.__init__, A.markers

    def init(self, root):
        orig_init(self, root)
        self.figures = FIGDIR

    def markers(paths):
        out = set(orig_markers(paths))
        for b in extra_batches:
            out.update(batch_markers(b))
        return sorted(out)

    A.Paths.__init__, A.markers = init, markers
    try:
        s = A.analyze(PROJ, figures=True)
    finally:
        A.Paths.__init__, A.markers = orig_init, orig_markers
    for c, d in s["campaigns"].items():
        print("%-8s %-8s labels=%s crosscheck=%d/%d" % (c, d["status"], ",".join(d["engines"]) or "-",
                                                         d["crosscheck"]["n_mismatch"], d["crosscheck"]["n_checks"]))
    print("ledger crosscheck: %d mismatches of %d" % (s["ledger_crosscheck"]["n_mismatch"],
                                                      s["ledger_crosscheck"]["n_checks"]))
    for n, f in s["figures"].items():
        print("%-40s %s" % (n, f["status"]))
    return s


def rep_spread(recs):
    """Spread of the repetitions per (cpus, engine, notebook) over all-ok runs (same rule as the 2026-10-05 F2 dry
    run, work/f2_dryrun_2026-10-05/run_f2_dryrun.py): max/min and CV of the summed ok-cell time; notebooks with a
    median below 1 s are counted but not summarized, since timer noise dominates them."""
    grp = collections.defaultdict(list)
    for r in recs:
        grp[(r["cpus"], r["engine"], r["nb"])].append((r["all_ok"], r["ok_cells_wall_s"]))
    out = {}
    for (cpus, e, nb), xs in sorted(grp.items()):
        if len(xs) < 2 or not all(x[0] for x in xs):
            continue
        ts = [x[1] for x in xs]
        row = out.setdefault("%s|%s" % (cpus, e), {"n": 0, "n_ge_1s": 0, "_r": [], "_cv": [], "_w": []})
        row["n"] += 1
        if statistics.median(ts) >= 1.0:
            row["n_ge_1s"] += 1
            ratio = max(ts) / min(ts) if min(ts) > 0 else float("inf")
            row["_r"].append(ratio)
            row["_cv"].append(statistics.pstdev(ts) / statistics.mean(ts))
            row["_w"].append({"nb": nb, "times_s": [round(t, 3) for t in ts], "max_over_min": round(ratio, 3)})
    for row in out.values():
        r_, c_, w_ = sorted(row.pop("_r")), row.pop("_cv"), row.pop("_w")
        row["max_over_min_median"] = round(statistics.median(r_), 3) if r_ else None
        row["max_over_min_max"] = round(max(r_), 3) if r_ else None
        row["cv_median"] = round(statistics.median(c_), 4) if c_ else None
        row["notebooks_max_over_min_gt_1_5"] = sum(1 for x in r_ if x > 1.5)
        row["notebooks_max_over_min_gt_2"] = sum(1 for x in r_ if x > 2.0)
        row["worst"] = sorted(w_, key=lambda x: -x["max_over_min"])[:3]
    return out


def completeness(recs, nexp, engines, cpus_list):
    out = {}
    for cpus in cpus_list:
        for e in engines:
            xs = [r for r in recs if r["cpus"] == cpus and r["engine"] == e]
            exp = nexp * REPS[cpus]
            out["%s|%s" % (cpus, e)] = {"records": len(xs), "expected": exp, "complete": len(xs) >= exp,
                                       "notebooks": len({r["nb"] for r in xs}),
                                       "by_status": dict(collections.Counter(str(r["status"]) for r in xs))}
    return out


def drift(recs_a, recs_b, cpus_a, cpus_b):
    """Median per-notebook ratio of the reference's median ok-cell time in period b over period a."""
    def med(recs, cpus):
        g = collections.defaultdict(list)
        for r in recs:
            if r["engine"] == "ref" and r["cpus"] == cpus:
                g[r["nb"]].append(r)
        return {nb: statistics.median(x["ok_cells_wall_s"] for x in xs) for nb, xs in g.items()
                if all(x["all_ok"] for x in xs)}
    a, b = med(recs_a, cpus_a), med(recs_b, cpus_b)
    common = sorted(nb for nb in a if nb in b and a[nb] > 0 and b[nb] > 0)
    rat = [b[nb] / a[nb] for nb in common]
    big = [b[nb] / a[nb] for nb in common if a[nb] >= 1.0]
    q = statistics.quantiles(rat, n=4, method="inclusive") if len(rat) >= 2 else None  # = numpy linear
    return {"notebooks": len(common), "notebooks_ref_ge_1s": len(big),
            "ratio_median": round(statistics.median(rat), 6) if rat else None,
            "ratio_p25_p75": [round(q[0], 6), round(q[2], 6)] if q else None,
            "ratio_median_ref_ge_1s": round(statistics.median(big), 6) if big else None,
            "ratio_min_max": [round(min(rat), 6), round(max(rat), 6)] if rat else None}


def medians(recs, cpus, engine):
    """Per notebook: median ok-cell time over the repetitions and whether every repetition ran every cell ok (the
    rule of analyze.timing_analysis for raw records)."""
    g = collections.defaultdict(list)
    for r in recs:
        if r["cpus"] == cpus and r["engine"] == engine:
            g[r["nb"]].append(r)
    return {nb: (statistics.median(x["ok_cells_wall_s"] for x in xs), all(x["all_ok"] for x in xs))
            for nb, xs in g.items()}


def per_notebook(recs, cpus, engine, ref_recs, ref_cpus):
    """Speed-up per both-ok notebook (reference median over engine median), as in analyze.timing_analysis."""
    d, ref = medians(recs, cpus, engine), medians(ref_recs, ref_cpus, "ref")
    rows = sorted(({"nb": nb, "ref_s": round(ref[nb][0], 6), "engine_s": round(m, 6),
                    "speedup": round(ref[nb][0] / m, 6)}
                   for nb, (m, ok) in d.items()
                   if ok and nb in ref and ref[nb][1] and m > 0 and ref[nb][0] > 0), key=lambda x: x["speedup"])
    sp = [x["speedup"] for x in rows]
    return {"notebooks": rows, "n": len(rows), "n_faster_than_ref": sum(1 for x in sp if x > 1.0),
            "speedup_min": min(sp) if sp else None, "speedup_max": max(sp) if sp else None,
            "speedup_median": round(statistics.median(sp), 6) if sp else None,
            "geomean": round(math.exp(statistics.fmean(math.log(x["ref_s"] / x["engine_s"]) for x in rows)), 6)
            if rows else None}


def host_load_overall(A):
    """Distribution of the 1-minute load samples in runs/host_load.jsonl per sampling window (windows are split
    at gaps above one hour, so a finished window's numbers do not change when the sampler runs again)."""
    smp = A.load_host_samples(A.HOST_LOAD_FILE)
    if not smp:
        return {"samples": 0, "windows": []}
    utc = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    wins, cur = [], [smp[0]]
    for a, b in zip(smp, smp[1:]):
        if b[0] - a[0] > 3600.0:
            wins.append(cur)
            cur = []
        cur.append(b)
    wins.append(cur)

    def desc(w):
        l1 = sorted(x[1] for x in w)
        q = statistics.quantiles(l1, n=4, method="inclusive") if len(l1) >= 2 else [l1[0], l1[0], l1[0]]
        return {"first_utc": utc(w[0][0]), "last_utc": utc(w[-1][0]), "samples": len(w), "cores": w[-1][3],
                "load1_median": round(statistics.median(l1), 2), "load1_p25": round(q[0], 2),
                "load1_p75": round(q[2], 2), "load1_min": round(l1[0], 2), "load1_max": round(l1[-1], 2)}
    return {"samples": len(smp), "windows": [desc(w) for w in wins],
            "gaps_over_1h": [{"from_utc": utc(a[-1][0]), "to_utc": utc(b[0][0]),
                              "hours": round((b[0][0] - a[-1][0]) / 3600.0, 2)} for a, b in zip(wins, wins[1:])]}


def run_cfg(campaign):
    """Distinct run configurations (cell and notebook timeouts, CPU budget) of a timing campaign's raw records."""
    root = os.path.join(PROJ, "results", campaign, "raw", "timing__hd1c421ecb5ee")
    seen = collections.Counter()
    for p in glob.glob(os.path.join(root, "*", "*", "*.json")):
        if os.path.basename(p).startswith(".tmp"):
            continue
        try:
            with open(p) as f:
                cfg = json.load(f).get("cfg") or {}
        except (OSError, ValueError):
            continue
        seen[(str(cfg.get("cpus")), cfg.get("cell_timeout"), cfg.get("nb_timeout"))] += 1
    return [{"cpus": c, "cell_timeout_s": ct, "nb_timeout_s": nt, "records": n} for (c, ct, nt), n in sorted(seen.items())]


def startup(campaign):
    """Engine start-up per (cpus, engine): the record's engine_setup_s (engine import and initialisation, outside
    the timed cells) and the rest of the run outside the timed cells (orchestrator wall time minus the cell time)."""
    root = os.path.join(PROJ, "results", campaign, "raw", "timing__hd1c421ecb5ee")
    grp = collections.defaultdict(lambda: {"setup": [], "outside": []})
    for p in glob.glob(os.path.join(root, "*", "*", "*.json")):
        if os.path.basename(p).startswith(".tmp"):
            continue
        try:
            with open(p) as f:
                r = json.load(f)
        except (OSError, ValueError):
            continue
        if r.get("status") != "completed":
            continue
        k = "%s|%s" % ((r.get("cfg") or {}).get("cpus"), r.get("engine"))
        if r.get("engine_setup_s") is not None:
            grp[k]["setup"].append(float(r["engine_setup_s"]))
        cw = sum((c.get("wall_s") or 0.0) for c in r.get("cells") or [])
        if r.get("orchestrator_wall_s") is not None:
            grp[k]["outside"].append(float(r["orchestrator_wall_s"]) - cw)

    def q(v):
        if not v:
            return None
        qs = statistics.quantiles(v, n=4, method="inclusive") if len(v) >= 2 else [v[0], v[0], v[0]]
        return {"n": len(v), "median": round(statistics.median(v), 3), "p25": round(qs[0], 3), "p75": round(qs[2], 3),
                "max": round(max(v), 3)}
    return {k: {"engine_setup_s": q(g["setup"]), "outside_timed_cells_s": q(g["outside"])} for k, g in sorted(grp.items())}


def bodo_r2(A, nexp, timing_recs):
    paths = A.Paths(PROJ)
    recs, unreadable = A.load_run_records(paths, R2, "timing")
    marker = os.path.exists(os.path.join(PROJ, "work", "batch", R2_MARKER[0], R2_MARKER[1] + ".done"))
    out = {"campaign": R2, "records": len(recs), "unreadable": unreadable, "marker_done": marker,
           "completeness": completeness(recs, nexp, ("ref", "bodo"), ("8",))}
    if not recs:
        out["status"] = "pending"
        return out, recs
    complete = marker and all(v["complete"] for v in out["completeness"].values())
    out["status"] = "complete" if complete else "partial"
    # analyze.timing_analysis reads results/timing/timing_report__<tag>.json when it exists; that report belongs
    # to campaign `timing`, so point `results` at a folder without it and use this campaign's raw records only
    paths.results = os.path.join(HERE, "_no_timing_report")
    samples = A.load_host_samples(A.HOST_LOAD_FILE)
    hl = A.timing_host_load(recs, samples, "runs/host_load.jsonl")
    t = A.timing_analysis(paths, recs, out["status"], None, hl)
    out["by_cpus"] = t["by_cpus"]
    out["failures"] = t["failures"]
    out["host_load"] = {k: v for k, v in hl.items() if k != "rows"}
    out["ref_drift_r2_over_timing_cpu8"] = drift(timing_recs, recs, "8", "8")
    out["rep_spread"] = rep_spread(recs)
    return out, recs


def bodo_default_same_period(A, recs, r2, r2_recs, comp):
    """Bodo at engine defaults (campaign `timing`, cpus=default) against a pandas reference timed in the same
    period (added 2026-10-27). analyze.timing_analysis compares every default-budget engine with the cpus=default
    reference of 5-6 October; Bodo's default runs are resumed by the 2026-10-26 queue (4 of 30 notebooks ran on
    5-6 October), so for each notebook this function takes the reference group whose median start time is closest
    to the Bodo run: the cpus=default reference of campaign `timing` or the cpus=8 reference of `timing_bodo_r2`
    (pandas runs single-threaded, so the CPU setting does not change what it executes). The chosen reference
    records are relabelled cpus=default and analyze.timing_analysis is run on them unchanged (both-ok rule,
    censored timeouts, bootstrap interval, host load)."""
    c = comp["default|bodo"]
    out = {"default_bodo": c, "bodo_r2_status": r2["status"]}
    if not c["complete"] or r2["status"] != "complete":
        out["status"] = "pending"
        return out, [], []

    def start(r):
        if r.get("started"):
            return float(r["started"])
        return float(r.get("mtime") or 0.0) - float(r.get("orchestrator_wall_s") or 0.0)
    bd = [r for r in recs if r["cpus"] == "default" and r["engine"] == "bodo"]
    groups = {"timing|default": [r for r in recs if r["cpus"] == "default" and r["engine"] == "ref"],
              R2 + "|8": [r for r in r2_recs if r["cpus"] == "8" and r["engine"] == "ref"]}
    chosen, rr = collections.Counter(), []
    for nb in sorted({r["nb"] for r in bd}):
        t_b = statistics.median(start(r) for r in bd if r["nb"] == nb)
        best = None
        for g, xs in groups.items():
            ys = [r for r in xs if r["nb"] == nb]
            if ys:
                dt = abs(statistics.median(start(r) for r in ys) - t_b)
                if best is None or dt < best[0]:
                    best = (dt, g, ys)
        if best is None:
            continue
        chosen[best[1]] += 1
        rr.extend(dict(r, cpus="default") for r in best[2])
    paths = A.Paths(PROJ)
    paths.results = os.path.join(HERE, "_no_timing_report")
    samples = A.load_host_samples(A.HOST_LOAD_FILE)
    hl = A.timing_host_load(bd + rr, samples, "runs/host_load.jsonl")
    t = A.timing_analysis(paths, bd + rr, "complete", None, hl)
    out["status"] = "complete"
    out["reference_group_by_notebook"] = dict(chosen)
    out["vs_same_period_ref"] = t["by_cpus"]["default"]["bodo"]
    out["host_load"] = {k: v for k, v in hl.items() if k != "rows"}
    out["ref_drift_r2_over_timing_default"] = drift(recs, r2_recs, "default", "8")
    return out, bd, rr


LABEL = {"modin": "Modin", "fireducks": "FireDucks", "bodo": "Bodo"}


def figure(A, rows):
    """Per-notebook speed-ups per engine and CPU budget (dots), censored timeouts (left triangles at their upper
    bound), and the geometric mean with its 95% interval; right: both-ok notebooks and the engine's conformance
    coordinate. Colours and fonts as analyze.fig_speed."""
    plt = A._mpl()
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter
    n = len(rows)
    fig, ax = plt.subplots(figsize=(3.45, 0.21 * n + 0.78))   # 2026-10-27: 0.3 * n + 0.85 before the Bodo rows
    for i, r in enumerate(rows):
        y = n - 1 - i
        col = A.ENG_COL.get(r["engine"], "black")
        xs = [x["speedup"] for x in r["per_notebook"]["notebooks"]]
        jit = [((k % 5) - 2) * 0.07 for k in range(len(xs))]
        ax.scatter(xs, [y + j for j in jit], s=7, color=col, alpha=0.55, linewidths=0, zorder=2)
        tb = sorted(t["speedup_upper_bound"] for t in r["timeouts"] if t.get("speedup_upper_bound"))
        ax.scatter(tb, [y + (k - (len(tb) - 1) / 2.0) * 0.13 for k in range(len(tb))], s=16, marker="<", facecolors="white",
                   edgecolors=col, linewidths=0.8, zorder=3)
        lo, hi = r["ci95"]
        ax.plot([lo, hi], [y, y], color="black", lw=1.4, solid_capstyle="butt", zorder=4)
        ax.scatter([r["geomean"]], [y], s=26, marker="D", color=col, edgecolors="black", linewidths=0.7, zorder=5)
        ax.text(1.02, y, "%d/30  %.1f%%" % (r["n_both_ok"], r["conformance"]), transform=ax.get_yaxis_transform(),
                va="center", ha="left", fontsize=6.2)
    ax.text(1.02, n - 0.62, "ok      conf.", transform=ax.get_yaxis_transform(), va="bottom", ha="left",
            fontsize=6.2, style="italic")
    ax.axvline(1.0, color="#888888", lw=0.6, ls="--", zorder=1)
    ax.set_xscale("log")
    ax.set_xlim(0.001, 12)   # 2026-10-28: was 0.005, which hid timeout bounds near 0.0016 (audit ICDE27-06-FA1, F8)
    ax.xaxis.set_major_locator(FixedLocator([0.001, 0.01, 0.1, 1, 10]))   # decades: half-decade labels collide below 0.03
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: "%g" % v))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_yticks(range(n))
    ax.set_yticklabels(["%s, %s" % (LABEL[r["engine"]], "8 CPUs" if r["cpus"] == "8" else "default")
                        for r in reversed(rows)])
    ax.set_ylim(-0.6, n - 0.25)
    ax.set_xlabel("Speed-up over pandas 2.3.3 per notebook (log scale; <1 = slower)")
    ax.grid(axis="x", color="#e5e5e5", lw=0.5, zorder=0)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    from matplotlib.lines import Line2D
    h = [Line2D([], [], ls="", marker="o", ms=3, color="#777777", alpha=0.6, label="notebook, both ran every cell"),
         Line2D([], [], ls="", marker="<", ms=4, mfc="white", mec="#777777", label="timeout: speed-up at most"),
         Line2D([], [], ls="-", lw=1.4, color="black", marker="D", ms=4, mfc="#777777", mec="black",
                label="geometric mean, 95% CI")]
    ax.legend(handles=h, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3, fontsize=5.6, frameon=False,
              handletextpad=0.3, columnspacing=0.8)
    fig.tight_layout()
    os.makedirs(FIGDIR, exist_ok=True)
    tmp = FIG + ".tmp%d.pdf" % os.getpid()
    fig.savefig(tmp, format="pdf", bbox_inches="tight", metadata={"CreationDate": None, "ModDate": None})
    os.replace(tmp, FIG)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run-analyze", action="store_true")
    ap.add_argument("--extra-batch", action="append", default=None)
    ap.add_argument("--no-figure", action="store_true")
    a = ap.parse_args(argv)
    A = load_analyze()
    if a.run_analyze:
        run_analyze(A, a.extra_batch if a.extra_batch is not None else ["icde27_remaining"])
    S = json.load(open(os.path.join(PROJ, "results", "summary.json")))
    T = S["timing"]
    paths = A.Paths(PROJ)
    nexp = len(A.notebook_set(paths, "timing30"))
    recs, unreadable = A.load_run_records(paths, "timing", "timing")
    r2, r2_recs = bodo_r2(A, nexp, recs)
    comp_all = completeness(recs, nexp, ("ref",) + ENGINES, ("8", "default"))
    bsp, bsp_bodo, bsp_ref = bodo_default_same_period(A, recs, r2, r2_recs, comp_all)
    out = {"generated_from": {"summary_generated_utc": S["generated_utc"], "summary_batch_markers": S["batch_markers_done"],
                              "timing_status": T["status"], "timing_records": len(recs),
                              "timing_records_unreadable": unreadable, "notebooks_expected": nexp},
           "completeness": comp_all,
           "rep_spread": rep_spread(recs),
           "host_load_overall": host_load_overall(A),
           "run_cfg": {"timing": run_cfg("timing"), R2: run_cfg(R2)},
           "startup": {"timing": startup("timing"), R2: startup(R2)},
           "bodo_r2": r2,
           "bodo_default_same_period": bsp,
           "per_notebook": {}}
    conf = T.get("conformance_on_timing30_clean_E2") or {}
    rows, left_out = [], []
    for e in ENGINES:
        for cpus in ("8", "default"):
            key = "%s|%s" % (cpus, e)
            src, g, comp = "summary.json timing.by_cpus.%s.%s" % (cpus, e), (T["by_cpus"].get(cpus) or {}).get(e), \
                out["completeness"][key]
            e_recs, ref_recs = recs, recs
            if cpus == "8" and e == "bodo":
                if r2["status"] != "complete":
                    left_out.append({"group": key, "reason": "campaign timing: %s (host-configuration crashes); "
                                     "rerun %s is %s" % (comp["by_status"], R2, r2["status"])})
                    continue
                src, g, comp = "rq4_timing.json bodo_r2.by_cpus.8.bodo", r2["by_cpus"]["8"]["bodo"], \
                    r2["completeness"]["8|bodo"]
                e_recs, ref_recs = r2_recs, r2_recs
            if cpus == "default" and e == "bodo":
                if bsp["status"] != "complete":
                    left_out.append({"group": key, "reason": "records %d of %d; same-period reference %s is %s" % (
                        comp["records"], comp["expected"], R2, r2["status"])})
                    continue
                src, g = "rq4_timing.json bodo_default_same_period.vs_same_period_ref", bsp["vs_same_period_ref"]
                e_recs, ref_recs = bsp_bodo, bsp_ref
            if not comp["complete"]:
                left_out.append({"group": key, "reason": "records %d of %d (runs pending)" % (comp["records"],
                                                                                              comp["expected"])})
                continue
            c = conf.get(e)
            if not g or "geomean_speedup_vs_ref" not in g or not c:
                left_out.append({"group": key, "reason": "no both-ok notebook or no conformance coordinate"})
                continue
            pn = per_notebook(e_recs, cpus, e, ref_recs, g["ref_cpus"])
            # the per-notebook speed-ups must reproduce the summary's geometric mean and both-ok count exactly
            if pn["n"] != g["notebooks_both_ok"] or abs(pn["geomean"] - g["geomean_speedup_vs_ref"]) > 2e-6:
                raise SystemExit("per-notebook speed-ups disagree with %s: %s vs %s" % (src, pn["geomean"],
                                                                                        g["geomean_speedup_vs_ref"]))
            out["per_notebook"][key] = pn
            rs = g["not_ok_by_reason"]
            rows.append({"cpus": cpus, "engine": e, "source": src, "geomean": g["geomean_speedup_vs_ref"],
                         "ci95": g["ci95"], "n_both_ok": g["notebooks_both_ok"], "per_notebook": pn,
                         "timeouts": rs["timeout"], "n_error_cells": len(rs["error_cells"]), "n_crash": len(rs["crash"]),
                         "n_other": len(rs["other"]), "conformance": 100 * c["cum_share_le_E2"],
                         "conformance_ci95": [100 * v for v in c["cum_ci95_le_E2"]], "conformance_cells": c["cells"]})
    out["figure"] = {"path": os.path.relpath(FIG, PROJ), "conformance_view": T.get("fig4_conformance_view"),
                     "rows": [{k: v for k, v in r.items() if k != "per_notebook"} for r in rows],
                     "left_out": left_out}
    if not a.no_figure and rows:
        figure(A, rows)
        out["figure"]["status"] = "written"
    else:
        out["figure"]["status"] = "not written"
    with open(OUT + ".tmp", "w") as f:
        json.dump(out, f, indent=1)
    os.replace(OUT + ".tmp", OUT)
    print(json.dumps({"rows": [(r["cpus"], r["engine"], r["geomean"], r["n_both_ok"],
                                r["per_notebook"]["n_faster_than_ref"]) for r in rows],
                      "left_out": left_out, "bodo_r2": r2["status"],
                      "bodo_default_same_period": bsp["status"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

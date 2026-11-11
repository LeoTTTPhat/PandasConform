#!/usr/bin/env python3
"""Project-level analysis of PandasConform (paper numbers and figures). Read-only on results/.

    ../.venv/bin/python \
        ../06_pandas_conformance/analyze.py

Rerun unchanged whenever a campaign of the main batch completes: campaign status is derived from
the batch markers work/batch/experiment_main/*.done and from record / compare-output counts, and
every figure whose inputs are complete is (re)written.

Inputs (read only; accepted tags ONLY: harness hd1c421ecb5ee, compare d92c8db54d45b)
  results/<campaign>/{summary,analysis,check}__hd1c421ecb5ee__d92c8db54d45b.json   (cross-check)
  results/<campaign>/metrics__runs__hd1c421ecb5ee.json, environment.json           (provenance)
  results/<campaign>/raw/compare__hd1c421ecb5ee__d92c8db54d45b/<eng>/<sf>/*.json   (per-cell classes)
  results/<campaign>/raw/runs__hd1c421ecb5ee/<eng>/<sf>/*.json                     (record status,
                                                       per-cell wall_s and capture time, versions)
  results/timing/raw/timing__hd1c421ecb5ee/... or results/timing/timing_report__hd1c421ecb5ee.json
Anything else under results/ (other harness or compare tags, superseded_* folders, the smoke and
smoke_timing campaigns) is listed under `excluded_inputs` and never read for numbers.

Outputs
  results/summary.json      stable keys (schema_version 1)
  results/analysis.md       human-readable report of the same numbers
  paper/figures/fig{1,2,3,4,5}_*.pdf   (fixed names; pilot versions *_pilot.pdf)

Analysis rules (implemented HERE, in the aggregation layer; src/pconf/classify.py is unchanged)
  * Excluded cells: REF_ERR (reference raised), NONDET (ref vs ref#2 differ), NOOUT (nothing
    comparable) and SETUP_ERR (engine never started; counted separately per engine). This is the
    same "comparable cell" population as scripts/analyze_campaign.py, so shares are cross-checked
    exactly against results/<campaign>/analysis__*.json.
  * Post-timeout cascades: every cell after the first engine TIMEOUT cell (cls or cls_raw TIMEOUT)
    of a notebook is a post-timeout cascade. Such cells are counted separately and EXCLUDED from
    the two clean-input views; the "all comparable" view keeps them under their own class so that
    it stays identical to the per-campaign analysis (their number is reported next to it).
  * nb_timeout records whose summed cell execution time (sum of cells[].wall_s) is below 3,600 s
    are reported as capture-inflated (ledger rule 2026-10-03) and never as engine slowness. For
    each such record the capture time and the time not covered by recorded cells are also given,
    because a notebook can also reach the 3,600 s limit through an in-flight cell the record does
    not contain (e.g. an engine blocked in native code).
  * Failure counts per engine: records by status (nb_crash, nb_memory, nb_timeout, nb_killed,
    engine_setup_error) and cells by class (CRASH, KILLED, MEMORY, TIMEOUT, NOTRUN, ERR); FALLBACK
    flags (cells whose engine flagged a fallback) per view.
  * Three attribution views (plan Section 8 + ledger A1 deviation): all comparable cells; strict
    clean-input (clean_input, every input E0-equal); clean at E2 (clean_level in E0..E2).

Statistics
  * Class shares are pooled over cells; 95% intervals are percentile bootstrap intervals over
    notebooks (N_BOOT resamples of notebooks with replacement). The generator is seeded with
    (SEED, crc32 of "<campaign>|<label>|<view>"), so every interval is reproducible and does not
    depend on which other campaigns or engines are present.
  * First divergence: per notebook, the first cell that breaks equality at each level (from the
    compare output), as an absolute cell number and as a relative position (rank / number of
    classified cells); the share of notebooks that diverge at all has a bootstrap interval.
  * Operation family x engine: the family of each cell IS recorded per cell by classify
    (`families`, from the attribute names in the cell's AST: classify.FAMILY_PATTERNS; a cell can
    belong to several families, 'other' when none matches). No source heuristic is needed here;
    the limits of that attribute-name rule are stated in analysis.md. Population: clean at E2
    minus post-timeout cascades. "Finest level reached" of a family = the finest level L such
    that at least half of its cells conform at <= L (">E4" when fewer than half conform at all).
  * Paired common-cell view (audit A11, added 2026-10-05; summary.json `common_clean_E2`): the
    cells, identified by (notebook, cell index), that are in the clean-at-E2 view (post-timeout
    cascades removed) of EVERY one of the five core conf_1x engines (pyarrow_backend, modin,
    fireducks, bodo, dask) AND both pandas versions of the drift campaign (p15, p30). A notebook
    enters only if all seven labels have a selected compare output with the same reference and
    replicate records (fingerprint file names) and the same cell index list. Every label's shares
    are over the SAME cells, so differences are paired by cell. Intervals: one shared set of
    N_BOOT notebook resamples (cluster bootstrap over the notebooks that hold at least one common
    cell, seed [SEED, crc32('common_clean_E2|paired')]); for each label the DIFF share, and for
    each engine the DIFF-share difference against pandas 3.0.6 (pre-specified baseline) and, as a
    secondary comparison, against 1.5.3, with percentile 95% intervals of that difference.
    Reading rule for the paper's A3 wording, fixed before the first run: an engine "differs in
    value about as often as" a pandas version when the paired 95% interval of its DIFF-share
    difference contains 0, and "more often" when the interval lies above 0.
  * Fallback flags (A12, 2026-10-05): `fallback.by_class_{all,clean_strict,clean_E2}` give the
    class counts of fallback-flagged cells per view (by_class_all is unchanged).
"""
import argparse
import collections
import datetime
import decimal
import glob
import json
import os
import resource
import sys
import time
import zlib

import numpy as np

HARNESS_TAG = "hd1c421ecb5ee"
COMPARE_TAG = "d92c8db54d45b"
TAG = "%s__%s" % (HARNESS_TAG, COMPARE_TAG)
SCHEMA_VERSION = 1
N_BOOT = 10000
SEED = 20261004
NB_TIMEOUT_S = 3600.0
MIN_FAMILY_CELLS = 10          # fig2: (family, engine) pairs with fewer cells are greyed out

LEVELS = ["E0", "E1", "E2", "E3", "E4"]
CLASSES = LEVELS + ["DIFF", "UNCOMPARABLE", "ERR", "TIMEOUT", "CRASH", "KILLED", "MEMORY", "NOTRUN"]
EXCLUDED = ("REF_ERR", "NONDET", "NOOUT", "SETUP_ERR")
VIEWS = ("all", "clean_strict", "clean_E2")
VIEW_TITLES = {"all": "All comparable cells", "clean_strict": "Strict clean-input cells",
               "clean_E2": "Cells clean at E2"}
FAILURE_CELL_CLASSES = ("ERR", "TIMEOUT", "CRASH", "KILLED", "MEMORY", "NOTRUN")
FAMILIES = ["read", "merge_join", "groupby_agg", "sort", "string", "datetime", "apply_map", "pivot_reshape",
            "describe_stats", "missing", "dedup_unique", "indexing", "dtype_conv", "other"]
CONF_ENGINES = ["pyarrow_backend", "modin", "fireducks", "bodo", "bodo_dw", "dask"]
BATCH = "experiment_main"
# A11 paired common-cell view: (campaign, label) of the five core engines and the two pandas versions
COMMON_LABELS = [("conf_1x", "pyarrow_backend"), ("conf_1x", "modin"), ("conf_1x", "fireducks"),
                 ("conf_1x", "bodo"), ("conf_1x", "dask"), ("drift", "p15"), ("drift", "p30")]
COMMON_ENGINES = ["pyarrow_backend", "modin", "fireducks", "bodo", "dask"]
COMMON_BASELINES = ["p30", "p15"]      # p30 (pandas 3.0.6) is the pre-specified baseline; p15 is secondary

# Campaign specification (plan Section 6 and scripts/steps_experiment_main.json). A group is the
# unit that completes together: its run configurations, its compare labels and the batch markers.
# Groups with core=False do not decide the campaign status (bodo_dw is a pilot addition).
CAMPAIGNS = {
    "pilot": {"set": "pilot", "mode": "capture", "is_pilot": True, "groups": [
        {"name": "pilot_main", "core": True, "run_configs": ["ref", "ref#2", "pyarrow_backend", "p15", "p30", "fireducks",
                                                            "bodo", "bodo_dw", "modin", "dask", "modin#2", "fireducks#2",
                                                            "bodo#2", "dask#2"],
         "run_markers": [], "compare_labels": ["ref#2", "pyarrow_backend", "p15", "p30", "fireducks", "bodo", "bodo_dw",
                                              "modin", "dask", "modin#2", "fireducks#2", "bodo#2", "dask#2"],
         "compare_marker": "pilot_compare"},
        {"name": "pilot_rep_modin", "core": True, "run_configs": [], "run_markers": [],
         "compare_labels": ["modin#2~vs~modin"], "compare_marker": "pilot_rep_modin"},
        {"name": "pilot_rep_fireducks", "core": True, "run_configs": [], "run_markers": [],
         "compare_labels": ["fireducks#2~vs~fireducks"], "compare_marker": "pilot_rep_fireducks"},
        {"name": "pilot_rep_bodo", "core": True, "run_configs": [], "run_markers": [],
         "compare_labels": ["bodo#2~vs~bodo"], "compare_marker": "pilot_rep_bodo"},
        {"name": "pilot_rep_dask", "core": True, "run_configs": [], "run_markers": [],
         "compare_labels": ["dask#2~vs~dask"], "compare_marker": "pilot_rep_dask"}]},
    "drift": {"set": "all", "mode": "capture", "is_pilot": False, "groups": [
        {"name": "drift", "core": True, "run_configs": ["ref", "ref#2", "p15", "p30"], "run_markers": ["drift_run"],
         "compare_labels": ["ref#2", "p15", "p30"], "compare_marker": "drift_compare"}]},
    "conf_1x": {"set": "all", "mode": "capture", "is_pilot": False, "groups": [
        {"name": "conf1x_core", "core": True,
         "run_configs": ["ref", "ref#2", "pyarrow_backend", "fireducks", "bodo", "modin", "dask"],
         "run_markers": ["conf1x_single", "conf1x_parallel"],
         "compare_labels": ["ref#2", "pyarrow_backend", "fireducks", "bodo", "modin", "dask"],
         "compare_marker": "conf1x_compare"},
        {"name": "conf1x_bodo_dw", "core": False, "run_configs": ["bodo_dw"], "run_markers": ["conf1x_bodo_dw"],
         "compare_labels": ["bodo_dw"], "compare_marker": "conf1x_compare_bodo_dw"}]},
    "timing": {"set": "timing30", "mode": "timing", "is_pilot": False, "groups": [
        {"name": "timing_cpu8", "core": True, "run_configs": ["ref", "modin", "fireducks", "bodo"], "reps": 3,
         "cpus": "8", "run_markers": ["timing_cpu8"], "compare_labels": [], "compare_marker": None},
        {"name": "timing_default", "core": True, "run_configs": ["ref", "modin", "fireducks", "bodo"], "reps": 1,
         "cpus": "default", "run_markers": ["timing_default"], "compare_labels": [], "compare_marker": None}]},
    # 2026-10-28: one conf5x notebook cannot be prepared at 5x (its PandasBench scaling cell calls
    # read_csv(error_bad_lines=...), removed in pandas 2.0; work/scaled/sf5/<nb>/.pconf_prepared.json status "error"),
    # so the orchestrator never runs it. It is excluded from the expected counts and from both sides of scale_effect.
    "conf_5x": {"set": "conf5x", "mode": "capture", "is_pilot": False, "excluded": {
        "jirakst/book-recommendation": "not prepared at 5x: its PandasBench scaling cell calls "
                                       "read_csv(error_bad_lines=...), which pandas 2.0 removed"}, "groups": [
        {"name": "conf5x", "core": True, "run_configs": ["ref", "ref#2", "modin", "fireducks", "bodo"],
         "run_markers": ["conf5x_run"], "compare_labels": ["ref#2", "modin", "fireducks", "bodo"],
         "compare_marker": "conf5x_compare"}]},
}

# Numbers stated in plan.md's Ledger (transcribed verbatim; line numbers of plan.md on 2026-10-04).
# kind 'pct1': percent with one decimal; 'count': exact integer. view 'clean_strict'/'clean_E2' here
# mean the clean views BEFORE post-timeout-cascade exclusion (the ledger predates that rule).
LEDGER_CLAIMS = []


def _ledger(campaign, label, view, metric, value, kind, line):
    LEDGER_CLAIMS.append({"campaign": campaign, "label": label, "view": view, "metric": metric, "value": value,
                          "kind": kind, "plan_line": line})


# plan.md lines 388-399: pilot table (all E0, all DIFF, all ERR, strict cells, strict E0, @E2 cells, @E2 DIFF)
for _lab, _vals, _ln in [("modin", (71.6, 6.9, 3.8, 281, 84.3, 338, 2.7), 390),
                         ("fireducks", (62.9, 9.2, 8.7, 170, 82.3, 183, 0.0), 391),
                         ("bodo", (29.7, 19.3, 17.8, 20, 40.0, 113, 6.2), 392),
                         ("bodo_dw", (29.7, 20.5, 18.3, 20, 40.0, 110, 7.3), 393),
                         ("dask", (16.3, 12.1, 58.9, 20, 40.0, 77, 11.7), 394),
                         ("pyarrow_backend", (39.4, 10.6, 8.9, 24, 50.0, 134, 2.2), 395),
                         ("p15", (74.3, 14.4, 0.0, 244, 91.0, 252, 1.2), 396),
                         ("p30", (34.9, 8.2, 2.7, 30, 60.0, 353, 2.8), 397)]:
    _ledger("pilot", _lab, "all", "E0", _vals[0], "pct1", _ln)
    _ledger("pilot", _lab, "all", "DIFF", _vals[1], "pct1", _ln)
    _ledger("pilot", _lab, "all", "ERR", _vals[2], "pct1", _ln)
    _ledger("pilot", _lab, "clean_strict", "cells", _vals[3], "count", _ln)
    _ledger("pilot", _lab, "clean_strict", "E0", _vals[4], "pct1", _ln)
    _ledger("pilot", _lab, "clean_E2", "cells", _vals[5], "count", _ln)
    _ledger("pilot", _lab, "clean_E2", "DIFF", _vals[6], "pct1", _ln)
_ledger("pilot", "modin", "all", "MEMORY", 0.2, "pct1", 399)
_ledger("pilot", "modin", "all", "NOTRUN", 8.6, "pct1", 399)
_ledger("pilot", "p30", "all", "E2", 53.7, "pct1", 399)
_ledger("pilot", "pyarrow_backend", "all", "E2", 24.3, "pct1", 399)
_ledger("pilot", "pyarrow_backend", "all", "E3", 16.6, "pct1", 399)
_ledger("pilot", "ref#2", "all", "cells", 404, "count", 384)
_ledger("pilot", "ref#2", "all", "count:E0", 404, "count", 384)
_ledger("pilot", "ref#2", "excluded", "count:NONDET", 0, "count", 384)
_ledger("pilot", "modin#2", "all", "E1", 1.2, "pct1", 400)
_ledger("pilot", "modin", "all", "E1", 0.9, "pct1", 400)
_ledger("pilot", "modin#2", "all", "DIFF", 6.7, "pct1", 400)
_ledger("pilot", "modin#2~vs~modin", "all", "cells", 366, "count", 437)
_ledger("pilot", "modin#2~vs~modin", "all", "non_E0", 1.6, "pct1", 437)
_ledger("pilot", "modin#2~vs~modin", "all", "count:E1", 3, "count", 437)
_ledger("pilot", "modin#2~vs~modin", "all", "count:E2", 2, "count", 437)
_ledger("pilot", "modin#2~vs~modin", "all", "count:DIFF", 1, "count", 437)
_ledger("pilot", "bodo#2~vs~bodo", "all", "cells", 331, "count", 437)
_ledger("pilot", "bodo#2~vs~bodo", "all", "non_E0", 0.9, "pct1", 437)
_ledger("pilot", "bodo#2~vs~bodo", "all", "count:DIFF", 3, "count", 437)
_ledger("pilot", "dask#2~vs~dask", "all", "cells", 194, "count", 437)
_ledger("pilot", "dask#2~vs~dask", "all", "DIFF", 3.1, "pct1", 437)
_ledger("pilot", "dask#2~vs~dask", "all", "UNCOMPARABLE", 14.9, "pct1", 437)
_ledger("pilot", "fireducks#2~vs~fireducks", "all", "cells", 379, "count", 437)
_ledger("pilot", "fireducks#2~vs~fireducks", "all", "E4", 0.3, "pct1", 437)
_ledger("pilot", "fireducks#2~vs~fireducks", "all", "UNCOMPARABLE", 2.6, "pct1", 437)
_ledger("pilot", "*", "total", "cells_in_outputs", 8225, "count", 427)
# plan.md lines 427-434: drift
_ledger("drift", "*", "total", "cells_in_outputs", 10824, "count", 427)
_ledger("drift", "ref#2", "all", "cells", 2809, "count", 430)
_ledger("drift", "ref#2", "all", "count:E0", 2809, "count", 430)
for _lab in ("ref#2", "p15", "p30"):
    _ledger("drift", _lab, "excluded", "count:NONDET", 14, "count", 430)
for _m, _v in (("E0", 70.0), ("E2", 9.8), ("E4", 7.2), ("DIFF", 11.1), ("ERR", 1.0)):
    _ledger("drift", "p15", "all", _m, _v, "pct1", 433)
_ledger("drift", "p15", "clean_strict", "cells", 1771, "count", 433)
_ledger("drift", "p15", "clean_strict", "DIFF", 2.2, "pct1", 433)
_ledger("drift", "p15", "clean_E2", "cells", 2129, "count", 433)
_ledger("drift", "p15", "clean_E2", "DIFF", 2.3, "pct1", 433)
for _m, _v in (("E0", 28.1), ("E2", 54.1), ("DIFF", 10.3), ("ERR", 6.1)):
    _ledger("drift", "p30", "all", _m, _v, "pct1", 434)
_ledger("drift", "p30", "clean_strict", "cells", 299, "count", 434)
_ledger("drift", "p30", "clean_E2", "cells", 2215, "count", 434)
for _m, _v in (("E2", 63.1), ("DIFF", 2.5), ("ERR", 2.1)):
    _ledger("drift", "p30", "clean_E2", _m, _v, "pct1", 434)


# ----------------------------------------------------------------------------------------------
# paths and small helpers

class Paths:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.results = os.path.join(self.root, "results")
        self.work = os.path.join(self.root, "work")
        self.data = os.path.join(self.root, "data")
        self.figures = os.path.join(self.root, "paper", "figures")
        self.markers = os.path.join(self.work, "batch", BATCH)

    def raw(self, campaign):
        return os.path.join(self.results, campaign, "raw")

    def rel(self, p):
        return os.path.relpath(p, self.root) if p else None


def read_json(p):
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def atomic_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp%d" % os.getpid()
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def pct1(count, n):
    """Percent with one decimal, round-half-up from the exact counts (ledger precision)."""
    if not n:
        return None
    q = decimal.Decimal(count) * 100 / decimal.Decimal(n)
    return float(q.quantize(decimal.Decimal("0.1"), rounding=decimal.ROUND_HALF_UP))


def r6(x):
    return None if x is None else round(float(x), 6)


def label_of(meta):
    ref = meta.get("ref") or "ref"
    return meta["engine"] if ref == "ref" else "%s~vs~%s" % (meta["engine"], ref)


def notebook_set(paths, name):
    if name == "all":
        d = read_json(os.path.join(paths.data, "PandasBench", "runner", "scales", "nbs_to_run_default.json"))
        return [e["nb"] for e in d["notebooks"]] if d else []
    d = read_json(os.path.join(paths.data, "notebook_sets", name + ".json"))
    return list(d["notebooks"]) if d else []


def rng_for(key):
    return np.random.default_rng([SEED, zlib.crc32(key.encode())])


# ----------------------------------------------------------------------------------------------
# inputs: excluded-input listing, markers, run records, compare outputs

ACCEPTED_TOP = ("summary__%s.json" % TAG, "analysis__%s.json" % TAG, "check__", "metrics__runs__%s.json" % HARNESS_TAG,
                "metrics__timing__%s.json" % HARNESS_TAG, "timing_report__%s.json" % HARNESS_TAG, "environment.json")
ACCEPTED_RAW = ("runs__%s" % HARNESS_TAG, "timing__%s" % HARNESS_TAG, "compare__%s" % TAG, "campaign_%s.json" % HARNESS_TAG)


def excluded_inputs(paths):
    out = []
    if not os.path.isdir(paths.results):
        return out
    for camp in sorted(os.listdir(paths.results)):
        cdir = os.path.join(paths.results, camp)
        if not os.path.isdir(cdir):
            continue
        if camp not in CAMPAIGNS:
            reason = ("copy of earlier project-level outputs (summary.json, analysis.md), kept for the record"
                      if camp.startswith("previous_") else
                      "campaign not analysed (not in plan matrix of the main batch)")
            out.append({"path": paths.rel(cdir), "reason": reason})
            continue
        for n in sorted(os.listdir(cdir)):
            p = os.path.join(cdir, n)
            if n == "raw":
                for m in sorted(os.listdir(p)):
                    if m not in ACCEPTED_RAW:
                        out.append({"path": paths.rel(os.path.join(p, m)), "reason": "tag not accepted"})
                continue
            if n.startswith("check__") and n.endswith("_%s.json" % TAG):
                continue
            if n in ACCEPTED_TOP:
                continue
            reason = "superseded folder" if n.startswith("superseded") else "tag not accepted"
            out.append({"path": paths.rel(p), "reason": reason})
    return out


def markers(paths):
    return sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(paths.markers, "*.done")))


def summarize_run_record(r):
    cells = r.get("cells") or []
    cfg = r.get("cfg") or {}
    cell_wall = sum((c.get("wall_s") or 0.0) for c in cells)
    capture = sum((c.get("t_capture_in") or 0.0) + (c.get("t_capture_out") or 0.0) for c in cells)
    fb = sum(1 for c in cells if any("fallback" in f or "default_to_pandas" in f for f in (c.get("flags") or [])))
    ok_wall = sum((c.get("wall_s") or 0.0) for c in cells if c.get("status") == "ok")
    all_ok = r.get("status") == "completed" and all(c.get("status") in ("ok", "setup", "empty", "skipped")
                                                     for c in cells)
    return {"engine": r.get("engine"), "nb": r.get("nb"), "scale": r.get("scale"), "status": r.get("status"),
            "pandas": r.get("pandas"), "rep": r.get("rep"), "cpus": str(cfg.get("cpus")), "mode": r.get("mode"),
            "n_cells": len(cells), "cell_wall_s": cell_wall, "capture_s": capture,
            "orchestrator_wall_s": r.get("orchestrator_wall_s"), "peak_tree_rss_gb": r.get("peak_tree_rss_gb"),
            "fallback_cells": fb, "ok_cells_wall_s": ok_wall, "all_ok": all_ok, "reused_from": r.get("reused_from"),
            "cell_status": dict(collections.Counter(str(c.get("status")) for c in cells)),
            "started": r.get("started"), "finished": r.get("finished")}


def load_run_records(paths, campaign, mode):
    root = os.path.join(paths.raw(campaign), ("runs__" if mode == "capture" else "timing__") + HARNESS_TAG)
    recs, unreadable = {}, 0
    for p in sorted(glob.glob(os.path.join(root, "*", "*", "*.json"))):
        if os.path.basename(p).startswith(".tmp"):
            continue
        r = read_json(p)
        if not r or "fingerprint" not in r:
            unreadable += 1
            continue
        s = summarize_run_record(r)
        s["path"] = paths.rel(p)
        s["mtime"] = os.path.getmtime(p)
        key = (s["engine"], s["nb"], s["scale"], s["rep"], s["cpus"])
        if key not in recs or s["mtime"] > recs[key]["mtime"]:
            recs[key] = s
    return list(recs.values()), unreadable


def select_compare_outputs(paths, campaign):
    """One output per (label, notebook, scale): with ref#2 first, then newest (identical to
    orchestrate summarize / scripts/analyze_campaign.py)."""
    root = os.path.join(paths.raw(campaign), "compare__" + TAG)
    best, n_files, unreadable = {}, 0, 0
    for p in sorted(glob.glob(os.path.join(root, "*", "*", "*.json"))):
        if os.path.basename(p).startswith(".tmp"):
            continue
        r = read_json(p)
        if not r or "meta" not in r or "cells" not in r:
            unreadable += 1
            continue
        n_files += 1
        key = (label_of(r["meta"]), r["meta"]["nb"], r["meta"].get("scale"))
        rank = (r["meta"].get("ref2_record") is not None, os.path.getmtime(p))
        if key not in best or rank > best[key][0]:
            best[key] = (rank, process_output(r))
    return {k: v[1] for k, v in best.items()}, n_files, unreadable


# ----------------------------------------------------------------------------------------------
# per-notebook processing (rules) and aggregation

def process_output(r):
    """One compare output -> compact per-notebook counts under the analysis rules."""
    cells = r["cells"]
    n = len(cells)
    t_idx = next((k for k, c in enumerate(cells) if c.get("cls") == "TIMEOUT" or c.get("cls_raw") == "TIMEOUT"), None)
    counts = {v: collections.Counter() for v in VIEWS}
    pre = {"clean_strict": collections.Counter(), "clean_E2": collections.Counter()}
    fb = {v: collections.Counter() for v in VIEWS}
    fam, fam_pre = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
    excluded, cascade, clean_dist, raw = (collections.Counter() for _ in range(4))
    cascade_clean = collections.Counter()
    clean_e2_cls = {}      # cell index -> class, for the cells of the clean-at-E2 view (A11 common-cell view)
    for k, c in enumerate(cells):
        cls = c["cls"]
        raw[cls] += 1
        if cls in EXCLUDED:
            excluded[cls] += 1
            continue
        fbk = bool(c.get("fallback"))
        strict = bool(c.get("clean_input"))
        e2 = c.get("clean_level") in ("E0", "E1", "E2")
        counts["all"][cls] += 1
        fb["all"][cls] += fbk
        clean_dist[c.get("clean_level") or "unclean"] += 1
        if strict:
            pre["clean_strict"][cls] += 1
        if e2:
            pre["clean_E2"][cls] += 1
            for f in c.get("families") or ["other"]:
                fam_pre[f][cls] += 1
        if t_idx is not None and k > t_idx:
            cascade[cls] += 1
            cascade_clean["clean_strict"] += strict
            cascade_clean["clean_E2"] += e2
            continue
        if strict:
            counts["clean_strict"][cls] += 1
            fb["clean_strict"][cls] += fbk
        if e2:
            counts["clean_E2"][cls] += 1
            fb["clean_E2"][cls] += fbk
            clean_e2_cls[c["i"]] = cls
            for f in c.get("families") or ["other"]:
                fam[f][cls] += 1
    pos = {c["i"]: k for k, c in enumerate(cells)}
    fd = {}
    for L in LEVELS:
        i = (r.get("first_divergent") or {}).get(L)
        if i is None or i not in pos:
            fd[L] = None
        else:
            c = cells[pos[i]]
            cls = c.get("cls_raw") if c.get("cls") == "NONDET" else c.get("cls")
            fd[L] = {"cell": i, "rank": pos[i] + 1, "rel": (pos[i] + 1) / n, "cls": cls}
    meta = r["meta"]
    return {"nb": meta["nb"], "scale": meta.get("scale"), "eng_status": meta.get("eng_status"),
            "eng_record": meta.get("eng_record"), "with_ref2": meta.get("ref2_record") is not None, "n_cells": n,
            "counts": counts, "pre": pre, "fallback": fb, "families": fam, "families_pre": fam_pre,
            "excluded": excluded, "raw": raw, "cascade": cascade, "cascade_clean": cascade_clean,
            "timeout_cell": cells[t_idx]["i"] if t_idx is not None else None, "clean_levels": clean_dist,
            "first_divergent": fd, "clean_E2_cls": clean_e2_cls, "cell_ids": tuple(c["i"] for c in cells),
            "ref_file": os.path.basename(meta.get("ref_record") or "") or None,
            "ref2_file": os.path.basename(meta.get("ref2_record") or "") or None}


def bootstrap_shares(rows, key, n_boot=N_BOOT):
    """rows: per-notebook Counters of classes (sorted by notebook). Pooled shares, cumulative
    shares <=Ek and non-conformant share, with percentile 95% intervals over notebooks."""
    arr = np.array([[c.get(k, 0) for k in CLASSES] for c in rows], dtype=float).reshape(len(rows), len(CLASSES))
    tot = arr.sum(axis=0)
    n = int(tot.sum())
    out = {"cells": n, "notebooks": len(rows), "notebooks_with_cells": int((arr.sum(axis=1) > 0).sum()),
           "counts": {k: int(tot[j]) for j, k in enumerate(CLASSES)}, "share": {}, "ci95": {},
           "cum_share": {}, "cum_ci95": {}, "nonconformant_share": None, "nonconformant_ci95": None,
           "n_boot": n_boot, "seed": [SEED, zlib.crc32(key.encode())]}
    if not n:
        return out
    nb = len(rows)
    idx = rng_for(key).integers(0, nb, size=(n_boot, nb))
    w = np.bincount((idx + np.arange(n_boot)[:, None] * nb).ravel(), minlength=n_boot * nb).reshape(n_boot, nb)
    boot = w.astype(float) @ arr
    den = boot.sum(axis=1)
    bs = boot[den > 0] / den[den > 0][:, None]
    cum = np.cumsum(bs[:, :len(LEVELS)], axis=1)

    def ci(v):
        return [r6(np.percentile(v, 2.5)), r6(np.percentile(v, 97.5))]

    for j, k in enumerate(CLASSES):
        out["share"][k] = r6(tot[j] / n)
        out["ci95"][k] = ci(bs[:, j])
    run = 0.0
    for j, L in enumerate(LEVELS):
        run += tot[j]
        out["cum_share"]["<=" + L] = r6(run / n)
        out["cum_ci95"]["<=" + L] = ci(cum[:, j])
    out["nonconformant_share"] = r6(1 - run / n)
    out["nonconformant_ci95"] = ci(1 - cum[:, -1])
    return out


def bootstrap_fraction(flags, key, n_boot=N_BOOT):
    """Share of notebooks with a property, bootstrap interval over notebooks."""
    a = np.array(flags, dtype=float)
    if not len(a):
        return None, None
    idx = rng_for(key).integers(0, len(a), size=(n_boot, len(a)))
    m = a[idx].mean(axis=1)
    return r6(a.mean()), [r6(np.percentile(m, 2.5)), r6(np.percentile(m, 97.5))]


def finest_level(counter):
    n = sum(counter.values())
    if not n:
        return None
    run = 0
    for L in LEVELS:
        run += counter.get(L, 0)
        if run / n >= 0.5:
            return L
    return ">E4"


def family_matrix(nbs):
    tot = collections.defaultdict(collections.Counter)
    for s in nbs:
        for f, c in s["families"].items():
            tot[f].update(c)
    out = {}
    for f in sorted(tot, key=lambda x: FAMILIES.index(x) if x in FAMILIES else 99):
        c = tot[f]
        n = sum(c.values())
        cum = {}
        run = 0
        for L in LEVELS:
            run += c.get(L, 0)
            cum["<=" + L] = r6(run / n)
        out[f] = {"cells": n, "counts": {k: int(v) for k, v in sorted(c.items())}, "share_E0": r6(c.get("E0", 0) / n),
                  "cum_share": cum, "finest_level_majority": finest_level(c)}
    return out


def first_divergence_stats(nbs, key):
    res = {}
    for L in LEVELS:
        hits = [s["first_divergent"][L] for s in nbs]
        flags = [h is not None for h in hits]
        share, ci = bootstrap_fraction(flags, key + "|fd|" + L)
        rel = sorted(h["rel"] for h in hits if h is not None)
        q = {}
        if rel:
            for p in (10, 25, 50, 75, 90):
                q["p%d" % p] = r6(np.percentile(rel, p))
        cls = collections.Counter(h["cls"] for h in hits if h is not None)
        res[L] = {"notebooks": len(nbs), "notebooks_diverged": int(sum(flags)), "share_diverged": share,
                  "share_diverged_ci95": ci, "rel_position_quantiles": q,
                  "abs_cell_median": r6(np.median([h["cell"] for h in hits if h is not None])) if rel else None,
                  "class_at_first_divergence": dict(sorted(cls.items())),
                  "first_cell_is_divergent": int(sum(1 for h in hits if h is not None and h["rank"] == 1))}
    return res


def aggregate_label(campaign, label, nbs):
    nbs = sorted(nbs, key=lambda s: (s["nb"], s["scale"] or 0))
    key = "%s|%s" % (campaign, label)
    views = {v: bootstrap_shares([s["counts"][v] for s in nbs], key + "|" + v) for v in VIEWS}
    pre = {v: dict(sum((s["pre"][v] for s in nbs), collections.Counter())) for v in ("clean_strict", "clean_E2")}
    cascade = sum((s["cascade"] for s in nbs), collections.Counter())
    casc_clean = sum((s["cascade_clean"] for s in nbs), collections.Counter())
    fb = {v: sum((s["fallback"][v] for s in nbs), collections.Counter()) for v in VIEWS}
    excluded = sum((s["excluded"] for s in nbs), collections.Counter())
    raw = sum((s["raw"] for s in nbs), collections.Counter())
    cl = sum((s["clean_levels"] for s in nbs), collections.Counter())
    allc = views["all"]["counts"]
    return {
        "notebooks": len(nbs),
        "notebooks_with_ref2": sum(1 for s in nbs if s["with_ref2"]),
        "views": views,
        "clean_views_before_cascade_exclusion": {v: {"cells": sum(c.values()), "counts": dict(sorted(c.items()))}
                                                 for v, c in pre.items()},
        "excluded_cells": dict(sorted(excluded.items())),
        "setup_err_cells": int(excluded.get("SETUP_ERR", 0)),
        "raw_class_counts": dict(sorted(raw.items())),
        "post_timeout_cascade": {
            "notebooks_with_engine_timeout": sum(1 for s in nbs if s["timeout_cell"] is not None),
            "cells": int(sum(cascade.values())), "by_class": dict(sorted(cascade.items())),
            "removed_from_clean_strict": int(casc_clean.get("clean_strict", 0)),
            "removed_from_clean_E2": int(casc_clean.get("clean_E2", 0)),
            "timeout_cells": {s["nb"]: s["timeout_cell"] for s in nbs if s["timeout_cell"] is not None}},
        "failure_cells": {k: int(allc.get(k, 0)) for k in FAILURE_CELL_CLASSES},
        "fallback": {"cells": {v: int(sum(fb[v].values())) for v in VIEWS},
                     "share": {v: r6(sum(fb[v].values()) / views[v]["cells"]) if views[v]["cells"] else None
                               for v in VIEWS},
                     "by_class_all": dict(sorted((k, int(x)) for k, x in fb["all"].items() if x)),
                     "by_class_clean_strict": dict(sorted((k, int(x)) for k, x in fb["clean_strict"].items() if x)),
                     "by_class_clean_E2": dict(sorted((k, int(x)) for k, x in fb["clean_E2"].items() if x)),
                     "notebooks_with_fallback": sum(1 for s in nbs if sum(s["fallback"]["all"].values()))},
        "clean_level_distribution_all": dict(sorted(cl.items())),
        "eng_status": dict(collections.Counter(str(s["eng_status"]) for s in nbs)),
        "first_divergence": first_divergence_stats(nbs, key),
        "first_divergence_per_notebook": {s["nb"]: {L: s["first_divergent"][L] for L in LEVELS} for s in nbs},
    }


def record_stats(recs):
    per = collections.defaultdict(lambda: {"records": 0, "by_status": collections.Counter(), "pandas": set(),
                                           "peak_tree_rss_gb": 0.0, "orchestrator_wall_s": 0.0, "cell_wall_s": 0.0,
                                           "capture_s": 0.0, "fallback_flagged_cells": 0, "reused": 0})
    for s in recs:
        g = per[s["engine"]]
        g["records"] += 1
        g["by_status"][str(s["status"])] += 1
        if s["pandas"]:
            g["pandas"].add(s["pandas"])
        g["peak_tree_rss_gb"] = max(g["peak_tree_rss_gb"], s["peak_tree_rss_gb"] or 0.0)
        g["orchestrator_wall_s"] += s["orchestrator_wall_s"] or 0.0
        g["cell_wall_s"] += s["cell_wall_s"]
        g["capture_s"] += s["capture_s"]
        g["fallback_flagged_cells"] += s["fallback_cells"]
        g["reused"] += bool(s["reused_from"])
    out = {}
    for e, g in sorted(per.items()):
        out[e] = {"records": g["records"], "by_status": dict(sorted(g["by_status"].items())),
                  "pandas": sorted(g["pandas"]), "peak_tree_rss_gb": r6(g["peak_tree_rss_gb"]),
                  "orchestrator_wall_s": r6(g["orchestrator_wall_s"]), "cell_wall_s": r6(g["cell_wall_s"]),
                  "capture_s": r6(g["capture_s"]), "fallback_flagged_cells": g["fallback_flagged_cells"],
                  "reused_records": g["reused"],
                  "nb_crash": g["by_status"].get("nb_crash", 0), "nb_memory": g["by_status"].get("nb_memory", 0),
                  "nb_timeout": g["by_status"].get("nb_timeout", 0), "nb_killed": g["by_status"].get("nb_killed", 0),
                  "engine_setup_error": g["by_status"].get("engine_setup_error", 0)}
    return out


def nb_timeout_rows(recs):
    """Ledger rule: nb_timeout with summed cell wall_s < 3,600 s is capture-inflated."""
    rows = []
    for s in sorted(recs, key=lambda x: (x["engine"], x["nb"])):
        if s["status"] != "nb_timeout":
            continue
        orch = s["orchestrator_wall_s"] or 0.0
        unrec = orch - s["cell_wall_s"] - s["capture_s"]
        rows.append({"engine": s["engine"], "nb": s["nb"], "record": s["path"], "cells_in_record": s["n_cells"],
                     "cell_wall_s": r6(s["cell_wall_s"]), "capture_s": r6(s["capture_s"]),
                     "orchestrator_wall_s": r6(orch), "not_in_recorded_cells_s": r6(unrec),
                     "capture_inflated": s["cell_wall_s"] < NB_TIMEOUT_S,
                     "larger_share": ("capture" if s["capture_s"] >= unrec else "time_outside_recorded_cells")})
    return rows


# ----------------------------------------------------------------------------------------------
# campaign status

def campaign_status(paths, campaign, spec, recs, outs, done):
    nbs = [nb for nb in notebook_set(paths, spec["set"]) if nb not in spec.get("excluded", {})]
    nexp = len(nbs)
    rec_by_cfg = collections.Counter(s["engine"] for s in recs)
    out_by_label = collections.Counter(k[0] for k in outs)
    groups, any_data = {}, bool(recs or outs)
    for g in spec["groups"]:
        reps = g.get("reps", 1)
        if spec["mode"] == "timing":
            found = sum(1 for s in recs if s["engine"] in g["run_configs"] and s["cpus"] == g["cpus"])
        else:
            found = sum(rec_by_cfg.get(e, 0) for e in g["run_configs"])
        rexp = len(g["run_configs"]) * nexp * reps
        cfound = sum(out_by_label.get(l, 0) for l in g["compare_labels"])
        cexp = len(g["compare_labels"]) * nexp
        mk = {m: m in done for m in g["run_markers"] + ([g["compare_marker"]] if g["compare_marker"] else [])}
        complete = all(mk.values()) and found >= rexp and cfound >= cexp
        compare_done = (g["compare_marker"] in done and cfound >= cexp) if g["compare_marker"] else False
        status = "complete" if complete else ("partial" if (found or cfound or any(mk.values())) else "pending")
        groups[g["name"]] = {"status": status, "core": g["core"], "markers": mk, "records_found": found,
                             "records_expected": rexp, "compare_outputs_found": cfound, "compare_outputs_expected": cexp,
                             "compare_complete": compare_done, "labels": g["compare_labels"]}
    core = [x for x in groups.values() if x["core"]]
    if all(x["status"] == "complete" for x in core):
        status = "complete"
    elif any_data or any(x["status"] != "pending" for x in groups.values()):
        status = "partial"
    else:
        status = "pending"
    return status, groups, nexp


def postprocessing_files(paths, campaign):
    d = os.path.join(paths.results, campaign)
    f = {"summary": os.path.join(d, "summary__%s.json" % TAG), "analysis": os.path.join(d, "analysis__%s.json" % TAG),
         "check": (glob.glob(os.path.join(d, "check__*_%s.json" % TAG)) or [None])[0],
         "metrics": os.path.join(d, "metrics__runs__%s.json" % HARNESS_TAG),
         "timing_report": os.path.join(d, "timing_report__%s.json" % HARNESS_TAG),
         "environment": os.path.join(d, "environment.json")}
    out = {k: (paths.rel(v) if v and os.path.exists(v) else None) for k, v in f.items()}
    chk = read_json(f["check"]) if f["check"] else None
    out["check_n_problems"] = chk.get("n_problems") if chk else None
    out["check_problems"] = (chk.get("problems") or [])[:20] if chk else None
    env = read_json(f["environment"]) if os.path.exists(f["environment"]) else None
    out["environment_compare_tag"] = env.get("compare_tag") if env else None
    return out


# ----------------------------------------------------------------------------------------------
# cross-checks

def crosscheck_campaign(paths, campaign, engines, outs):
    """Recomputed numbers vs results/<campaign>/{analysis,summary}__<tag>.json: must agree exactly."""
    checks, mism = 0, []

    def chk(what, expected, got):
        nonlocal checks
        checks += 1
        if expected != got:
            mism.append({"check": what, "file_value": expected, "recomputed": got})

    a = read_json(os.path.join(paths.results, campaign, "analysis__%s.json" % TAG))
    s = read_json(os.path.join(paths.results, campaign, "summary__%s.json" % TAG))
    if a is None and s is None:
        return {"analysis_file": None, "summary_file": None, "n_checks": 0, "n_mismatch": 0, "mismatches": [],
                "note": "no post-processing outputs yet"}
    vmap = {"all": "all", "clean_E0": "clean_strict", "clean_E2": "clean_E2"}
    if a is not None:
        chk("analysis.compare_tag", a.get("compare_tag"), TAG)
        chk("analysis.engines", sorted(a.get("engines", {})), sorted(engines))
        for lab, ea in sorted(a.get("engines", {}).items()):
            mine = engines.get(lab)
            if mine is None:
                continue
            for fv, mv in vmap.items():
                if mv == "all":
                    cnt = mine["views"]["all"]["counts"]
                else:
                    cnt = mine["clean_views_before_cascade_exclusion"][mv]["counts"]
                n = sum(cnt.values())
                fa = ea.get(fv) or {}
                chk("%s.%s.cells" % (lab, fv), fa.get("cells"), n)
                chk("%s.%s.notebooks" % (lab, fv), fa.get("notebooks"), mine["notebooks"])
                if n:
                    for k in CLASSES:
                        chk("%s.%s.share.%s" % (lab, fv, k), (fa.get("share") or {}).get(k), round(cnt.get(k, 0) / n, 4))
                    run = 0
                    for L in LEVELS:
                        run += cnt.get(L, 0)
                        chk("%s.%s.cum_share.<=%s" % (lab, fv, L), (fa.get("cum_share") or {}).get("<=" + L),
                            round(run / n, 4))
            chk("%s.excluded_cells" % lab, ea.get("excluded_cells"), mine["excluded_cells"])
            fbf = ea.get("fallback_cells") or {}
            pre_fb = sum(x for x in [mine["fallback"]["cells"]["all"]])
            chk("%s.fallback_cells.all" % lab, fbf.get("all", 0), pre_fb)
            fam_pre = collections.defaultdict(collections.Counter)
            for (l2, _, _), nbsum in outs.items():
                if l2 == lab:
                    for f, c in nbsum["families_pre"].items():
                        fam_pre[f].update(c)
            chk("%s.families(clean_E2)" % lab, a.get("families", {}).get(lab),
                {f: dict(c) for f, c in sorted(fam_pre.items())})
            fdf = a.get("first_divergent", {}).get(lab, {})
            fdm = {nb: {L: (h["cell"] if h else None) for L, h in d.items()}
                   for nb, d in mine["first_divergence_per_notebook"].items()}
            chk("%s.first_divergent" % lab, fdf, fdm)
    if s is not None:
        for lab, es in sorted(s.items()):
            if lab.startswith("_") or lab not in engines:
                continue
            chk("summary.%s.by_class" % lab, es.get("by_class"), engines[lab]["raw_class_counts"])
    return {"analysis_file": paths.rel(os.path.join(paths.results, campaign, "analysis__%s.json" % TAG)) if a else None,
            "summary_file": paths.rel(os.path.join(paths.results, campaign, "summary__%s.json" % TAG)) if s else None,
            "n_checks": checks, "n_mismatch": len(mism), "mismatches": mism[:50]}


def crosscheck_ledger(campaign_results):
    rows = []
    for c in LEDGER_CLAIMS:
        camp = campaign_results.get(c["campaign"]) or {}
        eng = camp.get("engines", {})
        got, note = None, None
        if c["view"] == "total":
            got = camp.get("cells_in_selected_outputs")
        elif c["label"] not in eng:
            note = "label not analysed"
        else:
            e = eng[c["label"]]
            if c["view"] == "excluded":
                got = e["excluded_cells"].get(c["metric"].split(":", 1)[1], 0)
            else:
                cnt = (e["views"]["all"]["counts"] if c["view"] == "all"
                       else e["clean_views_before_cascade_exclusion"][c["view"]]["counts"])
                n = sum(cnt.values())
                m = c["metric"]
                if m == "cells":
                    got = n
                elif m.startswith("count:"):
                    got = cnt.get(m.split(":", 1)[1], 0)
                elif m == "non_E0":
                    got = pct1(n - cnt.get("E0", 0), n)
                else:
                    got = pct1(cnt.get(m, 0), n)
        rows.append(dict(c, recomputed=got, agree=(got == c["value"]), note=note))
    bad = [r for r in rows if not r["agree"]]
    return {"n_checks": len(rows), "n_mismatch": len(bad), "mismatches": bad, "checks": rows}


# ----------------------------------------------------------------------------------------------
# timing (RQ4) and scale effect

def timing_failures(recs):
    """Per (cpus, engine): records by status and non-ok cells by status (crashes, notebook and cell timeouts,
    error cells), so that F2 reports them next to the speed-ups instead of only dropping the notebooks."""
    out = collections.defaultdict(lambda: {"records_by_status": collections.Counter(),
                                           "cells_by_status": collections.Counter(),
                                           "notebooks_with_error_cells": set(), "notebooks_with_timeout_cells": set(),
                                           "notebooks_with_crash_or_nb_timeout": set()})
    for s in recs:
        g = out["%s|%s" % (s["cpus"], s["engine"])]
        g["records_by_status"][str(s["status"])] += 1
        for k, v in s["cell_status"].items():
            if k not in ("ok", "setup", "empty", "skipped"):
                g["cells_by_status"][k] += v
        if s["cell_status"].get("error"):
            g["notebooks_with_error_cells"].add(s["nb"])
        if s["cell_status"].get("timeout"):
            g["notebooks_with_timeout_cells"].add(s["nb"])
        if s["status"] != "completed":
            g["notebooks_with_crash_or_nb_timeout"].add(s["nb"])
    return {k: {"records_by_status": dict(sorted(g["records_by_status"].items())),
                "cells_by_status": dict(sorted(g["cells_by_status"].items())),
                "notebooks_with_error_cells": len(g["notebooks_with_error_cells"]),
                "notebooks_with_timeout_cells": len(g["notebooks_with_timeout_cells"]),
                "notebooks_with_crash_or_nb_timeout": len(g["notebooks_with_crash_or_nb_timeout"])}
            for k, g in sorted(out.items())}


def timing_analysis(paths, recs, status, conf, host_load=None):
    """Speed-up of each engine over ref on notebooks where both ran every cell ok."""
    rep = read_json(os.path.join(paths.results, "timing", "timing_report__%s.json" % HARNESS_TAG))
    rows, source = [], None
    if rep:
        rows, source = rep, "results/timing/timing_report__%s.json" % HARNESS_TAG
    elif recs:
        agg = collections.defaultdict(list)
        for s in recs:
            agg[(s["engine"], s["nb"], s["scale"], s["cpus"])].append(s)
        for (e, nb, sc, cpus), xs in sorted(agg.items()):
            ts = [x["ok_cells_wall_s"] for x in xs]
            rows.append({"engine": e, "nb": nb, "scale": sc, "cpus": cpus, "reps": len(xs),
                         "median_s": float(np.median(ts)), "all_ok": all(x["all_ok"] for x in xs)})
        source = "raw timing records (same rule as pconf.timing report)"
    out = {"status": status, "source": source, "by_cpus": {}, "failures": timing_failures(recs)}
    if not rows:
        return out
    # load coverage per (cpus, engine, notebook): every repetition covered; median of the per-run mean load
    cov, load = {}, {}
    for r in (host_load or {}).get("rows", []):
        k = (r["cpus"], r["engine"], r["nb"])
        cov[k] = cov.get(k, True) and r["covered"]
        if r["covered"]:
            load.setdefault(k, []).append(r["load1_mean"])
    raw = collections.defaultdict(list)
    for s in recs:
        raw[(s["cpus"], s["engine"], s["nb"])].append(s)

    def not_ok_reasons(cpus, e, d, ref):
        """Why a timed notebook is outside the speed-up set. A notebook or cell timeout is a CENSORED slowdown,
        not a missing value: its speed-up is at most ref median / (time the engine was observed to take)."""
        out = {"crash": [], "timeout": [], "error_cells": [], "other": []}
        for nb in sorted(nb for nb in d if not d[nb]["all_ok"]):
            xs = raw.get((cpus, e, nb), [])
            if any(x["status"] in ("nb_crash", "nb_killed", "nb_memory") for x in xs):
                out["crash"].append(nb)
            elif any(x["status"] == "nb_timeout" or x["cell_status"].get("timeout") for x in xs):
                lb = float(np.median([x["orchestrator_wall_s"] if x["status"] == "nb_timeout" else x["cell_wall_s"]
                                      for x in xs])) if xs else None
                rm = ref.get(nb, {}).get("median_s") if ref.get(nb, {}).get("all_ok") else None
                out["timeout"].append({"nb": nb, "engine_time_lower_bound_s": r6(lb), "ref_median_s": r6(rm),
                                       "speedup_upper_bound": r6(rm / lb) if rm and lb else None})
            elif any(x["cell_status"].get("error") for x in xs):
                out["error_cells"].append(nb)
            else:
                out["other"].append(nb)
        return out

    by = collections.defaultdict(dict)
    for r in rows:
        by[(r["cpus"], r["engine"])][r["nb"]] = r
    for cpus in sorted({r["cpus"] for r in rows}):
        ref, ref_cpus = by.get((cpus, "ref"), {}), cpus
        if not ref and cpus != "8":
            ref, ref_cpus = by.get(("8", "ref"), {}), "8"   # ref is single-threaded: its cpus=8 times serve every budget
        res = {}
        for (c2, e), d in sorted(by.items()):
            if c2 != cpus or e == "ref":
                continue
            both = sorted(nb for nb in d if nb in ref and d[nb]["all_ok"] and ref[nb]["all_ok"]
                          and d[nb]["median_s"] > 0 and ref[nb]["median_s"] > 0)
            lr = np.array([np.log(ref[nb]["median_s"] / d[nb]["median_s"]) for nb in both])
            g = {"notebooks_timed": len(d), "notebooks_both_ok": len(both),
                 "notebooks_not_ok": sorted(nb for nb in d if not d[nb]["all_ok"]), "ref_cpus": ref_cpus,
                 "not_ok_by_reason": not_ok_reasons(cpus, e, d, ref)}
            if len(lr):
                idx = rng_for("timing|%s|%s" % (cpus, e)).integers(0, len(lr), size=(N_BOOT, len(lr)))
                bm = np.exp(lr[idx].mean(axis=1))
                g["geomean_speedup_vs_ref"] = r6(np.exp(lr.mean()))
                g["ci95"] = [r6(np.percentile(bm, 2.5)), r6(np.percentile(bm, 97.5))]
                g["total_time_ratio_ref_over_engine"] = r6(sum(ref[nb]["median_s"] for nb in both) /
                                                           sum(d[nb]["median_s"] for nb in both))
            covd = [nb for nb in both if cov.get((cpus, e, nb)) and cov.get((ref_cpus, "ref", nb))]
            g["load"] = {"pairs_with_load_on_both_runs": len(covd),
                         "engine_load1_median": r6(np.median([np.median(load[(cpus, e, nb)]) for nb in covd]))
                         if covd else None,
                         "ref_load1_median": r6(np.median([np.median(load[(ref_cpus, "ref", nb)]) for nb in covd]))
                         if covd else None,
                         "geomean_speedup_vs_ref_load_covered": r6(np.exp(np.mean(
                             [np.log(ref[nb]["median_s"] / d[nb]["median_s"]) for nb in covd]))) if covd else None}
            res[e] = g
        out["by_cpus"][cpus] = res
    # reference drift: ref is single-threaded, so its cpus=default run (timing_default) re-measures the same
    # configuration as its cpus=8 runs at a later time (with host load recorded); the ratio shows how much the
    # reference time moved between the two measurement periods (host contention, thermal state, caches)
    r8, rd = by.get(("8", "ref"), {}), by.get(("default", "ref"), {})
    common = sorted(nb for nb in rd if nb in r8 and rd[nb]["all_ok"] and r8[nb]["all_ok"]
                    and rd[nb]["median_s"] > 0 and r8[nb]["median_s"] > 0)
    rat = [rd[nb]["median_s"] / r8[nb]["median_s"] for nb in common]
    big = [rd[nb]["median_s"] / r8[nb]["median_s"] for nb in common if r8[nb]["median_s"] >= 1.0]
    out["ref_drift_default_over_8"] = {
        "notebooks": len(common), "notebooks_ref_ge_1s": len(big),
        "ratio_median": r6(np.median(rat)) if rat else None,
        "ratio_p25_p75": [r6(np.percentile(rat, 25)), r6(np.percentile(rat, 75))] if rat else None,
        "ratio_median_ref_ge_1s": r6(np.median(big)) if big else None,
        "ratio_min_max": [r6(min(rat)), r6(max(rat))] if rat else None}
    return out


def subset_shares(outs, label, nb_subset, key, view="all"):
    nbs = sorted([s for (l, nb, _), s in outs.items() if l == label and nb in nb_subset], key=lambda s: s["nb"])
    return bootstrap_shares([s["counts"][view] for s in nbs], key) if nbs else None


# ----------------------------------------------------------------------------------------------
# host-load covariate of timing runs (prepared 2026-10-05; runs/host_load.jsonl exists since 2026-10-05 02:32Z)

HOST_LOAD_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runs", "host_load.jsonl")
LOAD_AFTER_S = 75.0     # window end after a run: the sampler writes every 60-62 s (measured 2026-10-05), so every
                        # run, even a 1 s one, gets at least one 1-minute load average from its own minute
LOAD_EDGE_S = 90.0      # coverage: a sample within 90 s before the start and one within 90 s after the end
LOAD_MAX_GAP_S = 150.0  # coverage: no gap between consecutive samples longer than this around the run


def load_host_samples(path):
    """[(epoch_s, load1, load5, cores)] sorted by time; [] when the file is absent."""
    out = []
    try:
        f = open(path)
    except OSError:
        return out
    with f:
        for line in f:
            try:
                d = json.loads(line)
                t = datetime.datetime.strptime(d["utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=datetime.timezone.utc).timestamp()
                out.append((t, float(d["loadavg"][0]), float(d["loadavg"][1]), int(d.get("cores") or 0)))
            except (ValueError, KeyError, TypeError, IndexError):
                continue
    out.sort()
    return out


def join_host_load(rec, samples):
    """Host-load covariate of one timing record. The run interval is [started, finished] from the record; a
    record salvaged after a crash has neither, so its end is the file mtime and its start end - orchestrator
    wall time. Load = 1-minute load averages sampled in [start, end + LOAD_AFTER_S]."""
    fin, st, src = rec.get("finished"), rec.get("started"), "record"
    if not fin or not st:
        fin = rec.get("mtime")
        st = fin - (rec.get("orchestrator_wall_s") or 0.0) if fin else None
        src = "file_mtime_minus_orchestrator_wall"
    row = {"start": r6(st), "end": r6(fin), "times_from": src, "covered": False, "n_samples": 0,
           "load1_mean": None, "load1_max": None, "load5_at_end": None, "cores": None}
    if st is None or not samples:
        return row
    ts = [s[0] for s in samples]
    win = [s for s in samples if st <= s[0] <= fin + LOAD_AFTER_S]
    around = [t for t in ts if st - LOAD_EDGE_S <= t <= fin + LOAD_EDGE_S]
    gaps = [b - a for a, b in zip(around, around[1:])]
    covered = (bool(win) and any(st - LOAD_EDGE_S <= t <= st for t in ts) and any(fin <= t <= fin + LOAD_EDGE_S
                                                                                   for t in ts)
               and (max(gaps) if gaps else 0.0) <= LOAD_MAX_GAP_S)
    if win:
        end_s = min((s for s in samples if s[0] >= fin), key=lambda s: s[0], default=win[-1])
        row.update(n_samples=len(win), load1_mean=r6(np.mean([s[1] for s in win])),
                   load1_max=r6(max(s[1] for s in win)), load5_at_end=r6(end_s[2]), cores=win[-1][3])
    row["covered"] = bool(covered)
    return row


def timing_host_load(recs, samples, source):
    """Join every timing record with runs/host_load.jsonl; summaries per (cpus, engine)."""
    rows = []
    for s in sorted(recs, key=lambda x: (x["cpus"], x["engine"], x["nb"], x["rep"] or 0)):
        j = join_host_load(s, samples)
        rows.append(dict(j, engine=s["engine"], nb=s["nb"], rep=s["rep"], cpus=s["cpus"], status=s["status"],
                         all_ok=s["all_ok"]))
    out = {"source": source, "samples": len(samples),
           "first_sample_utc": (datetime.datetime.fromtimestamp(samples[0][0], datetime.timezone.utc)
                                .strftime("%Y-%m-%dT%H:%M:%SZ") if samples else None),
           "last_sample_utc": (datetime.datetime.fromtimestamp(samples[-1][0], datetime.timezone.utc)
                               .strftime("%Y-%m-%dT%H:%M:%SZ") if samples else None),
           "window": "1-minute load averages sampled in [start, end + %d s]; covered = a sample within %d s before "
                     "the start and within %d s after the end, no gap above %d s" % (LOAD_AFTER_S, LOAD_EDGE_S,
                                                                                    LOAD_EDGE_S, LOAD_MAX_GAP_S),
           "records": len(rows), "records_covered": sum(1 for r in rows if r["covered"]), "by_cpus_engine": {},
           "rows": rows}
    grp = collections.defaultdict(list)
    for r in rows:
        grp["%s|%s" % (r["cpus"], r["engine"])].append(r)
    for k, rs in sorted(grp.items()):
        cov = [r["load1_mean"] for r in rs if r["covered"]]
        ends = [r["end"] for r in rs if r["end"]]
        starts = [r["start"] for r in rs if r["start"]]
        out["by_cpus_engine"][k] = {
            "records": len(rs), "covered": len(cov),
            "first_start_utc": (datetime.datetime.fromtimestamp(min(starts), datetime.timezone.utc)
                                .strftime("%Y-%m-%dT%H:%M:%SZ") if starts else None),
            "last_end_utc": (datetime.datetime.fromtimestamp(max(ends), datetime.timezone.utc)
                             .strftime("%Y-%m-%dT%H:%M:%SZ") if ends else None),
            "load1_median": r6(np.median(cov)) if cov else None,
            "load1_p25": r6(np.percentile(cov, 25)) if cov else None,
            "load1_p75": r6(np.percentile(cov, 75)) if cov else None,
            "load1_max": r6(max(r["load1_max"] for r in rs if r["covered"])) if cov else None}
    return out


# ----------------------------------------------------------------------------------------------
# A11: paired common-cell view

def _reading(lo, hi):
    """A3 reading rule (fixed before the first run): interval contains 0 -> about as often."""
    if lo is None or hi is None:
        return None
    return "about as often" if lo <= 0 <= hi else ("more often" if lo > 0 else "less often")


def common_clean_view(all_outs, ready, n_boot=N_BOOT):
    """Cells clean at E2 (post-timeout cascades removed) under EVERY label of COMMON_LABELS.

    all_outs: {campaign: {(label, nb, scale): process_output(...)}} restricted to labels whose compare is
    complete; ready: {campaign: set of those labels}. Every label is scored on the same cells, so the
    DIFF-share differences are paired by cell; intervals come from one shared set of notebook resamples."""
    labels = [lab for _, lab in COMMON_LABELS]
    out = {"definition": "cells (notebook, cell index) in the clean_E2 view (post-timeout cascades removed) of every "
                         "label: " + ", ".join("%s:%s" % cl for cl in COMMON_LABELS),
           "labels": labels, "engines": list(COMMON_ENGINES), "baselines": list(COMMON_BASELINES),
           "bootstrap": {"resamples": n_boot, "unit": "notebook (only notebooks holding at least one common cell)",
                         "seed_marginal": "[SEED, crc32('common_clean_E2|<label>')]",
                         "seed_paired": [SEED, zlib.crc32(b"common_clean_E2|paired")],
                         "interval": "percentile 2.5/97.5 of the per-resample difference of pooled DIFF shares"},
           "reading_rule": "about as often: paired 95% interval of the DIFF-share difference contains 0; more often: "
                           "interval above 0; less often: interval below 0 (fixed 2026-10-05 before the first run)"}
    missing = ["%s:%s" % (c, l) for c, l in COMMON_LABELS if l not in (ready.get(c) or set())]
    if missing:
        out.update(status="pending", missing_labels=missing)
        return out
    per = collections.defaultdict(dict)                      # nb -> label -> processed output (1x only)
    for camp, lab in COMMON_LABELS:
        for (l, nb, sc), s in (all_outs.get(camp) or {}).items():
            if l == lab and sc in (None, 1, 1.0):
                per[nb][lab] = s
    excluded = collections.defaultdict(list)
    common = {}
    for nb in sorted(per):
        d = per[nb]
        if any(l not in d for l in labels):
            excluded["missing_label"].append(nb)
            continue
        refs = {(d[l]["ref_file"], d[l]["ref2_file"]) for l in labels}
        if len(refs) != 1 or None in next(iter(refs)):
            excluded["reference_or_replicate_record_differs"].append(nb)
            continue
        if len({d[l]["cell_ids"] for l in labels}) != 1:
            excluded["cell_list_differs"].append(nb)
            continue
        common[nb] = sorted(set.intersection(*(set(d[l]["clean_E2_cls"]) for l in labels)))
    nbs = [nb for nb in sorted(common) if common[nb]]
    sizes = [len(common[nb]) for nb in nbs]
    rows = {l: [collections.Counter(per[nb][l]["clean_E2_cls"][i] for i in common[nb]) for nb in nbs] for l in labels}
    out.update(status="complete", notebooks_compared=len(common), notebooks_with_common_cells=len(nbs),
               notebooks_excluded={k: len(v) for k, v in sorted(excluded.items())},
               notebooks_excluded_list={k: v for k, v in sorted(excluded.items())},
               cells=int(sum(sizes)),
               cells_per_notebook={"median": r6(np.median(sizes)) if sizes else None,
                                   "max": int(max(sizes)) if sizes else None,
                                   "largest_5_notebooks_share": r6(sum(sorted(sizes)[-5:]) / sum(sizes))
                                   if sizes else None},
               own_clean_E2_cells={l: sum(len(per[nb][l]["clean_E2_cls"]) for nb in common) for l in labels},
               per_label={l: bootstrap_shares(rows[l], "common_clean_E2|%s" % l, n_boot) for l in labels})
    if not nbs:
        return out
    n = len(nbs)
    tot = np.array(sizes, dtype=float)
    idx = rng_for("common_clean_E2|paired").integers(0, n, size=(n_boot, n))
    w = np.bincount((idx + np.arange(n_boot)[:, None] * n).ravel(), minlength=n_boot * n).reshape(n_boot, n)
    btot = w.astype(float) @ tot
    diff_cnt = {l: np.array([r.get("DIFF", 0) for r in rows[l]], dtype=float) for l in labels}
    bshare = {l: (w.astype(float) @ diff_cnt[l]) / btot for l in labels}
    N = float(tot.sum())
    for base in COMMON_BASELINES:
        res = {}
        for l in labels:
            if l == base:
                continue
            bd = bshare[l] - bshare[base]
            lo, hi = r6(np.percentile(bd, 2.5)), r6(np.percentile(bd, 97.5))
            res[l] = {"diff": r6((diff_cnt[l].sum() - diff_cnt[base].sum()) / N), "ci95": [lo, hi],
                      "diff_cells": int(diff_cnt[l].sum()), "base_diff_cells": int(diff_cnt[base].sum()),
                      "reading": _reading(lo, hi)}
        out["paired_DIFF_vs_" + base] = res
    return out


# ----------------------------------------------------------------------------------------------
# figures

COL = {"E0": "#08306b", "E1": "#2171b5", "E2": "#6baed6", "E3": "#a6cbe3", "E4": "#d4e4f2", "DIFF": "#E69F00",
       "UNCOMPARABLE": "#F0E442", "ERR": "#D55E00", "TIMEOUT": "#CC79A7", "CRASH": "#000000", "MEMORY": "#666666",
       "NOTRUN": "#bdbdbd"}
STACK = ["E0", "E1", "E2", "E3", "E4", "DIFF", "UNCOMPARABLE", "ERR", "TIMEOUT", "CRASH", "MEMORY", "NOTRUN"]
STACK_LABEL = {"UNCOMPARABLE": "UNCOMP.", "CRASH": "CRASH/KILLED"}
DARK = {"E0", "E1", "CRASH", "MEMORY", "ERR"}
ENG_COL = {"pyarrow_backend": "#0072B2", "modin": "#E69F00", "fireducks": "#009E73", "bodo": "#D55E00",
           "bodo_dw": "#CC79A7", "dask": "#56B4E9", "p15": "#000000", "p30": "#999999"}
ENG_LS = {"pyarrow_backend": "-", "modin": "--", "fireducks": "-.", "bodo": ":", "bodo_dw": (0, (5, 1, 1, 1)),
          "dask": (0, (3, 1, 1, 1, 1, 1))}
ENG_NAME = {"pyarrow_backend": "pandas+pyarrow", "modin": "Modin", "fireducks": "FireDucks", "bodo": "Bodo (1 worker)",
            "bodo_dw": "Bodo (default workers)", "dask": "Dask", "ref#2": "pandas 2.3.3 rerun", "ref": "pandas 2.3.3"}


def _mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    matplotlib.rcParams.update({"pdf.fonttype": 42, "ps.fonttype": 42, "font.size": 7, "axes.titlesize": 7,
                                "axes.labelsize": 7, "xtick.labelsize": 6.5, "ytick.labelsize": 6.5,
                                "legend.fontsize": 6.5, "hatch.linewidth": 0.6, "axes.linewidth": 0.6,
                                "font.family": "DejaVu Sans"})
    return plt


def _save(fig, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp%d.pdf" % os.getpid()
    fig.savefig(tmp, format="pdf", bbox_inches="tight", metadata={"CreationDate": None, "ModDate": None})
    os.replace(tmp, path)


def _top_layout(fig, plot_h, legend_in, title):
    """Reserve legend_in inches (plus 0.18 in for a title) above the axes; returns the legend anchor y."""
    title_in = 0.18 if title else 0.0
    H = plot_h + legend_in + title_in
    fig.set_size_inches(fig.get_size_inches()[0], H)
    fig.tight_layout(rect=[0, 0, 1, plot_h / H])
    if title:
        fig.suptitle(title, y=1 - 0.02 / H, va="top", fontsize=7)
    return 1 - title_in / H


def fig_conformance(path, camp, labels, title_suffix):
    plt = _mpl()
    from matplotlib.patches import Patch, Rectangle
    labels = [l for l in labels if l in camp["engines"]]
    h = 0.75 + 0.2 * len(labels)
    fig, axes = plt.subplots(1, 3, figsize=(7.0, h), sharey=True)
    for ax, v in zip(axes, VIEWS):
        for y, lab in enumerate(labels):
            e = camp["engines"][lab]
            vv = e["views"][v]
            n = vv["cells"]
            fbc = camp["_fallback_by_class"][lab][v]
            left = 0.0
            for k in STACK:
                cnt = vv["counts"].get(k, 0) + (vv["counts"].get("KILLED", 0) if k == "CRASH" else 0)
                if not n or not cnt:
                    continue
                w = 100.0 * cnt / n
                ax.barh(y, w, left=left, height=0.7, color=COL[k], edgecolor="white", linewidth=0.3)
                f = fbc.get(k, 0) + (fbc.get("KILLED", 0) if k == "CRASH" else 0)
                if f:
                    ax.add_patch(Rectangle((left, y - 0.35), 100.0 * f / n, 0.7, facecolor="none", linewidth=0,
                                           edgecolor="white" if k in DARK else "black", hatch="////"))
                left += w
            ax.text(101, y, "n=%d" % n, va="center", ha="left", fontsize=5.5, clip_on=False)
        ax.set_xlim(0, 100)
        ax.set_title(VIEW_TITLES[v])
        ax.set_xlabel("Share of cells (%)")
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels([ENG_NAME.get(l, l) for l in labels])
        ax.invert_yaxis()
        ax.tick_params(axis="y", length=0)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    handles = [Patch(facecolor=COL[k], edgecolor="white", label=STACK_LABEL.get(k, k)) for k in STACK]
    handles.append(Patch(facecolor="white", edgecolor="black", hatch="////", label="FALLBACK-flagged"))
    y = _top_layout(fig, h, 0.34, title_suffix)
    ncol = 7   # matplotlib fills legends column-first; reorder so that rows read E0..E4, DIFF, ...
    rows = [handles[i:i + ncol] for i in range(0, len(handles), ncol)]
    handles = [r[c] for c in range(ncol) for r in rows if c < len(r)]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, y), ncol=ncol, frameon=False,
               handlelength=1.2, columnspacing=0.8)
    _save(fig, path)
    plt.close(fig)


def fig_family(path, camp, labels, title_suffix):
    plt = _mpl()
    from matplotlib.colors import ListedColormap, BoundaryNorm
    labels = [l for l in labels if l in camp["families"]]
    fams = [f for f in FAMILIES if any(f in camp["families"][l] for l in labels)]
    lv_order = LEVELS + [">E4"]
    cat = np.full((len(fams), len(labels)), np.nan)
    e0 = np.full((len(fams), len(labels)), np.nan)
    ns = np.zeros((len(fams), len(labels)), dtype=int)
    for i, f in enumerate(fams):
        for j, l in enumerate(labels):
            d = camp["families"][l].get(f)
            if not d:
                continue
            ns[i, j] = d["cells"]
            if d["cells"] >= MIN_FAMILY_CELLS:
                cat[i, j] = lv_order.index(d["finest_level_majority"])
                e0[i, j] = 100.0 * d["share_E0"]
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 0.9 + 0.19 * len(fams)))
    cmap = ListedColormap([COL[L] for L in LEVELS] + [COL["DIFF"]]).with_extremes(bad="#eeeeee")
    norm = BoundaryNorm(np.arange(-0.5, 6.5, 1), cmap.N)
    ax = axes[0]
    ax.imshow(np.ma.masked_invalid(cat), cmap=cmap, norm=norm, aspect="auto")
    for i in range(len(fams)):
        for j in range(len(labels)):
            if np.isnan(cat[i, j]):
                ax.text(j, i, "n<%d" % MIN_FAMILY_CELLS if ns[i, j] else "", ha="center", va="center", fontsize=5,
                        color="#555555")
            else:
                k = int(cat[i, j])
                ax.text(j, i, lv_order[k], ha="center", va="center", fontsize=5.5,
                        color="white" if k in (0, 1) else "black")
    ax.set_title("Finest level reached by at least half of the cells")
    cm2 = plt.get_cmap("cividis").with_extremes(bad="#eeeeee")
    ax2 = axes[1]
    im = ax2.imshow(np.ma.masked_invalid(e0), cmap=cm2, vmin=0, vmax=100, aspect="auto")
    for i in range(len(fams)):
        for j in range(len(labels)):
            if not np.isnan(e0[i, j]):
                ax2.text(j, i, "%d" % round(e0[i, j]), ha="center", va="center", fontsize=5.5,
                         color="white" if e0[i, j] < 55 else "black")
    ax2.set_title("Bit-exact (E0) share of cells (%)")
    cb = fig.colorbar(im, ax=ax2, fraction=0.04, pad=0.02)
    cb.ax.tick_params(labelsize=5.5)
    for a in axes:
        a.set_xticks(range(len(labels)))
        a.set_xticklabels([ENG_NAME.get(l, l) for l in labels], rotation=35, ha="right")
        a.set_yticks(range(len(fams)))
        a.set_yticklabels(fams)
        a.set_ylabel("Operation family (from cell attribute names)")
        a.tick_params(length=0)
    axes[1].set_ylabel("")
    _top_layout(fig, 0.9 + 0.19 * len(fams), 0.0, title_suffix)
    _save(fig, path)
    plt.close(fig)


def fig_drift(path, camp, versions):
    plt = _mpl()
    labels = [l for l in ("p15", "ref#2", "p30") if l in camp["engines"]]
    metrics = [("<=E0", "bit-exact (E0)", COL["E0"]), ("<=E2", "conformant at E2", COL["E2"]),
               ("<=E3", "conformant at E3", COL["E3"]), ("ERR", "ERR", COL["ERR"])]
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.2), sharey=True)
    wbar = 0.2
    for ax, v in zip(axes, VIEWS):
        for j, (m, name, colr) in enumerate(metrics):
            xs, ys, lo, hi = [], [], [], []
            for i, l in enumerate(labels):
                vv = camp["engines"][l]["views"][v]
                if not vv["cells"]:
                    continue
                if m.startswith("<="):
                    s, ci = vv["cum_share"][m], vv["cum_ci95"][m]
                else:
                    s, ci = vv["share"][m], vv["ci95"][m]
                xs.append(i + (j - 1.5) * wbar)
                ys.append(100 * s)
                lo.append(100 * (s - ci[0]))
                hi.append(100 * (ci[1] - s))
            ax.bar(xs, ys, width=wbar, color=colr, edgecolor="black", linewidth=0.3, label=name)
            ax.errorbar(xs, ys, yerr=[lo, hi], fmt="none", ecolor="black", elinewidth=0.6, capsize=1.2)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(["%s\nn=%d" % (versions.get(l, l), camp["engines"][l]["views"][v]["cells"]) for l in labels],
                           fontsize=6)
        ax.set_xlabel("pandas version (vs. 2.3.3 reference)")
        ax.set_title(VIEW_TITLES[v])
        ax.set_ylim(0, 105)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes[0].set_ylabel("Share of cells (%)")
    h, l = axes[0].get_legend_handles_labels()
    y = _top_layout(fig, 2.2, 0.2, None)
    fig.legend(h, l, loc="upper center", bbox_to_anchor=(0.5, y), ncol=4, frameon=False)
    _save(fig, path)
    plt.close(fig)


def fig_first_divergence(path, camp, labels, title_suffix):
    plt = _mpl()
    labels = [l for l in labels if l in camp["engines"]]
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.1), sharey=True)
    for ax, L in zip(axes, ("E0", "E2", "E4")):
        for l in labels:
            per = camp["engines"][l]["first_divergence_per_notebook"]
            n = len(per)
            rel = sorted(h[L]["rel"] for h in per.values() if h[L] is not None)
            xs, ys = [0.0], [0.0]
            for k, x in enumerate(rel):          # step ECDF over ALL notebooks (plateau = never diverged)
                xs += [x, x]
                ys += [100.0 * k / n, 100.0 * (k + 1) / n]
            xs.append(1.0)
            ys.append(100.0 * len(rel) / n)
            ax.plot(xs, ys, color=ENG_COL.get(l, "black"), ls=ENG_LS.get(l, "-"), lw=1.2, label=ENG_NAME.get(l, l))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 100)
        ax.set_xlabel("Relative position of first divergent cell")
        ax.set_title("Divergence at %s (not equal at %s)" % (L, L))
        ax.grid(True, lw=0.3, color="#dddddd")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes[0].set_ylabel("Notebooks diverged by this point (%)")
    h, l = axes[0].get_legend_handles_labels()
    y = _top_layout(fig, 2.1, 0.2, title_suffix)
    fig.legend(h, l, loc="upper center", bbox_to_anchor=(0.5, y), ncol=len(labels), frameon=False)
    _save(fig, path)
    plt.close(fig)


def fig_speed(path, timing, conf_subset):
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(3.33, 2.4))
    for cpus, mk in (("8", "o"), ("default", "s")):
        for e, g in sorted((timing["by_cpus"].get(cpus) or {}).items()):
            c = conf_subset.get(e)
            if not c or "geomean_speedup_vs_ref" not in g or not c["cells"]:
                continue
            x, (xl, xh) = g["geomean_speedup_vs_ref"], g["ci95"]
            y, (yl, yh) = 100 * c["cum_share"]["<=E2"], [100 * t for t in c["cum_ci95"]["<=E2"]]
            ax.errorbar([x], [y], xerr=[[x - xl], [xh - x]], yerr=[[y - yl], [yh - y]], fmt=mk,
                        color=ENG_COL.get(e, "black"), mfc=ENG_COL.get(e, "black") if cpus == "8" else "white",
                        ms=4, elinewidth=0.6, capsize=1.5, label="%s (%s CPUs)" % (ENG_NAME.get(e, e), cpus))
    ax.axvline(1.0, color="#888888", lw=0.5, ls="--")
    ax.set_xscale("log")
    # plain-number ticks (the default 3x10^-1 style was unreadable in the 2026-10-05 dry run)
    from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter
    ax.xaxis.set_major_locator(LogLocator(base=10, subs=(1.0, 2.0, 3.0, 5.0)))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: "%g" % v))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_xlabel("Speed-up over pandas 2.3.3 (geometric mean, log scale)")
    ax.set_ylabel("Clean@E2 cells at E2 or finer (%)")
    ax.set_ylim(0, 100)
    ax.legend(loc="lower left", fontsize=5.5, frameon=False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    _save(fig, path)
    plt.close(fig)


# ----------------------------------------------------------------------------------------------
# report

def _pc(x):
    return "-" if x is None else "%.1f" % (100 * x)


def _pci(s, ci):
    if s is None:
        return "-"
    return "%.1f [%.1f, %.1f]" % (100 * s, 100 * ci[0], 100 * ci[1])


def write_markdown(paths, summary):
    L = []
    w = L.append
    w("# PandasConform: project-level analysis")
    w("")
    w("Generated %s by `analyze.py` (schema %d). Accepted tags: harness `%s`, compare `%s`. Every number below is "
      "read from `results/summary.json`, which is computed from the per-cell compare outputs and run records of "
      "those tags. Shares are pooled over cells; brackets are 95%% percentile bootstrap intervals over notebooks "
      "(%d resamples, seed %d combined with a per-series key)." % (summary["generated_utc"], SCHEMA_VERSION,
                                                                   HARNESS_TAG, COMPARE_TAG, N_BOOT, SEED))
    w("")
    w("## Campaign status")
    w("")
    w("| campaign | status | records found / expected | compare outputs found / expected | check n_problems |")
    w("|---|---|---|---|---|")
    for c, d in summary["campaigns"].items():
        rf = sum(g["records_found"] for g in d["groups"].values())
        re_ = sum(g["records_expected"] for g in d["groups"].values())
        cf = sum(g["compare_outputs_found"] for g in d["groups"].values())
        ce = sum(g["compare_outputs_expected"] for g in d["groups"].values())
        w("| %s%s | %s | %d / %d | %d / %d | %s |" % (c, " (PILOT, 10 notebooks)" if d["is_pilot"] else "", d["status"],
                                                     rf, re_, cf, ce, d["postprocessing"]["check_n_problems"]))
    w("")
    for c, d in summary["campaigns"].items():
        for gname, g in d["groups"].items():
            if g["status"] != "complete":
                w("- %s / %s: %s; markers %s." % (c, gname, g["status"],
                                                  ", ".join("%s=%s" % (k, "done" if v else "missing")
                                                            for k, v in g["markers"].items()) or "none"))
    w("")
    w("## Analysis rules applied here (aggregation layer, classify.py unchanged)")
    w("")
    for r in summary["method"]["rules"]:
        w("- " + r)
    w("")
    for c in ("drift", "pilot", "conf_1x", "conf_5x"):
        d = summary["campaigns"][c]
        if not d["engines"]:
            continue
        head = {"drift": "## RQ3: pandas version drift (drift campaign, 102 notebooks)",
                "pilot": "## PILOT (10 notebooks; pilot observations, not claims)",
                "conf_1x": "## RQ1: engine conformance (conf_1x)",
                "conf_5x": "## conf_5x (5x scale, %d of the %d conf5x notebooks%s)" % (
                    d["notebooks_expected"], d["notebooks_expected"] + len(d.get("notebooks_excluded", {})),
                    "; not run: " + "; ".join("%s (%s)" % kv for kv in sorted(d.get("notebooks_excluded", {}).items()))
                    if d.get("notebooks_excluded") else "")}[c]
        w(head)
        w("")
        for v in VIEWS:
            w("**%s.** Share of cells (%%) per class." % VIEW_TITLES[v])
            w("")
            w("| config | notebooks | cells | E0 | <=E2 | <=E4 | DIFF | ERR | TIMEOUT | CRASH | MEMORY | NOTRUN | UNCOMP. |")
            w("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
            for lab, e in d["engines"].items():
                vv = e["views"][v]
                if not vv["cells"]:
                    w("| %s | %d | 0 | | | | | | | | | | |" % (lab, vv["notebooks"]))
                    continue
                w("| %s | %d | %d | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                    lab, vv["notebooks"], vv["cells"], _pci(vv["share"]["E0"], vv["ci95"]["E0"]),
                    _pci(vv["cum_share"]["<=E2"], vv["cum_ci95"]["<=E2"]),
                    _pci(vv["cum_share"]["<=E4"], vv["cum_ci95"]["<=E4"]),
                    _pci(vv["share"]["DIFF"], vv["ci95"]["DIFF"]), _pci(vv["share"]["ERR"], vv["ci95"]["ERR"]),
                    _pc(vv["share"]["TIMEOUT"]), _pc(vv["share"]["CRASH"] + vv["share"]["KILLED"]),
                    _pc(vv["share"]["MEMORY"]), _pc(vv["share"]["NOTRUN"]), _pc(vv["share"]["UNCOMPARABLE"])))
            w("")
        w("**Failures, fallbacks, exclusions and cascades.**")
        w("")
        w("| config | records by status | ERR / TIMEOUT / CRASH / MEMORY / NOTRUN cells | FALLBACK cells (all / strict / @E2) | "
          "excluded REF_ERR / NONDET / NOOUT / SETUP_ERR | post-timeout cascade cells (removed strict / @E2) |")
        w("|---|---|---|---|---|---|")
        rs = d["run_records"]
        for lab, e in d["engines"].items():
            eng = lab.split("~vs~")[0]
            rec = rs.get(eng, {}).get("by_status", {}) if "~vs~" not in lab else {}
            fc, fb, ex, pc = e["failure_cells"], e["fallback"]["cells"], e["excluded_cells"], e["post_timeout_cascade"]
            w("| %s | %s | %d / %d / %d / %d / %d | %d / %d / %d | %d / %d / %d / %d | %d (%d / %d) |" % (
                lab, ", ".join("%s %d" % kv for kv in rec.items()) or "-", fc["ERR"], fc["TIMEOUT"],
                fc["CRASH"] + fc["KILLED"], fc["MEMORY"], fc["NOTRUN"], fb["all"], fb["clean_strict"], fb["clean_E2"],
                ex.get("REF_ERR", 0), ex.get("NONDET", 0), ex.get("NOOUT", 0), ex.get("SETUP_ERR", 0), pc["cells"],
                pc["removed_from_clean_strict"], pc["removed_from_clean_E2"]))
        w("")
        w("**First divergence per notebook** (share of notebooks with a divergent cell; median relative position).")
        w("")
        w("| config | at E0 | at E2 | at E4 | median rel. position at E0 / E2 / E4 |")
        w("|---|---|---|---|---|")
        for lab, e in d["engines"].items():
            fd = e["first_divergence"]
            w("| %s | %s | %s | %s | %s |" % (
                lab, _pci(fd["E0"]["share_diverged"], fd["E0"]["share_diverged_ci95"]),
                _pci(fd["E2"]["share_diverged"], fd["E2"]["share_diverged_ci95"]),
                _pci(fd["E4"]["share_diverged"], fd["E4"]["share_diverged_ci95"]),
                " / ".join("%.2f" % fd[x]["rel_position_quantiles"]["p50"] if fd[x]["rel_position_quantiles"] else "-"
                           for x in ("E0", "E2", "E4"))))
        w("")
        w("**Operation family x configuration** (clean at E2, post-timeout cascades removed): finest level reached by at "
          "least half of the cells, with the number of cells.")
        w("")
        labs = list(d["families"])
        w("| family | " + " | ".join(labs) + " |")
        w("|---|" + "---|" * len(labs))
        for f in FAMILIES:
            if not any(f in d["families"][l] for l in labs):
                continue
            w("| %s | %s |" % (f, " | ".join("%s (%d)" % (d["families"][l][f]["finest_level_majority"],
                                                         d["families"][l][f]["cells"]) if f in d["families"][l] else "-"
                                             for l in labs)))
        w("")
        xc = d["crosscheck"]
        w("Cross-check against `%s`: %d checks, %d mismatches." % (xc.get("analysis_file"), xc["n_checks"],
                                                                   xc["n_mismatch"]))
        for m in xc["mismatches"][:10]:
            w("- MISMATCH %s: file %s, recomputed %s" % (m["check"], m["file_value"], m["recomputed"]))
        w("")
    cc = summary.get("common_clean_E2") or {}
    w("## A11: paired common-cell view (clean at E2 under all five core engines and both pandas versions)")
    w("")
    if cc.get("status") != "complete":
        w("Status: %s (missing compare labels: %s)." % (cc.get("status"), ", ".join(cc.get("missing_labels") or [])
                                                         or "-"))
    else:
        w("Population: %s. Notebooks compared %d, with at least one common cell %d; excluded %s. Common cells: %d "
          "(median %s per notebook, at most %d; the 5 largest notebooks hold %.1f%%). Each label's own clean-at-E2 "
          "cells in the compared notebooks: %s." % (
              cc["definition"], cc["notebooks_compared"], cc["notebooks_with_common_cells"],
              cc["notebooks_excluded"] or "none", cc["cells"], cc["cells_per_notebook"]["median"],
              cc["cells_per_notebook"]["max"] or 0, 100 * (cc["cells_per_notebook"]["largest_5_notebooks_share"] or 0),
              ", ".join("%s %d" % kv for kv in cc["own_clean_E2_cells"].items())))
        w("")
        w("Reading rule: %s. Intervals of the differences use one shared set of %d notebook resamples (paired by "
          "cell and notebook)." % (cc["reading_rule"], cc["bootstrap"]["resamples"]))
        w("")
        w("| label | cells | DIFF cells | DIFF %% [95%% CI] | ERR %% | <=E2 %% | DIFF diff vs p30 (pp) [paired 95%% CI] | "
          "reading | DIFF diff vs p15 (pp) [paired 95%% CI] | reading |")
        w("|---|---|---|---|---|---|---|---|---|---|")
        for lab in cc["labels"]:
            v = cc["per_label"][lab]
            cols = []
            for base in ("p30", "p15"):
                p = (cc.get("paired_DIFF_vs_" + base) or {}).get(lab)
                cols += (["%+.1f [%+.1f, %+.1f]" % (100 * p["diff"], 100 * p["ci95"][0], 100 * p["ci95"][1]),
                          p["reading"]] if p else ["(baseline)", "-"])
            w("| %s | %d | %d | %s | %s | %s | %s |" % (
                lab, v["cells"], v["counts"]["DIFF"], _pci(v["share"].get("DIFF"), v["ci95"].get("DIFF", [0, 0])),
                _pc(v["share"].get("ERR")), _pc(v["cum_share"].get("<=E2")), " | ".join(cols)))
        w("")
    w("## nb_timeout records (all campaigns)")
    w("")
    w("Rule (ledger 2026-10-03): summed cell `wall_s` below 3,600 s means capture-inflated, never engine slowness. "
      "The last two columns split the remaining time between capture and time outside the recorded cells (e.g. an "
      "in-flight cell blocked in native code that the record does not contain).")
    w("")
    w("| campaign | engine | notebook | cells in record | cell wall_s | capture s | outside recorded cells s | "
      "capture-inflated (rule) | larger share |")
    w("|---|---|---|---|---|---|---|---|---|")
    for c, d in summary["campaigns"].items():
        for r in d["nb_timeouts"]:
            w("| %s | %s | %s | %d | %.1f | %.1f | %.1f | %s | %s |" % (c, r["engine"], r["nb"], r["cells_in_record"],
                                                                      r["cell_wall_s"], r["capture_s"],
                                                                      r["not_in_recorded_cells_s"],
                                                                      "yes" if r["capture_inflated"] else "no",
                                                                      r["larger_share"]))
    w("")
    w("## Run records per configuration (all campaigns, incl. partial ones)")
    w("")
    w("| campaign | config | records | by status | pandas | peak tree RSS GB | fallback-flagged cells |")
    w("|---|---|---|---|---|---|---|")
    for c, d in summary["campaigns"].items():
        for e, g in d["run_records"].items():
            w("| %s | %s | %d | %s | %s | %.1f | %d |" % (c, e, g["records"], ", ".join("%s %d" % kv for kv in
                                                                                       g["by_status"].items()),
                                                      ",".join(g["pandas"]), g["peak_tree_rss_gb"] or 0,
                                                      g["fallback_flagged_cells"]))
    w("")
    w("## RQ4: speed versus conformance")
    w("")
    t = summary["timing"]
    if not t["by_cpus"]:
        w("Timing campaign status: %s. Figure 4 is written once timing and conf_1x are complete." % t["status"])
    else:
        w("Source: %s (status %s).%s" % (t["source"], t["status"], "" if t["status"] == "complete" else
                                         " **The timing campaign is not complete: these rows are interim "
                                         "numbers, not results.**"))
        w("")
        w("| cpus | engine | notebooks both ok | geomean speed-up vs ref [95%] | not ok (crash / timeout / error "
          "cells / other) | pairs with host load on both runs |")
        w("|---|---|---|---|---|---|")
        for cpus, res in t["by_cpus"].items():
            for e, g in res.items():
                rs = g["not_ok_by_reason"]
                w("| %s | %s | %d | %s | %d (%d / %d / %d / %d) | %d |" % (
                    cpus, e, g["notebooks_both_ok"],
                    "%.2f [%.2f, %.2f]" % (g["geomean_speedup_vs_ref"], *g["ci95"]) if "ci95" in g else "-",
                    len(g["notebooks_not_ok"]), len(rs["crash"]), len(rs["timeout"]), len(rs["error_cells"]),
                    len(rs["other"]), g["load"]["pairs_with_load_on_both_runs"]))
        w("")
        rdr = t.get("ref_drift_default_over_8") or {}
        if rdr.get("notebooks"):
            w("Reference drift (ref at cpus=default over ref at cpus=8, same single-threaded configuration measured "
              "in two periods): median ratio %s, IQR %s, min/max %s over %d notebooks (%s for the %d notebooks with a "
              "reference time of at least 1 s)." % (rdr["ratio_median"], rdr["ratio_p25_p75"], rdr["ratio_min_max"],
                                                    rdr["notebooks"], rdr["ratio_median_ref_ge_1s"],
                                                    rdr["notebooks_ref_ge_1s"]))
            w("")
        for cpus, res in t["by_cpus"].items():
            for e, g in res.items():
                for x in g["not_ok_by_reason"]["timeout"]:
                    w("- censored slowdown (%s CPUs, %s, %s): engine observed for at least %s s, reference median %s s"
                      ", so speed-up at most %s." % (cpus, e, x["nb"], x["engine_time_lower_bound_s"],
                                                     x["ref_median_s"], x["speedup_upper_bound"]))
    w("")
    if t.get("failures"):
        w("**Timing failures** (records by status; non-ok cells by status; notebooks affected).")
        w("")
        w("| cpus / engine | records by status | non-ok cells | notebooks with error / timeout cells / crash or "
          "notebook timeout |")
        w("|---|---|---|---|")
        for k, g in t["failures"].items():
            w("| %s | %s | %s | %d / %d / %d |" % (k, ", ".join("%s %d" % kv for kv in g["records_by_status"].items()),
                                                  ", ".join("%s %d" % kv for kv in g["cells_by_status"].items()) or "-",
                                                  g["notebooks_with_error_cells"], g["notebooks_with_timeout_cells"],
                                                  g["notebooks_with_crash_or_nb_timeout"]))
        w("")
    hl = t.get("host_load") or {}
    if hl.get("records"):
        w("**Host load** (`%s`, %d samples, %s to %s; %s). Records covered: %d of %d." % (
            hl["source"], hl["samples"], hl["first_sample_utc"], hl["last_sample_utc"], hl["window"],
            hl["records_covered"], hl["records"]))
        w("")
        w("| cpus / engine | records | covered | runs from (UTC) | to (UTC) | load1 median [p25, p75] | load1 max |")
        w("|---|---|---|---|---|---|---|")
        for k, g in hl["by_cpus_engine"].items():
            w("| %s | %d | %d | %s | %s | %s | %s |" % (
                k, g["records"], g["covered"], g["first_start_utc"], g["last_end_utc"],
                "%.1f [%.1f, %.1f]" % (g["load1_median"], g["load1_p25"], g["load1_p75"])
                if g["load1_median"] is not None else "-", "%.1f" % g["load1_max"] if g["load1_max"] is not None else "-"))
        w("")
    ct = t.get("conformance_on_timing30_clean_E2") or {}
    if ct:
        w("Conformance coordinate of Figure 4 (%s view, timing30 notebooks; engine-specific cell sets, A11): %s." % (
            t.get("fig4_conformance_view"), "; ".join("%s %s of %d cells" % (
                e, _pci(v["cum_share_le_E2"], v["cum_ci95_le_E2"]), v["cells"]) for e, v in ct.items() if v)))
        w("")
    if summary["scale_effect"]:
        w("## Scale effect (conf_5x notebooks at 1x vs 5x, all comparable cells)")
        w("")
        w("| engine | 1x E0 | 5x E0 | 1x <=E2 | 5x <=E2 | 1x DIFF | 5x DIFF |")
        w("|---|---|---|---|---|---|---|")
        for e, d in summary["scale_effect"].items():
            a, b = d["1x"], d["5x"]
            w("| %s | %s | %s | %s | %s | %s | %s |" % (e, _pc(a["share"]["E0"]), _pc(b["share"]["E0"]),
                                                       _pc(a["cum_share"]["<=E2"]), _pc(b["cum_share"]["<=E2"]),
                                                       _pc(a["share"]["DIFF"]), _pc(b["share"]["DIFF"])))
        w("")
    w("## Ledger cross-check")
    w("")
    lc = summary["ledger_crosscheck"]
    w("%d numbers stated in plan.md's Ledger (drift and pilot) were recomputed from the compare outputs at the ledger's "
      "precision (percent with one decimal, round half up; counts exact): %d mismatches." % (lc["n_checks"],
                                                                                             lc["n_mismatch"]))
    for m in lc["mismatches"]:
        w("- MISMATCH plan.md line %d: %s %s %s %s: ledger %s, recomputed %s%s" % (
            m["plan_line"], m["campaign"], m["label"], m["view"], m["metric"], m["value"], m["recomputed"],
            " (%s)" % m["note"] if m["note"] else ""))
    w("")
    w("## Figures")
    w("")
    for name, f in summary["figures"].items():
        w("- `%s`: %s%s" % (name, f["status"], " (%s)" % f["note"] if f.get("note") else ""))
    w("")
    w("## Caveats")
    w("")
    for cv in summary["method"]["caveats"]:
        w("- " + cv)
    w("")
    w("## Excluded inputs")
    w("")
    for x in summary["excluded_inputs"]:
        w("- `%s`: %s" % (x["path"], x["reason"]))
    w("")
    atomic_write(os.path.join(paths.results, "analysis.md"), "\n".join(L))


# ----------------------------------------------------------------------------------------------
# main

def analyze(root, figures=True, host_load=None):
    """host_load: path of the per-minute host-load log (default HOST_LOAD_FILE, i.e. <repo>/runs/host_load.jsonl)."""
    t0 = time.time()
    paths = Paths(root)
    done = set(markers(paths))
    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "accepted_tags": {"harness": HARNESS_TAG, "compare": COMPARE_TAG},
        "batch_markers_done": sorted(done),
        "method": {
            "bootstrap": {"resamples": N_BOOT, "seed": SEED, "unit": "notebook", "interval": "percentile 2.5/97.5",
                          "estimator": "pooled cell share", "per_series_seed": "[SEED, crc32('<campaign>|<label>|<view>')]"},
            "views": {"all": "comparable cells (all classes except REF_ERR, NONDET, NOOUT, SETUP_ERR)",
                      "clean_strict": "comparable, clean_input (every input E0-equal), minus post-timeout cascades",
                      "clean_E2": "comparable, clean_level in E0..E2, minus post-timeout cascades",
                      "common_clean_E2": "A11 (2026-10-05): cells in the clean_E2 view of all five core conf_1x "
                                         "engines and both drift pandas versions (same cells for every label; "
                                         "summary key common_clean_E2)"},
            "rules": [
                "REF_ERR, NONDET (ref vs ref#2) and NOOUT cells are excluded from every view; SETUP_ERR cells are "
                "excluded and counted per engine.",
                "Cells after the first engine TIMEOUT cell of a notebook are post-timeout cascades: counted separately "
                "and excluded from the strict and clean-at-E2 views (the all-comparable view keeps them, so that it "
                "equals the per-campaign analysis).",
                "nb_timeout records with summed cell wall_s below 3,600 s are capture-inflated and never engine "
                "slowness results.",
                "CRASH/KILLED, MEMORY, TIMEOUT, NOTRUN and ERR cells and nb_crash/nb_memory/nb_timeout records are "
                "counted per engine; FALLBACK flags are counted per view.",
                "Operation families are the per-cell `families` recorded by classify (attribute names in the cell's "
                "AST); 'finest level reached' = finest L with at least half of the cells conformant at <= L."],
            "caveats": [
                "The pilot covers 10 notebooks and is a pilot, not a claim.",
                "Operation families come from attribute names only (e.g. any `.str`/`.dt` access, `.size`, `.agg`); "
                "a cell can count in several families, and function calls such as pd.merge(...) count only through "
                "their attribute name.",
                "The capture-inflated rule uses recorded cell time only; a notebook can reach the 3,600 s limit "
                "through an in-flight cell the record does not contain (native hang), which the rule also labels "
                "capture-inflated. The nb_timeout table splits that time for this reason.",
                "Shares pool cells across notebooks, so notebooks with many cells weigh more; the bootstrap resamples "
                "notebooks to reflect that clustering.",
                "Engines are converted to pandas with their own conversion before comparison (plan Section 2 "
                "confound); capture forces materialisation of lazy engines."]},
        "campaigns": {},
    }
    all_outs, ready_by_camp = {}, {}
    for camp, spec in CAMPAIGNS.items():
        recs, unread_r = load_run_records(paths, camp, spec["mode"])
        outs, n_files, unread_c = select_compare_outputs(paths, camp) if spec["mode"] == "capture" else ({}, 0, 0)
        status, groups, nexp = campaign_status(paths, camp, spec, recs, outs, done)
        ready = set()
        for g in groups.values():
            if g["compare_complete"]:
                ready.update(g["labels"])
        ready_by_camp[camp] = ready
        pending_labels = sorted({k[0] for k in outs} - ready)
        by_label = collections.defaultdict(list)
        for (lab, nb, sc), s in outs.items():
            if lab in ready:
                by_label[lab].append(s)
        order = [l for g in spec["groups"] for l in g["compare_labels"]]
        engines = {lab: aggregate_label(camp, lab, by_label[lab]) for lab in order if lab in by_label}
        fams = {lab: family_matrix(by_label[lab]) for lab in engines}
        used = {k: v for k, v in outs.items() if k[0] in ready}
        all_outs[camp] = used
        d = {"status": status, "is_pilot": spec["is_pilot"], "notebook_set": spec["set"], "notebooks_expected": nexp,
             "groups": groups, "postprocessing": postprocessing_files(paths, camp),
             "run_records": record_stats(recs), "run_records_unreadable": unread_r,
             "compare_outputs": {"files": n_files, "selected": len(outs), "superseded": n_files - len(outs),
                                 "unreadable": unread_c, "labels_pending_compare": pending_labels},
             "cells_in_selected_outputs": sum(s["n_cells"] for s in used.values()),
             "nb_timeouts": nb_timeout_rows(recs), "engines": engines, "families": fams}
        if spec.get("excluded"):
            d["notebooks_excluded"] = dict(spec["excluded"])
        d["crosscheck"] = crosscheck_campaign(paths, camp, engines, used) if engines else {
            "analysis_file": None, "summary_file": None, "n_checks": 0, "n_mismatch": 0, "mismatches": [],
            "note": "no analysed labels yet"}
        d["_fallback_by_class"] = {lab: {v: dict(sum((s["fallback"][v] for s in by_label[lab]), collections.Counter()))
                                         for v in VIEWS} for lab in engines}
        summary["campaigns"][camp] = d
        if camp == "timing":
            d["_recs"] = recs
    summary["ledger_crosscheck"] = crosscheck_ledger(summary["campaigns"])

    # timing / RQ4
    tim = summary["campaigns"]["timing"]
    conf = summary["campaigns"]["conf_1x"]
    trecs = tim.pop("_recs")
    hl_path = host_load if host_load is not None else HOST_LOAD_FILE
    hl = timing_host_load(trecs, load_host_samples(hl_path),
                          os.path.relpath(os.path.abspath(hl_path), os.path.dirname(os.path.dirname(HOST_LOAD_FILE))))
    summary["timing"] = timing_analysis(paths, trecs, tim["status"], conf, hl)
    summary["timing"]["host_load"] = hl
    t30 = set(notebook_set(paths, "timing30"))

    def t30_shares(view):
        sub = {e: subset_shares(all_outs["conf_1x"], e, t30, "conf_1x|%s|timing30|%s" % (e, view), view=view)
               for e in conf["engines"]} if conf["engines"] else {}
        return sub, {e: ({"cells": s["cells"], "notebooks": s["notebooks"], "cum_share_le_E2": s["cum_share"].get("<=E2"),
                          "cum_ci95_le_E2": s["cum_ci95"].get("<=E2")} if s else None) for e, s in sub.items()}

    _, summary["timing"]["conformance_on_timing30"] = t30_shares("all")
    conf_subset, summary["timing"]["conformance_on_timing30_clean_E2"] = t30_shares("clean_E2")
    # Figure 4's conformance coordinate is the clean@E2 view (as paper Section 9 states; fixed 2026-10-05 by the
    # F2 dry run, the code had used all comparable cells); it is over engine-specific cell sets (A11).
    summary["timing"]["fig4_conformance_view"] = "clean_E2"
    # scale effect (conf_5x vs conf_1x on the conf5x notebooks)
    summary["scale_effect"] = {}
    c5 = summary["campaigns"]["conf_5x"]
    if c5["engines"] and conf["engines"]:
        s30 = set(notebook_set(paths, "conf5x")) - set(CAMPAIGNS["conf_5x"].get("excluded", {}))
        for e in c5["engines"]:
            if e in conf["engines"] and e != "ref#2":
                a = subset_shares(all_outs["conf_1x"], e, s30, "conf_1x|%s|conf5x|all" % e)
                b = c5["engines"][e]["views"]["all"]
                if a:
                    summary["scale_effect"][e] = {"1x": {k: a[k] for k in ("cells", "notebooks", "share", "ci95",
                                                                           "cum_share", "cum_ci95")},
                                                  "5x": {k: b[k] for k in ("cells", "notebooks", "share", "ci95",
                                                                           "cum_share", "cum_ci95")}}
    # A11: paired common-cell view (conf_1x core engines and drift pandas versions on the same cells)
    summary["common_clean_E2"] = common_clean_view(all_outs, ready_by_camp)
    summary["excluded_inputs"] = excluded_inputs(paths)

    # figures
    figs = {}
    fdir = paths.figures

    def make(name, fn, *args, note=None):
        p = os.path.join(fdir, name)
        if not figures:
            figs[name] = {"status": "skipped (--no-figures)", "path": paths.rel(p), "note": note}
            return
        try:
            fn(p, *args)
            figs[name] = {"status": "written", "path": paths.rel(p), "note": note}
        except Exception as ex:  # a figure failure is recorded, never hidden
            figs[name] = {"status": "error: %s: %s" % (type(ex).__name__, str(ex)[:200]), "path": paths.rel(p),
                          "note": note}

    def pending(name, why):
        figs[name] = {"status": "pending", "path": paths.rel(os.path.join(fdir, name)), "note": why}

    drift = summary["campaigns"]["drift"]
    if drift["status"] == "complete" and drift["engines"]:
        versions = {}
        for lab in ("p15", "p30", "ref#2"):
            pv = drift["run_records"].get(lab, {}).get("pandas") or []
            versions[lab] = "/".join(pv) + (" rerun" if lab == "ref#2" else "")
        make("fig3_drift.pdf", fig_drift, drift, versions)
    else:
        pending("fig3_drift.pdf", "drift campaign not complete")
    conf_ready = conf["groups"]["conf1x_core"]["compare_complete"] and conf["engines"]
    pilot = summary["campaigns"]["pilot"]
    ptitle = "PILOT: 10 notebooks (pilot observations, not claims)"
    if pilot["status"] == "complete":
        make("fig1_conformance_by_engine_pilot.pdf", fig_conformance, pilot, CONF_ENGINES, ptitle)
        make("fig2_opfamily_heatmap_pilot.pdf", fig_family, pilot, CONF_ENGINES, ptitle)
        make("fig5_first_divergence_pilot.pdf", fig_first_divergence, pilot, CONF_ENGINES, ptitle)
    for name, fn in (("fig1_conformance_by_engine.pdf", fig_conformance), ("fig2_opfamily_heatmap.pdf", fig_family),
                     ("fig5_first_divergence.pdf", fig_first_divergence)):
        if conf_ready:
            make(name, fn, conf, CONF_ENGINES, None,
                 note=None if conf["status"] == "complete" else "conf_1x core compare complete; campaign status %s"
                 % conf["status"])
        else:
            pending(name, "conf_1x compare (step conf1x_compare) not complete")
    tready = summary["timing"]["status"] == "complete" and summary["timing"]["by_cpus"] and conf_ready
    if tready:
        make("fig4_speed_vs_conformance.pdf", fig_speed, summary["timing"], conf_subset)
    else:
        pending("fig4_speed_vs_conformance.pdf", "needs complete timing campaign and conf_1x compare")
    summary["figures"] = figs
    for d in summary["campaigns"].values():
        d.pop("_fallback_by_class", None)
    ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    summary["runtime"] = {"wall_s": r6(time.time() - t0),
                          "peak_rss_mb_self": r6(ru / (1 << 20) if sys.platform == "darwin" else ru / 1024.0)}
    atomic_write(os.path.join(paths.results, "summary.json"), json.dumps(summary, indent=1, sort_keys=False,
                                                                         default=str))
    write_markdown(paths, summary)
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=os.path.dirname(os.path.abspath(__file__)), help="project directory")
    ap.add_argument("--no-figures", action="store_true")
    ap.add_argument("--host-load", default=None, help="per-minute host-load log (default <repo>/runs/host_load.jsonl)")
    a = ap.parse_args(argv)
    s = analyze(a.root, figures=not a.no_figures, host_load=a.host_load)
    for c, d in s["campaigns"].items():
        print("%-8s %-8s labels=%s crosscheck=%d/%d" % (c, d["status"], ",".join(d["engines"]) or "-",
                                                         d["crosscheck"]["n_mismatch"], d["crosscheck"]["n_checks"]))
    print("ledger crosscheck: %d mismatches of %d" % (s["ledger_crosscheck"]["n_mismatch"],
                                                      s["ledger_crosscheck"]["n_checks"]))
    for n, f in s["figures"].items():
        print("%-40s %s" % (n, f["status"]))
    print("runtime %.1f s, peak RSS %.0f MB" % (s["runtime"]["wall_s"], s["runtime"]["peak_rss_mb_self"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Tests of the project-level analysis (analyze.py) on synthetic inputs only.

    ../.venv/bin/python -m unittest \
        ../06_pandas_conformance/tests/test_analyze.py -v

Covers the aggregation-layer rules (REF_ERR/NONDET exclusion, post-timeout cascades, capture-
inflated nb_timeouts), bootstrap determinism, ledger rounding, campaign status from batch markers,
and an end-to-end run that writes every figure into a temporary project tree.
"""
import importlib.util
import json
import os
import random
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("pconf_analyze", os.path.join(os.path.dirname(HERE), "analyze.py"))
A = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A)


def cell(i, cls, clean_input=True, clean_level="E0", fallback=False, families=("other",), cls_raw=None):
    c = {"i": i, "cls": cls, "clean_input": clean_input, "clean_level": clean_level, "fallback": fallback,
         "families": list(families)}
    if cls_raw:
        c["cls_raw"] = cls_raw
    return c


def output(engine, nb, cells, ref="ref", ref2=True, eng_status="completed", fd=None):
    return {"meta": {"engine": engine, "nb": nb, "ref": ref, "scale": 1.0, "eng_status": eng_status,
                     "ref2_record": "x" if ref2 else None, "eng_record": "rec"},
            "cells": cells, "first_divergent": fd or {L: None for L in A.LEVELS}}


def run_record(engine, nb, status="completed", walls=(1.0,), cap=0.0, orch=10.0, cpus=None, rep=1, mode="capture",
               cell_status="ok"):
    return {"engine": engine, "nb": nb, "scale": 1.0, "status": status, "pandas": "2.3.3", "rep": rep, "mode": mode,
            "cfg": {"cpus": cpus}, "orchestrator_wall_s": orch, "peak_tree_rss_gb": 1.0, "fingerprint": "f",
            "cells": [{"i": k + 1, "status": cell_status, "wall_s": w, "t_capture_in": cap / 2, "t_capture_out": cap / 2,
                       "flags": []} for k, w in enumerate(walls)]}


class TestRules(unittest.TestCase):
    def test_post_timeout_cascade_excluded_from_clean_views(self):
        cells = [cell(1, "E0"), cell(2, "TIMEOUT"), cell(3, "E0"), cell(4, "DIFF", clean_level="E2", clean_input=False),
                 cell(5, "ERR")]
        s = A.process_output(output("bodo", "u/a", cells))
        self.assertEqual(s["timeout_cell"], 2)
        # all comparable view keeps every cell
        self.assertEqual(sum(s["counts"]["all"].values()), 5)
        # strict view: only cells 1 and 2 (3 and 5 are cascades; 4 is not strict-clean)
        self.assertEqual(dict(s["counts"]["clean_strict"]), {"E0": 1, "TIMEOUT": 1})
        self.assertEqual(dict(s["counts"]["clean_E2"]), {"E0": 1, "TIMEOUT": 1})
        self.assertEqual(dict(s["cascade"]), {"E0": 1, "DIFF": 1, "ERR": 1})
        self.assertEqual(s["cascade_clean"]["clean_strict"], 2)
        self.assertEqual(s["cascade_clean"]["clean_E2"], 3)
        # the pre-exclusion clean counts (for the cross-check) still contain the cascades
        self.assertEqual(sum(s["pre"]["clean_strict"].values()), 4)
        self.assertEqual(sum(s["pre"]["clean_E2"].values()), 5)

    def test_no_timeout_no_cascade(self):
        s = A.process_output(output("modin", "u/a", [cell(1, "E0"), cell(2, "ERR"), cell(3, "E1")]))
        self.assertIsNone(s["timeout_cell"])
        self.assertEqual(sum(s["cascade"].values()), 0)
        self.assertEqual(sum(s["counts"]["clean_strict"].values()), 3)

    def test_nondet_with_raw_timeout_starts_cascade(self):
        cells = [cell(1, "NONDET", cls_raw="TIMEOUT"), cell(2, "E0"), cell(3, "E0")]
        s = A.process_output(output("bodo", "u/a", cells))
        self.assertEqual(s["timeout_cell"], 1)
        self.assertEqual(s["excluded"]["NONDET"], 1)
        self.assertEqual(sum(s["counts"]["clean_strict"].values()), 0)
        self.assertEqual(sum(s["counts"]["all"].values()), 2)

    def test_ref_err_nondet_noout_setup_err_excluded(self):
        cells = [cell(1, "REF_ERR"), cell(2, "NONDET", cls_raw="DIFF"), cell(3, "NOOUT"), cell(4, "SETUP_ERR"),
                 cell(5, "E2", clean_level="E1", clean_input=False)]
        s = A.process_output(output("dask", "u/a", cells))
        self.assertEqual(dict(s["counts"]["all"]), {"E2": 1})
        self.assertEqual(dict(s["excluded"]), {"REF_ERR": 1, "NONDET": 1, "NOOUT": 1, "SETUP_ERR": 1})
        self.assertEqual(dict(s["counts"]["clean_E2"]), {"E2": 1})
        self.assertEqual(sum(s["counts"]["clean_strict"].values()), 0)

    def test_fallback_counted_per_view(self):
        cells = [cell(1, "E0", fallback=True), cell(2, "DIFF", fallback=True, clean_input=False, clean_level=None),
                 cell(3, "E0")]
        agg = A.aggregate_label("t", "fireducks", [A.process_output(output("fireducks", "u/a", cells))])
        self.assertEqual(agg["fallback"]["cells"], {"all": 2, "clean_strict": 1, "clean_E2": 1})
        self.assertEqual(agg["fallback"]["notebooks_with_fallback"], 1)
        # A12 (2026-10-05): class split of fallback-flagged cells per view
        self.assertEqual(agg["fallback"]["by_class_all"], {"DIFF": 1, "E0": 1})
        self.assertEqual(agg["fallback"]["by_class_clean_strict"], {"E0": 1})
        self.assertEqual(agg["fallback"]["by_class_clean_E2"], {"E0": 1})

    def test_fallback_by_class_clean_e2_drops_post_timeout_cascade(self):
        cells = [cell(1, "E2", fallback=True, clean_level="E2", clean_input=False), cell(2, "TIMEOUT"),
                 cell(3, "DIFF", fallback=True)]
        agg = A.aggregate_label("t", "bodo", [A.process_output(output("bodo", "u/a", cells))])
        self.assertEqual(agg["fallback"]["by_class_all"], {"DIFF": 1, "E2": 1})
        self.assertEqual(agg["fallback"]["by_class_clean_E2"], {"E2": 1})     # cell 3 is a post-timeout cascade
        self.assertEqual(agg["fallback"]["by_class_clean_strict"], {})

    def test_capture_inflated_timeouts(self):
        s = A.summarize_run_record
        recs = [dict(s(run_record("bodo", "u/a", "nb_timeout", walls=(600.0, 400.0), cap=2000.0, orch=3600.0)),
                     path="a"),
                dict(s(run_record("bodo", "u/b", "nb_timeout", walls=(3000.0, 700.0), cap=10.0, orch=3720.0)), path="b"),
                dict(s(run_record("bodo", "u/c", "nb_timeout", walls=(5.0,), cap=1.0, orch=3600.0)), path="c"),
                dict(s(run_record("bodo", "u/d", "completed", walls=(1.0,), orch=5.0)), path="d")]
        rows = {r["nb"]: r for r in A.nb_timeout_rows(recs)}
        self.assertEqual(set(rows), {"u/a", "u/b", "u/c"})
        self.assertTrue(rows["u/a"]["capture_inflated"])
        self.assertEqual(rows["u/a"]["larger_share"], "capture")
        self.assertFalse(rows["u/b"]["capture_inflated"])          # 3,700 s of cell time: a real timeout
        self.assertTrue(rows["u/c"]["capture_inflated"])           # rule label, but the time is not capture:
        self.assertEqual(rows["u/c"]["larger_share"], "time_outside_recorded_cells")
        self.assertAlmostEqual(rows["u/c"]["not_in_recorded_cells_s"], 3594.0, places=6)
        st = A.record_stats(recs)["bodo"]
        self.assertEqual((st["nb_timeout"], st["records"]), (3, 4))

    def test_pct1_round_half_up(self):
        self.assertEqual(A.pct1(140, 170), 82.4)     # 82.35294 -> 82.4
        self.assertEqual(A.pct1(4, 419), 1.0)        # 0.95465 -> 1.0
        self.assertEqual(A.pct1(1, 8), 12.5)
        self.assertEqual(A.pct1(1, 400), 0.3)        # 0.25 -> 0.3 (half up)
        self.assertIsNone(A.pct1(1, 0))

    def test_finest_level_majority(self):
        from collections import Counter
        self.assertEqual(A.finest_level(Counter({"E0": 5, "DIFF": 5})), "E0")
        self.assertEqual(A.finest_level(Counter({"E0": 4, "E2": 1, "DIFF": 5})), "E2")
        self.assertEqual(A.finest_level(Counter({"E0": 4, "DIFF": 6})), ">E4")


class TestCommonCells(unittest.TestCase):
    """A11 (2026-10-05): cells clean at E2 under all five core engines and both pandas versions."""
    LABELS = [l for _, l in A.COMMON_LABELS]
    CAMP = {l: c for c, l in A.COMMON_LABELS}

    def build(self, spec, ref_override=None):
        """spec: {nb: {label: [cells]}} -> (all_outs, ready) as analyze() passes them."""
        all_outs = {"conf_1x": {}, "drift": {}}
        for nb, d in spec.items():
            for lab, cells in d.items():
                o = output(lab, nb, cells)
                key = nb.replace("/", "__")
                o["meta"]["ref_record"] = "results/%s/raw/runs__h/ref/sf1/%s__%s.json" % (
                    self.CAMP[lab], key, (ref_override or {}).get((nb, lab), "fpref"))
                o["meta"]["ref2_record"] = "results/%s/raw/runs__h/ref_r2/sf1/%s__fpref2.json" % (self.CAMP[lab], key)
                all_outs[self.CAMP[lab]][(lab, nb, 1.0)] = A.process_output(o)
        ready = {"conf_1x": set(A.COMMON_ENGINES), "drift": {"p15", "p30"}}
        return all_outs, ready

    @staticmethod
    def four_e0():
        return [cell(1, "E0"), cell(2, "E0"), cell(3, "E0"), cell(4, "E0")]

    def test_intersection_cascades_and_notebook_exclusions(self):
        spec = {"u/a": {l: self.four_e0() for l in self.LABELS}}
        spec["u/a"]["dask"][2] = cell(3, "ERR", clean_input=False, clean_level=None)   # cell 3 not clean for dask
        spec["u/a"]["bodo"][1] = cell(2, "DIFF")
        spec["u/a"]["p30"][1] = cell(2, "DIFF")
        spec["u/a"]["fireducks"][2] = cell(3, "TIMEOUT")    # cell 4 becomes a post-timeout cascade for fireducks
        spec["u/b"] = {l: self.four_e0() for l in self.LABELS}       # reference record differs for p15
        spec["u/c"] = {l: self.four_e0() for l in self.LABELS if l != "p15"}   # p15 output missing
        spec["u/d"] = {l: self.four_e0() for l in self.LABELS}
        spec["u/d"]["p30"] = self.four_e0() + [cell(5, "E0")]               # cell list differs
        outs, ready = self.build(spec, ref_override={("u/b", "p15"): "other"})
        c = A.common_clean_view(outs, ready, n_boot=500)
        self.assertEqual(c["status"], "complete")
        self.assertEqual(c["notebooks_compared"], 1)
        self.assertEqual(c["notebooks_excluded"], {"cell_list_differs": 1, "missing_label": 1,
                                                   "reference_or_replicate_record_differs": 1})
        self.assertEqual(c["cells"], 2)                                        # cells 1 and 2 only
        self.assertEqual(c["per_label"]["bodo"]["counts"]["DIFF"], 1)
        self.assertEqual(c["per_label"]["modin"]["counts"]["E0"], 2)
        self.assertEqual(c["own_clean_E2_cells"]["dask"], 3)
        self.assertEqual(c["own_clean_E2_cells"]["fireducks"], 3)             # the timeout cell itself stays
        p = c["paired_DIFF_vs_p30"]
        self.assertEqual(p["bodo"]["diff"], 0.0)
        self.assertEqual(p["modin"]["diff"], -0.5)
        self.assertEqual(p["modin"]["ci95"], [-0.5, -0.5])                     # one notebook: degenerate interval
        self.assertEqual(p["modin"]["reading"], "less often")
        self.assertIn("p15", p)
        self.assertNotIn("p30", p)
        self.assertEqual(c["paired_DIFF_vs_p15"]["p30"]["diff"], 0.5)

    def test_paired_bootstrap_readings_and_determinism(self):
        spec = {}
        for k in range(12):
            d = {l: self.four_e0() for l in self.LABELS}
            for l in ("p30", "modin"):                     # modin differs exactly where pandas 3 does
                d[l][0] = cell(1, "DIFF")
            d["bodo"][0] = cell(1, "DIFF")
            if k % 2 == 0:
                d["bodo"][1] = cell(2, "DIFF")             # bodo: one extra DIFF cell in every second notebook
            if k == 0:
                d["dask"][0] = cell(1, "DIFF")
                d["dask"][1] = cell(2, "DIFF")             # dask: one extra DIFF cell in one notebook only
            else:
                d["dask"][0] = cell(1, "DIFF")
            spec["u/%02d" % k] = d
        outs, ready = self.build(spec)
        a = A.common_clean_view(outs, ready, n_boot=2000)
        b = A.common_clean_view(outs, ready, n_boot=2000)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        p = a["paired_DIFF_vs_p30"]
        self.assertEqual(a["cells"], 48)
        self.assertEqual((p["modin"]["diff"], p["modin"]["ci95"], p["modin"]["reading"]), (0.0, [0.0, 0.0],
                                                                                           "about as often"))
        self.assertAlmostEqual(p["bodo"]["diff"], 6 / 48, places=6)
        self.assertGreater(p["bodo"]["ci95"][0], 0)
        self.assertEqual(p["bodo"]["reading"], "more often")
        self.assertAlmostEqual(p["dask"]["diff"], 1 / 48, places=6)
        self.assertEqual(p["dask"]["ci95"][0], 0.0)        # notebook 0 is absent from about a third of resamples
        self.assertEqual(p["dask"]["reading"], "about as often")
        for l, v in p.items():                             # paired point estimate = difference of the label shares
            self.assertAlmostEqual(v["diff"], a["per_label"][l]["share"]["DIFF"] -
                                   a["per_label"]["p30"]["share"]["DIFF"], places=5)
            self.assertLessEqual(v["ci95"][0], v["diff"] + 1e-9)
            self.assertGreaterEqual(v["ci95"][1], v["diff"] - 1e-9)

    def test_pending_when_a_label_is_not_ready(self):
        outs, ready = self.build({"u/a": {l: self.four_e0() for l in self.LABELS}})
        ready["conf_1x"].discard("dask")
        c = A.common_clean_view(outs, ready, n_boot=100)
        self.assertEqual((c["status"], c["missing_labels"]), ("pending", ["conf_1x:dask"]))


class TestHostLoadJoin(unittest.TestCase):
    """Timing records x runs/host_load.jsonl (prepared 2026-10-05 for F2)."""
    T0 = 1_791_000_000.0

    def samples(self, times, load=lambda t: 10.0 + t / 60.0):
        return [(self.T0 + t, load(t), 2 * load(t), 32) for t in times]

    def test_covered_run_uses_its_minute_and_the_next(self):
        s = self.samples(range(0, 601, 60))
        j = A.join_host_load({"started": self.T0 + 100, "finished": self.T0 + 130}, s)
        self.assertTrue(j["covered"])
        self.assertEqual(j["times_from"], "record")
        self.assertEqual(j["n_samples"], 2)                       # samples at +120 and +180 (window end +205)
        self.assertAlmostEqual(j["load1_mean"], (12.0 + 13.0) / 2, places=6)
        self.assertAlmostEqual(j["load5_at_end"], 26.0, places=6)  # first sample at or after the end (+180)
        self.assertEqual(j["cores"], 32)

    def test_run_before_sampling_started_is_not_covered(self):
        j = A.join_host_load({"started": self.T0 - 500, "finished": self.T0 - 400}, self.samples(range(0, 601, 60)))
        self.assertFalse(j["covered"])
        self.assertIsNone(j["load1_mean"])

    def test_salvaged_record_uses_mtime_minus_wall_time(self):
        rec = {"mtime": self.T0 + 300, "orchestrator_wall_s": 50.0}
        j = A.join_host_load(rec, self.samples(range(0, 601, 60)))
        self.assertEqual((j["times_from"], j["start"], j["end"]), ("file_mtime_minus_orchestrator_wall",
                                                                 self.T0 + 250, self.T0 + 300))
        self.assertTrue(j["covered"])

    def test_gap_in_sampling_is_not_covered(self):
        s = self.samples([0, 60, 120, 180, 420, 480, 540, 600])
        self.assertFalse(A.join_host_load({"started": self.T0 + 100, "finished": self.T0 + 500}, s)["covered"])
        self.assertFalse(A.join_host_load({"started": self.T0 + 250, "finished": self.T0 + 260}, s)["covered"])
        self.assertTrue(A.join_host_load({"started": self.T0 + 430, "finished": self.T0 + 440}, s)["covered"])

    def test_sampler_jitter_still_gives_every_short_run_a_sample(self):
        s = self.samples([62 * k for k in range(12)])              # 62 s gaps, the largest measured
        for st in range(70, 560, 7):
            j = A.join_host_load({"started": self.T0 + st, "finished": self.T0 + st + 1}, s)
            self.assertTrue(j["covered"], st)
            self.assertGreaterEqual(j["n_samples"], 1)

    def test_load_file_parsing_and_aggregate(self):
        d = tempfile.mkdtemp(prefix="pconf_hl_")
        try:
            p = os.path.join(d, "host_load.jsonl")
            with open(p, "w") as f:
                f.write('{"utc": "2026-10-05T02:32:05Z", "loadavg": [23.5, 54.1, 70.1], "cores": 32}\n')
                f.write("not json\n")
                f.write('{"utc": "2026-10-05T02:33:05Z", "loadavg": [24.9, 49.0, 67.1], "cores": 32}\n')
            s = A.load_host_samples(p)
            self.assertEqual(len(s), 2)
            self.assertEqual(s[0][1:], (23.5, 54.1, 32))
            self.assertEqual(A.load_host_samples(os.path.join(d, "absent.jsonl")), [])
            t = s[0][0]
            recs = [{"engine": "ref", "nb": "u/a", "rep": 1, "cpus": "8", "status": "completed", "all_ok": True,
                     "started": t + 1, "finished": t + 2},
                    {"engine": "ref", "nb": "u/b", "rep": 1, "cpus": "8", "status": "completed", "all_ok": True,
                     "started": t - 900, "finished": t - 890}]
            h = A.timing_host_load(recs, s, "runs/host_load.jsonl")
            self.assertEqual((h["records"], h["records_covered"]), (2, 1))
            self.assertEqual(h["first_sample_utc"], "2026-10-05T02:32:05Z")
            self.assertEqual(h["by_cpus_engine"]["8|ref"]["covered"], 1)
            self.assertAlmostEqual(h["by_cpus_engine"]["8|ref"]["load1_median"], 24.9, places=6)  # window starts at +1 s
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestTimingReasons(unittest.TestCase):
    """Notebooks outside the speed-up set are classified; a timeout is a censored slowdown (2026-10-05)."""

    def test_crash_timeout_error_reasons_and_censored_bound(self):
        S = A.summarize_run_record
        recs = []
        for k in (1, 2, 3):
            for nb in ("u/a", "u/b", "u/c"):
                recs.append(S(run_record("ref", nb, walls=(10.0,), cpus="8", rep=k, mode="timing")))
            recs.append(S(run_record("modin", "u/a", walls=(5.0,), cpus="8", rep=k, mode="timing")))
            recs.append(S(run_record("modin", "u/b", "nb_timeout", walls=(1200.0,), orch=3600.0, cpus="8", rep=k,
                                     mode="timing", cell_status="timeout")))
            recs.append(S(run_record("modin", "u/c", walls=(3.0,), cpus="8", rep=k, mode="timing",
                                     cell_status="error")))
            recs.append(S(run_record("bodo", "u/a", "nb_crash", walls=(0.1,), cpus="8", rep=k, mode="timing")))
        d = tempfile.mkdtemp(prefix="pconf_timing_")
        try:
            t = A.timing_analysis(A.Paths(d), recs, "partial", {})
        finally:
            shutil.rmtree(d, ignore_errors=True)
        m = t["by_cpus"]["8"]["modin"]
        self.assertEqual(m["notebooks_both_ok"], 1)
        self.assertAlmostEqual(m["geomean_speedup_vs_ref"], 2.0, places=6)
        r = m["not_ok_by_reason"]
        self.assertEqual(r["error_cells"], ["u/c"])
        self.assertEqual(len(r["timeout"]), 1)
        self.assertEqual((r["timeout"][0]["nb"], r["timeout"][0]["engine_time_lower_bound_s"],
                          r["timeout"][0]["ref_median_s"]), ("u/b", 3600.0, 10.0))
        self.assertAlmostEqual(r["timeout"][0]["speedup_upper_bound"], 10.0 / 3600.0, places=6)
        self.assertEqual(t["by_cpus"]["8"]["bodo"]["not_ok_by_reason"]["crash"], ["u/a"])
        f = t["failures"]
        self.assertEqual(f["8|modin"]["records_by_status"], {"completed": 6, "nb_timeout": 3})
        self.assertEqual(f["8|modin"]["cells_by_status"], {"error": 3, "timeout": 3})
        self.assertEqual((f["8|modin"]["notebooks_with_timeout_cells"], f["8|bodo"]["notebooks_with_crash_or_nb_timeout"]),
                         (1, 1))


class TestBootstrap(unittest.TestCase):
    def rows(self, seed=1, n=25):
        from collections import Counter
        r = random.Random(seed)
        return [Counter({"E0": r.randint(0, 30), "E2": r.randint(0, 10), "DIFF": r.randint(0, 5), "ERR": r.randint(0, 3)})
                for _ in range(n)]

    def test_deterministic_and_order_of_calls_irrelevant(self):
        rows = self.rows()
        a = A.bootstrap_shares(rows, "c|e|all")
        A.bootstrap_shares(self.rows(seed=9), "c|other|all")      # another series in between
        b = A.bootstrap_shares(rows, "c|e|all")
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertGreaterEqual(a["n_boot"], 2000)

    def test_interval_contains_estimate_and_key_changes_draws(self):
        rows = self.rows()
        a = A.bootstrap_shares(rows, "c|e|all")
        b = A.bootstrap_shares(rows, "c|e|clean_E2")
        self.assertEqual(a["share"], b["share"])                     # point estimates do not depend on the seed
        self.assertNotEqual(a["ci95"]["E0"], b["ci95"]["E0"])        # draws do
        for k in ("E0", "E2", "DIFF", "ERR"):
            lo, hi = a["ci95"][k]
            self.assertLessEqual(lo, a["share"][k] + 1e-9)
            self.assertGreaterEqual(hi, a["share"][k] - 1e-9)
        tot = sum(sum(c.values()) for c in rows)
        self.assertEqual(a["cells"], tot)
        self.assertAlmostEqual(a["share"]["E0"], round(sum(c["E0"] for c in rows) / tot, 6))
        self.assertAlmostEqual(a["cum_share"]["<=E4"] + a["nonconformant_share"], 1.0, places=6)

    def test_aggregate_independent_of_input_order(self):
        outs = [A.process_output(output("modin", "u/%02d" % k, [cell(1, "E0"), cell(2, ["DIFF", "E1", "ERR"][k % 3])],
                                        fd={"E0": 2, "E1": 2 if k % 3 != 1 else None, "E2": 2 if k % 3 != 1 else None,
                                            "E3": 2 if k % 3 != 1 else None, "E4": 2 if k % 3 != 1 else None}))
                for k in range(12)]
        a = A.aggregate_label("c", "modin", outs)
        random.Random(3).shuffle(outs)
        b = A.aggregate_label("c", "modin", outs)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertEqual(a["first_divergence"]["E0"]["notebooks_diverged"], 12)
        self.assertEqual(a["first_divergence"]["E4"]["notebooks_diverged"], 8)

    def test_empty_population(self):
        a = A.bootstrap_shares([], "c|e|all")
        self.assertEqual(a["cells"], 0)
        self.assertEqual(a["share"], {})


class TestEndToEnd(unittest.TestCase):
    """A temporary project tree: drift and conf_1x complete, timing complete, pilot and conf_5x pending."""
    NBS = ["u/a", "u/b", "u/c"]

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="pconf_analyze_test_")
        R = self.root
        os.makedirs(os.path.join(R, "data", "PandasBench", "runner", "scales"))
        self.wj(os.path.join(R, "data", "PandasBench", "runner", "scales", "nbs_to_run_default.json"),
                {"notebooks": [{"nb": n} for n in self.NBS]})
        for s in ("pilot", "timing30", "conf5x"):
            self.wj(os.path.join(R, "data", "notebook_sets", s + ".json"), {"notebooks": self.NBS[:2]})
        for m in ("drift_run", "drift_compare", "conf1x_single", "conf1x_parallel", "conf1x_compare", "timing_cpu8",
                  "timing_default"):
            self.wj(os.path.join(R, "work", "batch", A.BATCH, m + ".done"), {"finished": "t"})
        # drift: records + outputs
        for e in ("ref", "ref#2", "p15", "p30"):
            for nb in self.NBS:
                self.rec("drift", e, nb, run_record(e, nb))
        for e in ("ref#2", "p15", "p30"):
            for k, nb in enumerate(self.NBS):
                cls = "E0" if e == "ref#2" else ["E0", "E2", "DIFF"][k]
                self.out("drift", e, nb, output(e, nb, [cell(1, "E0"), cell(2, cls), cell(3, "REF_ERR"),
                                                        cell(4, "NONDET", cls_raw="DIFF")]))
        # conf_1x: core engines; bodo has an engine TIMEOUT followed by a cascade, and an nb_timeout record
        for e in ("ref", "ref#2", "pyarrow_backend", "fireducks", "bodo", "modin", "dask"):
            for nb in self.NBS:
                st = "nb_timeout" if (e == "bodo" and nb == "u/a") else "completed"
                self.rec("conf_1x", e, nb, run_record(e, nb, st, walls=(600.0, 2.0), orch=3600.0 if st != "completed"
                                                      else 9.0))
        for e in ("ref#2", "pyarrow_backend", "fireducks", "bodo", "modin", "dask"):
            for nb in self.NBS:
                if e == "bodo" and nb == "u/a":
                    cells = [cell(1, "E0", families=("read",)), cell(2, "TIMEOUT"), cell(3, "E0"), cell(4, "ERR")]
                    fd = {L: 2 for L in A.LEVELS}
                else:
                    cells = [cell(1, "E0", families=("read",)), cell(2, "E1", fallback=(e == "fireducks"),
                                                                     families=("sort", "groupby_agg")),
                             cell(3, "DIFF", clean_level="E2", clean_input=False)]
                    fd = {"E0": 2, "E1": 3, "E2": 3, "E3": 3, "E4": 3}
                self.out("conf_1x", e, nb, output(e, nb, cells, fd=fd))
        # bodo_dw: records only (its group is not complete)
        self.rec("conf_1x", "bodo_dw", "u/a", run_record("bodo_dw", "u/a"))
        # timing: 4 engines x 2 notebooks x (3 reps at cpus 8 + 1 rep at default)
        for e, t in (("ref", 10.0), ("modin", 5.0), ("fireducks", 1.0), ("bodo", 20.0)):
            for nb in self.NBS[:2]:
                for cpus, reps in (("8", 3), ("default", 1)):
                    for rep in range(1, reps + 1):
                        r = run_record(e, nb, walls=(t,), cpus=cpus, rep=rep, mode="timing")
                        self.wj(os.path.join(R, "results", "timing", "raw", "timing__" + A.HARNESS_TAG, e.replace("#", "_r"),
                                             "sf1", "%s__%s__%d.json" % (nb.replace("/", "__"), cpus, rep)), r)
        # an input under a non-accepted tag must be listed as excluded and never read
        self.wj(os.path.join(R, "results", "drift", "raw", "compare__%s__dffffffffffff" % A.HARNESS_TAG, "p15", "sf1",
                             "x.json"), output("p15", "u/a", [cell(1, "DIFF")]))
        self.wj(os.path.join(R, "results", "drift", "analysis__%s__dffffffffffff.json" % A.HARNESS_TAG), {})
        # a synthetic per-minute host-load log around the time the timing records were written (their mtime)
        import datetime
        import time
        now = time.time()
        self.hl = os.path.join(R, "host_load.jsonl")
        with open(self.hl, "w") as f:
            for k in range(-60, 61):
                t = datetime.datetime.fromtimestamp(now + 60 * k, datetime.timezone.utc)
                f.write(json.dumps({"utc": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "loadavg": [100.0, 90.0, 80.0],
                                    "cores": 32}) + "\n")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def wj(self, p, obj):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            json.dump(obj, f)

    def rec(self, camp, e, nb, r):
        self.wj(os.path.join(self.root, "results", camp, "raw", "runs__" + A.HARNESS_TAG, e.replace("#", "_r"), "sf1",
                             nb.replace("/", "__") + ".json"), r)

    def out(self, camp, e, nb, r):
        self.wj(os.path.join(self.root, "results", camp, "raw", "compare__" + A.TAG, e.replace("#", "_r"), "sf1",
                             nb.replace("/", "__") + ".json"), r)

    def test_end_to_end(self):
        s = A.analyze(self.root, figures=True, host_load=self.hl)
        c = s["campaigns"]
        self.assertEqual(list(c), ["pilot", "drift", "conf_1x", "timing", "conf_5x"])      # stable keys
        self.assertEqual({k: v["status"] for k, v in c.items()},
                         {"pilot": "pending", "drift": "complete", "conf_1x": "complete", "timing": "complete",
                          "conf_5x": "pending"})
        self.assertEqual(c["conf_1x"]["groups"]["conf1x_bodo_dw"]["status"], "partial")
        self.assertNotIn("bodo_dw", c["conf_1x"]["engines"])
        # drift: REF_ERR and NONDET excluded; the non-accepted tag is not read
        p15 = c["drift"]["engines"]["p15"]
        self.assertEqual(p15["views"]["all"]["cells"], 6)
        self.assertEqual(p15["views"]["all"]["counts"]["DIFF"], 1)
        self.assertEqual(p15["excluded_cells"], {"NONDET": 3, "REF_ERR": 3})
        ex = {x["path"] for x in s["excluded_inputs"]}
        self.assertIn("results/drift/raw/compare__%s__dffffffffffff" % A.HARNESS_TAG, ex)
        self.assertIn("results/drift/analysis__%s__dffffffffffff.json" % A.HARNESS_TAG, ex)
        # conf_1x cascade rule and capture-inflated rule
        bodo = c["conf_1x"]["engines"]["bodo"]
        self.assertEqual(bodo["post_timeout_cascade"]["cells"], 2)
        self.assertEqual(bodo["views"]["all"]["cells"], 4 + 3 + 3)
        self.assertEqual(bodo["views"]["clean_strict"]["cells"], 2 + 2 + 2)
        self.assertEqual(bodo["failure_cells"]["TIMEOUT"], 1)
        nbt = c["conf_1x"]["nb_timeouts"]
        self.assertEqual(len(nbt), 1)
        self.assertTrue(nbt[0]["capture_inflated"])                  # 602 s of cell time < 3,600 s
        self.assertEqual(c["conf_1x"]["engines"]["fireducks"]["fallback"]["cells"]["all"], 3)
        fam = c["conf_1x"]["families"]["modin"]
        self.assertEqual(fam["read"]["finest_level_majority"], "E0")
        self.assertEqual(fam["sort"]["finest_level_majority"], "E1")
        # timing / RQ4
        g = s["timing"]["by_cpus"]["8"]
        self.assertAlmostEqual(g["fireducks"]["geomean_speedup_vs_ref"], 10.0, places=6)
        self.assertAlmostEqual(g["bodo"]["geomean_speedup_vs_ref"], 0.5, places=6)
        # host-load join (salvage-style times: file mtime minus orchestrator wall) and failure counts
        hl = s["timing"]["host_load"]
        self.assertEqual((hl["records"], hl["records_covered"]), (32, 32))
        self.assertEqual(hl["by_cpus_engine"]["8|ref"]["load1_median"], 100.0)
        self.assertEqual(g["fireducks"]["load"]["pairs_with_load_on_both_runs"], 2)
        self.assertAlmostEqual(g["fireducks"]["load"]["geomean_speedup_vs_ref_load_covered"], 10.0, places=6)
        self.assertEqual(s["timing"]["failures"]["8|bodo"]["records_by_status"], {"completed": 6})
        rd = s["timing"]["ref_drift_default_over_8"]                  # same reference times in both periods
        self.assertEqual((rd["notebooks"], rd["ratio_median"], rd["ratio_min_max"]), (2, 1.0, [1.0, 1.0]))
        # Figure 4's conformance coordinate is the clean@E2 view on the timing30 notebooks
        self.assertEqual(s["timing"]["fig4_conformance_view"], "clean_E2")
        self.assertEqual(s["timing"]["conformance_on_timing30_clean_E2"]["bodo"]["cells"], 5)  # u/a: cascade cells 3-4 out
        self.assertEqual(s["timing"]["conformance_on_timing30"]["bodo"]["cells"], 7)           # all view keeps them
        # figures: pilot pending -> no pilot figures; conf_1x complete -> fig1/2/5; drift -> fig3; timing -> fig4
        st = {k: v["status"] for k, v in s["figures"].items()}
        for f in ("fig1_conformance_by_engine.pdf", "fig2_opfamily_heatmap.pdf", "fig3_drift.pdf",
                  "fig4_speed_vs_conformance.pdf", "fig5_first_divergence.pdf"):
            self.assertEqual(st[f], "written", f)
            p = os.path.join(self.root, "paper", "figures", f)
            with open(p, "rb") as fh:
                self.assertEqual(fh.read(5), b"%PDF-")
        self.assertNotIn("fig1_conformance_by_engine_pilot.pdf", st)
        # A11 view: both campaigns complete, but the synthetic outputs carry no reference record file name,
        # so every notebook is excluded by the same-reference check rather than silently paired
        cc = s["common_clean_E2"]
        self.assertEqual((cc["status"], cc["notebooks_compared"], cc["cells"]), ("complete", 0, 0))
        self.assertEqual(cc["notebooks_excluded"], {"reference_or_replicate_record_differs": 3})
        # the outputs exist and the markdown names the rules
        self.assertTrue(os.path.exists(os.path.join(self.root, "results", "summary.json")))
        with open(os.path.join(self.root, "results", "analysis.md")) as f:
            md = f.read()
        self.assertIn("post-timeout cascades", md)
        self.assertIn("capture-inflated", md)

    def test_conf1x_without_compare_marker_is_partial_and_figures_pending(self):
        os.remove(os.path.join(self.root, "work", "batch", A.BATCH, "conf1x_compare.done"))
        s = A.analyze(self.root, figures=False, host_load=os.path.join(self.root, "absent_host_load.jsonl"))
        self.assertEqual(s["timing"]["host_load"]["records_covered"], 0)
        self.assertEqual(s["campaigns"]["conf_1x"]["status"], "partial")
        self.assertEqual(s["campaigns"]["conf_1x"]["engines"], {})
        self.assertEqual(s["figures"]["fig1_conformance_by_engine.pdf"]["status"], "pending")
        self.assertEqual(s["figures"]["fig4_speed_vs_conformance.pdf"]["status"], "pending")
        self.assertIn("bodo", s["campaigns"]["conf_1x"]["compare_outputs"]["labels_pending_compare"])
        # run-record failure counts are reported for a partial campaign
        self.assertEqual(s["campaigns"]["conf_1x"]["run_records"]["bodo"]["nb_timeout"], 1)


if __name__ == "__main__":
    unittest.main()

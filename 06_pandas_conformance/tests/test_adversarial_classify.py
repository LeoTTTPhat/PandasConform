"""Adversarial review of clean-input attribution, cell classes and the AST input model
(review 2026-10-02).

Tests named *_documented assert the CURRENT behaviour and exist to make a validity issue
visible and measurable (see plan.md ledger, Review). Tests decorated @unittest.expectedFailure
assert the behaviour the plan requires and flip to "unexpected success" once fixed.
Fix stage 2026-10-02: A1 (level-aware clean), A2 (hidden globals) and A3 (crash classes,
engine-independent NONDET) are fixed; the decorators are removed and the two *_documented
tests of A3 now assert the fixed behaviour (renamed *_fixed).
"""
import unittest

import numpy as np
import pandas as pd

from _common import TempStore
from pconf import classify, nbsource
from pconf.capture import Capturer
from test_classify import RunBuilder


class _Base(unittest.TestCase):
    def setUp(self):
        self.ts = TempStore()
        self.cap = Capturer(self.ts.dir)

    def tearDown(self):
        self.ts.cleanup()


class TestHiddenInputsThroughUserFunctions(_Base):
    """A cell that calls a user function reads the globals used in the function body, but the
    AST model only sees the function name (callables are ignored by the clean-input test).
    On the 102 PandasBench notebooks, 86 of 3,683 cells (2.3%) in 17 notebooks call such a
    function whose body reads a global data name the cell itself does not load."""

    def test_static_loads_miss_function_globals_documented(self):
        defs = nbsource.analyze(nbsource.prepare_cell("def total():\n    return df['x'].sum()\n")[0])
        call = nbsource.analyze(nbsource.prepare_cell("r = total()\nr")[0])
        self.assertEqual(defs["loads"], [])
        self.assertEqual(call["loads"], ["total"])  # 'df' is invisible to the input model

    def test_cell_reading_a_divergent_global_via_function_is_not_clean(self):
        df_ref = pd.DataFrame({"x": [1, 2, 3]})
        df_eng = pd.DataFrame({"x": [1, 2, 4]})          # diverged in an earlier cell
        ref = (RunBuilder(self.cap)
               .cell(1, outputs={"df": df_ref})
               .cell(2, inputs={"total": len}, outputs={"r": int(df_ref["x"].sum())}))
        eng = (RunBuilder(self.cap)
               .cell(1, outputs={"df": df_eng})
               .cell(2, inputs={"total": len}, outputs={"r": int(df_eng["x"].sum())}))
        for rec, df in ((ref.rec, df_ref), (eng.rec, df_eng)):
            rec["cells"][1]["static"] = {"attrs": [], "loads": ["total"], "stores": ["r"]}
            # fix stage: the runner now records, for the cell that defines `total`, the globals
            # its body reads (nbsource fn_globals); the fixture states it explicitly
            rec["cells"][0]["static"]["fn_globals"] = {"total": ["df"]}
        rows = {c["i"]: c for c in classify.classify_run(ref.rec, eng.rec, self.ts.dir)["cells"]}
        self.assertEqual(rows[2]["cls"], "DIFF")
        # the DIFF at cell 2 is a cascade of cell 1, so cell 2 must not be counted as clean-input
        self.assertFalse(rows[2]["clean_input"])
        self.assertIn("hidden_global_via_function:df", rows[2]["unclean"])

    def test_fn_globals_reach_the_record_through_nbsource(self):
        an = nbsource.analyze(nbsource.prepare_cell("def total():\n    return df['x'].sum()\n")[0])
        self.assertEqual(an["fn_globals"], {"total": ["df"]})
        both = nbsource.analyze(nbsource.prepare_cell("def h():\n    return df2\nr = h()\n")[0])
        self.assertEqual(both["bound_loads"], ["h"])

    def test_same_cell_definition_and_call(self):
        df_ref, df_eng = pd.DataFrame({"x": [1]}), pd.DataFrame({"x": [2]})
        ref = RunBuilder(self.cap).cell(1, outputs={"df": df_ref}).cell(2, outputs={"r": 1})
        eng = RunBuilder(self.cap).cell(1, outputs={"df": df_eng}).cell(2, outputs={"r": 1})
        for rec in (ref.rec, eng.rec):
            rec["cells"][1]["static"] = {"attrs": [], "loads": [], "bound_loads": ["h"], "fn_globals": {"h": ["df"]}}
        rows = {c["i"]: c for c in classify.classify_run(ref.rec, eng.rec, self.ts.dir)["cells"]}
        self.assertFalse(rows[2]["clean_input"])
        self.assertEqual(rows[2]["hidden_globals"], ["df"])


class TestCleanInputUnderDtypeDrift(_Base):
    """Clean-input is defined at E0. When an engine's reader changes dtypes (pandas 3 'str',
    pyarrow backend, Bodo's arrow dtypes), every later cell that reads the frame is unclean, so
    clean-input statistics shrink to read cells and cells without data inputs. In the smoke
    campaign: p30 6 and pyarrow_backend 6 clean comparable (non-NOOUT) cells of 34, modin 27 of 34."""

    def test_clean_set_collapses_after_e2_read_documented(self):
        df_ref = pd.DataFrame({"s": pd.Series(["a", "b"], dtype=object), "v": [1.0, 2.0]})
        df_eng = df_ref.astype({"s": "string"})        # E2-equal frame (stringy family)
        ref, eng = RunBuilder(self.cap).cell(1, outputs={"df": df_ref}), RunBuilder(self.cap).cell(1, outputs={"df": df_eng})
        for i in range(2, 7):
            out_r = {"__last__": float(df_ref["v"].sum() * i)}
            ref.cell(i, inputs={"df": df_ref}, outputs=out_r)
            eng.cell(i, inputs={"df": df_eng}, outputs=out_r)   # identical (E0) results downstream
        res = classify.classify_run(ref.rec, eng.rec, self.ts.dir)
        rows = {c["i"]: c for c in res["cells"]}
        self.assertEqual(rows[1]["cls"], "E2")
        self.assertTrue(all(rows[i]["cls"] == "E0" for i in range(2, 7)))
        # five conformant downstream cells are all excluded from the STRICT clean-input statistics
        self.assertEqual(res["summary"]["clean_cells"], 1)
        self.assertEqual(res["summary"]["clean_by_class"], {"E2": 1})

    def test_level_aware_clean_keeps_downstream_cells(self):
        """Fix of A1: clean@E2 counts the downstream cells whose inputs are E2-equal."""
        df_ref = pd.DataFrame({"s": pd.Series(["a", "b"], dtype=object), "v": [1.0, 2.0]})
        df_eng = df_ref.astype({"s": "string"})
        ref, eng = RunBuilder(self.cap).cell(1, outputs={"df": df_ref}), RunBuilder(self.cap).cell(1, outputs={"df": df_eng})
        for i in range(2, 7):
            out_r = {"__last__": float(df_ref["v"].sum() * i)}
            ref.cell(i, inputs={"df": df_ref}, outputs=out_r)
            eng.cell(i, inputs={"df": df_eng}, outputs=out_r)
        res = classify.classify_run(ref.rec, eng.rec, self.ts.dir)
        rows = {c["i"]: c for c in res["cells"]}
        self.assertEqual([rows[i]["clean_level"] for i in range(1, 7)], ["E0"] + ["E2"] * 5)
        self.assertEqual(res["summary"]["clean_cells_at"], {"E0": 1, "E1": 1, "E2": 6, "E3": 6, "E4": 6})
        self.assertEqual(res["summary"]["clean_at"]["E2"], {"E2": 1, "E0": 5})
        self.assertEqual(rows[2]["input_levels"], {"df": "E2"})
        # a DIFF input is unclean at every level
        bad = RunBuilder(self.cap).cell(1, outputs={"df": df_ref}).cell(2, inputs={"df": df_ref.iloc[:1]}, outputs={"__last__": 3.0})
        res2 = classify.classify_run(ref.rec, bad.rec, self.ts.dir)
        self.assertIsNone({c["i"]: c for c in res2["cells"]}[2]["clean_level"])


class TestCrashAttribution(_Base):
    def _runs(self, eng_status):
        df = pd.DataFrame({"a": [1, 2]})
        ref = (RunBuilder(self.cap).cell(1, outputs={"df": df})
               .cell(2, inputs={"df": df}, outputs={"m": df * 2})
               .cell(3, inputs={"df": df}, outputs={"n": df + 1}))
        eng = RunBuilder(self.cap).cell(1, outputs={"df": df})   # crashed while running cell 2
        eng.rec["status"] = eng_status
        return ref.rec, eng.rec

    def test_crashing_cell_has_a_clean_flag_fixed(self):
        # review documented: the crashing cell had no clean flag and was classed TIMEOUT.
        # fixed: class CRASH, clean flag from the engine's last captured values; later cells NOTRUN
        ref, eng = self._runs("nb_crash")
        res = classify.classify_run(ref, eng, self.ts.dir)
        rows = {c["i"]: c for c in res["cells"]}
        self.assertEqual(rows[2]["cls"], "CRASH")
        self.assertTrue(rows[2]["clean_input"])
        self.assertEqual(rows[3]["cls"], "NOTRUN")
        self.assertFalse(rows[3]["clean_input"])
        self.assertEqual(res["summary"]["clean_by_class"].get("CRASH"), 1)

    def test_crashing_cell_with_clean_inputs_counts_as_failure(self):
        ref, eng = self._runs("nb_crash")
        res = classify.classify_run(ref, eng, self.ts.dir)
        failures = sum(v for k, v in res["summary"]["clean_by_class"].items() if k in ("ERR", "TIMEOUT", "CRASH"))
        self.assertEqual(failures, 1)

    def test_engine_setup_error_is_not_a_timeout(self):
        ref, eng = self._runs("engine_setup_error")
        eng["cells"] = []
        rows = {c["i"]: c for c in classify.classify_run(ref, eng, self.ts.dir)["cells"]}
        self.assertNotEqual(rows[1]["cls"], "TIMEOUT")

    def test_nondet_exclusion_is_engine_independent_fixed(self):
        """Review documented: a reference-non-deterministic cell was NONDET for an engine that ran
        it but TIMEOUT for an engine that crashed before it. Fixed: NONDET is decided from ref and
        ref#2 alone (same excluded set for every engine); the engine class is kept in cls_raw and
        still counts for the first-divergent cell."""
        ref, _ = self._runs("completed")
        ref2 = RunBuilder(self.cap)
        df = pd.DataFrame({"a": [1, 2]})
        ref2.cell(1, outputs={"df": df}).cell(2, inputs={"df": df}, outputs={"m": df * 3}).cell(3, inputs={"df": df}, outputs={"n": df + 1})
        eng_ok = RunBuilder(self.cap)
        eng_ok.cell(1, outputs={"df": df}).cell(2, inputs={"df": df}, outputs={"m": df * 2}).cell(3, inputs={"df": df}, outputs={"n": df + 1})
        _, eng_dead = self._runs("nb_crash")
        a = {c["i"]: c["cls"] for c in classify.classify_run(ref, eng_ok.rec, self.ts.dir, ref2=ref2.rec)["cells"]}
        rb = classify.classify_run(ref, eng_dead, self.ts.dir, ref2=ref2.rec)
        b = {c["i"]: c for c in rb["cells"]}
        self.assertEqual(a[2], "NONDET")
        self.assertEqual(b[2]["cls"], "NONDET")
        self.assertEqual(b[2]["cls_raw"], "CRASH")
        self.assertEqual(rb["first_divergent"]["E4"], 2)


class TestOutputMatching(_Base):
    def test_engine_missing_output_and_deleted(self):
        df = pd.DataFrame({"a": [1]})
        ref = RunBuilder(self.cap).cell(1, outputs={"x": df, "y": "deleted"})
        eng = RunBuilder(self.cap).cell(1, outputs={"y": "deleted"})
        row = classify.classify_run(ref.rec, eng.rec, self.ts.dir)["cells"][0]
        self.assertEqual(row["cls"], "DIFF")
        self.assertEqual(row["outputs"]["x"]["reason"], "missing_in_engine")

    def test_worst_output_decides(self):
        df = pd.DataFrame({"a": [1.0, 2.0]})
        ref = RunBuilder(self.cap).cell(1, outputs={"x": df, "y": df})
        eng = RunBuilder(self.cap).cell(1, outputs={"x": df.iloc[::-1], "y": df.astype("Float64")})
        row = classify.classify_run(ref.rec, eng.rec, self.ts.dir)["cells"][0]
        self.assertEqual(row["outputs"]["x"]["level"], "E1")
        self.assertEqual(row["cls"], "E2")


if __name__ == "__main__":
    unittest.main()

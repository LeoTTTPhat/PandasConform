"""Clean-input detection, cell outcome classes, first-divergent-cell attribution, non-determinism."""
import unittest

import numpy as np
import pandas as pd

from _common import TempStore
from pconf import classify
from pconf.capture import Capturer


class RunBuilder:
    """Builds runner_child-shaped records from python values."""

    def __init__(self, cap):
        self.cap = cap
        self.rec = {"status": "completed", "cells": [], "objects": {}}

    def _ref(self, v):
        r = self.cap.capture(v)
        if r["h"] is None:
            return {"kind": r["kind"], "type": r["info"].get("type")}
        self.rec["objects"][r["h"]] = r
        return r["h"]

    def cell(self, i, status="ok", inputs=None, outputs=None, flags=None, exc=None, attrs=None):
        c = {"i": i, "status": status, "static": {"attrs": attrs or []},
             "inputs": {k: self._ref(v) for k, v in (inputs or {}).items()},
             "outputs": {k: (v if isinstance(v, str) and v in ("absent", "deleted") else self._ref(v))
                         for k, v in (outputs or {}).items()},
             "flags": flags or []}
        if exc:
            c["exc_type"] = exc
        self.rec["cells"].append(c)
        return self


class TestClassify(unittest.TestCase):
    def setUp(self):
        self.ts = TempStore()
        self.cap = Capturer(self.ts.dir)

    def tearDown(self):
        self.ts.cleanup()

    def build(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [0.5, np.nan, 1.5]})
        dfe = df.astype({"a": "float64"})
        ref = (RunBuilder(self.cap)
               .cell(0, status="setup")
               .cell(1, outputs={"df": df}, attrs=["read_csv"])
               .cell(2, inputs={"df": df}, outputs={"__last__": df["a"].sum()}, attrs=["sum"])
               .cell(3, inputs={"df": df}, outputs={"g": df.groupby("a").size()}, attrs=["groupby", "size"])
               .cell(4, inputs={"df": df, "pd": pd}, status="error", exc="KeyError")
               .cell(5, inputs={"df": df}, outputs={"__last__": len(df)})
               .cell(6, inputs={"df": df}, outputs={})
               .cell(7, inputs={"df": df}, outputs={"__last__": df.shape}))
        eng = (RunBuilder(self.cap)
               .cell(0, status="setup")
               .cell(1, outputs={"df": dfe}, flags=["modin_default_to_pandas"])   # E2 (int->float)
               .cell(2, inputs={"df": dfe}, outputs={"__last__": float(df["a"].sum())})   # E2, not clean
               .cell(3, inputs={"df": dfe}, outputs={"g": df.groupby("a").size().iloc[::-1]})  # E1, not clean
               .cell(4, inputs={"df": dfe, "pd": pd}, status="ok")              # REF_ERR
               .cell(5, inputs={"df": dfe}, status="error", exc="ValueError")   # ERR
               .cell(6, inputs={"df": dfe}, outputs={})                          # NOOUT
               .cell(7, inputs={"df": dfe}, outputs={"__last__": (3, 3)}))       # DIFF
        return ref.rec, eng.rec

    def test_classes(self):
        ref, eng = self.build()
        res = classify.classify_run(ref, eng, self.ts.dir)
        cls = {c["i"]: c["cls"] for c in res["cells"]}
        self.assertEqual(cls, {1: "E2", 2: "E2", 3: "E1", 4: "REF_ERR", 5: "ERR", 6: "NOOUT", 7: "DIFF"})
        rows = {c["i"]: c for c in res["cells"]}
        self.assertTrue(rows[1]["fallback"])
        self.assertTrue(rows[1]["clean_input"])
        self.assertFalse(rows[2]["clean_input"])
        self.assertIn("input_differs:df", rows[2]["unclean"])
        self.assertEqual(rows[1]["families"], ["read"])

    def test_clean_input_ignores_modules_and_requires_equal_hashes(self):
        df = pd.DataFrame({"a": [1]})
        ref = RunBuilder(self.cap).cell(1, inputs={"df": df, "pd": pd, "f": len}, outputs={"x": 1})
        eng = RunBuilder(self.cap).cell(1, inputs={"df": df.copy(), "pd": np, "f": len}, outputs={"x": 1})
        res = classify.classify_run(ref.rec, eng.rec, self.ts.dir)
        self.assertTrue(res["cells"][0]["clean_input"])
        g = df.groupby("a")
        ref2 = RunBuilder(self.cap).cell(1, inputs={"g": g}, outputs={"x": 1})
        eng2 = RunBuilder(self.cap).cell(1, inputs={"g": g}, outputs={"x": 1})
        res2 = classify.classify_run(ref2.rec, eng2.rec, self.ts.dir)
        self.assertFalse(res2["cells"][0]["clean_input"])
        self.assertTrue(res2["cells"][0]["unclean"][0].startswith("uncapturable_input:g"))

    def test_materialization_error_is_err(self):
        df = pd.DataFrame({"a": [1]})
        ref = RunBuilder(self.cap).cell(1, outputs={"__last__": df})
        eng = RunBuilder(self.cap).cell(1, outputs={"__last__": df})
        eng.rec["cells"][0]["outputs"]["__last__"] = {"kind": "unconvertible", "type": "dask.DataFrame",
                                                      "error": "ValueError: Mismatched dtypes found"}
        row = classify.classify_run(ref.rec, eng.rec, self.ts.dir)["cells"][0]
        self.assertEqual(row["cls"], "ERR")
        self.assertEqual(row["eng_exc"], "materialize_error")

    def test_first_divergent(self):
        ref, eng = self.build()
        res = classify.classify_run(ref, eng, self.ts.dir)
        fd = res["first_divergent"]
        self.assertEqual(fd["E0"], 1)
        self.assertEqual(fd["E1"], 1)
        self.assertEqual(fd["E2"], 5)   # cells 1-3 pass at E2; ERR at 5
        self.assertEqual(fd["E4"], 5)

    def test_engine_crash_marks_missing_cells_timeout(self):
        # fix stage 2026-10-02 (review A3): only the cell running when the notebook timeout hit
        # is TIMEOUT; later cells were never reached (NOTRUN, never clean)
        ref, eng = self.build()
        eng["status"] = "nb_timeout"
        eng["cells"] = eng["cells"][:3]
        res = classify.classify_run(ref, eng, self.ts.dir)
        cls = {c["i"]: c["cls"] for c in res["cells"]}
        self.assertEqual(cls[3], "TIMEOUT")
        self.assertEqual(cls[7], "NOTRUN")

    def test_nondeterminism(self):
        ref, eng = self.build()
        _, ref2 = self.build()
        res = classify.classify_run(ref, eng, self.ts.dir, ref2=ref2)
        cls = {c["i"]: c["cls"] for c in res["cells"]}
        self.assertEqual(cls[1], "NONDET")   # ref2 differs from ref at cell 1
        same = classify.classify_run(ref, eng, self.ts.dir, ref2=ref)
        self.assertNotIn("NONDET", [c["cls"] for c in same["cells"]])

    def test_summary_counts(self):
        ref, eng = self.build()
        s = classify.classify_run(ref, eng, self.ts.dir)["summary"]
        self.assertEqual(s["n_cells"], 7)
        self.assertEqual(s["fallback_cells"], 1)
        self.assertEqual(sum(s["by_class"].values()), 7)

    def test_op_families(self):
        self.assertEqual(classify.op_families(["merge", "groupby"]), ["merge_join", "groupby_agg"])
        self.assertEqual(classify.op_families([]), ["other"])


if __name__ == "__main__":
    unittest.main()

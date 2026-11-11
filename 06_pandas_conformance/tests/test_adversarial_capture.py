"""Adversarial review of capture (2026-10-02): exotic values never break capture, E0 is
reflexive on copies, hashes do not depend on the Python hash seed, and the 'capped'
(UNCOMPARABLE) status depends on which runs wrote blobs first."""
import copy
import datetime as dt
import decimal
import json
import os
import subprocess
import sys
import unittest
import warnings

import numpy as np
import pandas as pd

from _common import TempStore, SRC, TESTS
from pconf import dfeq
from pconf.capture import Capturer


def exotic_values():
    idx = pd.MultiIndex.from_tuples([("a", 1), ("a", 2), ("b", 1)], names=["k", None])
    return {
        "mixed_object": pd.Series([1, "1", 1.0, True, None, np.nan, pd.NA, b"x", decimal.Decimal("1.10"),
                                   dt.date(2020, 1, 2), (1, 2), [3], {"a": 1}, {"s", "t"}], dtype=object),
        "surrogates": pd.Series(["ok", "\udc80bad", "\\xed"], dtype=object),
        "nul_and_unicode": pd.Series(["a\x00b", "é", "😀", ""], dtype=object),
        "period": pd.Series(pd.period_range("2020-01", periods=3, freq="M")),
        "interval": pd.Series(pd.interval_range(0, 3)),
        "tz_index": pd.DataFrame({"v": [1, 2]}, index=pd.DatetimeIndex(["2020-01-01", "2020-06-01"]).tz_localize("Asia/Tokyo")),
        "multiindex_rows": pd.DataFrame({"v": [1.0, 2.0, 3.0]}, index=idx),
        "sparse": pd.Series(pd.arrays.SparseArray([0, 0, 1.5, 0])),
        "complex": pd.Series([1 + 2j, np.nan + 0j]),
        "timedelta": pd.Series(pd.to_timedelta([1, None], unit="h")),
        "ordered_cat": pd.Series(pd.Categorical(["lo", "hi", None], categories=["lo", "hi"], ordered=True)),
        "int_cols_labels": pd.DataFrame([[1, 2]], columns=[0, 1.5]),
        "bool_with_na": pd.Series([True, None], dtype="boolean"),
        "arrow_list": pd.Series([[1, 2], None], dtype=pd.ArrowDtype(__import__("pyarrow").list_(__import__("pyarrow").int64()))),
        "empty_df": pd.DataFrame(),
        "set_of_str": {"pear", "apple", "fig"},
        "dict_mixed": {"b": 1, 2: [1, 2], None: np.nan},
        "nested_tuple": (1, (2, "x"), [None]),
        "zero_d": np.array(3.5),
        "struct": np.array([(1, 2.0)], dtype=[("a", "i4"), ("b", "f8")]),
    }


class TestExoticCapture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ts = TempStore()
        cls.cap = Capturer(cls.ts.dir)

    @classmethod
    def tearDownClass(cls):
        cls.ts.cleanup()

    def test_capture_never_raises_and_e0_is_reflexive(self):
        for name, v in exotic_values().items():
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                r1 = self.cap.capture(v)
                r2 = self.cap.capture(copy.deepcopy(v))
            self.assertIn("kind", r1, name)
            if name == "struct":
                self.assertIsNone(r1["h"])  # structured arrays are recorded as 'other' (not comparable)
                continue
            self.assertNotEqual(r1["kind"], "unconvertible", (name, r1.get("info")))
            self.assertIsNotNone(r1["h"], name)
            self.assertEqual(r1["h"], r2["h"], name)
            self.assertEqual(dfeq.compare(r1, r2, self.ts.dir)["level"], "E0", name)

    def test_hashes_independent_of_python_hash_seed(self):
        code = ("import sys, json, warnings; warnings.simplefilter('ignore'); sys.path[:0]=[%r, %r];"
                "import test_adversarial_capture as T; from pconf.capture import Capturer; import tempfile;"
                "c=Capturer(tempfile.mkdtemp());"
                "print(json.dumps({k: c.capture(v)['h'] for k, v in T.exotic_values().items()}))") % (SRC, TESTS)
        outs = []
        for seed in ("1", "2"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=300)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            outs.append(json.loads(r.stdout.strip().splitlines()[-1]))
        self.assertEqual(outs[0], outs[1])


class TestCappingOrderDependence(unittest.TestCase):
    def test_capped_status_recomputed_from_store_fixed(self):
        """Review documented: columns beyond the per-run blob budget are 'capped' unless another
        run already wrote the same blob, so comparability depended on run order. Fixed
        (2026-10-02): dfeq treats a column as available iff its blob is in the store at compare
        time, so both records compare alike (the record's own 'capped' flag still reflects
        what that run wrote)."""
        ts = TempStore()
        try:
            df = pd.DataFrame({"x": np.arange(1000, dtype="float64")})
            other = df * (1 + 1e-12)
            # run A: budget 0 -> nothing stored; run B (unlimited) stores df first
            first = Capturer(ts.dir, limits={"run_budget_bytes": 0}).capture(df)
            Capturer(ts.dir).capture(df)
            later = Capturer(ts.dir, limits={"run_budget_bytes": 0}).capture(df)
            self.assertEqual(first["h"], later["h"])
            self.assertTrue(first["info"]["capped"])
            self.assertFalse(later["info"]["capped"])
            eng = Capturer(ts.dir).capture(other)
            self.assertEqual(dfeq.compare(first, eng, ts.dir)["level"], "E2")
            self.assertEqual(dfeq.compare(later, eng, ts.dir)["level"], "E2")
        finally:
            ts.cleanup()


if __name__ == "__main__":
    unittest.main()

"""Capture: hashing determinism, E0 <=> hash equality, decode round trips, caps, and
serialisation round trips in EVERY engine environment (records written there, read here)."""
import json
import os
import subprocess
import unittest

import numpy as np
import pandas as pd

from _common import ALL_ENVS, TESTS, TempStore, env_python
from pconf import capture as C
from pconf import dfeq


class TestCaptureLocal(unittest.TestCase):
    def setUp(self):
        self.ts = TempStore()
        self.cap = C.Capturer(self.ts.dir)

    def tearDown(self):
        self.ts.cleanup()

    def test_hash_deterministic_and_dtype_sensitive(self):
        df = pd.DataFrame({"a": [1, 2], "b": [0.5, np.nan]})
        h1 = self.cap.capture(df)["h"]
        h2 = C.Capturer(self.ts.dir).capture(df.copy())["h"]
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, self.cap.capture(df.astype({"a": "int32"}))["h"])
        self.assertNotEqual(h1, self.cap.capture(df.rename(columns={"a": "z"}))["h"])
        self.assertNotEqual(h1, self.cap.capture(df.set_axis([5, 6]))["h"])

    def test_nan_payload_canonical(self):
        a = np.array([1.0, np.nan])
        b = a.copy()
        b.view(np.uint64)[1] = 0x7FF8000000000001  # a different quiet-NaN payload
        self.assertTrue(np.isnan(b[1]))
        self.assertEqual(self.cap.capture(pd.Series(a))["h"], self.cap.capture(pd.Series(b))["h"])

    def test_sentinels_distinguished(self):
        a = pd.Series(["x", None], dtype=object)
        b = pd.Series(["x", np.nan], dtype=object)
        self.assertNotEqual(self.cap.capture(a)["h"], self.cap.capture(b)["h"])

    def test_dedup_blobs(self):
        df = pd.DataFrame({"a": range(100), "b": range(100)})
        self.cap.capture(df)
        n1 = self.cap.blobs_written
        self.cap.capture(df.assign(c=1))  # only the new column (and nothing else) is new
        self.assertEqual(self.cap.blobs_written - n1, 1)

    def test_decode_roundtrip(self):
        objs = [
            pd.DataFrame({"i": [1, 2, 3], "f": [0.5, np.nan, 2.0], "s": ["a", None, "c"]}),
            pd.Series([1, None, 3], dtype="Int64", name="x"),
            pd.Series(pd.Categorical(["u", "v", "u"])),
            pd.Series(pd.to_datetime(["2020-01-01", None])),
            pd.Index([3, 1, 2], name="k"),
            np.arange(6).reshape(2, 3),
            (1, "a", 2.5), [None, 1], {"a": 1},
            3.25, "s", None,
        ]
        for o in objs:
            rec = self.cap.capture(o)
            back = C.decode_to_pandas(self.ts.dir, rec)
            rec2 = self.cap.capture(back)
            self.assertEqual(dfeq.compare(rec, rec2, self.ts.dir)["level"], "E0", repr(o))

    def test_extension_array_outputs(self):
        ea = pd.Series(["a", "b", "a"], dtype="string").unique()
        rec = self.cap.capture(ea)
        self.assertEqual(rec["kind"], "ndarray")
        self.assertEqual(rec["meta"]["array_type"], type(ea).__name__)
        nd = self.cap.capture(np.array(["a", "b"], dtype=object))
        self.assertEqual(dfeq.compare(nd, rec, self.ts.dir)["level"], "E2")
        back = C.decode_to_pandas(self.ts.dir, rec)
        self.assertEqual(self.cap.capture(back)["h"], rec["h"])
        ints = pd.array([1, None], dtype="Int64")
        self.assertEqual(dfeq.compare(self.cap.capture(ints), self.cap.capture(np.array([1.0, np.nan])), self.ts.dir)["level"], "E3")

    def test_cap_hash_only(self):
        cap = C.Capturer(self.ts.dir, limits={"max_cells": 10})
        big = pd.DataFrame({"a": range(20)})
        rec = cap.capture(big)
        self.assertTrue(rec["info"]["capped"])
        self.assertFalse(rec["cols"][0]["stored"])
        rec2 = cap.capture(big.assign(a=big.a + 1))
        self.assertEqual(dfeq.compare(rec, rec2, self.ts.dir)["level"], "UNCOMPARABLE")
        self.assertEqual(dfeq.compare(rec, cap.capture(big.copy()), self.ts.dir)["level"], "E0")

    def test_run_budget(self):
        cap = C.Capturer(self.ts.dir, limits={"run_budget_bytes": 1})
        r1 = cap.capture(pd.Series(range(1000)))
        r2 = cap.capture(pd.Series(range(1000, 2000)))
        self.assertTrue(r1["cols"][0]["stored"])  # first blob always fits (budget checked before write)
        self.assertFalse(r2["cols"][0]["stored"])
        self.assertGreaterEqual(cap.capped_columns, 1)

    def test_uncapturable_kinds(self):
        self.assertEqual(self.cap.capture(pd)["kind"], "module")
        self.assertEqual(self.cap.capture(len)["kind"], "callable")
        self.assertEqual(self.cap.capture(lambda x: x)["kind"], "callable")
        self.assertEqual(self.cap.capture(pd.DataFrame({"a": [1]}).groupby("a"))["kind"], "other")

    def test_tag_value_exact(self):
        self.assertEqual(C.tag_value(0.1)[1], repr(0.1))
        self.assertEqual(C.tag_value(np.float32(0.1))[1], repr(float(np.float32(0.1))))
        self.assertEqual(C.tag_value(np.int64(5))[:2], (C.T_INT, "5"))
        self.assertEqual(C.tag_value(True)[0], C.T_BOOL)
        self.assertEqual(C.tag_value(pd.NaT)[0], C.T_NAT)
        self.assertEqual(C.tag_value(pd.NA)[0], C.T_NA)
        self.assertEqual(C.tag_value(float("nan"))[0], C.T_NAN)


class TestCaptureEnvironments(unittest.TestCase):
    """Serialisation round trips in every environment: records are produced by each env's
    pandas/pyarrow/numpy and must load and compare here."""

    @classmethod
    def setUpClass(cls):
        cls.ts = TempStore()
        cls.recs = {}
        for env in ALL_ENVS:
            py = env_python(env)
            if py is None:
                continue
            engine = env if env in ("modin", "fireducks", "bodo", "dask") else "pandas"
            envv = dict(os.environ, PYTHONHASHSEED="0", BODO_NUM_WORKERS="1", RAY_ENABLE_MAC_LARGE_OBJECT_STORE="1")
            r = subprocess.run([py, os.path.join(TESTS, "env_roundtrip_script.py"), cls.ts.dir, engine],
                               capture_output=True, text=True, timeout=600, env=envv)
            lines = [l for l in r.stdout.splitlines() if l.startswith("{")]
            cls.recs[env] = json.loads(lines[-1]) if lines else {"__error__": r.stderr[-2000:]}

    @classmethod
    def tearDownClass(cls):
        cls.ts.cleanup()

    def test_all_envs_produced_records(self):
        for env in ALL_ENVS:
            if env_python(env) is None:
                continue
            self.assertIn(env, self.recs)
            self.assertNotIn("__error__", self.recs[env], "%s: %s" % (env, self.recs[env].get("__error__")))

    def test_records_decode_in_comparison_env(self):
        for env, recs in self.recs.items():
            for name, rec in recs.items():
                if rec.get("h") is None:
                    continue
                o = dfeq.Obj(rec, self.ts.dir)
                for c in o.cols + o.idx:  # decodes every stored column blob
                    self.assertEqual(len(c.miss), c.n, "%s %s" % (env, name))

    def test_same_pandas_version_identical_hashes(self):
        """Envs with pandas 2.3.3 (different numpy/pyarrow builds, e.g. fireducks has pyarrow 21)
        must produce bit-identical captures for the same plain-pandas objects."""
        ref = self.recs.get("ref")
        if not ref:
            self.skipTest("ref env missing")
        for env in ("modin", "fireducks", "bodo", "dask"):
            if env not in self.recs:
                continue
            for name, rec in ref.items():
                if name.startswith("pandas:"):
                    self.assertEqual(rec["h"], self.recs[env][name]["h"], "%s %s" % (env, name))

    def test_cross_version_levels(self):
        """pandas 1.5.3 must equal 2.3.3 bit-exactly on explicit-dtype objects; every object
        must at least be comparable across versions."""
        ref = self.recs.get("ref")
        if not ref:
            self.skipTest("ref env missing")
        if "p15" in self.recs:
            for name in ("pandas:Int64", "pandas:cat", "pandas:dt_ns", "pandas:ndarr", "pandas:col_f", "pandas:len"):
                self.assertEqual(ref[name]["h"], self.recs["p15"][name]["h"], name)
        for env in ("p15", "p30"):
            if env not in self.recs:
                continue
            for name, rec in ref.items():
                lv = dfeq.compare(rec, self.recs[env][name], self.ts.dir)["level"]
                self.assertNotEqual(lv, "UNCOMPARABLE", "%s %s" % (env, name))

    def test_engine_objects_convert(self):
        ref = self.recs.get("ref")
        if not ref:
            self.skipTest("ref env missing")
        for env in ("modin", "fireducks", "bodo", "dask"):
            if env not in self.recs:
                continue
            for name, rec in self.recs[env].items():
                if not name.startswith("engine:"):
                    continue
                self.assertIsNotNone(rec.get("h"), "%s %s: %s" % (env, name, rec.get("info")))
                base = ref["pandas:" + name.split(":", 1)[1]]
                lv = dfeq.compare(base, rec, self.ts.dir)["level"]
                self.assertIn(lv, dfeq.LEVELS + ["DIFF"], "%s %s" % (env, name))


if __name__ == "__main__":
    unittest.main()

"""Fix stage (2026-10-02): the row-matching step of dfeq (identity -> joint-key sort ->
bipartite matching inside tie groups), tested against the independent oracle and brute force."""
import itertools
import time
import unittest
import warnings

import numpy as np
import pandas as pd

import adversarial_oracle as O
from _common import TempStore
from pconf import dfeq
from pconf.capture import Capturer


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ts = TempStore()
        cls.cap = Capturer(cls.ts.dir)

    @classmethod
    def tearDownClass(cls):
        cls.ts.cleanup()

    def cmp(self, a, b):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return dfeq.compare(self.cap.capture(a), self.cap.capture(b), self.ts.dir)


class TestMatchingPath(_Base):
    LO, HI = 1.0000004999999999, 1.0000005000000001   # within 2e-16, straddle the 7-digit boundary

    def test_rounding_boundary_straddle_resolved_by_group_key(self):
        # a: (LO,5)@0 (HI,3)@1 ; b: (LO,3)@1 (HI,5)@0. The tolerant sort pairs (LO,5) with (LO,3);
        # grouping on the exact index then pairs rows by index and verifies.
        a = pd.DataFrame({"x": [self.LO, self.HI], "y": [5.0, 3.0]}, index=[0, 1])
        b = pd.DataFrame({"x": [self.LO, self.HI], "y": [3.0, 5.0]}, index=[1, 0])
        self.assertEqual(O.oracle_level(a, b), "E2")
        r = self.cmp(a, b)
        self.assertEqual(r["level"], "E2")
        self.assertEqual(r["match"], "matching")

    def test_bipartite_inside_a_tie_group(self):
        # duplicate index labels: one tie group of two rows; only bipartite matching pairs them
        a = pd.DataFrame({"x": [self.LO, self.HI], "y": [5.0, 3.0]}, index=[7, 7])
        b = pd.DataFrame({"x": [self.LO, self.HI], "y": [3.0, 5.0]}, index=[7, 7])
        self.assertEqual(O.oracle_level(a, b), "E2")
        r = self.cmp(a, b)
        self.assertEqual(r["level"], "E2")
        self.assertEqual(r["match"], "matching")
        # and a genuine difference in the same layout stays DIFF
        c = pd.DataFrame({"x": [self.LO, self.HI], "y": [3.0, 6.0]}, index=[7, 7])
        self.assertEqual(O.oracle_level(a, c), "DIFF")
        self.assertEqual(self.cmp(a, c)["level"], "DIFF")

    def test_bipartite_against_brute_force(self):
        rng = np.random.default_rng(3)
        for t in range(400):
            n = int(rng.integers(1, 7))
            ok = rng.random((n, n)) < rng.choice([0.2, 0.4, 0.7])
            m, _ = dfeq._bipartite(ok, 10 ** 6)
            exists = any(all(ok[i, p[i]] for i in range(n)) for p in itertools.permutations(range(n)))
            self.assertEqual(m is not None, exists, ok)
            if m is not None:
                self.assertEqual(sorted(m.tolist()), list(range(n)))
                self.assertTrue(all(ok[i, m[i]] for i in range(n)))

    def test_big_tie_group_with_noise_is_fast(self):
        rng = np.random.default_rng(0)
        n = 200_000
        a = pd.DataFrame({"g": rng.integers(0, 5, n).astype(float), "v": np.round(rng.random(n), 2)})
        b = a.sample(frac=1.0, random_state=1).reset_index(drop=True)
        b["v"] = b["v"] * (1 + 1e-13)
        t0 = time.time()
        r = self.cmp(a, b)
        self.assertEqual(r["level"], "E4")
        self.assertLess(time.time() - t0, 60)

    def test_diff_on_large_frame_terminates(self):
        rng = np.random.default_rng(1)
        n = 100_000
        a = pd.DataFrame({"v": rng.random(n)})
        b = a.copy()
        b.iloc[5, 0] += 1.0
        t0 = time.time()
        self.assertEqual(self.cmp(a, b)["level"], "DIFF")
        self.assertLess(time.time() - t0, 60)

    def test_wide_string_frame_diff_is_fast(self):
        # pilot 2026-10-02: a 355-column survey frame took 171 s to classify before the
        # hash-based joint keys and the per-column fail-fast check; now well under a few seconds
        rng = np.random.default_rng(2)
        a = pd.DataFrame({"c%d" % j: rng.choice(["x%d" % k for k in range(50)], 20_000).astype(object)
                          for j in range(300)})
        b = a.copy()
        b.iloc[17, 5] = "changed"
        t0 = time.time()
        self.assertEqual(self.cmp(a, b)["level"], "DIFF")
        self.assertEqual(self.cmp(a, a.iloc[::-1])["level"], "E1")
        self.assertLess(time.time() - t0, 60)

    def test_long_series_diff_and_permutation_are_fast(self):
        # pilot 2026-10-03: long Series (tens of millions of rows) made every level run several
        # multi-key sorts. Now: single-column feasibility first, cached sorts, constant keys pruned.
        rng = np.random.default_rng(3)
        n = 3_000_000
        a = pd.Series(rng.random(n), name="v")
        b = a.copy()
        b.iloc[123] = -1.0
        t0 = time.time()
        self.assertEqual(self.cmp(a, b)["level"], "DIFF")
        t_diff = time.time() - t0
        c = a.sample(frac=1.0, random_state=0)
        self.assertEqual(self.cmp(a, c)["level"], "E1")
        self.assertLess(t_diff, 30)
        self.assertLess(time.time() - t0, 90)

    def test_single_tolerant_column_shuffled_with_noise(self):
        # one tolerant column and no exact key: the exact value sort is the optimal pairing, so
        # group matching is skipped; equality modulo order and tolerance must still be found
        rng = np.random.default_rng(5)
        n = 1_000_000
        a = pd.Series(np.round(rng.random(n), 3) + 1.0000004999999999)
        b = (a * (1 + 1e-13)).sample(frac=1.0, random_state=2).reset_index(drop=True)
        t0 = time.time()
        r = self.cmp(a, b)
        self.assertEqual(r["level"], "E4")
        self.assertLess(time.time() - t0, 60)
        c = b.copy()
        c.iloc[7] += 1e-6
        self.assertEqual(self.cmp(a, c)["level"], "DIFF")

    def test_object_mixed_numbers_and_strings_shuffled(self):
        a = pd.Series([2, "x", 10, 2.5, None, "y"], dtype=object)
        b = pd.Series([10.0, "y", 2.0, "x", 2.5, np.nan], dtype=object)
        self.assertEqual(self.cmp(a, b)["level"], O.oracle_level(a, b))
        c = pd.Series([2, "x", 10, 2.5, None, "y"], dtype=object).iloc[::-1].reset_index(drop=True)
        self.assertEqual(self.cmp(a, c)["level"], "E4")

    def test_uint64_beyond_int64_and_int64(self):
        a = pd.Series([2 ** 63 + 5, 3], dtype="uint64")
        b = pd.Series([3, 2 ** 63 + 5], dtype="uint64").iloc[::-1]
        self.assertEqual(self.cmp(a, b.reset_index(drop=True))["level"], "E0")
        self.assertEqual(self.cmp(a, pd.Series([3, 2 ** 63 + 5], dtype="uint64"))["level"], "E4")

    def test_categorical_shuffled_with_other_categories(self):
        a = pd.Series(pd.Categorical(["x", "y", "x", None], categories=["x", "y"]))
        b = pd.Series(pd.Categorical(["y", None, "x", "x"], categories=["y", "x", "z"]))
        self.assertEqual(self.cmp(a, b)["level"], O.oracle_level(a, b))

    def test_signed_zero_rows_permuted_is_e1(self):
        a = pd.DataFrame({"x": [0.0, -0.0], "k": ["p", "p"]}, index=[1, 1])
        b = a.iloc[[1, 0]]
        self.assertEqual(O.oracle_level(a, b), "E1")
        self.assertEqual(self.cmp(a, b)["level"], "E1")

    def test_vacuous_object_vs_categorical_is_diff(self):
        a = pd.Series([None, None], dtype=object)
        b = pd.Series(pd.Categorical([None, None], categories=["x"]))
        self.assertEqual(O.oracle_level(a, b, vacuous_obj="any"), "DIFF")
        self.assertEqual(self.cmp(a, b)["level"], "DIFF")


class TestCappedStoreRecompute(_Base):
    def test_capped_flag_recomputed_from_store(self):
        small = Capturer(self.ts.dir, limits={"run_budget_bytes": 0})
        df = pd.DataFrame({"x": np.arange(50.0) + 0.123456})
        a = small.capture(df)
        self.assertTrue(a["info"]["capped"])
        self.assertEqual(dfeq.compare(a, self.cap.capture(df.iloc[::-1]), self.ts.dir)["level"], "UNCOMPARABLE")
        self.cap.capture(df)                       # another run stores the same columns
        b = self.cap.capture(df.iloc[::-1])
        # a's columns are now present in the store: comparable regardless of run order
        self.assertEqual(dfeq.compare(a, b, self.ts.dir)["level"], "E1")


if __name__ == "__main__":
    unittest.main()

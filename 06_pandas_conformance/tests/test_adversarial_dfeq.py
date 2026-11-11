"""Adversarial review of dfeq (2026-10-02): randomized differential tests against an INDEPENDENT
oracle (tests/adversarial_oracle.py: element-wise on pandas objects, row order decided by
bipartite matching, no pconf imports), targeted reproducers of confirmed comparator bugs, and
edge cases (empty inputs, duplicates, ties, boundaries).

Confirmed bugs were written as tests of the CORRECT behaviour decorated with
@unittest.expectedFailure; all were fixed in the fix stage (2026-10-02) and the decorators removed. Run in both the shared
venv (pandas 3.0.6) and the ref env (pandas 2.3.3, where campaign comparisons actually run):
    envs/ref/bin/python -m unittest discover -s tests -p 'test_adversarial_dfeq.py'
"""
import math
import unittest
import warnings

import numpy as np
import pandas as pd
import pandas.testing as pdt

import adversarial_gen as G
import adversarial_oracle as O
from _common import TempStore
from pconf import dfeq
from pconf.capture import Capturer

CLEAN_PERTURB = [p for p in G.PERTURBATIONS if p not in ("to_object", "noise_ulp", "noise_tiny")]


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ts = TempStore()
        cls.cap = Capturer(cls.ts.dir)

    @classmethod
    def tearDownClass(cls):
        cls.ts.cleanup()

    def dfeq_level(self, a, b):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return dfeq.compare(self.cap.capture(a), self.cap.capture(b), self.ts.dir)["level"]


# --------------------------------------------------------------------------- mismatch signatures
def _obj_numeric(x):
    cols = [x] if isinstance(x, pd.Series) else [x.iloc[:, j] for j in range(x.shape[1])]
    cols += [x.index.get_level_values(i) for i in range(x.index.nlevels)]
    for s in cols:
        if str(s.dtype) == "object" and any(isinstance(v, (int, float, np.integer, np.floating))
                                            and not isinstance(v, (bool, np.bool_)) and v == v for v in s):
            return True
    return False


def _float_ties(x):
    cols = [x] if isinstance(x, pd.Series) else [x.iloc[:, j] for j in range(x.shape[1])]
    for s in cols:
        if O.family(s) not in ("float",) and not (O.family(s) == "obj"):
            continue
        v = [float(e) for e in s if isinstance(e, (float, np.floating, int, np.integer)) and not isinstance(e, bool)
             and e == e and not O.missing_kind(e)]
        for i in range(len(v)):
            for j in range(i + 1, len(v)):
                if v[i] == v[j] or math.isclose(v[i], v[j], rel_tol=O.RTOL, abs_tol=0.0):
                    return True
    return False


def _big_int(x):
    cols = [x] if isinstance(x, pd.Series) else [x.iloc[:, j] for j in range(x.shape[1])]
    return any(isinstance(e, (int, np.integer)) and abs(int(e)) == 2 ** 53 + 1 for s in cols for e in s)


def signature(a, b):
    """Known-bug signature that explains a dfeq/oracle disagreement (None = unexplained)."""
    if _obj_numeric(a) or _obj_numeric(b):
        return "objnum_lexicographic_sort"
    if _big_int(a) or _big_int(b):
        return "int_2p53_plus_1_boundary"
    if _float_ties(a) or _float_ties(b):
        return "float_near_tie_sort"
    return None


def run_differential(test, seed, trials, clean):
    rng = np.random.default_rng(seed)
    mismatches, levels = [], {}
    for t in range(trials):
        if clean:
            a = G.gen_frame(rng, allow=("int", "float", "str", "bool", "dt", "cat"), big_int=False,
                            float_pool=G.FLOAT_POOL_NO_NEAR_TIES)
        else:
            a = G.gen_frame(rng)
        b, chain = a, []
        for _ in range(int(rng.integers(1, 4))):
            if clean:
                b, c = G.perturb(rng, b, choices=CLEAN_PERTURB, int_widen=("float64", "Int64", "int32"))
            else:
                b, c = G.perturb(rng, b)
            chain.append(c)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # Fix stage 2026-10-02: dfeq implements the vacuous reading of WIDENING_DOC (B3):
            # an object column with no non-missing value is compatible with every family.
            exp = O.oracle_level(a, b, vacuous_obj="any")
        got = test.dfeq_level(a, b)
        levels[exp] = levels.get(exp, 0) + 1
        if got != exp:
            mismatches.append({"trial": t, "oracle": exp, "dfeq": got, "chain": chain, "sig": signature(a, b),
                               "a": repr(a)[:400], "b": repr(b)[:400]})
    return mismatches, levels


class TestDifferentialVsIndependentOracle(_Base):
    def test_clean_domain_agrees_exactly(self):
        """Outside the three known bug triggers (object-held numbers, float near-ties, the
        int 2**53+1 boundary) dfeq must agree with the independent oracle on every trial, and
        every level must be exercised."""
        for seed in (101, 202):
            mism, levels = run_differential(self, seed, 1000, clean=True)
            self.assertEqual(mism, [], "seed %d: %d mismatches, first: %s" % (seed, len(mism), mism[:1]))
            for L in O.LEVELS + ["DIFF"]:
                self.assertGreater(levels.get(L, 0), 5, (seed, levels))

    def test_full_domain_mismatches_are_only_known_bugs(self):
        """With all triggers enabled, every disagreement must carry a known-bug signature; an
        unexplained disagreement is a NEW bug."""
        mism, levels = run_differential(self, 303, 1500, clean=False)
        unexplained = [m for m in mism if m["sig"] is None]
        self.assertEqual(unexplained, [], unexplained[:2])
        # direction of every known-bug disagreement: dfeq is coarser (or DIFF) where the oracle
        # finds a finer level, except the 2**53+1 boundary where dfeq is too lenient
        for m in mism:
            order = O.LEVELS + ["DIFF"]
            if m["sig"] == "int_2p53_plus_1_boundary":
                self.assertLess(order.index(m["dfeq"]), order.index(m["oracle"]), m)
            else:
                self.assertGreater(order.index(m["dfeq"]), order.index(m["oracle"]), m)

    def test_full_domain_no_mismatch(self):
        """Were KNOWN BUGS at the review (object-held numbers, float near-ties, the 2**53+1
        boundary); fixed 2026-10-02 (identity order, joint keys, bipartite matching)."""
        mism, _ = run_differential(self, 303, 1500, clean=False)
        self.assertEqual(mism, [])


class TestOracleSanity(_Base):
    """The oracle itself must agree with pandas.testing where both are defined."""

    def test_oracle_e0_vs_assert_frame_equal(self):
        rng = np.random.default_rng(9)
        for t in range(300):
            a = G.gen_frame(rng, allow=("int", "float", "bool", "dt"))
            b, _ = G.perturb(rng, a)
            if not isinstance(a, pd.DataFrame) or not isinstance(b, pd.DataFrame):
                continue
            try:
                pdt.assert_frame_equal(a, b, check_exact=True, check_freq=False, check_flags=False)
                pd_eq = True
            except AssertionError:
                pd_eq = False
            ours = O.level_holds(a, b, "E0")
            if ours:
                self.assertTrue(pd_eq, t)
            elif pd_eq:  # pandas treats -0.0 == 0.0; the oracle (bit-exact) does not
                self.assertTrue(any((np.signbit(a[c].to_numpy()) != np.signbit(b[c].to_numpy())).any()
                                    for c in a.columns if a[c].dtype.kind == "f"), t)

    def test_oracle_matching_finds_permutations(self):
        a = pd.DataFrame({"x": [1.0, 2.0, 2.0, 3.0], "k": ["p", "q", "r", "s"]})
        b = a.iloc[[3, 2, 0, 1]]
        self.assertEqual(O.oracle_level(a, b), "E1")
        self.assertEqual(O.oracle_level(a, b.reset_index(drop=True)), "E4")


# --------------------------------------------------------------------------- confirmed bugs
class TestConfirmedComparatorBugs(_Base):
    """Each test asserts the behaviour the plan's lattice requires."""

    def test_near_tie_same_row_order_frame(self):
        # summation-order noise (0.1+0.2 vs 0.3) on two rows that are mathematically tied:
        # same row order, values within 1e-9 -> E2. dfeq sorts each side by its own float bits,
        # the two sorts disagree, and the frame is reported DIFF.
        a = pd.DataFrame({"x": [0.1 + 0.2, 0.3], "k": ["a", "b"]})
        b = pd.DataFrame({"x": [0.3, 0.1 + 0.2], "k": ["a", "b"]})
        self.assertEqual(O.oracle_level(a, b), "E2")
        self.assertEqual(self.dfeq_level(a, b), "E2")

    def test_near_tie_groupby_series_is_not_an_index_difference(self):
        # a groupby-mean style result: same groups, same order, noise in the last bit.
        # dfeq reports E4 ("differs modulo index"), i.e. it misattributes float noise to the index.
        a = pd.Series([0.1 + 0.2, 0.3], index=pd.Index(["g1", "g2"], name="k"), name="v")
        b = pd.Series([0.3, 0.1 + 0.2], index=pd.Index(["g1", "g2"], name="k"), name="v")
        self.assertEqual(O.oracle_level(a, b), "E2")
        self.assertEqual(self.dfeq_level(a, b), "E2")

    def test_exact_tie_plus_ulp_noise(self):
        # exact duplicates in the reference + 1-ulp noise in the engine: the common case
        a = pd.Series([2.5, 2.5, 1.0], index=["p", "q", "r"])
        b = pd.Series([np.nextafter(2.5, 3.0), 2.5, 1.0], index=["p", "q", "r"])
        self.assertEqual(O.oracle_level(a, b), "E2")
        self.assertEqual(self.dfeq_level(a, b), "E2")

    def test_object_ints_vs_int64(self):
        # WIDENING {int,obj}: an object column holding ints vs int64, same order. dfeq's sort key for
        # object numbers is the string 'n|<repr(float)>' ('n|10.0' < 'n|2.0'), so the two sides
        # are sorted differently and the result is DIFF.
        a = pd.Series([2, 10], dtype=object)
        b = pd.Series([2, 10], dtype="int64")
        self.assertEqual(O.oracle_level(a, b), "E2")
        self.assertEqual(self.dfeq_level(a, b), "E2")

    def test_object_floats_vs_float64_negative(self):
        a = pd.Series([-1.5, -2.0, 3.0], dtype=object)
        b = pd.Series([-1.5, -2.0, 3.0])
        self.assertEqual(O.oracle_level(a, b), "E2")
        self.assertEqual(self.dfeq_level(a, b), "E2")

    def test_int_2p53_plus_1_widened_to_float_is_diff(self):
        # 2**53+1 is not representable in float64; dfeq checks representability AFTER the cast
        # (which rounds it to 2**53) and accepts the pair at E2.
        a = pd.Series([2 ** 53 + 1, 1], dtype="int64")
        b = a.astype("float64")
        self.assertEqual(O.oracle_level(a, b), "DIFF")
        self.assertEqual(self.dfeq_level(a, b), "DIFF")

    def test_all_missing_object_vs_all_nan_float(self):
        # WIDENING_DOC: 'object holding only bools/numbers (+ missing) <-> bool/int/float'. An
        # all-missing object column satisfies it vacuously; dfeq encodes it as 'str' -> DIFF.
        a = pd.Series([np.nan, np.nan], dtype=object)
        b = pd.Series([np.nan, np.nan], dtype="float64")
        self.assertEqual(O.oracle_level(a, b, vacuous_obj="any"), "E2")
        self.assertEqual(self.dfeq_level(a, b), "E2")

    def test_empty_object_vs_empty_float(self):
        # pandas 2.0 changed the default dtype of an empty Series from float64 to object: a drift
        # cell with no values at all is reported as a value-level DIFF.
        self.assertEqual(self.dfeq_level(pd.Series([], dtype=object), pd.Series([], dtype="float64")), "E2")


class TestCappedObjects(_Base):
    def test_capped_objects_with_different_shapes_are_diff(self):
        """Capped (hash-only) objects still carry shape, labels and dtypes. A row-count difference
        (e.g. a reader dropping rows) on a capped frame is reported UNCOMPARABLE instead of DIFF."""
        big = Capturer(self.ts.dir, limits={"max_cells": 5})
        a = big.capture(pd.DataFrame({"x": np.arange(10.0)}))
        b = big.capture(pd.DataFrame({"x": np.arange(9.0)}))
        self.assertTrue(a["info"]["capped"] and b["info"]["capped"])
        self.assertEqual(dfeq.compare(a, b, self.ts.dir)["level"], "DIFF")


# --------------------------------------------------------------------------- edge cases that hold
class TestEdgeCases(_Base):
    def test_empty_and_zero_column(self):
        e = pd.DataFrame({"a": pd.Series([], dtype="int64")})
        self.assertEqual(self.dfeq_level(e, e.copy()), "E0")
        self.assertEqual(self.dfeq_level(e, e.astype("float64")), "E2")
        z = pd.DataFrame(index=[0, 1, 2])
        self.assertEqual(self.dfeq_level(z, z.copy()), "E0")
        self.assertEqual(self.dfeq_level(z, pd.DataFrame(index=[0, 1])), "DIFF")
        self.assertEqual(self.dfeq_level(pd.DataFrame(), pd.DataFrame()), "E0")

    def test_duplicate_column_labels(self):
        a = pd.DataFrame([[1, 2], [3, 4]], columns=["x", "x"])
        self.assertEqual(self.dfeq_level(a, a.copy()), "E0")
        self.assertEqual(self.dfeq_level(a, a.iloc[:, ::-1]), "DIFF")  # same labels, swapped contents

    def test_duplicate_index_labels_shuffled(self):
        a = pd.DataFrame({"v": [1, 2, 3, 4]}, index=["k", "k", "m", "m"])
        self.assertEqual(self.dfeq_level(a, a.iloc[[3, 1, 2, 0]]), "E1")
        self.assertEqual(O.oracle_level(a, a.iloc[[3, 1, 2, 0]]), "E1")

    def test_multiindex_columns(self):
        a = pd.DataFrame([[1, 2.0], [3, 4.0]], columns=pd.MultiIndex.from_tuples([("a", 1), ("a", 2)]))
        self.assertEqual(self.dfeq_level(a, a.copy()), "E0")
        b = a.copy()
        b.columns = pd.MultiIndex.from_tuples([("a", 1), ("a", 3)])
        self.assertEqual(self.dfeq_level(a, b), "DIFF")
        c = a.astype({("a", 1): "float64"})
        self.assertEqual(self.dfeq_level(a, c), "E2")

    def test_tolerance_boundary_exact(self):
        x = 1.0
        y = x * (1 + 1e-9)  # relative difference just under/at 1e-9 in binary
        rel = abs(x - y) / max(abs(x), abs(y))
        lvl = self.dfeq_level(pd.Series([x]), pd.Series([y]))
        self.assertEqual(lvl, "E2" if rel <= 1e-9 else "DIFF")
        self.assertEqual(self.dfeq_level(pd.Series([1.0]), pd.Series([1.0 + 2e-9])), "DIFF")

    def test_infinities_and_nan(self):
        self.assertEqual(self.dfeq_level(pd.Series([np.inf, -np.inf]), pd.Series([np.inf, -np.inf])), "E0")
        self.assertEqual(self.dfeq_level(pd.Series([np.inf]), pd.Series([-np.inf])), "DIFF")
        self.assertEqual(self.dfeq_level(pd.Series([np.inf]), pd.Series([np.nan])), "DIFF")
        self.assertEqual(self.dfeq_level(pd.Series([1e308]), pd.Series([np.inf])), "DIFF")

    def test_signed_zero_is_e2_not_e0(self):
        self.assertEqual(self.dfeq_level(pd.Series([0.0]), pd.Series([-0.0])), "E2")

    def test_int64_extremes_and_uint64(self):
        imax, imin = np.iinfo(np.int64).max, np.iinfo(np.int64).min
        a = pd.Series([imax, imin], dtype="int64")
        self.assertEqual(self.dfeq_level(a, a.copy()), "E0")
        self.assertEqual(self.dfeq_level(a, a.astype("Int64")), "E2")
        self.assertEqual(self.dfeq_level(a, a.astype("float64")), "DIFF")  # not representable
        u = pd.Series([2 ** 63 + 5], dtype="uint64")
        self.assertEqual(self.dfeq_level(u, pd.Series([2 ** 63 + 5], dtype="UInt64")), "E2")

    def test_timezones_and_units(self):
        s = pd.Series(pd.to_datetime(["2020-01-01 12:00"]).tz_localize("UTC"))
        self.assertEqual(self.dfeq_level(s, s.dt.tz_convert("Europe/Paris")), "DIFF")  # same instant, other tz
        n = pd.Series(pd.to_datetime(["2020-01-01 12:00:00.000001"])).astype("datetime64[ns]")
        self.assertEqual(self.dfeq_level(n, n.astype("datetime64[us]")), "E2")
        self.assertEqual(self.dfeq_level(n, n.astype("datetime64[s]")), "DIFF")  # truncation is a value change

    def test_sentinels_chain(self):
        a = pd.Series([1.0, np.nan])
        self.assertEqual(self.dfeq_level(a, pd.Series([1.0, None], dtype=object)), "E3")
        self.assertEqual(self.dfeq_level(a, pd.Series([1, None], dtype="Int64")), "E3")
        self.assertEqual(self.dfeq_level(pd.Series([pd.NaT, pd.Timestamp("2020")]),
                                         pd.Series([None, pd.Timestamp("2020")], dtype=object)), "DIFF")  # dt vs obj family

    def test_scalars_and_arrays(self):
        self.assertEqual(self.dfeq_level(np.nan, pd.NA), "E3")
        self.assertEqual(self.dfeq_level(np.float64(0.1 + 0.2), 0.3), "E2")
        self.assertEqual(self.dfeq_level(2 ** 53 + 1, float(2 ** 53 + 1)), "DIFF")  # scalar path is exact
        self.assertEqual(self.dfeq_level(np.array([], dtype="int64"), np.array([], dtype="int64")), "E0")
        self.assertEqual(self.dfeq_level(np.zeros((2, 0)), np.zeros((2, 0))), "E0")

    def test_levels_never_skip_on_random_pairs(self):
        """Chain property under the full generator: check_levels is monotone."""
        rng = np.random.default_rng(55)
        for t in range(300):
            a = G.gen_frame(rng)
            b, _ = G.perturb(rng, a)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                lv = dfeq.check_levels(self.cap.capture(a), self.cap.capture(b), self.ts.dir)
            seen = False
            for L in dfeq.LEVELS:
                if lv[L]:
                    seen = True
                else:
                    self.assertFalse(seen, (t, lv))


if __name__ == "__main__":
    unittest.main()

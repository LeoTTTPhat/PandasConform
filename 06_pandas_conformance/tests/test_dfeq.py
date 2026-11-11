"""dfeq: every lattice level, every widening-table dtype pair, sentinels, row order, index,
randomized differential tests against independent oracles (pandas.testing), monotonicity."""
import unittest

import numpy as np
import pandas as pd
import pandas.testing as pdt

from _common import TempStore
from pconf import dfeq
from pconf.capture import Capturer


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ts = TempStore()
        cls.cap = Capturer(cls.ts.dir)

    @classmethod
    def tearDownClass(cls):
        cls.ts.cleanup()

    def level(self, a, b):
        return dfeq.compare(self.cap.capture(a), self.cap.capture(b), self.ts.dir)["level"]

    def levels(self, a, b):
        return dfeq.check_levels(self.cap.capture(a), self.cap.capture(b), self.ts.dir)


def base_df():
    return pd.DataFrame({"i": np.array([3, 1, 2, 5], dtype="int64"),
                         "f": [0.25, 1.5, np.nan, -2.0],
                         "s": np.array(["b", "a", None, "c"], dtype=object),
                         "d": pd.to_datetime(["2020-01-01", None, "2021-02-03", "2019-12-31"]).astype("datetime64[ns]"),
                         "b": [True, False, True, True]})


class TestLevels(Base):
    def test_e0_identical(self):
        df = base_df()
        self.assertEqual(self.level(df, df.copy()), "E0")

    def test_e1_row_order_index_carried(self):
        df = base_df()
        self.assertEqual(self.level(df, df.iloc[[3, 0, 2, 1]]), "E1")

    def test_e1_not_reached_when_index_detached(self):
        df = base_df()
        shuffled = df.iloc[[3, 0, 2, 1]].copy()
        shuffled.index = df.index  # rows moved, labels did not: index no longer carried with rows
        self.assertEqual(self.level(df, shuffled), "E4")

    def test_e2_int_to_float(self):
        df = base_df()
        self.assertEqual(self.level(df, df.astype({"i": "float64"})), "E2")

    def test_e2_int_not_representable(self):
        a = pd.Series([2 ** 60 + 1, 1], dtype="int64")
        b = a.astype("float64")
        self.assertEqual(self.level(a, b), "DIFF")

    def test_e2_float_tolerance_boundary(self):
        a = pd.Series([1.0, 1000.0, -3.5])
        self.assertEqual(self.level(a, a * (1 + 5e-10)), "E2")
        self.assertEqual(self.level(a, a * (1 + 5e-9)), "DIFF")

    def test_e2_relative_only_no_abs_tol(self):
        a = pd.Series([0.0, 1.0])
        b = pd.Series([1e-17, 1.0])
        self.assertEqual(self.level(a, b), "DIFF")  # plan: relative tolerance only

    def test_e2_datetime_units(self):
        s = pd.Series(pd.to_datetime(["2020-01-01 00:00:01", None])).astype("datetime64[ns]")
        self.assertEqual(self.level(s, s.astype("datetime64[us]")), "E2")
        self.assertEqual(self.level(s, s.astype("datetime64[s]")), "E2")

    def test_tz_mismatch_is_diff(self):
        s = pd.Series(pd.to_datetime(["2020-01-01"])).dt.tz_localize("UTC")
        self.assertEqual(self.level(s, s.dt.tz_convert("US/Eastern")), "DIFF")

    def test_e2_bool_boolean(self):
        s = pd.Series([True, False, True])
        self.assertEqual(self.level(s, s.astype("boolean")), "E2")

    def test_e2_object_string(self):
        s = pd.Series(["a", "b", "c"], dtype=object)
        self.assertEqual(self.level(s, s.astype("string")), "E2")
        self.assertEqual(self.level(s, s.astype("string[pyarrow]")), "E2")

    def test_e3_sentinels(self):
        s_nan = pd.Series(["a", np.nan, "c"], dtype=object)
        s_none = pd.Series(["a", None, "c"], dtype=object)
        s_na = pd.Series(["a", None, "c"], dtype="string")
        self.assertEqual(self.level(s_nan, s_none), "E3")
        self.assertEqual(self.level(s_nan, s_na), "E3")
        f = pd.Series([1.0, np.nan])
        self.assertEqual(self.level(f, f.astype("Float64")), "E3")
        i = pd.Series([1, None], dtype="Int64")
        self.assertEqual(self.level(f, i), "E3")

    def test_missing_mask_mismatch_is_diff(self):
        a = pd.Series([1.0, np.nan, 3.0])
        b = pd.Series([1.0, 2.0, np.nan])
        self.assertEqual(self.level(a, b), "DIFF")

    def test_e4_index_reset_and_names(self):
        df = base_df().set_index("i")
        self.assertEqual(self.level(df, df.reset_index(drop=True)), "E4")
        s = pd.Series([1, 2], name="x")
        self.assertEqual(self.level(s, s.rename("count")), "E4")
        df2 = df.copy()
        df2.index.name = "other"
        self.assertEqual(self.level(df, df2), "E4")

    def test_diff_values_and_labels(self):
        df = base_df()
        self.assertEqual(self.level(df, df.assign(i=[3, 1, 2, 6])), "DIFF")
        self.assertEqual(self.level(df, df[["f", "i", "s", "d", "b"]]), "DIFF")  # column order is never relaxed
        self.assertEqual(self.level(df, df.rename(columns={"f": "g"})), "DIFF")
        self.assertEqual(self.level(df, df.iloc[:3]), "DIFF")

    def test_kind_mismatch_diff(self):
        df = base_df()
        self.assertEqual(self.level(df[["i"]], df["i"]), "DIFF")

    def test_uncomparable(self):
        df = base_df()
        g = df.groupby("i")
        r = dfeq.compare(self.cap.capture(g), self.cap.capture(df), self.ts.dir)
        self.assertEqual(r["level"], "UNCOMPARABLE")

    def test_scalars(self):
        self.assertEqual(self.level(np.int64(3), np.int64(3)), "E0")
        self.assertEqual(self.level(np.int64(3), 3), "E2")
        self.assertEqual(self.level(3, 3.0), "E2")
        self.assertEqual(self.level(0.1 + 0.2, 0.3), "E2")
        self.assertEqual(self.level(np.nan, None), "E3")
        self.assertEqual(self.level(pd.NaT, np.nan), "E3")
        self.assertEqual(self.level(True, 1), "DIFF")
        self.assertEqual(self.level("a", "b"), "DIFF")
        self.assertEqual(self.level(pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-01").to_pydatetime()), "E2")

    def test_categorical(self):
        a = pd.Series(pd.Categorical(["x", "y", "x"], categories=["x", "y"]))
        b = pd.Series(pd.Categorical(["x", "y", "x"], categories=["y", "x"]))
        self.assertEqual(self.level(a, a.copy()), "E0")
        self.assertEqual(self.level(a, b), "E2")
        self.assertEqual(self.level(a, a.astype(object)), "DIFF")  # category <-> object is not in the table

    def test_index_objects_and_arrays(self):
        idx = pd.Index(["a", "b"], name="n")
        self.assertEqual(self.level(idx, idx.rename("m")), "E4")
        arr = np.array([[1, 2], [3, 4]])
        self.assertEqual(self.level(arr, arr.astype(float)), "E2")
        self.assertEqual(self.level(arr, arr[::-1]), "E1")

    def test_containers(self):
        self.assertEqual(self.level((3, 4), (3, 4)), "E0")
        self.assertEqual(self.level([1, 2, 3], [3, 1, 2]), "E1")
        self.assertEqual(self.level({"a": 1}, {"a": 1.0}), "E2")

    def test_multiindex(self):
        df = pd.DataFrame({"k1": ["a", "a", "b"], "k2": [1, 2, 1], "v": [1.0, 2.0, 3.0]}).set_index(["k1", "k2"])
        self.assertEqual(self.level(df, df.iloc[::-1]), "E1")
        self.assertEqual(self.level(df, df.reset_index()), "DIFF")  # different shape

    def test_pyarrow_backend_family(self):
        df = pd.DataFrame({"i": [1, 2, 3], "f": [0.5, 1.5, 2.5], "s": ["a", "b", "c"]})
        self.assertEqual(self.level(df, df.convert_dtypes(dtype_backend="pyarrow")), "E2")

    def test_widening_table_pairs(self):
        """Every same-family dtype pair and cross-family pair listed in WIDENING reaches E2 on
        values without missing data, and non-listed pairs do not."""
        cases_e2 = [
            (pd.Series([1, 2], dtype="int32"), pd.Series([1, 2], dtype="int64")),
            (pd.Series([1, 2], dtype="uint8"), pd.Series([1, 2], dtype="Int64")),
            (pd.Series([1, 2], dtype="int64"), pd.Series([1, 2], dtype="int64[pyarrow]")),
            (pd.Series([1.5, 2], dtype="float32"), pd.Series([1.5, 2], dtype="float64")),
            (pd.Series([1.5, 2], dtype="Float64"), pd.Series([1.5, 2], dtype="double[pyarrow]")),
            (pd.Series([1, 2], dtype="int64"), pd.Series([1.0, 2.0], dtype="float64")),
            (pd.Series([True, False]), pd.Series([True, False], dtype="bool[pyarrow]")),
            (pd.Series(["a", "b"], dtype=object), pd.Series(["a", "b"], dtype="string[python]")),
            (pd.Series(["a", 1], dtype=object), pd.Series(["a", "1"], dtype=object).astype("string")),
            (pd.Series([True, False], dtype=object), pd.Series([True, False], dtype="boolean")),
            (pd.Series([1, 2.5], dtype=object), pd.Series([1.0, 2.5])),
            (pd.Series(pd.to_timedelta([1, 2], unit="s")), pd.Series(pd.to_timedelta([1, 2], unit="s")).astype("timedelta64[ms]")),
        ]
        for a, b in cases_e2:
            got = self.level(a, b)
            if a.dtype == object and str(b.dtype) == "string" and a.tolist() == ["a", 1]:
                self.assertEqual(got, "DIFF", (a.dtype, b.dtype))  # 1 vs '1': value differs
            else:
                self.assertEqual(got, "E2", (a.dtype, b.dtype))
        cases_diff = [
            (pd.Series([True, False]), pd.Series([1, 0])),
            (pd.Series(["1", "2"], dtype=object), pd.Series([1, 2])),
            (pd.Series(pd.to_datetime(["2020-01-01"])), pd.Series(["2020-01-01"], dtype=object)),
        ]
        for a, b in cases_diff:
            self.assertEqual(self.level(a, b), "DIFF", (a.dtype, b.dtype))


# --------------------------------------------------------------------------- randomized
def random_frame(rng, n=None):
    n = n if n is not None else int(rng.integers(0, 40))
    cols = {}
    for j in range(int(rng.integers(1, 5))):
        kind = rng.choice(["int", "float", "str", "bool", "dt"])
        if kind == "int":
            cols["c%d" % j] = rng.integers(-5, 5, n)
        elif kind == "float":
            v = rng.normal(size=n) * 10 ** float(rng.integers(-3, 6))
            if n:
                v[rng.random(n) < 0.2] = np.nan
            cols["c%d" % j] = v
        elif kind == "str":
            v = np.array([rng.choice(list("abcde")) for _ in range(n)], dtype=object)
            if n:
                v[rng.random(n) < 0.2] = None
            cols["c%d" % j] = v
        elif kind == "bool":
            cols["c%d" % j] = rng.random(n) < 0.5
        else:
            cols["c%d" % j] = pd.to_datetime(rng.integers(1.5e9, 1.7e9, n), unit="s").astype("datetime64[ns]")
    df = pd.DataFrame(cols)
    if rng.random() < 0.3:
        df.index = pd.Index(rng.permutation(n) * 3, dtype="int64")
    return df


def _kind(s):
    t = pd.api.types
    if t.is_bool_dtype(s.dtype):
        return "bool"
    if t.is_integer_dtype(s.dtype):
        return "int"
    if t.is_float_dtype(s.dtype):
        return "float"
    if t.is_datetime64_any_dtype(s.dtype):
        return "dt"
    return "str"  # object (pandas <3) or str (pandas 3)


def perturb(rng, df):
    """Apply one transformation with a known expected level (pandas-version agnostic)."""
    choice = rng.choice(["same", "shuffle", "widen_int", "tol", "sentinel", "reset", "value"])
    out = df.copy()
    n = len(df)
    kinds = {c: _kind(df[c]) for c in df.columns}
    if choice == "same":
        return out, "E0"
    if choice == "shuffle":
        if n < 2:
            return out, "E0"
        perm = rng.permutation(n)
        if (perm == np.arange(n)).all():
            return out, "E0"
        return df.iloc[perm], "E1"
    if choice == "widen_int":
        ints = [c for c in df.columns if kinds[c] == "int"]
        if not ints or n == 0:
            return out, "E0"
        out[ints[0]] = out[ints[0]].astype("float64")
        return out, "E2"
    if choice == "tol":
        fl = [c for c in df.columns if kinds[c] == "float" and (df[c].fillna(0) != 0).any()]
        if not fl:
            return out, "E0"
        out[fl[0]] = out[fl[0]] * (1 + 1e-12)
        return out, ("E0" if out[fl[0]].equals(df[fl[0]]) else "E2")
    if choice == "sentinel":
        st = [c for c in df.columns if kinds[c] == "str" and df[c].isna().any()]
        if not st:
            return out, "E0"
        out[st[0]] = out[st[0]].astype("string")  # NA sentinel instead of None/NaN
        return out, "E3"
    if choice == "reset":
        if n == 0 or (df.index == pd.RangeIndex(n)).all():
            return out, "E0"
        return out.reset_index(drop=True), "E4"
    if choice == "value":
        if n == 0:
            return out, "E0"
        c = df.columns[0]
        k = kinds[c]
        col = out[c].copy()
        if k == "int":
            col.iloc[0] = int(df[c].iloc[0]) + 100
        elif k == "float":
            col.iloc[0] = 0.0 if pd.isna(df[c].iloc[0]) else df[c].iloc[0] * 2 + 1
        elif k == "bool":
            col.iloc[0] = not df[c].iloc[0]
        elif k == "str":
            col.iloc[0] = "zz"
        else:
            col.iloc[0] = pd.Timestamp("1999-01-01")
        out[c] = col
        return out, "DIFF"
    raise AssertionError(choice)


class TestRandomized(Base):
    N = 400

    def test_random_known_levels(self):
        rng = np.random.default_rng(20261002)
        counts = {}
        for t in range(self.N):
            df = random_frame(rng)
            other, expect = perturb(rng, df)
            got = self.level(df, other)
            counts[expect] = counts.get(expect, 0) + 1
            self.assertEqual(got, expect, "trial %d: expected %s got %s\n%s\n%s" % (t, expect, got, df, other))
        for L in ("E0", "E1", "E2", "E3", "E4", "DIFF"):
            self.assertGreater(counts.get(L, 0), 5, counts)

    def test_e0_matches_assert_frame_equal(self):
        """Independent oracle: E0 <=> pandas.testing.assert_frame_equal(check_exact=True) on
        frames without object-sentinel ambiguity."""
        rng = np.random.default_rng(7)
        agree = 0
        for t in range(self.N):
            df = random_frame(rng)
            other, _ = perturb(rng, df)
            try:
                pdt.assert_frame_equal(df, other, check_exact=True, check_index_type=True, check_column_type=True,
                                       check_freq=False, check_flags=False)
                pd_eq = True
            except AssertionError:
                pd_eq = False
            ours = self.level(df, other) == "E0"
            if pd_eq and not ours:
                # assert_frame_equal treats NaN/None/NA as equal missing values; E0 does not
                na = any(_kind(df[c]) == "str" and df[c].isna().any() for c in df.columns)
                self.assertTrue(na, "trial %d: pandas equal but dfeq not E0" % t)
            elif ours:
                self.assertTrue(pd_eq, "trial %d: dfeq E0 but pandas differs" % t)
            agree += pd_eq == ours
        self.assertGreater(agree, self.N * 0.9)

    def test_e1_matches_sorted_assert_frame_equal(self):
        rng = np.random.default_rng(11)
        for t in range(200):
            df = random_frame(rng)
            if len(df) < 2:
                continue
            perm = rng.permutation(len(df))
            other = df.iloc[perm]
            self.assertIn(self.level(df, other), ("E0", "E1"), t)
            key = list(df.columns)
            a = df.reset_index().sort_values(key + ["index"], kind="mergesort", na_position="last").reset_index(drop=True)
            b = other.reset_index().sort_values(key + ["index"], kind="mergesort", na_position="last").reset_index(drop=True)
            pdt.assert_frame_equal(a, b)

    def test_monotone_chain(self):
        rng = np.random.default_rng(3)
        for t in range(self.N):
            df = random_frame(rng)
            other, _ = perturb(rng, df)
            if rng.random() < 0.3:
                other, _ = perturb(rng, other)
            lv = self.levels(df, other)
            seen = False
            for L in dfeq.LEVELS:
                if lv[L]:
                    seen = True
                elif seen:
                    self.fail("trial %d: non-monotone %s" % (t, lv))
            got = self.level(df, other)
            first = next((L for L in dfeq.LEVELS if lv[L]), "DIFF")
            self.assertEqual(got, first, t)


if __name__ == "__main__":
    unittest.main()

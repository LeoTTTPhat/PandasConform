"""Random frame generator and perturbations for the adversarial differential tests (review
2026-10-02). Values are drawn from small pools so that duplicates, ties, near-ties (values equal
within 1e-9 but not bit-equal), signed zeros, infinities, missing sentinels and empty frames are
frequent. Perturbations compose (1 to 3 per trial)."""
import numpy as np
import pandas as pd

FLOAT_POOL = [0.0, -0.0, 1.0, 2.5, 0.1 + 0.2, 0.3, 1e-300, -7.25, 1e15 + 0.5, np.inf, -np.inf, np.nan, 10.0, 2.0]
# no two values within 1e-9 of each other and no value where +1000 stays within tolerance
FLOAT_POOL_NO_NEAR_TIES = [0.0, -0.0, 1.0, 2.5, 0.3, 1e-300, -7.25, np.inf, -np.inf, np.nan, 10.0, 2.0]
INT_POOL = [0, 1, 2, 3, -1, 10, 2 ** 53 + 1]
STR_POOL = ["a", "b", "c", "", "10", "2", None]
OBJNUM_POOL = [2, 10, -1, 2.5, -2.0, 0.5, None]


def gen_frame(rng, allow=("int", "float", "str", "bool", "dt", "objnum", "cat"), nmax=7, ncols=(1, 4), big_int=True, float_pool=None):
    n = int(rng.integers(0, nmax + 1))
    cols = {}
    for j in range(int(rng.integers(ncols[0], ncols[1] + 1))):
        kind = str(rng.choice(list(allow)))
        name = "c%d" % j
        if kind == "int":
            pool = INT_POOL if (big_int and rng.random() < 0.2) else INT_POOL[:-1]
            cols[name] = pd.Series(np.array([pool[k] for k in rng.integers(0, len(pool), n)], dtype="int64"))
        elif kind == "float":
            fp = float_pool or FLOAT_POOL
            cols[name] = pd.Series(np.array([fp[k] for k in rng.integers(0, len(fp), n)], dtype="float64"))
        elif kind == "str":
            cols[name] = pd.Series(np.array([STR_POOL[k] for k in rng.integers(0, len(STR_POOL), n)], dtype=object), dtype=object)
        elif kind == "bool":
            cols[name] = pd.Series(rng.random(n) < 0.5)
        elif kind == "dt":
            v = pd.to_datetime(rng.integers(0, 3, n) * 86400 + 1.6e9, unit="s").astype("datetime64[ns]")
            s = pd.Series(v)
            if n and rng.random() < 0.3:
                s.iloc[0] = pd.NaT
            cols[name] = s
        elif kind == "objnum":
            cols[name] = pd.Series(np.array([OBJNUM_POOL[k] for k in rng.integers(0, len(OBJNUM_POOL), n)], dtype=object), dtype=object)
        elif kind == "cat":
            v = [["x", "y", "z", None][k] for k in rng.integers(0, 4, n)]
            cols[name] = pd.Series(pd.Categorical(v, categories=["x", "y", "z"]))
    df = pd.DataFrame(cols)
    r = rng.random()
    if r < 0.25:
        df.index = pd.Index(rng.permutation(n) * 3, dtype="int64")
    elif r < 0.4:
        df.index = pd.Index([["k", "m"][k] for k in rng.integers(0, 2, n)], dtype=object)  # duplicate labels
    if rng.random() < 0.25 and df.shape[1] >= 1:
        return df.iloc[:, 0]  # a Series
    return df


def _cols(x):
    return [x] if isinstance(x, pd.Series) else [x.iloc[:, j] for j in range(x.shape[1])]


def _set_col(x, j, s):
    """Replace column j (or the Series' values) by the values of `s`, positionally (no alignment)."""
    if isinstance(x, pd.Series):
        return pd.Series(s.array, index=x.index, name=x.name)
    out = x.copy()
    out.isetitem(j, s.array)
    return out


PERTURBATIONS = ["shuffle", "shuffle_detach", "widen", "noise_tiny", "noise_ulp", "noise_big", "sentinel",
                 "to_string", "to_object", "value", "reset", "rename"]


def perturb(rng, x, choice=None, choices=None, int_widen=("float64", "Int64", "int32", "object")):
    """Return (transformed copy, perturbation name); no expected level: the oracle decides."""
    choice = choice or str(rng.choice(list(choices or PERTURBATIONS)))
    n = len(x)
    cols = _cols(x)
    j = int(rng.integers(0, len(cols))) if cols else 0
    if choice == "shuffle" and n > 1:
        return x.iloc[rng.permutation(n)], choice
    if choice == "shuffle_detach" and n > 1:
        y = x.iloc[rng.permutation(n)].copy()
        y.index = x.index
        return y, choice
    if not cols:
        return x.copy(), choice
    s = cols[j]
    k = s.dtype.kind if isinstance(s.dtype, np.dtype) else "x"
    if choice == "widen":
        if k in "iu":
            t = str(rng.choice(list(int_widen)))
            try:
                s2 = s.astype(t) if t != "object" else pd.Series(np.array([int(v) for v in s], dtype=object), dtype=object)
            except (OverflowError, TypeError, ValueError):
                return x.copy(), choice
            return _set_col(x, j, s2), choice
        if k == "b":
            return _set_col(x, j, s.astype(str(rng.choice(["boolean", "object"] if "object" in int_widen else ["boolean"])))), choice
        if k == "M":
            return _set_col(x, j, s.astype("datetime64[us]")), choice
        if k == "f":
            return _set_col(x, j, s.astype(str(rng.choice(["Float64", "float32"])))), choice
    if choice in ("noise_tiny", "noise_ulp", "noise_big") and k == "f":
        v = s.to_numpy(copy=True)
        if choice == "noise_tiny":
            v = v * (1 + float(rng.choice([1e-12, -1e-12, 3e-10])))
        elif choice == "noise_ulp":
            m = rng.random(len(v)) < 0.5
            v[m] = np.nextafter(v[m], np.inf)
        else:
            v = v * (1 + 1e-6)
        return _set_col(x, j, pd.Series(v, dtype="float64")), choice
    if choice == "sentinel" and k == "O":
        v = s.to_numpy(copy=True)
        for i in range(len(v)):
            if v[i] is None:
                v[i] = np.nan
        return _set_col(x, j, pd.Series(v, dtype=object)), choice
    if choice == "to_string" and k == "O" and all(isinstance(v, str) or v is None for v in s):
        return _set_col(x, j, s.astype(str(rng.choice(["string", "string[pyarrow]"])))), choice
    if choice == "to_object" and k in ("f", "i"):
        return _set_col(x, j, pd.Series(np.array([v.item() if hasattr(v, "item") else v for v in s], dtype=object),
                                        dtype=object)), choice
    if choice == "value" and n:
        v = s.astype(object).to_numpy(copy=True)
        v[0] = "zz" if not isinstance(v[0], (int, float, np.number)) or isinstance(v[0], bool) else v[0] + 1000
        try:
            return _set_col(x, j, pd.Series(v, dtype=s.dtype if not isinstance(s.dtype, pd.CategoricalDtype) else object)), choice
        except (TypeError, ValueError):
            return _set_col(x, j, pd.Series(v, dtype=object)), choice
    if choice == "reset" and n:
        return x.reset_index(drop=True), choice
    if choice == "rename":
        y = x.copy()
        if isinstance(y, pd.Series):
            y.name = "renamed"
        else:
            y.index.name = "renamed"
        return y, choice
    return x.copy(), "noop"

"""Independent reference oracle for the equivalence lattice (review 2026-10-02).

Written from plan.md Section 2 and dfeq.WIDENING_DOC only. It never imports pconf: it works on
pandas objects element by element (``.iloc`` values), and it decides "modulo row order" by
bipartite row MATCHING (does a permutation exist?) instead of by a canonical sort. It is slow
and meant for small frames (tens of rows).

Level semantics (cumulative chain, as in the plan):
  E0  same kind, shape, dtype strings, labels (with python types), names, index; values identical
      (floats bit-identical except NaN payloads; same missing sentinel; same python element types)
  E1  E0 modulo a row permutation (index carried with its row)
  E2  E1 + dtype widening (families below) + float relative tolerance 1e-9 (no absolute tol.)
  E3  E2 + NaN/None/NA/NaT unified
  E4  E3 + index ignored; index names, column-axis names and Series names ignored
Families: bool, int, float, str, obj, dt(tz), td, cat. Compatible at E2+: equal families and the
unordered pairs {int,float}, {str,obj}, {bool,obj}, {int,obj}, {float,obj}. An object column whose
non-missing elements are all str is 'str'; ``vacuous_obj`` controls what an object column with NO
non-missing element is (dfeq encodes it as 'str'; WIDENING_DOC also allows reading it as
'object holding only numbers (+missing)', i.e. compatible with every family above).
"""
import math

import numpy as np
import pandas as pd

LEVELS = ["E0", "E1", "E2", "E3", "E4"]
RTOL = 1e-9
MAX_EXACT = 2 ** 53
PAIRS = {frozenset(p) for p in (("int", "float"), ("str", "obj"), ("bool", "obj"), ("int", "obj"), ("float", "obj"))}


# ----------------------------------------------------------------------------- elements
def missing_kind(v):
    if v is None:
        return "none"
    if v is pd.NA:
        return "na"
    if v is pd.NaT:
        return "nat"
    if isinstance(v, (float, np.floating)) and v != v:
        return "nan"
    if isinstance(v, (np.datetime64, np.timedelta64)) and np.isnat(v):
        return "nat"
    return None


def exact_key(v):
    m = missing_kind(v)
    if m:
        return ("M", m)
    if isinstance(v, (float, np.floating)):
        return ("F", type(v).__name__, float(v).hex())
    if isinstance(v, pd.Timestamp):
        return ("T", v.value, str(v.tz))
    if isinstance(v, pd.Timedelta):
        return ("D", v.value)
    return (type(v).__name__, repr(v))


def norm(v):
    m = missing_kind(v)
    if m:
        return ("M", m)
    if isinstance(v, (bool, np.bool_)):
        return ("B", bool(v))
    if isinstance(v, (int, np.integer)):
        return ("I", int(v))
    if isinstance(v, (float, np.floating)):
        return ("F", float(v))
    if isinstance(v, (str, np.str_)):
        return ("S", str(v))
    if isinstance(v, pd.Timestamp):
        return ("T", v.value, str(v.tz) if v.tz is not None else None)
    if isinstance(v, pd.Timedelta):
        return ("D", v.value)
    return ("O", repr(v))


def elem_eq(x, y, unify):
    """E2 (unify=False) / E3+ (unify=True) equality of normalised elements."""
    if x[0] == "M" or y[0] == "M":
        return x[0] == "M" and y[0] == "M" and (unify or x[1] == y[1])
    if x[0] in "IF" and y[0] in "IF":
        if x[0] == "I" and y[0] == "I":
            return x[1] == y[1]
        if (x[0] == "I" and abs(x[1]) > MAX_EXACT) or (y[0] == "I" and abs(y[1]) > MAX_EXACT):
            return False
        a, b = float(x[1]), float(y[1])
        return a == b or math.isclose(a, b, rel_tol=RTOL, abs_tol=0.0)
    return x == y


# ----------------------------------------------------------------------------- columns
def values_of(s):
    """Element list of a Series/Index/categorical (categoricals decoded to their values)."""
    return list(s.astype(object)) if isinstance(s.dtype, pd.CategoricalDtype) else list(s)


def family(s, vacuous_obj="str"):
    dt = s.dtype
    name = str(dt)
    if isinstance(dt, pd.CategoricalDtype):
        return "cat"
    if pd.api.types.is_bool_dtype(dt):
        return "bool"
    if pd.api.types.is_integer_dtype(dt):
        return "int"
    if pd.api.types.is_float_dtype(dt):
        return "float"
    if pd.api.types.is_datetime64_any_dtype(dt) or name.startswith("timestamp"):
        tz = getattr(dt, "tz", None)
        if tz is None and hasattr(dt, "pyarrow_dtype"):
            tz = getattr(dt.pyarrow_dtype, "tz", None)
        return "dt:%s" % (str(tz) if tz is not None else None)
    if pd.api.types.is_timedelta64_dtype(dt) or name.startswith("duration"):
        return "td"
    if name != "object" and pd.api.types.is_string_dtype(dt):
        return "str"
    present = [v for v in s if missing_kind(v) is None]
    if not present:
        return vacuous_obj
    return "str" if all(isinstance(v, str) for v in present) else "obj"


def families_ok(fa, fb):
    if fa == "any" or fb == "any":
        return True
    return fa == fb or frozenset({fa, fb}) in PAIRS


# ----------------------------------------------------------------------------- objects
def as_table(x):
    """-> (kind, columns [Series], index levels [Index], meta dict)."""
    if isinstance(x, pd.DataFrame):
        cols = [x.iloc[:, j] for j in range(x.shape[1])]
        lv = [x.index.get_level_values(i) for i in range(x.index.nlevels)]
        meta = {"labels": list(x.columns), "labels_dtype": str(x.columns.dtype), "colnames": list(x.columns.names),
                "names": list(x.index.names)}
        return "DataFrame", cols, lv, meta
    if isinstance(x, pd.Series):
        lv = [x.index.get_level_values(i) for i in range(x.index.nlevels)]
        return "Series", [x], lv, {"labels": [], "labels_dtype": "", "colnames": [], "names": list(x.index.names),
                                  "sname": [x.name]}
    raise TypeError(type(x))


def _label_key(v, level):
    if level in ("E0", "E1"):
        return exact_key(v)
    return norm(v)


def _labels_eq(la, lb, level):
    if len(la) != len(lb):
        return False
    unify = level in ("E3", "E4")
    for x, y in zip(la, lb):
        if isinstance(x, tuple) or isinstance(y, tuple):
            if not (isinstance(x, tuple) and isinstance(y, tuple) and len(x) == len(y)):
                return False
            if not _labels_eq(list(x), list(y), level):
                return False
            continue
        if level in ("E0", "E1"):
            if exact_key(x) != exact_key(y):
                return False
        elif not elem_eq(norm(x), norm(y), unify):
            return False
    return True


def _label_family(d):
    if d in ("object", "str", "string", "string[python]", "string[pyarrow]", "large_string[pyarrow]"):
        return "str"
    if d.startswith(("int", "uint", "Int", "UInt")):
        return "int"
    if d.startswith(("float", "Float", "double")):
        return "float"
    if d.startswith(("datetime64", "timestamp")):
        return "dt"
    return d


def _perfect_matching(ok):
    n = len(ok)
    match_b = [-1] * n

    def try_row(i, seen):
        for j in range(n):
            if ok[i][j] and not seen[j]:
                seen[j] = True
                if match_b[j] == -1 or try_row(match_b[j], seen):
                    match_b[j] = i
                    return True
        return False

    return all(try_row(i, [False] * n) for i in range(n))


def level_holds(a, b, level, vacuous_obj="str"):
    ka, ca, ia, ma = as_table(a)
    kb, cb, ib, mb = as_table(b)
    if ka != kb or a.shape != b.shape:
        return False
    exact = level in ("E0", "E1")
    unify = level in ("E3", "E4")
    use_index = level != "E4"
    # labels / names
    if exact:
        if ma["labels_dtype"] != mb["labels_dtype"]:
            return False
    elif _label_family(ma["labels_dtype"]) != _label_family(mb["labels_dtype"]):
        return False
    if not _labels_eq(ma["labels"], mb["labels"], level):
        return False
    if level != "E4":
        if not _labels_eq(ma["names"], mb["names"], level) or not _labels_eq(ma["colnames"], mb["colnames"], level):
            return False
        if ka == "Series" and not _labels_eq(ma["sname"], mb["sname"], level):
            return False
        if len(ia) != len(ib):
            return False
    # per-column type checks
    pairs = list(zip(ca, cb)) + (list(zip(ia, ib)) if use_index else [])
    for x, y in pairs:
        if exact:
            if str(x.dtype) != str(y.dtype):
                return False
            if isinstance(x.dtype, pd.CategoricalDtype) and (
                    list(x.dtype.categories) != list(y.dtype.categories) or x.dtype.ordered != y.dtype.ordered):
                return False
        else:
            fx, fy = family(x, vacuous_obj), family(y, vacuous_obj)
            if fx == "cat" or fy == "cat":
                if fx != fy:
                    return False
                fx = family(pd.Series(x.dtype.categories), vacuous_obj) if len(x.dtype.categories) else "any"
                fy = family(pd.Series(y.dtype.categories), vacuous_obj) if len(y.dtype.categories) else "any"
            if not families_ok(fx, fy):
                return False
    n = len(a)
    if n == 0:
        return True
    keyf = (lambda v: exact_key(v)) if exact else norm
    va = [[keyf(v) for v in values_of(s)] for s, _ in pairs]
    vb = [[keyf(v) for v in values_of(t)] for _, t in pairs]

    def row_ok(i, j):
        for xa, xb in zip(va, vb):
            if exact:
                if xa[i] != xb[j]:
                    return False
            elif not elem_eq(xa[i], xb[j], unify):
                return False
        return True

    if level == "E0":
        return all(row_ok(i, i) for i in range(n))
    ok = [[row_ok(i, j) for j in range(n)] for i in range(n)]
    return _perfect_matching(ok)


def oracle_level(a, b, vacuous_obj="str"):
    for L in LEVELS:
        if level_holds(a, b, L, vacuous_obj):
            return L
    return "DIFF"

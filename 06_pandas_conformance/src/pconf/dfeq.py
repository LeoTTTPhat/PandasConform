"""dfeq: the equivalence-lattice comparator (plan.md Section 2). Runs in the `ref` environment
(and in the shared venv for tests); reads captured column blobs and object records.

Levels form a chain of cumulative relaxations; compare() returns the finest level reached:
  E0 bit-exact         same kind, shape, column labels and order, index, names, dtype strings;
                       values identical with NaN/None/NA/NaT in the same positions
                       (== object-hash equality, see capture.py)
  E1 row order         equal after a canonical stable sort on all columns (index carried)
  E2 widening + tol    dtype pairs in WIDENING (int*/Int*/uint* <-> float* when the integers are
                       exactly representable; object/str/string; datetime units; timedelta
                       units; bool/boolean; plus pyarrow-backed variants of the same families);
                       floats equal within relative tolerance 1e-9 (math.isclose, abs_tol=0);
                       column-label dtypes and label values compared under the same widening
  E3 missing sentinel  NaN, None, pd.NA and NaT unified (only the missing mask must agree)
  E4 index             index ignored (rows re-sorted without it), index names, columns-axis
                       names and Series names ignored
Outcomes beyond the chain: DIFF (not equal at E4), UNCOMPARABLE (either side not serialisable,
capped beyond E0, or failed engine->pandas conversion). A capped pair whose shape, labels or
column count already differ (E4 metadata) is DIFF, not UNCOMPARABLE. A column counts as capped
only if its blob is absent from the store at compare time (order-independent).

"Modulo row order" (E1..E4) means: a row permutation EXISTS under which every column is equal
at that level. It is decided in three steps (fix of review findings B1/B2, 2026-10-02):
  1. the identity order (same row order, the common case, e.g. float noise on tied values);
  2. a canonical sort of both sides on keys in a common space: at E1 exact bit-level keys
     (complete: exact multisets sort identically); at E2+ normalised element classes, exact
     keys for non-numeric values (strings ranked jointly over both sides, object-held numbers
     ranked by value), numbers rounded to 7 significant digits, exact numbers as tie-breakers;
  3. (E2+) bipartite matching inside groups of rows whose non-tolerant parts are equal, with
     the element relation of compare_columns (relative tolerance, exact int-int, 2**53 rule).
     Groups above MATCH_LIMIT rows are paired by the sorted order and only the residual is
     matched; if the residual is still too large the level fails with 'match_limit' noted.
Every candidate permutation is verified by compare_columns, so a level is never claimed
without an explicit permutation that satisfies it.
An object-dtype column with no non-missing value (all missing, or empty) has family 'any'
(WIDENING_DOC: 'object holding only ... (+ missing)' holds vacuously): it is compatible with
every family at E2+, and only its missing mask/sentinels are compared.

compare() also reports, per failed level, the first failing check, so that root causes can be
grouped (e.g. 'dtype_family:category/object', 'values:col=3:row=17', 'index:values').
"""
import collections
import math

import numpy as np

from pconf import capture as C

import os

LEVELS = ["E0", "E1", "E2", "E3", "E4"]
FLOAT_RTOL = 1e-9
MAX_EXACT_INT = 2 ** 53
MATCH_LIMIT = 2000          # rows per tie group handled by exact bipartite matching
MATCH_BUDGET = 20_000_000   # max candidate-pair evaluations per object comparison
LARGE_ROWS = int(os.environ.get("PCONF_LARGE_ROWS", "100000"))  # above this, all single-column checks run before any joint sort
HASH_SORT_ROWS = int(os.environ.get("PCONF_HASH_SORT_ROWS", "200000"))  # above this, canonical sorts use one 64-bit row hash of the exact/coarse keys

# Families that may be compared at E2 (unordered pairs). Same-family pairs are always allowed
# (e.g. int32 vs Int64 vs int64[pyarrow], datetime64[ns] vs datetime64[us]).
WIDENING = {
    frozenset({"int", "float"}),     # when every integer is exactly representable as float64
    frozenset({"str", "obj"}),       # object/str/string family (elementwise, tag-aware)
    frozenset({"bool", "obj"}),      # object column holding only bools (+ missing) vs bool/boolean
    frozenset({"int", "obj"}),       # object column holding only numbers vs numeric
    frozenset({"float", "obj"}),
}
WIDENING_DOC = [
    "int8..int64, uint8..uint64, Int8..Int64, UInt8..UInt64, int*/uint*[pyarrow] (same family)",
    "float16..float64, Float32/Float64, float/double[pyarrow] (same family)",
    "int family <-> float family when all integers satisfy |v| <= 2**53",
    "object (all str + missing), str (pandas 3), string[python], string[pyarrow], large_string[pyarrow] (same family 'str')",
    "object (mixed python values) <-> str family, elementwise",
    "object holding only bools/numbers (+ missing) <-> bool/int/float family, elementwise",
    "datetime64[s|ms|us|ns] and timestamp[*][pyarrow], same timezone (same family 'dt')",
    "timedelta64[*] and duration[*][pyarrow] (same family 'td')",
    "bool, boolean, bool[pyarrow] (same family 'bool')",
    "category <-> category: compared on decoded values (categories list/order may differ)",
    "object column with no non-missing value (all missing or empty) <-> any family (vacuous)",
]

_UNIT_NS = {"s": 10 ** 9, "ms": 10 ** 6, "us": 10 ** 3, "ns": 1}


# ----------------------------------------------------------------------------- column views

class Col:
    """Normalised view of one captured column."""

    def __init__(self, desc, store):
        self.desc = desc
        self.dtype = desc["dtype"]
        self.enc = desc["enc"]
        self.raw = _decode_cached(store, desc)[0]
        self.n = desc["n"]
        self.miss = self.raw["miss"]
        self._norm()

    def _norm(self):
        r, enc = self.raw, self.enc
        self.tz = None
        if enc in ("num", "nmask"):
            k = r["v"].dtype.kind
            self.family = {"b": "bool", "i": "int", "u": "int", "f": "float"}[k]
            self.values = r["v"]
        elif enc in ("dt", "td"):
            unit = self.desc["x"].get("unit", "ns")
            if str(unit).startswith("period"):
                self.family = "period:" + unit
                self.values = r["v"]
            else:
                self.family = enc
                self.values = r["v"].astype(np.int64) * _UNIT_NS.get(unit, 1)
                self.tz = self.desc["x"].get("tz")
        elif enc == "str":
            self.family = "str"
            self.values = r["v"]
            if self.dtype == "object" and not np.any(self.miss == 0):
                self.family = "any"   # vacuous: no non-missing element (B3)
        elif enc == "obj":
            self.family = "obj"
            self.values = None
            self.tags, self.payload = r["t"], r["p"]
        elif enc == "cat":
            inner = _CatInner(r["cats"])
            codes = r["codes"]
            self.family = "cat:" + inner.family
            self.inner = inner
            self.codes = codes
        elif enc == "cplx":
            self.family = "complex"
            self.values = (r["re"], r["im"])
        else:
            raise ValueError(enc)

    def arrays_for_exact(self):
        """All stored arrays (bitwise comparable)."""
        out = {}
        for k, v in self.raw.items():
            if isinstance(v, np.ndarray):
                out[k] = v
        return out


class _CatInner:
    def __init__(self, cats_raw):
        self.raw = cats_raw
        enc = cats_raw["enc"]
        if enc in ("num", "nmask"):
            self.family = {"b": "bool", "i": "int", "u": "int", "f": "float"}[cats_raw["v"].dtype.kind]
        elif enc in ("dt", "td"):
            self.family = enc
        elif enc == "str":
            self.family = "str" if (cats_raw["dtype"] != "object" or len(cats_raw["v"])) else "any"
        else:
            self.family = "obj"

    def key_strings(self):
        r = self.raw
        if r["enc"] == "obj":
            return [_obj_key(t, p) for t, p in zip(r["t"], r["p"])]
        if r["enc"] == "str":
            return [("s|" + v) for v in r["v"]]
        return [repr(v) for v in r["v"].tolist()]

    def element(self, code):
        r = self.raw
        if r["enc"] == "obj":
            return int(r["t"][code]), r["p"][code]
        if r["enc"] == "str":
            return C.T_STR, r["v"][code]
        v = r["v"][code]
        if r["enc"] in ("num", "nmask"):
            k = r["v"].dtype.kind
            if k == "b":
                return C.T_BOOL, "True" if v else "False"
            if k in "iu":
                return C.T_INT, str(int(v))
            return C.T_FLOAT, repr(float(v))
        return C.T_DATETIME if r["enc"] == "dt" else C.T_TIMEDELTA, str(int(v))


def _obj_key(t, p):
    t = int(t)
    if t in (C.T_INT, C.T_FLOAT):
        try:
            return "n|" + repr(float(p))
        except ValueError:
            return "n|" + p
    if t in C.TAG_MISSING:
        return "m|"
    if t == C.T_STR:
        return "s|" + p
    return "%d|%s" % (t, p)


# ----------------------------------------------------------------------------- element comparisons

def _obj_ne(x, y):
    """Elementwise x != y for object arrays of strings (C loop); falls back to Python."""
    try:
        r = np.asarray(x != y)
        if r.dtype == bool and r.shape == np.shape(x):
            return r
    except Exception:
        pass
    return np.array([u != v for u, v in zip(list(x), list(y))], dtype=bool)


def _tagged_bad(present, ta, pa_, tb, pb_):
    """Element inequality at E2+ for tagged arrays: vectorised where both elements are strings
    (the common case), per element (_tag_elem_equal) for everything else."""
    ta = np.asarray(ta, dtype=np.uint8)
    tb = np.asarray(tb, dtype=np.uint8)
    both_str = (ta == C.T_STR) & (tb == C.T_STR)
    bad = np.zeros(len(present), bool)
    if both_str.any():
        bad[both_str] = _obj_ne(np.asarray(pa_, dtype=object)[both_str], np.asarray(pb_, dtype=object)[both_str])
    rest = np.flatnonzero(present & ~both_str)
    if len(rest):
        pa_l, pb_l = np.asarray(pa_, dtype=object), np.asarray(pb_, dtype=object)
        bad[rest] = [not _tag_elem_equal(int(ta[i]), pa_l[i], int(tb[i]), pb_l[i]) for i in rest.tolist()]
    return bad & present


def _int_beyond_2p53(v):
    v = np.asarray(v)
    if v.dtype.kind == "u":
        return v > np.uint64(MAX_EXACT_INT)
    v = v.astype(np.int64, copy=False)
    return (v > MAX_EXACT_INT) | (v < -MAX_EXACT_INT)


def _float_close(a, b):
    """Vectorised math.isclose(rel_tol=1e-9, abs_tol=0) with equal infinities."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    with np.errstate(invalid="ignore", over="ignore"):
        eq = a == b
        tol = FLOAT_RTOL * np.maximum(np.abs(a), np.abs(b))
        close = np.abs(a - b) <= tol
    return eq | (close & np.isfinite(a) & np.isfinite(b))


def _err_stats(a, b):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    fin = np.isfinite(a) & np.isfinite(b)
    if not fin.any():
        return None
    d = np.abs(a[fin] - b[fin])
    m = np.maximum(np.abs(a[fin]), np.abs(b[fin]))
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = np.where(m > 0, d / m, 0.0)
    return {"max_abs_err": float(d.max()), "max_rel_err": float(rel.max())}


def _tag_elem_equal(ta, pa_, tb, pb_):
    """Element equality at E2 for tagged values (number widening with tolerance)."""
    if ta in (C.T_INT, C.T_FLOAT) and tb in (C.T_INT, C.T_FLOAT):
        if ta == C.T_INT and tb == C.T_INT:
            return int(pa_) == int(pb_)
        try:
            if ta == C.T_INT and abs(int(pa_)) > MAX_EXACT_INT:
                return False
            if tb == C.T_INT and abs(int(pb_)) > MAX_EXACT_INT:
                return False
            x, y = float(pa_), float(pb_)
        except ValueError:
            return False
        return x == y or math.isclose(x, y, rel_tol=FLOAT_RTOL, abs_tol=0.0)
    if ta == C.T_COMPLEX and tb == C.T_COMPLEX:
        x, y = complex(pa_), complex(pb_)
        return math.isclose(x.real, y.real, rel_tol=FLOAT_RTOL) and math.isclose(x.imag, y.imag, rel_tol=FLOAT_RTOL)
    return ta == tb and pa_ == pb_


def _as_tagged(col, perm):
    """Column -> (tags, payloads) after permutation (used for obj-family widening)."""
    if col.family == "obj":
        return col.tags[perm], col.payload[perm]
    n = len(perm)
    tags = np.empty(n, np.uint8)
    pay = np.empty(n, dtype=object)
    miss = col.miss[perm]
    if col.family == "str":
        v = col.values[perm]
        tags[:] = C.T_STR
        pay[:] = v
    elif col.family in ("int", "float", "bool"):
        v = col.values[perm]
        if col.family == "bool":
            tags[:] = C.T_BOOL
            pay[:] = ["True" if x else "False" for x in v.tolist()]
        elif col.family == "int":
            tags[:] = C.T_INT
            pay[:] = [str(int(x)) for x in v.tolist()]
        else:
            tags[:] = C.T_FLOAT
            pay[:] = [repr(float(x)) for x in v.tolist()]
    else:
        raise TypeError(col.family)
    for code, tag in ((C.M_NONE, C.T_NONE), (C.M_NAN, C.T_NAN), (C.M_NA, C.T_NA), (C.M_NAT, C.T_NAT)):
        tags[miss == code] = tag
        pay[miss == code] = ""
    return tags, pay


def _families_compatible(fa, fb, a, b):
    if "any" in (fa, fb):
        other = fb if fa == "any" else fa
        if not other.startswith("cat:"):
            return True, None
        return False, "dtype_family:%s/%s" % (fa, fb)
    if fa.startswith("cat:") and fb.startswith("cat:") and "any" in (fa[4:], fb[4:]):
        return True, None
    if fa == fb:
        if fa == "dt" and (a.tz or None) != (b.tz or None):
            return False, "tz:%s/%s" % (a.tz, b.tz)
        return True, None
    if fa.startswith("cat:") and fb.startswith("cat:"):
        ia, ib = fa[4:], fb[4:]
        ok = ia == ib or frozenset({ia, ib}) in WIDENING
        return ok, None if ok else "dtype_family:%s/%s" % (fa, fb)
    if frozenset({fa, fb}) in WIDENING:
        return True, None
    return False, "dtype_family:%s/%s" % (fa, fb)


def _cat_tagged(col, perm):
    codes = col.codes[perm]
    k = len(col.inner.raw.get("v", col.inner.raw.get("t", [])))
    ct = np.empty(k + 1, np.uint8)
    cp = np.empty(k + 1, dtype=object)
    for c in range(k):
        ct[c], cp[c] = col.inner.element(c)
    ct[k], cp[k] = C.T_NAN, ""            # code -1 (missing)
    idx = np.where(codes >= 0, codes, k)
    return ct[idx], cp[idx]


def compare_columns(a, b, pa, pb, level, where):
    """Compare two columns (rows permuted by pa/pb) at `level` (E0/E1 exact; E2 widen; E3 sentinel).
    Returns (ok, reason, stats)."""
    if level in ("E0", "E1"):
        if a.dtype != b.dtype:
            return False, "dtype:%s:%s/%s" % (where, a.dtype, b.dtype), None
        if a.enc != b.enc:
            return False, "encoding:%s:%s/%s" % (where, a.enc, b.enc), None
        if a.enc == "cat" and a.desc["x"]["cats"]["h"] != b.desc["x"]["cats"]["h"]:
            return False, "categories:%s" % where, None
        aa, bb = a.arrays_for_exact(), b.arrays_for_exact()
        for k in sorted(aa):
            x, y = aa[k][pa], bb[k][pb]
            if x.dtype != y.dtype:
                return False, "encoding_dtype:%s:%s:%s/%s" % (where, k, x.dtype, y.dtype), None
            if x.dtype.kind == "f":
                bad = x.view("u%d" % x.itemsize) != y.view("u%d" % y.itemsize)
            elif x.dtype == object or y.dtype == object:
                bad = _obj_ne(x, y)
            else:
                bad = x != y
            if np.any(bad):
                row = int(np.flatnonzero(bad)[0])
                kind = "missing" if k in ("m", "k") else "values"
                return False, "%s:%s:row=%d" % (kind, where, row), None
        return True, None, None
    strict_sentinel = level == "E2"
    ok, why = _families_compatible(a.family, b.family, a, b)
    if not ok:
        return False, why + ":" + where, None
    ma, mb = a.miss[pa], b.miss[pb]
    if not np.array_equal(ma > 0, mb > 0):
        row = int(np.flatnonzero((ma > 0) != (mb > 0))[0])
        return False, "missing_mask:%s:row=%d" % (where, row), None
    if strict_sentinel and not np.array_equal(ma, mb):
        row = int(np.flatnonzero(ma != mb)[0])
        return False, "sentinel:%s:row=%d:%d/%d" % (where, row, int(ma[row]), int(mb[row])), None
    present = ma == 0
    fa, fb = a.family, b.family
    stats = None
    if "any" in (fa, fb):
        bad = present.copy()   # vacuous side has no present element; masks agree -> nothing left
    elif fa.startswith("cat:") or fb.startswith("cat:"):
        ta, pa_ = _cat_tagged(a, pa)
        tb, pb_ = _cat_tagged(b, pb)
        bad = _tagged_bad(present, ta, pa_, tb, pb_)
    elif "obj" in (fa, fb) or (fa != fb and "str" in (fa, fb)):
        try:
            ta, pa_ = _as_tagged(a, pa)
            tb, pb_ = _as_tagged(b, pb)
        except TypeError:
            return False, "dtype_family:%s/%s:%s" % (fa, fb, where), None
        bad = _tagged_bad(present, ta, pa_, tb, pb_)
    elif fa in ("int", "float") and fb in ("int", "float"):
        x, y = a.values[pa][present], b.values[pb][present]
        if fa == "int" and fb == "int":
            if x.dtype != y.dtype and (x.dtype.kind == "u" or y.dtype.kind == "u"):
                badp = np.array([int(u) != int(v) for u, v in zip(x.tolist(), y.tolist())], dtype=bool)
            else:
                badp = x != y
        else:
            for side, fam in ((x, fa), (y, fb)):
                # representability is decided on the integers themselves, before any cast (B4)
                if fam == "int" and side.size and _int_beyond_2p53(side).any():
                    return False, "int_not_representable:%s" % where, None
            badp = ~_float_close(x, y)
            stats = _err_stats(x, y)
        bad = np.zeros(len(present), bool)
        bad[present] = badp
    elif fa == "complex":
        (ra, ia), (rb, ib) = a.values, b.values
        bad = ~(_float_close(ra[pa], rb[pb]) & _float_close(ia[pa], ib[pb])) & present
    elif fa in ("str",):
        x, y = a.values[pa], b.values[pb]
        bad = _obj_ne(x, y) & present
    else:  # bool, dt, td, period: exact on normalised values
        x, y = a.values[pa], b.values[pb]
        bad = (x != y) & present
    if np.any(bad):
        row = int(np.flatnonzero(bad)[0])
        return False, "values:%s:row=%d" % (where, row), stats
    return True, None, stats


# ----------------------------------------------------------------------------- labels / names

def _label_exact(la, lb):
    return la == lb


def _label_elem(x, y, unify_missing):
    if isinstance(x, list) and x and x[0] == "tuple":
        if not (isinstance(y, list) and y and y[0] == "tuple") or len(x[1]) != len(y[1]):
            return False
        return all(_label_elem(u, v, unify_missing) for u, v in zip(x[1], y[1]))
    if isinstance(y, list) and y and y[0] == "tuple":
        return False
    tx, px, ty, py = int(x[0]), x[1], int(y[0]), y[1]
    if unify_missing and tx in C.TAG_MISSING and ty in C.TAG_MISSING:
        return True
    return _tag_elem_equal(tx, px, ty, py)


def _labels_relaxed(la, lb, unify_missing=False):
    return len(la) == len(lb) and all(_label_elem(x, y, unify_missing) for x, y in zip(la, lb))


_STRINGY = {"object", "str", "string", "string[python]", "string[pyarrow]", "large_string[pyarrow]", "string[pyarrow_numpy]"}


def _label_dtype_family(d):
    if d in _STRINGY:
        return "str"
    if d.startswith(("int", "uint", "Int", "UInt")):
        return "int"
    if d.startswith(("float", "Float", "double")):
        return "float"
    if d.startswith(("datetime64", "timestamp")):
        return "dt"
    return d


# ----------------------------------------------------------------------------- objects

_DECODE_CACHE = collections.OrderedDict()   # blob hash -> decoded raw dict (per process, LRU)
_DECODE_CACHE_BYTES = [0]
DECODE_CACHE_LIMIT = int(float(os.environ.get("PCONF_DECODE_CACHE_GB", "4")) * 1e9)


def _raw_nbytes(raw):
    tot = 0
    for v in raw.values():
        if isinstance(v, np.ndarray):
            tot += v.nbytes if v.dtype != object else 64 * v.size
        elif isinstance(v, dict):
            tot += _raw_nbytes(v)
    return tot


def _decode_cached(store, desc):
    """capture.decode_column_values with a per-process LRU cache keyed by the column's content
    hash (identical content -> identical decoded view), bounded by DECODE_CACHE_LIMIT bytes."""
    key = (store, desc["h"], desc["enc"], desc["dtype"], desc["n"])
    hit = _DECODE_CACHE.get(key)
    if hit is not None:
        _DECODE_CACHE.move_to_end(key)
        return hit
    raw = C.decode_column_values(store, desc)
    nb = _raw_nbytes(raw)
    if nb <= DECODE_CACHE_LIMIT // 4:
        _DECODE_CACHE[key] = (raw, nb)
        _DECODE_CACHE_BYTES[0] += nb
        while _DECODE_CACHE_BYTES[0] > DECODE_CACHE_LIMIT and _DECODE_CACHE:
            _, (_, b) = _DECODE_CACHE.popitem(last=False)
            _DECODE_CACHE_BYTES[0] -= b
        return raw, nb
    return raw, nb


class _LazyCols:
    """Column views decoded on first access (a column never read is never decoded)."""

    def __init__(self, descs, store):
        self.descs, self.store, self._c = descs, store, {}

    def __len__(self):
        return len(self.descs)

    def __getitem__(self, j):
        if j not in self._c:
            self._c[j] = Col(self.descs[j], self.store)
        return self._c[j]

    def __iter__(self):
        return (self[j] for j in range(len(self.descs)))

    def __add__(self, other):
        return list(self) + list(other)


class Obj:
    def __init__(self, rec, store):
        self.rec = rec
        self.kind = rec["kind"]
        self.meta = rec.get("meta", {})
        self.store = store
        self.cols = _LazyCols(rec.get("cols", []), store)
        self.idx = _LazyCols(rec.get("idx", []), store)

    def capped(self):
        """A column is unavailable only if its blob is absent from the store NOW (a blob written
        by any run of the campaign counts), so comparability does not depend on run order."""
        def all_stored(d):
            if not (d.get("stored", False) or os.path.exists(C.blob_path(self.store, d["h"]))):
                return False
            sub = d.get("x", {}).get("cats")
            return all_stored(sub) if isinstance(sub, dict) else True
        return not all(all_stored(c) for c in self.rec.get("cols", []) + self.rec.get("idx", []))

    def nrows(self):
        sh = self.meta.get("shape") or [0]
        return int(sh[0]) if self.kind != "scalar" else 1


def _compare_scalars(a, b, level):
    ta, pa_, ya = a.meta["value"]
    tb, pb_, yb = b.meta["value"]
    if level in ("E0", "E1"):
        if [ta, pa_, ya] == [tb, pb_, yb]:
            return True, None
        if ta != tb:
            return False, "scalar_tag:%d/%d" % (ta, tb)
        if pa_ != pb_:
            return False, "scalar_value"
        return False, "scalar_type:%s/%s" % (ya, yb)
    if ta in C.TAG_MISSING and tb in C.TAG_MISSING:
        if level == "E2" and ta != tb:
            return False, "sentinel:scalar:%d/%d" % (ta, tb)
        return True, None
    if (ta == C.T_BOOL) != (tb == C.T_BOOL):
        return False, "scalar_family:%s/%s" % (ya, yb)
    if _tag_elem_equal(int(ta), pa_, int(tb), pb_):
        return True, None
    return False, "scalar_value"


def _meta_check(a, b, level):
    """Shape, labels and names. Returns reason or None."""
    ma, mb = a.meta, b.meta
    if ma.get("shape") != mb.get("shape"):
        return "shape:%s/%s" % (ma.get("shape"), mb.get("shape"))
    exact = level in ("E0", "E1")
    names_ignored = level == "E4"
    um = level in ("E3", "E4")
    if a.kind == "DataFrame":
        if exact:
            if ma["columns"] != mb["columns"]:
                return "labels"
            if ma["columns_dtype"] != mb["columns_dtype"]:
                return "labels_dtype:%s/%s" % (ma["columns_dtype"], mb["columns_dtype"])
        else:
            if not _labels_relaxed(ma["columns"], mb["columns"], um):
                return "labels"
            if _label_dtype_family(ma["columns_dtype"]) != _label_dtype_family(mb["columns_dtype"]):
                return "labels_dtype:%s/%s" % (ma["columns_dtype"], mb["columns_dtype"])
        if not names_ignored:
            for key in ("columns_names", "index_names"):
                if (ma[key] != mb[key]) if exact else not _labels_relaxed(ma[key], mb[key], um):
                    return "names:%s" % key
    elif a.kind == "Series":
        if not names_ignored:
            if (ma["name"] != mb["name"]) if exact else not _labels_relaxed([ma["name"]], [mb["name"]], um):
                return "names:series_name"
            if (ma["index_names"] != mb["index_names"]) if exact else not _labels_relaxed(ma["index_names"], mb["index_names"], um):
                return "names:index_names"
    elif a.kind in ("Index", "MultiIndex"):
        if not names_ignored:
            if (ma["names"] != mb["names"]) if exact else not _labels_relaxed(ma["names"], mb["names"], um):
                return "names:index_names"
    elif a.kind == "ndarray":
        if exact and ma.get("dtype") != mb.get("dtype"):
            return "dtype:ndarray:%s/%s" % (ma.get("dtype"), mb.get("dtype"))
        if exact and ma.get("array_type", "ndarray") != mb.get("array_type", "ndarray"):
            return "array_type:%s/%s" % (ma.get("array_type", "ndarray"), mb.get("array_type", "ndarray"))
    if a.kind in ("DataFrame", "Series") and level != "E4":
        if ma.get("index_nlevels") != mb.get("index_nlevels"):
            return "index:nlevels"
    return None


def compare(rec_a, rec_b, store_a, store_b=None):
    """Compare captured object records (a = reference, b = engine). See module docstring."""
    store_b = store_b or store_a
    res = {"level": None, "fails": {}}
    ha, hb = rec_a.get("h"), rec_b.get("h")
    if ha is None or hb is None:
        res["level"] = "UNCOMPARABLE"
        res["reason"] = "not_serialisable:%s/%s" % (rec_a.get("kind"), rec_b.get("kind"))
        return res
    if ha == hb:
        res["level"] = "E0"
        return res
    a, b = Obj(rec_a, store_a), Obj(rec_b, store_b)
    if a.kind != b.kind:
        res["level"] = "DIFF"
        res["fails"] = {L: "kind:%s/%s" % (a.kind, b.kind) for L in LEVELS}
        return res
    if a.kind == "scalar":
        for L in LEVELS:
            ok, why = _compare_scalars(a, b, L)
            if ok:
                res["level"] = L
                return res
            res["fails"][L] = why
        res["level"] = "DIFF"
        return res
    if a.capped() or b.capped():
        # shape, labels and column count are known without the column data (B5)
        why = _meta_check(a, b, "E4")
        if why is None and len(a.rec.get("cols", [])) != len(b.rec.get("cols", [])):
            why = "ncols:%d/%d" % (len(a.rec.get("cols", [])), len(b.rec.get("cols", [])))
        if why is not None:
            res["level"] = "DIFF"
            res["reason"] = "capped_meta"
            res["fails"] = {L: why for L in LEVELS}
            return res
        res["level"] = "UNCOMPARABLE"
        res["reason"] = "capped"
        res["fails"]["E0"] = "hash"
        return res
    stats_all = {}
    matcher = _Matcher(a, b)
    for L in LEVELS:
        why = _level_holds(a, b, L, stats_all, matcher)
        if why is None:
            res["level"] = L
            if L != "E0" and matcher.how.get(L):
                res["match"] = matcher.how[L]
            if stats_all:
                res["float_err"] = stats_all
            return res
        res["fails"][L] = why
    res["level"] = "DIFF"
    if matcher.limit_hit:
        res["match_limit"] = sorted(matcher.limit_hit)
    if stats_all:
        res["float_err"] = stats_all
    return res


def _merge_stats(stats_all, level, st):
    if st:
        prev = stats_all.get(level)
        stats_all[level] = st if prev is None else {k: max(prev[k], st[k]) for k in st}


def _structural(why):
    """A failing check that no row permutation can repair."""
    return "row=" not in why


def _level_holds(a, b, L, stats_all, matcher):
    """None if a and b are equal at level L, else the first failing check (see docstring)."""
    why = _meta_check(a, b, L)
    if why is not None:
        return why
    n = a.nrows()
    ident = np.arange(n)
    st = {}
    why0 = _compare_tables(a, b, ident, ident, L, st, identity=True)
    if L == "E0" or why0 is None or n <= 1 or _structural(why0):
        if why0 is None:
            matcher.how[L] = "identity"
            _merge_stats(stats_all, L, st.get(L))
        return why0
    with_index = L != "E4"
    try:
        if not matcher.column_feasible(L, why0, with_index):
            return why0   # the failing column alone cannot match under any row permutation
        if n > LARGE_ROWS:
            # E4's element relation is the most permissive (widening, tolerance, unified missing);
            # a data column whose multiset cannot match even at E4 cannot match at any level
            if "E4_data_feasible" not in matcher.how:
                matcher.how["E4_data_feasible"] = matcher.all_columns_feasible("E4", False)
            if not matcher.how["E4_data_feasible"]:
                return why0
            if not matcher.all_columns_feasible(L, with_index):
                return why0   # some other column cannot match on its own: no permutation exists
        pa, pb = matcher.sorted_perms(L, with_index)
    except _NotNormalisable:
        return why0
    st = {}
    why1 = _compare_tables(a, b, pa, pb, L, st)
    if why1 is None:
        matcher.how[L] = "sort"
        _merge_stats(stats_all, L, st.get(L))
        return None
    if L == "E1":
        return why1   # exact keys: equal multisets always sort identically
    m = matcher.group_match(L, with_index)
    if m is not None:
        st = {}
        why2 = _compare_tables(a, b, m[0], m[1], L, st)
        if why2 is None:
            matcher.how[L] = "matching"
            _merge_stats(stats_all, L, st.get(L))
            return None
    return why1


def _same_content(da, db):
    """Equal column content hash (E0 content address, sub-columns included) -> identical column."""
    return da.get("h") is not None and da.get("h") == db.get("h")


def _compare_tables(a, b, pa, pb, level, stats_all, identity=False):
    """identity=True: pa and pb are both the identity order, so columns with equal content
    hashes are equal at every level and are not decoded."""
    if len(a.cols) != len(b.cols):
        return "ncols:%d/%d" % (len(a.cols), len(b.cols))
    if level != "E4" and a.kind in ("DataFrame", "Series"):
        if len(a.idx) != len(b.idx):
            return "index:nlevels"
        for j in range(len(a.idx)):
            if identity and _same_content(a.idx.descs[j], b.idx.descs[j]):
                continue
            ok, why, st = compare_columns(a.idx[j], b.idx[j], pa, pb, "E1" if level == "E0" else level, "index%d" % j)
            if not ok:
                return "index:" + why
    for j in range(len(a.cols)):
        if identity and _same_content(a.cols.descs[j], b.cols.descs[j]):
            continue
        x, y = a.cols[j], b.cols[j]
        ok, why, st = compare_columns(x, y, pa, pb, "E1" if level == "E0" else level, "col%d" % j)
        _merge_stats(stats_all, level, st)
        if not ok:
            return why
    if level == "E0":
        # all checks passed but hashes differ: a difference only E0 sees (e.g. label python types)
        return "hash_only"
    return None


def check_levels(rec_a, rec_b, store_a, store_b=None):
    """For testing the lattice: evaluate EVERY level independently -> {level: bool}.
    The chain property requires these to be monotone (once True, True for all coarser levels)."""
    store_b = store_b or store_a
    out = {}
    if rec_a.get("h") is None or rec_b.get("h") is None:
        return {L: False for L in LEVELS}
    a, b = Obj(rec_a, store_a), Obj(rec_b, store_b)
    matcher = _Matcher(a, b) if a.kind == b.kind else None
    for L in LEVELS:
        if L == "E0":
            out[L] = rec_a["h"] == rec_b["h"]
            continue
        if a.kind != b.kind:
            out[L] = False
            continue
        if a.kind == "scalar":
            out[L] = _compare_scalars(a, b, L)[0]
            continue
        out[L] = _level_holds(a, b, L, {}, matcher) is None
    return out


# ----------------------------------------------------------------------------- row matching

class _NotNormalisable(Exception):
    pass


# element classes in the common (level-normalised) space
K_BOOL, K_NUM, K_STR, K_DT, K_TD, K_PERIOD, K_CPLX, K_OTHER, K_MISS = 1, 2, 3, 4, 5, 6, 7, 50, 100


class _Elems:
    """Level-normalised view of one column: per element a class, exact keys and numbers."""
    __slots__ = ("cls", "ikey", "skey", "isint", "big", "ival", "fval", "fval2", "exact_int")

    def __init__(self, n):
        self.cls = np.zeros(n, np.int64)
        self.ikey = np.zeros(n, np.int64)
        self.skey = None            # object array of str ('' when unused) or None
        self.isint = np.zeros(n, bool)
        self.big = np.zeros(n, bool)  # integer outside int64 (exact compare via skey)
        self.ival = np.zeros(n, np.int64)
        self.fval = np.zeros(n, np.float64)
        self.fval2 = None
        self.exact_int = False      # whole column is an integer-family column


def _tagged_elems(tags, payloads):
    """Tagged (object / categorical) elements -> _Elems, vectorised by tag; per element only for
    integers outside int64 and complex numbers."""
    tags = np.asarray(tags, dtype=np.uint8)
    pay = np.asarray(payloads, dtype=object)
    n = len(tags)
    e = _Elems(n)
    sk = np.full(n, "", dtype=object)
    used_s = False
    m = tags == C.T_STR
    if m.any():
        e.cls[m] = K_STR
        sk[m] = pay[m]
        used_s = True
    m = tags == C.T_BOOL
    if m.any():
        e.cls[m] = K_BOOL
        e.ikey[m] = (pay[m] == "True").astype(np.int64)
    m = tags == C.T_FLOAT
    if m.any():
        e.cls[m] = K_NUM
        e.fval[m] = pay[m].astype(np.float64)
    m = tags == C.T_INT
    if m.any():
        e.cls[m] = K_NUM
        e.isint[m] = True
        idx = np.flatnonzero(m)
        try:
            iv = pay[m].astype(np.int64)
            e.ival[m] = iv
            e.fval[m] = iv.astype(np.float64)
        except (OverflowError, ValueError):
            for i in idx.tolist():
                iv = int(pay[i])
                if -2 ** 63 <= iv < 2 ** 63:
                    e.ival[i] = iv
                else:
                    e.big[i] = True
                    sk[i] = pay[i]
                    used_s = True
                try:
                    e.fval[i] = float(iv)
                except OverflowError:
                    e.fval[i] = math.inf if iv > 0 else -math.inf
    m = tags == C.T_COMPLEX
    if m.any():
        cplx = np.zeros(n, np.float64)
        for i in np.flatnonzero(m).tolist():
            c = complex(pay[i])
            e.cls[i] = K_CPLX
            e.fval[i], cplx[i] = c.real, c.imag
        e.fval2 = cplx
    other = ~np.isin(tags, [C.T_STR, C.T_BOOL, C.T_FLOAT, C.T_INT, C.T_COMPLEX] + list(C.TAG_MISSING))
    if other.any():
        e.cls[other] = K_OTHER + tags[other].astype(np.int64)
        sk[other] = pay[other]
        used_s = True
    e.skey = sk if used_s else None
    return e


def _raw_elems(col):
    """Col -> _Elems (missing classes not yet applied)."""
    n, fam = col.n, col.family
    if fam == "any":
        return _Elems(n)
    if fam == "int":
        e = _Elems(n)
        v = col.values
        e.cls[:] = K_NUM
        e.isint[:] = True
        e.exact_int = True
        if v.dtype.kind == "u" and v.dtype.itemsize == 8:
            big = v > np.uint64(2 ** 63 - 1)
            if big.any():
                e.big = big
                sk = np.full(n, "", dtype=object)
                sk[big] = [str(int(x)) for x in v[big].tolist()]
                e.skey = sk
            e.ival = np.where(big, 0, v).astype(np.int64)
        else:
            e.ival = v.astype(np.int64)
        e.fval = v.astype(np.float64)
        return e
    if fam == "float":
        e = _Elems(n)
        e.cls[:] = K_NUM
        e.fval = col.values.astype(np.float64)
        return e
    if fam == "bool":
        e = _Elems(n)
        e.cls[:] = K_BOOL
        e.ikey = col.values.astype(np.int64)
        return e
    if fam in ("dt", "td") or fam.startswith("period:"):
        e = _Elems(n)
        e.cls[:] = {"dt": K_DT, "td": K_TD}.get(fam, K_PERIOD)
        e.ikey = col.values.astype(np.int64)
        return e
    if fam == "str":
        e = _Elems(n)
        e.cls[:] = K_STR
        e.skey = np.asarray(col.values, dtype=object)
        return e
    if fam == "obj":
        return _tagged_elems(col.tags, col.payload)
    if fam == "complex":
        e = _Elems(n)
        e.cls[:] = K_CPLX
        e.fval, e.fval2 = col.values[0].astype(np.float64), col.values[1].astype(np.float64)
        return e
    if fam.startswith("cat:"):
        k = len(col.inner.raw.get("v", col.inner.raw.get("t", [])))
        ct = np.empty(k, np.uint8)
        cp = np.empty(k, dtype=object)
        for c in range(k):
            ct[c], cp[c] = col.inner.element(c)
        ce = _tagged_elems(ct, cp)
        codes = col.codes
        safe = np.where(codes >= 0, codes, 0)
        e = _Elems(n)
        if k:
            e.cls, e.ikey, e.isint, e.big, e.ival, e.fval = (ce.cls[safe], ce.ikey[safe], ce.isint[safe],
                                                             ce.big[safe], ce.ival[safe], ce.fval[safe])
            e.skey = ce.skey[safe] if ce.skey is not None else None
            e.fval2 = ce.fval2[safe] if ce.fval2 is not None else None
        return e
    raise _NotNormalisable(fam)


def _level_elems(col, level):
    e = _raw_elems(col)
    miss = col.miss
    m = miss > 0
    if m.any():
        e.cls = e.cls.copy()
        e.cls[m] = K_MISS + (miss[m].astype(np.int64) if level == "E2" else 0)
        for name in ("ikey", "ival", "fval"):
            arr = getattr(e, name).copy()
            arr[m] = 0
            setattr(e, name, arr)
        e.isint = e.isint & ~m
        e.big = e.big & ~m
        if e.skey is not None:
            e.skey = e.skey.copy()
            e.skey[m] = ""
        if e.fval2 is not None:
            e.fval2 = e.fval2.copy()
            e.fval2[m] = 0.0
    return e


def _joint_rank(u, v):
    """Codes of u and v in a common key space: equal values get equal codes on both sides.
    Only consistency matters (keys are used for canonical sorting and grouping), not
    lexicographic order, so object arrays use hash-based factorisation (pandas) and floats
    their exact bit patterns."""
    nu = len(u)
    u, v = np.asarray(u), np.asarray(v)
    if u.dtype.kind == "f" and v.dtype.kind == "f" and u.dtype == v.dtype:
        u = u.view("u%d" % u.itemsize)   # exact bits (signed zeros and NaN payloads distinct)
        v = v.view("u%d" % v.itemsize)
    both = np.concatenate([u, v])
    if both.dtype == object:
        try:
            import pandas as _pd
            codes, _ = _pd.factorize(both, sort=False, use_na_sentinel=False)
            codes = np.asarray(codes, dtype=np.int64)
            return codes[:nu], codes[nu:]
        except Exception:
            both = both.astype(str)
    _, inv = np.unique(both, return_inverse=True)
    inv = inv.reshape(-1).astype(np.int64)
    return inv[:nu], inv[nu:]


def _prune_keys(ka, kb):
    """Drop key pairs that hold one and the same constant on both sides: they cannot change a
    sort or a grouping (keys constant on each side but different are kept, so multiset
    differences remain visible)."""
    outa, outb = [], []
    for x, y in zip(ka, kb):
        if len(x) and len(y):
            x0 = x[0]
            if x0 == y[0] and np.all(x == x0) and np.all(y == x0):
                continue
        elif not len(x) and not len(y):
            continue
        outa.append(x)
        outb.append(y)
    return outa, outb


def _as_u64(k):
    k = np.asarray(k)
    if k.dtype.kind == "f":
        k = np.where(k == 0, 0.0, k).astype(np.float64)   # signed zeros unified
        return k.view(np.uint64)
    return k.astype(np.int64, copy=False).view(np.uint64)


def _row_hash(keys):
    """Deterministic 64-bit hash per row of several key arrays (splitmix64-style mixing).
    Equal rows -> equal hashes on both sides; used only to order rows (every permutation found
    this way is verified column by column, so a collision can cost a match, never a false one)."""
    n = len(keys[0])
    h = np.full(n, 0x243F6A8885A308D3, dtype=np.uint64)
    with np.errstate(over="ignore"):
        for k in keys:
            h ^= _as_u64(k) + np.uint64(0x9E3779B97F4A7C15) + (h << np.uint64(6)) + (h >> np.uint64(2))
            h = (h ^ (h >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
            h = (h ^ (h >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
            h ^= h >> np.uint64(31)
    return h


def _sort_rows(keys, tie=()):
    """Permutation ordering rows by (keys..., then tie keys); large inputs hash the main keys."""
    n = len(keys[0]) if keys else (len(tie[0]) if tie else 0)
    if keys and n > HASH_SORT_ROWS and len(keys) > 1:
        keys = [_row_hash(keys)]
    allk = list(keys) + list(tie)
    if not allk:
        return np.arange(n)
    if len(allk) == 1:
        return np.argsort(allk[0], kind="stable")
    return np.lexsort(allk[::-1])


def _same_multiset(ka, kb):
    """Do the rows of key arrays ka and kb form the same multiset? Large inputs compare sorted
    64-bit row hashes: equal multisets always give equal hash multisets, so this can only err
    toward 'same' (then the caller continues and verification decides), never toward 'different'."""
    if not ka:
        return True
    n = len(ka[0])
    if n > HASH_SORT_ROWS or len(ka) > 1:
        ha, hb = (_row_hash(ka), _row_hash(kb)) if len(ka) > 1 else (_as_u64(ka[0]), _as_u64(kb[0]))
        return np.array_equal(np.sort(ha), np.sort(hb))
    return np.array_equal(np.sort(ka[0]), np.sort(kb[0]))


def _group_ids(keys):
    """Dense ids of the distinct rows of several equally long int64 key arrays (hash-based)."""
    try:
        import pandas as _pd
        df = _pd.DataFrame({i: np.asarray(k) for i, k in enumerate(keys)}, copy=False)
        return df.groupby(list(range(len(keys))), sort=False, observed=True).ngroup().to_numpy(dtype=np.int64)
    except Exception:
        _, inv = np.unique(np.stack(keys, axis=1), axis=0, return_inverse=True)
        return inv.reshape(-1).astype(np.int64)


def _round_sig(v, sig=7):
    """Numbers rounded to `sig` significant digits (signed zeros unified): values within the
    relative tolerance share a key except at rounding boundaries (handled by matching)."""
    v = np.asarray(v, dtype=np.float64)
    out = v.copy()
    fin = np.isfinite(v) & (v != 0)
    if fin.any():
        x = v[fin]
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            ex = np.floor(np.log10(np.abs(x)))
            scale = np.power(10.0, sig - 1 - ex)
            r = np.round(x * scale) / scale
        bad = ~np.isfinite(r)
        r[bad] = x[bad]
        out[fin] = r
    out[v == 0] = 0.0
    return out


def _num_relation(xa, xb, A, B):
    """Element relation of compare_columns for numeric elements: rows A of side a vs rows B of
    side b (index arrays; pass A[:, None], B[None, :] for all pairs, or aligned vectors).
    int-int exact; an integer with |v| > 2**53 never equals a float (decided on the integer);
    otherwise relative tolerance FLOAT_RTOL with equal infinities."""
    ai, bi = xa.isint[A], xb.isint[B]
    abig, bbig = xa.big[A], xb.big[B]
    av, bv = xa.ival[A], xb.ival[B]
    eq_int = (av == bv) & ~abig & ~bbig
    if abig.any() and bbig.any():
        sa = xa.skey[A] if xa.skey is not None else np.full(np.shape(A), "", dtype=object)
        sb = xb.skey[B] if xb.skey is not None else np.full(np.shape(B), "", dtype=object)
        eq_int = eq_int | (abig & bbig & (sa == sb))
    nonrep_a = ai & (abig | (av > MAX_EXACT_INT) | (av < -MAX_EXACT_INT))
    nonrep_b = bi & (bbig | (bv > MAX_EXACT_INT) | (bv < -MAX_EXACT_INT))
    close = _float_close(xa.fval[A], xb.fval[B])
    if xa.fval2 is not None or xb.fval2 is not None:
        fa2 = xa.fval2[A] if xa.fval2 is not None else np.zeros(np.shape(A))
        fb2 = xb.fval2[B] if xb.fval2 is not None else np.zeros(np.shape(B))
        close = close & _float_close(fa2, fb2)
    tol_ok = close & ~nonrep_a & ~nonrep_b
    # non-numeric elements in a tolerant column (e.g. missing, or str inside an object column)
    # were already equal through the group key
    num = (np.isin(xa.cls[A], (K_NUM, K_CPLX)) | np.isin(xb.cls[B], (K_NUM, K_CPLX)))
    return np.where(num, np.where(ai & bi, eq_int, tol_ok), True)


def _bipartite(ok, budget):
    """Perfect matching on a boolean matrix (greedy start + Kuhn augmenting paths).
    Returns (match_of_row array or None, evaluations used)."""
    n = ok.shape[0]
    adj = [np.flatnonzero(ok[i]).tolist() for i in range(n)]
    used = sum(len(x) for x in adj)
    match_col = [-1] * n
    match_row = [-1] * n
    for i in range(n):                       # greedy
        for j in adj[i]:
            if match_col[j] < 0:
                match_col[j], match_row[i] = i, j
                break
    for i in range(n):
        if match_row[i] >= 0:
            continue
        if not adj[i]:
            return None, used
        # iterative DFS for an augmenting path from row i
        seen = set()
        stack = [(i, iter(adj[i]))]
        parent = {}
        found = None
        while stack and found is None:
            r, it = stack[-1]
            advanced = False
            for j in it:
                used += 1
                if used > budget:
                    return None, used
                if j in seen:
                    continue
                seen.add(j)
                parent[j] = r
                if match_col[j] < 0:
                    found = j
                    break
                stack.append((match_col[j], iter(adj[match_col[j]])))
                advanced = True
                break
            if found is None and not advanced:
                stack.pop()
        if found is None:
            return None, used
        j = found
        while True:                          # flip the path
            r = parent[j]
            prev = match_row[r]
            match_col[j], match_row[r] = r, j
            if r == i:
                break
            j = prev
    return np.array(match_row, dtype=np.int64), used


class _Matcher:
    """Candidate row permutations for one object pair (cached per level)."""

    def __init__(self, a, b):
        self.a, self.b = a, b
        self.how = {}
        self.limit_hit = set()
        self._elems = {}

    def _pairs(self, with_index):
        pairs = list(zip(self.a.cols, self.b.cols))
        if with_index and self.a.kind in ("DataFrame", "Series"):
            pairs += list(zip(self.a.idx, self.b.idx))
        return pairs

    def _col_elems(self, j, L):
        """(elems_a, elems_b, skey ranks a, skey ranks b) for pair column j at level L, cached;
        E3 and E4 share the same element normalisation."""
        lk = "E2" if L == "E2" else "E3"
        key = ("col", j, lk)
        if key not in self._elems:
            ncols = len(self.a.cols)
            x = self.a.cols[j] if j < ncols else self.a.idx[j - ncols]
            y = self.b.cols[j] if j < ncols else self.b.idx[j - ncols]
            ok, _ = _families_compatible(x.family, y.family, x, y)
            if not ok:
                raise _NotNormalisable("family")
            ea, eb = _level_elems(x, lk), _level_elems(y, lk)
            ra = rb = None
            if ea.skey is not None or eb.skey is not None:
                sa = ea.skey if ea.skey is not None else np.full(len(ea.cls), "", dtype=object)
                sb = eb.skey if eb.skey is not None else np.full(len(eb.cls), "", dtype=object)
                ra, rb = _joint_rank(sa, sb)
            self._elems[key] = (ea, eb, ra, rb)
        return self._elems[key]

    def _elem_pairs(self, L, with_index):
        n_pairs = len(self._pairs(with_index))
        return [self._col_elems(j, L)[:2] for j in range(n_pairs)]

    def column_feasible(self, L, why, with_index):
        """Necessary condition, checked on the column named in `why` only: its two value
        multisets can be matched at level L (exact at E1; element relation at E2+, numbers
        within tolerance after sorting each side by value). False -> no row permutation of the
        whole table can exist."""
        import re
        m = re.search(r"(col|index)(\d+):row=", why)
        if not m:
            return True
        j = int(m.group(2))
        if m.group(1) == "index":
            j += len(self.a.cols)
        return self._col_feasible(L, j, with_index)

    def all_columns_feasible(self, L, with_index, skip=None):
        """The single-column necessary condition for every column (cheap single-column sorts);
        False as soon as one column cannot match on its own."""
        n_pairs = len(self.a.cols) + (len(self.a.idx) if with_index and self.a.kind in ("DataFrame", "Series") else 0)
        for j in range(n_pairs):
            if j == skip:
                continue
            if not self._col_feasible(L, j, with_index):
                return False
        return True

    def _col_feasible(self, L, j, with_index):
        ncols = len(self.a.cols)
        if j < ncols:
            dx, dy = self.a.cols.descs[j], self.b.cols.descs[j]
        else:
            if not (with_index and self.a.kind in ("DataFrame", "Series")) or j - ncols >= len(self.a.idx):
                return True
            dx, dy = self.a.idx.descs[j - ncols], self.b.idx.descs[j - ncols]
        if _same_content(dx, dy):
            return True        # identical content: trivially the same multiset
        x = self.a.cols[j] if j < ncols else self.a.idx[j - ncols]
        y = self.b.cols[j] if j < ncols else self.b.idx[j - ncols]
        if L == "E1":
            ax, ay = x.arrays_for_exact(), y.arrays_for_exact()
            if sorted(ax) != sorted(ay):
                return False
            ka, kb = [], []
            for k in sorted(ax):
                ra, rb = _joint_rank(ax[k], ay[k])
                ka.append(ra)
                kb.append(rb)
            ka, kb = _prune_keys(ka, kb)
            return _same_multiset(ka, kb)
        try:
            ea, eb, ra, rb = self._col_elems(j, L)
        except _NotNormalisable:
            return False
        ka, kb = [ea.cls, ea.ikey], [eb.cls, eb.ikey]
        if ra is not None:
            ka.append(ra)
            kb.append(rb)
        ka, kb = _prune_keys(ka, kb)
        if not _same_multiset(ka, kb):
            return False   # exact parts (classes, exact keys) differ as multisets
        # numbers: sorted pairing is optimal for the relative-tolerance relation when both sides
        # are plain numeric columns (int/float families); other columns skip this test
        if x.family in ("int", "float") and y.family in ("int", "float"):
            fa = np.where(ea.fval == 0, 0.0, ea.fval)
            fb = np.where(eb.fval == 0, 0.0, eb.fval)
            if np.array_equal(ea.cls, ea.cls[:1].repeat(len(ea.cls))) and np.array_equal(eb.cls, eb.cls[:1].repeat(len(eb.cls))) \
                    and not ea.isint.any() and not eb.isint.any():
                oa, ob = np.argsort(fa, kind="stable"), np.argsort(fb, kind="stable")
            else:
                oa = np.lexsort((ea.ival, fa, ea.cls))
                ob = np.lexsort((eb.ival, fb, eb.cls))
            if not bool(np.all(_num_relation(ea, eb, oa, ob))):
                return False
        return True

    def sorted_perms(self, L, with_index):
        key = ("sorted", L, with_index)
        if key not in self._elems:
            self._elems[key] = self._sorted_perms(L, with_index)
        return self._elems[key]

    def _sorted_perms(self, L, with_index):
        a, b = self.a, self.b
        ka, kb = [], []
        tie_a, tie_b = [], []
        if L == "E1":
            for x, y in self._pairs(with_index):
                ax, ay = x.arrays_for_exact(), y.arrays_for_exact()
                if sorted(ax) != sorted(ay):
                    raise _NotNormalisable("arrays")
                for k in sorted(ax):
                    ra, rb = _joint_rank(ax[k], ay[k])
                    ka.append(ra)
                    kb.append(rb)
        else:
            for jj in range(len(self._pairs(with_index))):
                ea, eb, ra, rb = self._col_elems(jj, L)
                ka += [ea.cls, ea.ikey]
                kb += [eb.cls, eb.ikey]
                if ra is not None:
                    ka.append(ra)
                    kb.append(rb)
                ka.append(_round_sig(ea.fval))
                kb.append(_round_sig(eb.fval))
                tie_a.append(np.where(ea.fval == 0, 0.0, ea.fval))
                tie_b.append(np.where(eb.fval == 0, 0.0, eb.fval))
                if ea.fval2 is not None or eb.fval2 is not None:
                    f2a = ea.fval2 if ea.fval2 is not None else np.zeros(len(ea.cls))
                    f2b = eb.fval2 if eb.fval2 is not None else np.zeros(len(eb.cls))
                    ka.append(_round_sig(f2a))
                    kb.append(_round_sig(f2b))
                    tie_a.append(f2a)
                    tie_b.append(f2b)
        ka, kb = _prune_keys(ka, kb)
        tie_a, tie_b = _prune_keys(tie_a, tie_b)
        if not ka and not tie_a:
            n = a.nrows()
            return np.arange(n), np.arange(n)
        return _sort_rows(ka, tie_a), _sort_rows(kb, tie_b)

    def group_match(self, L, with_index):
        """Bipartite matching inside groups of rows with equal non-tolerant parts (E2+)."""
        a = self.a
        n = a.nrows()
        try:
            pairs = self._elem_pairs(L, with_index)
        except _NotNormalisable:
            return None
        ga_keys, gb_keys, tol = [], [], []
        for jj, (ea, eb) in enumerate(pairs):
            ra, rb = self._col_elems(jj, L)[2:]
            ga_keys += [ea.cls, ea.ikey]
            gb_keys += [eb.cls, eb.ikey]
            if ra is not None:
                ga_keys.append(ra)
                gb_keys.append(rb)
            if ea.exact_int and eb.exact_int:
                ga_keys.append(ea.ival)       # int vs int is exact: part of the group key
                gb_keys.append(eb.ival)
            elif (np.isin(ea.cls, (K_NUM, K_CPLX)).any() or np.isin(eb.cls, (K_NUM, K_CPLX)).any()):
                tol.append((ea, eb))
        ga_keys, gb_keys = _prune_keys(ga_keys, gb_keys)
        if not ga_keys and len(tol) == 1 and tol[0][0].fval2 is None and tol[0][1].fval2 is None:
            # one tolerant column and no exact key: the canonical sort is the exact value sort,
            # which is already the optimal pairing for the relative-tolerance relation
            return None
        if ga_keys:
            ids = _group_ids([np.concatenate([x, y]) for x, y in zip(ga_keys, gb_keys)])
            ga, gb = ids[:n], ids[n:]
        else:
            ga = gb = np.zeros(n, np.int64)
        ng = int(max(ga.max(initial=-1), gb.max(initial=-1))) + 1
        if not np.array_equal(np.bincount(ga, minlength=ng), np.bincount(gb, minlength=ng)):
            return None
        oa = np.argsort(ga, kind="stable")
        ob = np.argsort(gb, kind="stable")
        if not tol:
            return oa, ob
        # within groups: start from the tolerant sort order, then repair by matching
        pa_sorted, pb_sorted = self.sorted_perms(L, with_index)
        rank_a = np.empty(n, np.int64)
        rank_a[pa_sorted] = np.arange(n)
        rank_b = np.empty(n, np.int64)
        rank_b[pb_sorted] = np.arange(n)
        oa = np.lexsort((rank_a, ga))
        ob = np.lexsort((rank_b, gb))
        counts = np.bincount(ga[oa], minlength=ng)
        bounds = np.concatenate([[0], np.cumsum(counts)])
        budget = MATCH_BUDGET
        out_b = ob.copy()
        for g in np.flatnonzero(counts > 1):
            s0, s1 = int(bounds[g]), int(bounds[g + 1])
            ia, ib = oa[s0:s1], ob[s0:s1]
            k = s1 - s0
            # positional pairs from the sorted order that already satisfy the relation
            okpos = np.ones(k, bool)
            for ea, eb in tol:
                okpos &= _num_relation(ea, eb, ia, ib)
            if okpos.all():
                continue
            if k > MATCH_LIMIT:
                ra_, rb_ = ia[~okpos], ib[~okpos]
                if len(ra_) > MATCH_LIMIT:
                    self.limit_hit.add(L)
                    return None
                # residual only (approximate for huge tie groups; noted when it fails)
                sub_a, sub_b, base = ra_, rb_, np.flatnonzero(~okpos)
            else:
                sub_a, sub_b, base = ia, ib, np.arange(k)
            rel = np.ones((len(sub_a), len(sub_b)), bool)
            for ea, eb in tol:
                rel &= _num_relation(ea, eb, sub_a[:, None], sub_b[None, :])
                budget -= rel.size
            if budget < 0:
                self.limit_hit.add(L)
                return None
            match, used = _bipartite(rel, max(budget, 0))
            budget -= used
            if match is None:
                if budget < 0:
                    self.limit_hit.add(L)
                return None
            seg = out_b[s0:s1].copy()
            seg[base] = sub_b[match]
            out_b[s0:s1] = seg
        return oa, out_b


def worst(levels):
    """Coarsest outcome over several outputs of one cell."""
    order = {L: i for i, L in enumerate(LEVELS + ["UNCOMPARABLE", "DIFF"])}
    return max(levels, key=lambda L: order[L]) if levels else None

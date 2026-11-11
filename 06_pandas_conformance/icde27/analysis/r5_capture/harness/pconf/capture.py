"""Capture of cell outputs into a content-addressed column store (Arrow IPC) + JSON records.

Runs inside every engine environment (pandas 1.5.3 / 2.3.3 / 3.0.x, pyarrow 17-25, numpy 1.26-2.5),
and in the comparison environment (dfeq). Only numpy, pandas and pyarrow are imported.

Model
-----
A captured value becomes an *object record* (JSON-able dict):
    {"kind": DataFrame|Series|Index|MultiIndex|ndarray|scalar|list|tuple|set|dict|other|module|callable|unconvertible,
     "h":    object hash (sha256) of the E0-relevant content, or None if not hashable,
     "meta": E0-relevant metadata (shape, column labels, names, index dtype strings, ...),
     "cols": [column descriptors], "idx": [index-level descriptors],
     "info": non-content info (python type, conversion route, capped columns, timings)}
A column descriptor is {"h": column hash, "enc": encoding, "dtype": dtype string, "x": extra,
"n": length, "stored": bool}. Column data lives in captures/cols/<h[:2]>/<h>.arrow (zstd Arrow IPC),
written once (dedup across cells, notebooks and engines: E0-equal columns share one file).

The column hash covers encoding, dtype string, extra metadata and the exact value bytes, and the
object hash covers kind, meta and the column hashes. Hence, by construction,
    object hash equal  <=>  E0 (bit-exact) equal,
which is what dfeq's E0 check and classify's clean-input test use.

Encodings (missing-kind codes: 0 value, 1 None, 2 NaN, 3 pd.NA, 4 NaT)
    num    numpy bool/int/uint/float: 'v' (NaN payloads canonicalised); NaN = missing kind 2
    nmask  masked (Int64, Float64, boolean, ArrowDtype numerics): 'v' + 'm' mask; x.miss = 3
    dt/td  datetime64/timedelta64 (any unit, tz in x): 'v' int64 (NaT->0) + 'm'; x.unit, x.tz
    str    strings with missing: 'v' large_string (missing -> '') + 'k' missing kinds
    obj    anything else: per element 't' tag, 'p' exact payload string, 'y' python type name
    cat    categorical: 'c' codes; categories stored as their own column (x.cats descriptor)
    cplx   complex: 're', 'im'
"""
import datetime as _dt
import decimal as _decimal
import hashlib
import json
import os
import time
import types as _types

import numpy as np

# R5 B1 copy (2026-11-10): exact recursive encoding of nested values. The original module (capture_orig.py, byte-
# identical to src/pconf/capture.py) gives an element of an object column that is a container, a frame, an array or
# any other object without an exact scalar encoding tag T_CONTAINER (a printed form of its elements) or T_OTHER
# (repr). Here such an element is captured recursively as an object record of its own (engine objects first converted
# with the engine's own conversion, as for top-level values) and tagged T_NESTED with the payload "<kind>#<object
# hash>", so equal payloads <=> E0-equal nested values. Lazy engine scalars become their computed exact scalar tag;
# NumPy and pandas dtype objects, ranges, slices and bound methods get exact pseudo-records. Only an element that has
# no exact encoding even then (an arbitrary object, a nesting deeper than MAX_NEST_DEPTH, a nested budget overrun)
# keeps T_OTHER with its repr, and the Capturer lists it in `nested_inexact`. Everything else (encodings, hashes,
# ENCODING_VERSION) is unchanged, so a value without such elements has the same hash under both modules.
# A nested container whose elements are (recursively) exactly tagged scalars is encoded inline, without a record of its
# own: payload "<kind>j#<canonical JSON of [tag, payload, type] triples>" (JSON escaping makes it unambiguous), or
# "<kind>h#<sha256 of that JSON>" above INLINE_MAX_CHARS; insertion order is kept for lists, tuples and dicts (as the
# original printed form did) and set elements are sorted. Nested object records are limited to NEST_RECORD_BUDGET per
# top-level value; elements beyond it stay T_OTHER and are listed as inexact.
ENCODING_VERSION = 1

# missing kinds
M_NONE, M_NAN, M_NA, M_NAT = 1, 2, 3, 4
# object tags
T_STR, T_NONE, T_NAN, T_NA, T_NAT, T_BOOL, T_INT, T_FLOAT, T_BYTES, T_DATETIME, T_TIMEDELTA, \
    T_DATE, T_TIME, T_DECIMAL, T_COMPLEX, T_CONTAINER, T_OTHER, T_PERIOD, T_INTERVAL = range(19)
T_NESTED = 19          # R5 B1: exactly encoded nested value, payload "<kind>#<object hash>"
TAG_MISSING = {T_NONE: M_NONE, T_NAN: M_NAN, T_NA: M_NA, T_NAT: M_NAT}
MAX_NEST_DEPTH = int(os.environ.get("PCONF_MAX_NEST_DEPTH", 8))
NEST_CELL_BUDGET = int(os.environ.get("PCONF_NEST_CELL_BUDGET", 50_000_000))   # nested cells per top-level capture
NEST_RECORD_BUDGET = int(os.environ.get("PCONF_NEST_RECORD_BUDGET", 2000))     # nested object records per top-level capture
INLINE_MAX_CHARS = 2048       # a container of scalars is encoded inline (canonical JSON) up to this length, else hashed
INLINE_MAX_ELEMS = 100_000
_NEST_STACK = []       # active Capturer while a top-level value is encoded (tag_value consults it)

DEFAULT_LIMITS = {
    "max_cells": int(os.environ.get("PCONF_MAX_CELLS", 200_000_000)),     # per object; above: hash only
    "max_container": int(os.environ.get("PCONF_MAX_CONTAINER", 1_000_000)),
    "run_budget_bytes": int(float(os.environ.get("PCONF_RUN_BLOB_BUDGET_GB", 6)) * 1e9),
}


def _pd():
    import pandas as pd
    return pd


def _pa():
    import pyarrow as pa
    return pa


# ----------------------------------------------------------------------------- engine -> pandas

def to_pandas_obj(x):
    """Convert an engine object to a plain pandas/numpy/python object with the engine's own
    conversion (documented confound). Returns (obj, route) or raises."""
    pd = _pd()
    mod = type(x).__module__ or ""
    top = mod.split(".")[0]
    if top in ("pandas", "numpy", "builtins") or mod == "":
        return x, "native"
    if top == "modin":
        if hasattr(x, "_to_pandas"):
            return x._to_pandas(), "modin._to_pandas"
        return x, "native"
    if top == "fireducks":
        for m in ("to_pandas", "_to_pandas"):
            if hasattr(x, m):
                return getattr(x, m)(), "fireducks." + m
        return x, "native"
    if top == "bodo":
        return _bodo_to_plain(x), "bodo.execute_plan"
    if top == "dask":
        if hasattr(x, "compute"):
            return x.compute(), "dask.compute"
        return x, "native"
    if isinstance(x, (pd.DataFrame, pd.Series, pd.Index)) and type(x) not in (pd.DataFrame, pd.Series):
        return x, "subclass"
    return x, "native"


def _bodo_to_plain(x):
    pd = _pd()
    if hasattr(x, "execute_plan"):
        try:
            x.execute_plan()
        except Exception:
            pass
    if isinstance(x, pd.DataFrame):
        arrays = [x.iloc[:, j].array for j in range(x.shape[1])]
        idx = _bodo_to_plain(x.index) if not type(x.index).__module__.startswith("pandas") else x.index
        out = pd.DataFrame(dict(zip(range(len(arrays)), arrays)), index=idx, copy=False)
        out.columns = x.columns
        return out
    if isinstance(x, pd.Series):
        return pd.Series(x.array, index=x.index, name=x.name, copy=False)
    return x


# ----------------------------------------------------------------------------- tagging scalars

def _type_name(v):
    t = type(v)
    m = t.__module__
    return t.__name__ if m in ("builtins",) else "%s.%s" % (m.split(".")[0], t.__name__)


def tag_value(v):
    """Python/numpy/pandas scalar -> (tag, payload string, type name). Exact and deterministic."""
    pd = _pd()
    tn = _type_name(v)
    if v is None:
        return T_NONE, "", tn
    if v is pd.NA:
        return T_NA, "", tn
    if v is pd.NaT:
        return T_NAT, "", tn
    if isinstance(v, (str, np.str_)):
        return T_STR, str(v), tn
    if isinstance(v, (bool, np.bool_)):
        return T_BOOL, "True" if v else "False", tn
    if isinstance(v, (int, np.integer)):
        return T_INT, str(int(v)), tn
    if isinstance(v, (float, np.floating)):
        f = float(v)
        if f != f:
            return T_NAN, "", tn
        return T_FLOAT, repr(f), tn
    if isinstance(v, (complex, np.complexfloating)):
        return T_COMPLEX, repr(complex(v)), tn
    if isinstance(v, np.datetime64):
        if np.isnat(v):
            return T_NAT, "", tn
        try:
            return T_DATETIME, "%d|None" % pd.Timestamp(v).value, tn
        except Exception:
            return T_OTHER, repr(v), tn
    if isinstance(v, np.timedelta64):
        if np.isnat(v):
            return T_NAT, "", tn
        try:
            return T_TIMEDELTA, str(pd.Timedelta(v).value), tn
        except Exception:
            return T_OTHER, repr(v), tn
    if isinstance(v, _dt.datetime):  # includes pd.Timestamp
        try:
            ts = pd.Timestamp(v)
            return T_DATETIME, "%d|%s" % (ts.value, str(ts.tz) if ts.tz is not None else "None"), tn
        except Exception:
            return T_OTHER, repr(v), tn
    if isinstance(v, _dt.timedelta):  # includes pd.Timedelta
        try:
            return T_TIMEDELTA, str(pd.Timedelta(v).value), tn
        except Exception:
            return T_OTHER, repr(v), tn
    if isinstance(v, _dt.date):
        return T_DATE, v.isoformat(), tn
    if isinstance(v, _dt.time):
        return T_TIME, v.isoformat(), tn
    if isinstance(v, _decimal.Decimal):
        if v.is_nan():
            return T_NAN, "", tn
        return T_DECIMAL, str(v), tn
    if isinstance(v, bytes):
        return T_BYTES, v.hex(), tn
    if isinstance(v, pd.Period):
        return T_PERIOD, str(v), tn
    if isinstance(v, pd.Interval):
        return T_INTERVAL, repr(v), tn
    if _NEST_STACK:
        return _NEST_STACK[-1].nested_tag(v)
    if isinstance(v, (list, tuple, dict, set, frozenset)):
        return T_CONTAINER, _container_repr(v), tn
    try:
        r = repr(v)
    except Exception:
        r = "<unrepr>"
    return T_OTHER, r, tn


def _safe_repr(v):
    try:
        return repr(v)
    except Exception:
        return "<unrepr>"


def _container_repr(v, depth=0):
    if depth > 4:
        return "..."
    if isinstance(v, dict):
        items = [(_container_repr(k, depth + 1), _container_repr(x, depth + 1)) for k, x in v.items()]
        return "{" + ",".join("%s:%s" % kv for kv in items) + "}"
    if isinstance(v, (set, frozenset)):
        return "set(" + ",".join(sorted(_container_repr(x, depth + 1) for x in v)) + ")"
    if isinstance(v, (list, tuple)):
        o, c = ("[", "]") if isinstance(v, list) else ("(", ")")
        return o + ",".join(_container_repr(x, depth + 1) for x in v) + c
    t, p, y = tag_value(v)
    return "%d:%s:%s" % (t, y, p)


def is_scalar_like(v):
    pd = _pd()
    return (v is None or v is pd.NA or v is pd.NaT or isinstance(
        v, (str, bytes, bool, int, float, complex, np.generic, _dt.datetime, _dt.date, _dt.time,
            _dt.timedelta, _decimal.Decimal, pd.Period, pd.Interval)))


# ----------------------------------------------------------------------------- column encoders

def _canon_float(a):
    a = np.ascontiguousarray(a)
    if a.dtype == np.float16:
        a = a.astype(np.float32)
    nan = np.isnan(a)
    if nan.any():
        a = a.copy()
        a[nan] = np.nan  # canonical NaN bit pattern
    return a


def _missing_code(v):
    pd = _pd()
    if v is None:
        return M_NONE
    if v is pd.NA:
        return M_NA
    if v is pd.NaT:
        return M_NAT
    if isinstance(v, float) and v != v:
        return M_NAN
    if isinstance(v, np.floating) and v != v:
        return M_NAN
    if isinstance(v, (np.datetime64, np.timedelta64)) and np.isnat(v):
        return M_NAT
    return 0


def _encode_strings_or_obj(arr, na_code_for_null=None):
    """Object ndarray -> ('str', arrays, x) when all non-missing are str, else ('obj', ...)."""
    pd = _pd()
    arr = np.asarray(arr, dtype=object)
    n = len(arr)
    if n == 0:
        return "str", {"v": np.array([], dtype=object), "k": np.zeros(0, np.uint8)}, {}
    inferred = pd.api.types.infer_dtype(arr, skipna=True)
    if inferred in ("string", "empty"):
        miss = pd.isna(arr)
        k = np.zeros(n, np.uint8)
        if miss.any():
            vals = arr.copy()
            for i in np.flatnonzero(miss):
                c = _missing_code(arr[i])
                k[i] = c if c else (na_code_for_null or M_NONE)
                vals[i] = ""
        else:
            vals = arr
        # numpy str_ subclasses are str; normalise to str for arrow
        return "str", {"v": vals, "k": k}, {}
    return _encode_obj(arr)


def _encode_obj(arr):
    n = len(arr)
    t = np.empty(n, np.uint8)
    p = [None] * n
    y = [None] * n
    for i, v in enumerate(arr):
        a, b, c = tag_value(v)
        t[i] = a
        p[i] = b
        y[i] = c
    return "obj", {"t": t, "p": np.array(p, dtype=object), "y": np.array(y, dtype=object)}, {}


def _arrow_chunked(values):
    pa = _pa()
    for attr in ("_pa_array", "_data"):
        ca = getattr(values, attr, None)
        if isinstance(ca, (pa.ChunkedArray, pa.Array)):
            return ca if isinstance(ca, pa.ChunkedArray) else pa.chunked_array([ca])
    res = values.__arrow_array__()
    return res if isinstance(res, pa.ChunkedArray) else pa.chunked_array([res])


def _encode_arrow(ca, na_code=M_NA):
    pa = _pa()
    import pyarrow.compute as pc
    t = ca.type
    arr = ca.combine_chunks() if ca.num_chunks != 1 else ca.chunk(0)
    n = len(arr)
    nulls = np.asarray(arr.is_null().to_numpy(zero_copy_only=False), dtype=bool) if n else np.zeros(0, bool)
    if pa.types.is_integer(t) or pa.types.is_floating(t) or pa.types.is_boolean(t):
        filled = arr.fill_null(False if pa.types.is_boolean(t) else 0)
        v = np.asarray(filled.to_numpy(zero_copy_only=False))
        if v.dtype.kind == "f":
            v = _canon_float(v)
        return "nmask", {"v": np.ascontiguousarray(v), "m": nulls}, {"miss": na_code}
    if pa.types.is_string(t) or pa.types.is_large_string(t) or getattr(pa.types, "is_string_view", lambda _: False)(t):
        vals = np.asarray(arr.fill_null("").to_numpy(zero_copy_only=False), dtype=object)
        return "str", {"v": vals, "k": np.where(nulls, na_code, 0).astype(np.uint8)}, {}
    if pa.types.is_timestamp(t) or pa.types.is_duration(t):
        v = np.asarray(pc.cast(arr, pa.int64()).fill_null(0).to_numpy(zero_copy_only=False), dtype=np.int64)
        enc = "dt" if pa.types.is_timestamp(t) else "td"
        x = {"unit": t.unit, "tz": (str(t.tz) if getattr(t, "tz", None) else None), "miss": na_code}
        return enc, {"v": v, "m": nulls}, x
    # anything else (dates, decimals, lists, structs): python objects
    vals = np.empty(n, dtype=object)
    vals[:] = arr.to_pylist()
    vals[nulls] = None
    enc, d, x = _encode_obj(vals)
    if nulls.any():
        d["t"][nulls] = T_NA if na_code == M_NA else T_NONE
    return enc, d, x


def encode_values(values, dtype):
    """values: numpy array or pandas ExtensionArray; dtype: its dtype.
    Returns (enc, arrays dict, extra dict, subcolumns list of (name, values, dtype))."""
    pd = _pd()
    if isinstance(dtype, np.dtype):
        k = dtype.kind
        arr = np.asarray(values)
        if k in "biu":
            return "num", {"v": np.ascontiguousarray(arr)}, {}, []
        if k == "f":
            return "num", {"v": _canon_float(arr)}, {}, []
        if k == "c":
            return "cplx", {"re": _canon_float(arr.real), "im": _canon_float(arr.imag)}, {}, []
        if k in "mM":
            unit = np.datetime_data(dtype)[0]
            m = np.isnat(arr)
            v = np.where(m, 0, arr.view("i8")).astype(np.int64)
            return ("dt" if k == "M" else "td"), {"v": v, "m": m}, {"unit": unit, "tz": None, "miss": M_NAT}, []
        if k in "OUS":
            enc, d, x = _encode_strings_or_obj(arr.astype(object) if k != "O" else arr)
            return enc, d, x, []
        enc, d, x = _encode_obj(arr.astype(object))
        return enc, d, x, []
    # extension dtypes
    dname = type(dtype).__name__
    if dname == "DatetimeTZDtype":
        i8 = np.asarray(values.asi8 if hasattr(values, "asi8") else values.view("i8"), dtype=np.int64)
        m = np.asarray(pd.isna(values), dtype=bool)
        unit = getattr(dtype, "unit", "ns")
        return "dt", {"v": np.where(m, 0, i8), "m": m}, {"unit": unit, "tz": str(dtype.tz), "miss": M_NAT}, []
    if dname == "CategoricalDtype":
        codes = np.asarray(values.codes)
        cats = values.categories
        return "cat", {"c": np.ascontiguousarray(codes.astype(np.int64))}, {"ordered": bool(dtype.ordered)}, \
            [("cats", cats.array if hasattr(cats, "array") else np.asarray(cats), cats.dtype)]
    if dname == "PeriodDtype":
        i8 = np.asarray(values.asi8, dtype=np.int64)
        m = np.asarray(pd.isna(values), dtype=bool)
        return "dt", {"v": np.where(m, 0, i8), "m": m}, {"unit": "period[%s]" % getattr(dtype, "freqstr", dtype), "tz": None, "miss": M_NAT}, []
    if hasattr(values, "_data") and hasattr(values, "_mask") and isinstance(getattr(values, "_mask", None), np.ndarray):
        v = np.asarray(values._data)
        m = np.asarray(values._mask, dtype=bool)
        v = np.where(m, v.dtype.type(0) if v.dtype.kind != "b" else False, v)
        if v.dtype.kind == "f":
            v = _canon_float(v)
        return "nmask", {"v": np.ascontiguousarray(v), "m": m}, {"miss": M_NA}, []
    if dname == "StringDtype":
        na_value = getattr(dtype, "na_value", pd.NA)
        na_code = M_NA if na_value is pd.NA else M_NAN
        storage = getattr(dtype, "storage", "python")
        if storage in ("pyarrow", "pyarrow_numpy"):
            ca = _arrow_chunked(values)
            if storage == "pyarrow_numpy":
                na_code = M_NAN
            enc, d, x = _encode_arrow(ca, na_code)
            return enc, d, x, []
        arr = np.asarray(values._ndarray if hasattr(values, "_ndarray") else values, dtype=object)
        enc, d, x = _encode_strings_or_obj(arr, na_code)
        return enc, d, x, []
    if dname == "ArrowDtype":
        enc, d, x = _encode_arrow(_arrow_chunked(values), M_NA)
        return enc, d, x, []
    if dname == "SparseDtype":
        dense = np.asarray(values)
        return encode_values(dense, dense.dtype)
    # Interval and any other extension type: python objects
    enc, d, x = _encode_obj(np.asarray(values, dtype=object))
    return enc, d, x, []


# ----------------------------------------------------------------------------- hashing & storage

def _str_arrow(vals):
    pa = _pa()
    try:
        return pa.array(vals, type=pa.large_string(), from_pandas=False), False
    except (pa.ArrowInvalid, pa.ArrowTypeError, UnicodeEncodeError):
        esc = [s.encode("utf-8", "surrogatepass").decode("utf-8", "backslashreplace") if isinstance(s, str) else str(s)
               for s in vals]
        return pa.array(esc, type=pa.large_string(), from_pandas=False), True


def _to_arrow_arrays(arrays):
    """dict name -> numpy -> dict name -> pyarrow array (strings as large_string)."""
    pa = _pa()
    out, escaped = {}, False
    for k in sorted(arrays):
        a = arrays[k]
        if isinstance(a, np.ndarray) and a.dtype == object:
            arr, esc = _str_arrow(a)
            escaped = escaped or esc
            out[k] = arr
        else:
            out[k] = pa.array(np.ascontiguousarray(a))
    return out, escaped


def _hash_arrow_array(h, arr):
    pa = _pa()
    if pa.types.is_large_string(arr.type):
        bufs = arr.buffers()
        n = len(arr)
        offs = np.frombuffer(bufs[1], dtype=np.int64, count=n + 1, offset=arr.offset * 8)
        start, end = int(offs[0]), int(offs[-1])
        h.update((offs - start).tobytes())
        if bufs[2] is not None and end > start:
            h.update(memoryview(bufs[2])[start:end])
    else:
        a = arr.to_numpy(zero_copy_only=False)
        h.update(np.ascontiguousarray(a).tobytes())


def column_hash(enc, dtype_str, extra, arrow_arrays):
    h = hashlib.sha256()
    h.update(json.dumps([ENCODING_VERSION, enc, dtype_str, extra], sort_keys=True, default=str).encode())
    for k in sorted(arrow_arrays):
        a = arrow_arrays[k]
        h.update(("|%s:%s:%d|" % (k, a.type, len(a))).encode())
        _hash_arrow_array(h, a)
    return h.hexdigest()


def blob_path(store, h):
    return os.path.join(store, "cols", h[:2], h + ".arrow")


def _write_blob(store, h, arrow_arrays, meta):
    pa = _pa()
    path = blob_path(store, h)
    if os.path.exists(path):
        return 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tbl = pa.table(arrow_arrays) if arrow_arrays else pa.table({"_empty": pa.array([], pa.int8())})
    tbl = tbl.replace_schema_metadata({"pconf": json.dumps(meta, default=str)})
    tmp = "%s.tmp.%d" % (path, os.getpid())
    try:
        opts = pa.ipc.IpcWriteOptions(compression="zstd")
    except Exception:
        opts = None
    with pa.OSFile(tmp, "wb") as sink:
        with (pa.ipc.new_file(sink, tbl.schema, options=opts) if opts else pa.ipc.new_file(sink, tbl.schema)) as w:
            w.write_table(tbl)
    size = os.path.getsize(tmp)
    os.replace(tmp, path)
    return size


def load_blob(store, h):
    """-> dict name -> numpy array (strings as object arrays)."""
    pa = _pa()
    with pa.memory_map(blob_path(store, h), "r") as src:
        tbl = pa.ipc.open_file(src).read_all()
    out = {}
    for name in tbl.column_names:
        if name == "_empty":
            continue
        col = tbl.column(name)
        if pa.types.is_large_string(col.type) or pa.types.is_string(col.type):
            out[name] = np.asarray(col.to_numpy(), dtype=object)
        else:
            out[name] = np.asarray(col.to_numpy())
    return out


class Capturer:
    """Encodes values into object records and writes column blobs. One per child run."""

    def __init__(self, store, limits=None, write=True):
        self.store = store
        self.limits = dict(DEFAULT_LIMITS)
        if limits:
            self.limits.update(limits)
        self.write = write
        self.bytes_written = 0
        self.blobs_written = 0
        self.capped_columns = 0
        self._seen = set()
        # R5 B1: nested records (hash -> record) and the elements left without an exact encoding (type -> count)
        self.nested = {}
        self.nested_new = []
        self.nested_inexact = {}
        self.nested_hit = False
        self.last_inexact = {}
        self._depth = 0
        self._nest_cells = 0
        self._nest_records = 0

    # columns ---------------------------------------------------------------
    def column(self, values, dtype, cap=False):
        dstr = str(dtype)
        enc, arrays, extra, subs = encode_values(values, dtype)
        for name, sv, sd in subs:
            extra[name] = self.column(sv, sd, cap=cap)
        aa, escaped = _to_arrow_arrays(arrays)
        if escaped:
            extra["escaped"] = True
        n = len(next(iter(arrays.values()))) if arrays else 0
        # sub-column descriptors enter the hash by their content hash only (not 'stored')
        hx = {k: (v["h"] if isinstance(v, dict) and "h" in v else v) for k, v in extra.items()}
        h = column_hash(enc, dstr, hx, aa)
        stored = False
        if self.write and not cap:
            if h in self._seen or os.path.exists(blob_path(self.store, h)):
                stored = True
            elif self.bytes_written < self.limits["run_budget_bytes"]:
                sz = _write_blob(self.store, h, aa, {"enc": enc, "dtype": dstr, "x": extra})
                self.bytes_written += sz
                self.blobs_written += 1 if sz else 0
                stored = True
        if stored:
            self._seen.add(h)
        else:
            self.capped_columns += 1
        return {"h": h, "enc": enc, "dtype": dstr, "x": extra, "n": int(n), "stored": stored}

    # objects ---------------------------------------------------------------
    def capture(self, value):
        t0 = time.perf_counter()
        self.nested_hit = False
        self.last_inexact = {}
        self._nest_cells = 0
        self._nest_records = 0
        _NEST_STACK.append(self)
        try:
            rec = self._capture(value)
        except Exception as e:  # never let capture kill the run
            rec = {"kind": "unconvertible", "h": None, "info": {"error": "%s: %s" % (type(e).__name__, str(e)[:300]),
                                                                  "type": _type_name(value)}}
        finally:
            _NEST_STACK.pop()
        rec.setdefault("info", {})["capture_s"] = round(time.perf_counter() - t0, 6)
        if self.nested_hit:
            rec["info"]["nested"] = True
            if self.last_inexact:
                rec["info"]["nested_inexact"] = dict(self.last_inexact)
        return rec

    # nested values (R5 B1) ---------------------------------------------------
    def _inexact(self, v, why, tn=None):
        tn = tn or _type_name(v)
        key = "%s:%s" % (why, tn)
        self.nested_inexact[key] = self.nested_inexact.get(key, 0) + 1
        self.last_inexact[key] = self.last_inexact.get(key, 0) + 1
        return T_OTHER, _safe_repr(v), tn

    def _keep(self, rec):
        h = rec["h"]
        if h not in self.nested:
            self.nested[h] = rec
            self.nested_new.append(h)
        return h

    def _pseudo(self, kind, meta):
        h = hashlib.sha256(json.dumps([ENCODING_VERSION, kind, meta], sort_keys=True, default=str).encode()).hexdigest()
        return {"kind": kind, "h": h, "meta": meta, "cols": [], "idx": [], "info": {}}

    def _tag_plain(self, v):
        """tag_value without the nested hook (scalars)."""
        _NEST_STACK.append(None)
        try:
            t, p, y = tag_value(v) if not isinstance(v, (list, tuple, dict, set, frozenset)) else (None, None, None)
        finally:
            _NEST_STACK.pop()
        if t is None or t == T_OTHER:
            return self._inexact(v, "scalar_without_encoding")
        return t, p, y

    def _inline(self, v, depth, count):
        """Canonical JSON-able form of a container of exactly tagged scalars, or None."""
        if depth > MAX_NEST_DEPTH:
            return None
        if isinstance(v, (list, tuple, set, frozenset)):
            count[0] += len(v)
            if count[0] > INLINE_MAX_ELEMS:
                return None
            items = []
            for x in v:
                e = self._inline(x, depth + 1, count)
                if e is None:
                    return None
                items.append(e)
            if isinstance(v, (set, frozenset)):
                items.sort(key=lambda e: json.dumps(e, ensure_ascii=False, separators=(",", ":")))
                return ["set", items]
            return ["tuple" if isinstance(v, tuple) else "list", items]
        if isinstance(v, dict):
            count[0] += len(v)
            if count[0] > INLINE_MAX_ELEMS:
                return None
            items = []
            for k, x in v.items():
                ek, ex = self._inline(k, depth + 1, count), self._inline(x, depth + 1, count)
                if ek is None or ex is None:
                    return None
                items.append([ek, ex])
            return ["dict", items]
        if v is None or is_scalar_like(v):
            _NEST_STACK.append(None)
            try:
                t, p, y = tag_value(v)
            finally:
                _NEST_STACK.pop()
            return None if t == T_OTHER else [int(t), p, y]
        return None

    def nested_tag(self, v):
        """An element that the original module prints (T_CONTAINER / T_OTHER) -> exact tag or (T_OTHER, repr)."""
        pd = _pd()
        self.nested_hit = True
        if self._depth >= MAX_NEST_DEPTH:
            return self._inexact(v, "depth")
        if isinstance(v, (list, tuple, dict, set, frozenset)):
            form = self._inline(v, self._depth, [0])
            if form is not None:
                kind = form[0]
                js = json.dumps(form[1], ensure_ascii=False, separators=(",", ":"))
                if len(js) <= INLINE_MAX_CHARS:
                    return T_NESTED, kind + "j#" + js, _type_name(v)
                return T_NESTED, kind + "h#" + hashlib.sha256(js.encode("utf-8", "surrogatepass")).hexdigest(), _type_name(v)
        self._depth += 1
        try:
            tn0 = _type_name(v)
            top = (type(v).__module__ or "").split(".")[0]
            if top in ("modin", "fireducks", "bodo", "dask"):
                try:
                    v, _route = to_pandas_obj(v)
                except Exception as e:
                    return self._inexact(v, "conversion_error", tn0)
            if v is None or is_scalar_like(v):
                return self._tag_plain(v)
            tn = _type_name(v)
            if isinstance(v, np.dtype) or isinstance(v, pd.api.extensions.ExtensionDtype):
                meta = {"type": tn, "str": str(v)}
                if isinstance(v, np.dtype):
                    meta.update({"repr": repr(v), "descr": str(v.descr), "byteorder": v.str})
                elif type(v).__name__ == "CategoricalDtype":
                    cats = v.categories
                    meta.update({"ordered": bool(v.ordered),
                                 "categories": None if cats is None else self._keep(self._capture(cats))})
                else:
                    meta.update({"repr": repr(v), "storage": str(getattr(v, "storage", None)),
                                 "na_value": repr(getattr(v, "na_value", None))})
                return T_NESTED, "dtype#" + self._keep(self._pseudo("dtype", meta)), tn
            if isinstance(v, range):
                return T_NESTED, "range#" + self._keep(self._pseudo("range", [v.start, v.stop, v.step])), tn
            if isinstance(v, slice):
                meta = [list(self.nested_tag(x)) if not is_scalar_like(x) and x is not None else list(self._tag_plain(x))
                        for x in (v.start, v.stop, v.step)]
                return T_NESTED, "slice#" + self._keep(self._pseudo("slice", meta)), tn
            if isinstance(v, _types.MethodType):
                f = v.__func__
                meta = {"func": "%s.%s" % (getattr(f, "__module__", "?"), getattr(f, "__qualname__", "?")),
                        "self": list(self.nested_tag(v.__self__))}
                if meta["self"][0] == T_OTHER:
                    return self._inexact(v, "method_self_without_encoding", tn)
                return T_NESTED, "method#" + self._keep(self._pseudo("method", meta)), tn
            size = None
            if isinstance(v, (pd.DataFrame, pd.Series, pd.Index, np.ndarray)) or isinstance(v, pd.api.extensions.ExtensionArray):
                try:
                    size = int(np.prod(v.shape)) if hasattr(v, "shape") else len(v)
                except Exception:
                    size = None
            elif isinstance(v, (list, tuple, dict, set, frozenset)):
                size = len(v)
            if size is None:
                return self._inexact(v, "no_exact_encoding", tn)
            if self._nest_cells + size > NEST_CELL_BUDGET:
                return self._inexact(v, "nested_budget", tn)
            if self._nest_records >= NEST_RECORD_BUDGET:
                return self._inexact(v, "nested_record_budget", tn)
            self._nest_cells += size
            self._nest_records += 1
            rec = self._capture(v)
            if rec.get("h") is None:
                return self._inexact(v, "no_exact_encoding:" + str(rec.get("kind")), tn)
            if (rec.get("info") or {}).get("capped"):
                return self._inexact(v, "capped", tn)
            rec.setdefault("info", {}).setdefault("type", tn)
            return T_NESTED, "%s#%s" % (rec["kind"], self._keep(rec)), tn
        finally:
            self._depth -= 1

    def _capture(self, value):
        import types
        pd = _pd()
        if isinstance(value, types.ModuleType):
            return {"kind": "module", "h": None, "info": {"type": value.__name__}}
        if isinstance(value, type) or (callable(value) and not hasattr(value, "shape")
                                       and not isinstance(value, (pd.DataFrame, pd.Series, pd.Index, np.ndarray))):
            return {"kind": "callable", "h": None, "info": {"type": _type_name(value)}}
        route = "native"
        try:
            value, route = to_pandas_obj(value)
        except Exception as e:
            return {"kind": "unconvertible", "h": None,
                    "info": {"type": _type_name(value), "error": "%s: %s" % (type(e).__name__, str(e)[:300])}}
        if isinstance(value, pd.DataFrame):
            rec = self._frame(value)
        elif isinstance(value, pd.Series):
            rec = self._series(value)
        elif isinstance(value, pd.Index):
            rec = self._index_obj(value)
        elif isinstance(value, np.ndarray):
            rec = self._ndarray(value)
        elif isinstance(value, pd.api.extensions.ExtensionArray):
            rec = self._ext_array(value)
        elif is_scalar_like(value):
            rec = self._scalar(value)
        elif isinstance(value, (list, tuple, set, frozenset, dict)):
            rec = self._container(value)
        else:
            rec = {"kind": "other", "h": None, "info": {"type": _type_name(value)}}
        rec.setdefault("info", {})["route"] = route
        rec["info"].setdefault("type", _type_name(value))
        return rec

    def _labels(self, idx):
        """Index (column labels / index names) -> JSON-able tagged list."""
        out = []
        for v in list(idx):
            if isinstance(v, tuple):
                out.append(["tuple", [list(tag_value(e)) for e in v]])
            else:
                out.append(list(tag_value(v)))
        return out

    def _names(self, names):
        return [list(tag_value(n)) if not isinstance(n, tuple) else ["tuple", [list(tag_value(e)) for e in n]]
                for n in names]

    def _index_levels(self, idx, cap):
        levels = []
        if isinstance(idx, _pd().MultiIndex):
            for i in range(idx.nlevels):
                lv = idx.get_level_values(i)
                levels.append(self.column(lv.array, lv.dtype, cap))
        else:
            levels.append(self.column(idx.array, idx.dtype, cap))
        return levels

    def _finish(self, kind, meta, cols, idx, info):
        h = hashlib.sha256()
        h.update(json.dumps([ENCODING_VERSION, kind, meta], sort_keys=True, default=str).encode())
        for c in cols:
            h.update(("c" + c["h"]).encode())
        for c in idx:
            h.update(("i" + c["h"]).encode())
        return {"kind": kind, "h": h.hexdigest(), "meta": meta, "cols": cols, "idx": idx, "info": info}

    def _frame(self, df):
        nr, nc = df.shape
        cap = nr * max(nc, 1) > self.limits["max_cells"]
        cols = [self.column(df.iloc[:, j].array, df.dtypes.iloc[j], cap) for j in range(nc)]
        idx = self._index_levels(df.index, cap)
        meta = {"shape": [int(nr), int(nc)], "columns": self._labels(df.columns),
                "columns_dtype": str(df.columns.dtype), "columns_names": self._names(df.columns.names),
                "index_names": self._names(df.index.names), "index_nlevels": int(df.index.nlevels)}
        info = {"index_class": type(df.index).__name__, "capped": cap or any(not c["stored"] for c in cols + idx)}
        return self._finish("DataFrame", meta, cols, idx, info)

    def _series(self, s):
        cap = len(s) > self.limits["max_cells"]
        cols = [self.column(s.array, s.dtype, cap)]
        idx = self._index_levels(s.index, cap)
        meta = {"shape": [int(len(s))], "name": self._names([s.name])[0],
                "index_names": self._names(s.index.names), "index_nlevels": int(s.index.nlevels)}
        info = {"index_class": type(s.index).__name__, "capped": cap or any(not c["stored"] for c in cols + idx)}
        return self._finish("Series", meta, cols, idx, info)

    def _index_obj(self, idx):
        cap = len(idx) * idx.nlevels > self.limits["max_cells"]
        cols = self._index_levels(idx, cap)
        kind = "MultiIndex" if isinstance(idx, _pd().MultiIndex) else "Index"
        meta = {"shape": [int(len(idx))], "names": self._names(idx.names), "nlevels": int(idx.nlevels)}
        info = {"index_class": type(idx).__name__, "capped": cap or any(not c["stored"] for c in cols)}
        return self._finish(kind, meta, cols, [], info)

    def _ndarray(self, a):
        if a.dtype.names is not None:
            return {"kind": "other", "h": None, "info": {"type": "structured ndarray"}}
        shape = [int(s) for s in a.shape]
        cap = a.size > self.limits["max_cells"]
        if a.ndim == 0:
            a2 = a.reshape(1, 1)
        elif a.ndim == 1:
            a2 = a.reshape(-1, 1)
        else:
            a2 = a.reshape(a.shape[0], -1)
        cols = [self.column(np.ascontiguousarray(a2[:, j]), a2.dtype, cap) for j in range(a2.shape[1])]
        meta = {"shape": shape, "dtype": str(a.dtype)}
        return self._finish("ndarray", meta, cols, [], {"capped": cap or any(not c["stored"] for c in cols)})

    def _ext_array(self, a):
        """pandas ExtensionArray (e.g. Series.unique() on str/Int64/arrow dtypes): an array output.
        Kind 'ndarray' so it compares with numpy results; the array type is E0 content."""
        cap = len(a) > self.limits["max_cells"]
        cols = [self.column(a, a.dtype, cap)]
        meta = {"shape": [int(len(a))], "dtype": str(a.dtype), "array_type": type(a).__name__}
        return self._finish("ndarray", meta, cols, [], {"capped": cap or not cols[0]["stored"]})

    def _scalar(self, v):
        t, p, y = tag_value(v)
        meta = {"value": [t, p, y]}
        return self._finish("scalar", meta, [], [], {})

    def _container(self, v):
        kind = type(v).__name__ if type(v) in (list, tuple, set, frozenset, dict) else "list"
        if kind == "frozenset":
            kind = "set"
        n = len(v)
        if n > self.limits["max_container"]:
            return {"kind": "other", "h": None, "info": {"type": kind, "len": n, "reason": "container too large"}}
        if kind == "dict":
            keys = np.empty(n, dtype=object)
            vals = np.empty(n, dtype=object)
            for i, (k, x) in enumerate(v.items()):
                keys[i] = k
                vals[i] = x
            cols = [self.column(_flat(keys), np.dtype(object)), self.column(_flat(vals), np.dtype(object))]
        else:
            items = list(v)
            arr = np.empty(len(items), dtype=object)
            arr[:] = _flat(items)
            if kind == "set":
                order = sorted(range(len(arr)), key=lambda i: tag_value(arr[i])[:2])
                arr = arr[order] if len(arr) else arr
            cols = [self.column(arr, np.dtype(object))]
        meta = {"shape": [n]}
        return self._finish(kind, meta, cols, [], {"capped": any(not c["stored"] for c in cols)})


def _flat(items):
    out = np.empty(len(items), dtype=object)
    for i, x in enumerate(items):
        out[i] = x
    return out


# ----------------------------------------------------------------------------- decoding (dfeq, rootcause)

def decode_column_values(store, col):
    """Column descriptor -> python-level view used by dfeq:
    dict(enc, dtype, n, miss (uint8 kinds), and enc-specific arrays)."""
    d = load_blob(store, col["h"])
    enc = col["enc"]
    n = col["n"]
    out = {"enc": enc, "dtype": col["dtype"], "x": col["x"], "n": n}
    if enc == "num":
        v = d["v"]
        out["v"] = v
        out["miss"] = (np.isnan(v).astype(np.uint8) * M_NAN) if v.dtype.kind == "f" else np.zeros(n, np.uint8)
    elif enc == "nmask":
        v, m = d["v"], d["m"].astype(bool)
        out["v"] = v
        miss = np.where(m, col["x"].get("miss", M_NA), 0).astype(np.uint8)
        if v.dtype.kind == "f":
            miss = np.where(~m & np.isnan(v), M_NAN, miss).astype(np.uint8)
        out["miss"] = miss
    elif enc in ("dt", "td"):
        out["v"] = d["v"].astype(np.int64)
        out["miss"] = np.where(d["m"].astype(bool), col["x"].get("miss", M_NAT), 0).astype(np.uint8)
    elif enc == "str":
        out["v"] = d["v"]
        out["miss"] = d["k"].astype(np.uint8)
    elif enc == "obj":
        t = d["t"].astype(np.uint8)
        out["t"], out["p"], out["y"] = t, d["p"], d["y"]
        miss = np.zeros(n, np.uint8)
        for tag, code in TAG_MISSING.items():
            miss[t == tag] = code
        out["miss"] = miss
    elif enc == "cat":
        codes = d["c"].astype(np.int64)
        cats = decode_column_values(store, col["x"]["cats"])
        out["codes"] = codes
        out["cats"] = cats
        out["miss"] = np.where(codes < 0, M_NAN, 0).astype(np.uint8)
    elif enc == "cplx":
        out["re"], out["im"] = d["re"], d["im"]
        out["miss"] = (np.isnan(d["re"]) | np.isnan(d["im"])).astype(np.uint8) * M_NAN
    else:
        raise ValueError("unknown encoding %s" % enc)
    return out


def untag(t, p, y=None):
    """Inverse of tag_value for reconstruction (rootcause reproducers)."""
    pd = _pd()
    if t == T_STR:
        return p
    if t == T_NONE:
        return None
    if t == T_NAN:
        return float("nan")
    if t == T_NA:
        return pd.NA
    if t == T_NAT:
        return pd.NaT
    if t == T_BOOL:
        return p == "True"
    if t == T_INT:
        return int(p)
    if t == T_FLOAT:
        return float(p)
    if t == T_DATETIME:
        ns, tz = p.split("|")
        ts = pd.Timestamp(int(ns))
        return ts.tz_localize("UTC").tz_convert(tz) if tz != "None" else ts
    if t == T_TIMEDELTA:
        return pd.Timedelta(int(p))
    if t == T_DATE:
        return _dt.date.fromisoformat(p)
    if t == T_DECIMAL:
        return _decimal.Decimal(p)
    if t == T_BYTES:
        return bytes.fromhex(p)
    if t == T_COMPLEX:
        return complex(p)
    return p


def decode_to_pandas(store, rec):
    """Object record -> pandas/numpy/python object (best effort, dtype restored by dtype string).
    Used to rebuild cell inputs for root-cause minimisation."""
    pd = _pd()
    kind = rec["kind"]
    if kind == "scalar":
        return untag(*rec["meta"]["value"][:2])

    def col_to_array(c):
        v = decode_column_values(store, c)
        enc = v["enc"]
        if enc == "num":
            arr = v["v"]
        elif enc == "nmask":
            vals = [None if m else x for x, m in zip(v["v"].tolist(), v["miss"].tolist())]
            try:
                return pd.array(vals, dtype=c["dtype"])
            except Exception:
                return np.array(vals, dtype=object)
        elif enc in ("dt", "td"):
            unit = c["x"].get("unit", "ns")
            if unit.startswith("period"):
                return np.array([None if m else x for x, m in zip(v["v"].tolist(), v["miss"].tolist())], dtype=object)
            base = np.array(v["v"], dtype="int64").view(("M8[%s]" if enc == "dt" else "m8[%s]") % unit).copy()
            base[v["miss"] > 0] = np.datetime64("NaT") if enc == "dt" else np.timedelta64("NaT")
            s = pd.Series(base)
            if c["x"].get("tz"):
                s = s.dt.tz_localize("UTC").dt.tz_convert(c["x"]["tz"])
            try:
                return s.astype(c["dtype"]).array
            except Exception:
                return s.array
        elif enc == "str":
            arr = v["v"].copy()
            for code, sent in ((M_NONE, None), (M_NAN, float("nan")), (M_NA, pd.NA), (M_NAT, pd.NaT)):
                arr[v["miss"] == code] = sent
        elif enc == "obj":
            arr = np.empty(c["n"], dtype=object)
            for i in range(c["n"]):
                arr[i] = untag(int(v["t"][i]), v["p"][i])
        elif enc == "cat":
            cats = col_to_array(c["x"]["cats"])
            return pd.Categorical.from_codes(v["codes"], categories=pd.Index(cats), ordered=c["x"].get("ordered", False))
        elif enc == "cplx":
            arr = v["re"] + 1j * v["im"]
        else:
            raise ValueError(enc)
        try:
            return pd.array(arr, dtype=c["dtype"]) if c["dtype"] not in ("object",) else arr
        except Exception:
            return arr

    def labels_to_index(tagged, dtype):
        vals = [tuple(untag(*e[:2]) for e in l[1]) if l and l[0] == "tuple" else untag(*l[:2]) for l in tagged]
        if vals and isinstance(vals[0], tuple):
            return pd.MultiIndex.from_tuples(vals)
        try:
            return pd.Index(vals, dtype=dtype)
        except Exception:
            return pd.Index(vals, dtype=object)

    def name_of(t):
        return tuple(untag(*e[:2]) for e in t[1]) if t and t[0] == "tuple" else untag(*t[:2])

    def build_index(levels, names):
        arrs = [col_to_array(c) for c in levels]
        if len(arrs) == 1:
            return pd.Index(arrs[0], name=name_of(names[0]))
        return pd.MultiIndex.from_arrays(arrs, names=[name_of(n) for n in names])

    meta = rec["meta"]
    if kind == "DataFrame":
        data = {j: col_to_array(c) for j, c in enumerate(rec["cols"])}
        idx = build_index(rec["idx"], meta["index_names"])
        df = pd.DataFrame(data, index=idx)
        df.columns = labels_to_index(meta["columns"], meta["columns_dtype"])
        return df
    if kind == "Series":
        return pd.Series(col_to_array(rec["cols"][0]), index=build_index(rec["idx"], meta["index_names"]),
                         name=name_of(meta["name"]))
    if kind in ("Index", "MultiIndex"):
        return build_index(rec["cols"], meta["names"])
    if kind == "ndarray" and meta.get("array_type", "ndarray") != "ndarray":
        return pd.array(col_to_array(rec["cols"][0]), dtype=meta["dtype"])
    if kind == "ndarray":
        cols = [np.asarray(col_to_array(c)) for c in rec["cols"]]
        a = np.column_stack(cols) if cols else np.empty((0,))
        return a.reshape(meta["shape"]).astype(meta["dtype"]) if meta["dtype"] != "object" else a.reshape(meta["shape"])
    if kind in ("list", "tuple", "set"):
        vals = list(col_to_array(rec["cols"][0]))
        return {"list": list, "tuple": tuple, "set": set}[kind](vals)
    if kind == "dict":
        return dict(zip(col_to_array(rec["cols"][0]), col_to_array(rec["cols"][1])))
    raise ValueError("cannot decode kind %s" % kind)

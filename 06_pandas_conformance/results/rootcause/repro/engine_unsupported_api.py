"""Reproducer for root cause `engine_unsupported_api` (PandasConform, results/rootcause/taxonomy.json).

PCONF_REPRO_KIND: engine
PCONF_REPRO_ENGINES: dask, bodo, fireducks
Documented: https://docs.dask.org/en/stable/dataframe-indexing.html (Dask iloc only)
Observed in: roopahegde c10 (dask drop inplace), deffro c10 (dask cut), shashi772 c6 (bodo infer_datetime_format), sabya40 c16 (fireducks groupby sum of strings)

Run: PCONF_REPRO_MODE=<pandas|pyarrow_backend|modin|fireducks|bodo|dask> <env python> engine_unsupported_api.py
(pandas modes run in envs/ref, envs/p15, envs/p30; engine modes only in a guarded probes campaign)
"""
import io, os, sys, warnings
warnings.simplefilter("ignore")
MODE = os.environ.get("PCONF_REPRO_MODE", "pandas")   # pandas | pyarrow_backend | modin | fireducks | bodo | dask
if MODE == "modin":
    import ray
    ray.init(num_cpus=1, include_dashboard=False, log_to_driver=False)
    import modin.pandas as pd
elif MODE == "fireducks":
    import fireducks.pandas as pd
elif MODE == "bodo":
    import bodo.pandas as pd
elif MODE == "dask":
    import dask
    dask.config.set(scheduler="synchronous")
    import dask.dataframe as pd
else:
    import pandas as pd
import numpy as np
import pandas as _pandas


def read_csv(text, **kw):
    """read_csv from literal text; pyarrow_backend mode passes dtype_backend='pyarrow' like the campaign shim."""
    if MODE == "pyarrow_backend":
        kw.setdefault("dtype_backend", "pyarrow")
    if MODE in ("bodo", "dask"):     # these engines read from files
        p = os.path.join(os.environ.get("TMPDIR", "/tmp"), "pconf_repro_%d.csv" % os.getpid())
        with open(p, "w") as f:
            f.write(text)
        return pd.read_csv(p, **kw)
    return pd.read_csv(io.StringIO(text), **kw)


def frame(d, **kw):
    """DataFrame constructor for every engine (dask: from_pandas with 2 partitions)."""
    if MODE == "dask":
        return pd.from_pandas(_pandas.DataFrame(d, **kw), npartitions=2)
    return pd.DataFrame(d, **kw)


def show(o):
    if hasattr(o, "compute"):
        o = o.compute()
    if hasattr(o, "_to_pandas"):
        o = o._to_pandas()
    elif hasattr(o, "to_pandas") and not isinstance(o, (_pandas.DataFrame, _pandas.Series)):
        try:
            o = o.to_pandas()
        except Exception:
            pass
    if isinstance(o, (_pandas.DataFrame, _pandas.Series, _pandas.Index)):
        return repr(o.to_dict() if not isinstance(o, _pandas.Index) else list(o)) + " dtype=" + (
            str(dict(o.dtypes.astype(str))) if isinstance(o, _pandas.DataFrame) else str(o.dtype))
    return repr(o)


def check(name, fn):
    try:
        print("RESULT %s: %s" % (name, fn()))
    except Exception as e:
        print("RESULT %s: raised %s: %s" % (name, type(e).__name__, str(e).splitlines()[0][:160] if str(e) else ""))


print("RESULT env: mode=%s pandas=%s" % (MODE, _pandas.__version__))

d = frame({"a": [1, 2, 3], "s": ["x", "y", "z"], "t": ["2020-01-01", "2020-01-02", "2020-01-03"]})
check("drop(columns, inplace=True)", lambda: d.drop("a", axis=1, inplace=True))
check("pd.cut", lambda: show(pd.cut(d["a"], [0, 2, 5])))
check("iloc row selection", lambda: show(d.iloc[0:2]))
check("to_datetime(infer_datetime_format=True)", lambda: show(pd.to_datetime(d["t"], infer_datetime_format=True)))
check("groupby sum over string column", lambda: show(frame({"k": [1, 1], "s": ["a", "b"]}).groupby("k").sum()))

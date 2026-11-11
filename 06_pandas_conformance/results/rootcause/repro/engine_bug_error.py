"""Reproducer for root cause `engine_bug_error` (PandasConform, results/rootcause/taxonomy.json).

PCONF_REPRO_KIND: engine
PCONF_REPRO_ENGINES: bodo, bodo_dw, modin, fireducks
Documented: not documented (FireDucks documents deferred error timing only)
Observed in: kimtaehun c9 / trinath003 c10 (bodo _plan), yonelanuba c68 (bodo str[0]), corazzon c21 (modin Series.filter), corazzon c56 (fireducks)

Run: PCONF_REPRO_MODE=<pandas|pyarrow_backend|modin|fireducks|bodo|dask> <env python> engine_bug_error.py
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

d = frame({"k": ["a", "b", "a"], "v": [1.0, 2.0, 3.0], "s": ["1 2", "3 4", "5 6"]})
check("groupby(['k']).mean().reset_index()", lambda: show(d.groupby(["k"])["v"].mean().reset_index()))
check("groupby('k').count()", lambda: show(d.groupby("k").count()))
check("str.split(' ').str[0]", lambda: show(d["s"].str.split(" ").str[0]))
q = pd.Series(["t1", "t2"], index=["Q7_Part_1", "Q8"])
check("Series.filter(regex)", lambda: show(q.filter(regex="Q7")))

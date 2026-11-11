"""Reproducer for root cause `str_dtype_object_checks` (PandasConform, results/rootcause/taxonomy.json).

PCONF_REPRO_KIND: pandas
PCONF_REPRO_ENGINES: p30, pyarrow_backend vs ref; engines bodo, dask (probe)
Documented: https://pandas.pydata.org/docs/user_guide/migration-3-strings.html
Observed in: yonelanuba/elo-merchant c16 (p30, bodo, dask, pyarrow_backend), saniaks/melbourne c7 (p30)

Run: PCONF_REPRO_MODE=<pandas|pyarrow_backend|modin|fireducks|bodo|dask> <env python> str_dtype_object_checks.py
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

df = read_csv("city,price,rooms\nA,1.5,2\nB,2.5,3\n")
check("cat cols via dtypes == 'object'", lambda: list(df.dtypes[df.dtypes == "object"].index))
check("num cols via dtype != 'object'", lambda: [c for c in df.columns if df[c].dtype != "object"])
check("select_dtypes(include='object')", lambda: list(df.select_dtypes(include="object").columns))

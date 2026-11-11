"""Reproducer for root cause `row_order_ties` (PandasConform, results/rootcause/taxonomy.json).

PCONF_REPRO_KIND: pandas
PCONF_REPRO_ENGINES: p30 vs ref (value_counts ties); engines modin, fireducks, bodo (probe)
Documented: https://modin.readthedocs.io/en/latest/supported_apis/dataframe_supported.html (Modin sort ties); https://fireducks-dev.github.io/docs/user-guide/04-compatibility/ (FireDucks merge)
Observed in: grudd0 c42, mikedelong c8 (p30); trinath003 c9 (modin, fireducks); corazzon c33 (bodo groupby)

Run: PCONF_REPRO_MODE=<pandas|pyarrow_backend|modin|fireducks|bodo|dask> <env python> row_order_ties.py
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

# pandas: value_counts ties on a string column (2,000 values over 300 names, 5% missing) order differently in p30
rng = np.random.default_rng(1)
names = np.array(["n%03d" % i for i in range(300)])
vals = [v if rng.random() > 0.05 else "" for v in rng.choice(names, 2000)]
col = read_csv("x\n" + "\n".join(vals) + "\n")["x"]
check("value_counts().nlargest(10) labels", lambda: show(col.value_counts().nlargest(10).index) if MODE != "dask" else show(col.value_counts().compute().nlargest(10).index))
df = frame({"v": [3, 1, 2, 1, 3, 2, 1], "id": list(range(7))})
check("sort_values ties: id order", lambda: show(df.sort_values("v")["id"]))
check("groupby default group order", lambda: show(frame({"g": ["Man", "Woman", "Man", "Nonbinary"], "x": [1, 2, 3, 4]}).groupby("g").count()))

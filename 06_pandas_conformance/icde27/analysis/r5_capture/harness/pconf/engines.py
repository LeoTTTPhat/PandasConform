"""Engine configurations (plan.md Section 4). Parent side; the child receives `setup`, `teardown`,
`evaluate_lazy` and `env_vars` in its job file.

Each engine names a uv environment under envs/, Python code that binds `pd` (the module that
`import pandas as pd` resolves to inside the notebook), and the documented resource caps.
Settings are engine defaults except the caps listed here (plan.md Section 7).
"""
import os

from . import util

# threads: the memory guard exports OMP/OPENBLAS/MKL/VECLIB_*_NUM_THREADS=1 to its child. For
# engines whose default execution is multi-threaded we remove those caps in the child so the
# engine runs at its defaults (fairness rule); single-threaded engines keep them (no effect).
#
# CPU budget (fix of review finding T2, 2026-10-02), child env PCONF_CPUS, run config "cpus":
#   unset      conformance runs: documented caps (Modin Ray num_cpus=8, Bodo 1 worker,
#              FireDucks and Dask at their defaults)
#   N          every parallel engine gets N CPUs: Ray num_cpus=N, BODO_NUM_WORKERS=N, dask
#              num_workers=N (threaded scheduler), FireDucks OMP_NUM_THREADS=N (its dfkl/Arrow
#              pool follows it: measured 2026-10-02, CPU/wall 14.1 at default, 1.0 at 1, 3.2 at 4);
#              BLAS/OpenMP stays at 1 thread inside Modin/Bodo/Dask workers (no oversubscription)
#   default    the engines' own defaults (Modin: Ray sees all cores; Bodo default workers)
# pandas configurations are single-threaded in every case.
THREAD_VARS = ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"]

PYARROW_SHIM = r'''
import functools as _ft, types as _types
import pandas as _real_pd
class _PyarrowBackendPandas(_types.ModuleType):
    """`pandas` with dtype_backend='pyarrow' passed to every reader that accepts it."""
    def __getattr__(self, name):
        return getattr(_real_pd, name)
pd = _PyarrowBackendPandas("pandas")
pd.__dict__["__version__"] = _real_pd.__version__
def _wrap(f):
    @_ft.wraps(f)
    def g(*a, **k):
        k.setdefault("dtype_backend", "pyarrow")
        return f(*a, **k)
    return g
for _n in ("read_csv", "read_table", "read_fwf", "read_excel", "read_json", "read_parquet", "read_orc",
           "read_feather", "read_html", "read_xml", "read_sql", "read_sql_query", "read_sql_table", "read_spss"):
    if hasattr(_real_pd, _n):
        setattr(pd, _n, _wrap(getattr(_real_pd, _n)))
'''

MODIN_SETUP = r'''
import os, ray
os.environ.setdefault("RAY_ENABLE_MAC_LARGE_OBJECT_STORE", "1")
_c = os.environ.get("PCONF_CPUS", "")
_kw = {} if _c == "default" else {"num_cpus": int(_c) if _c else 8}
ray.init(object_store_memory=16 * 10**9, include_dashboard=False, log_to_driver=False,
         configure_logging=False, runtime_env={"env_vars": {"__MODIN_AUTOIMPORT_PANDAS__": "1"}}, **_kw)
import modin.pandas as pd
import modin.config
modin.config.Engine.put("Ray")
'''

DASK_SETUP = r'''
import os, dask
_c = os.environ.get("PCONF_CPUS", "")
if _c and _c != "default":
    dask.config.set(num_workers=int(_c))
import dask.dataframe as pd
'''

ENGINES = {
    "ref": {"env": "ref", "setup": "import pandas as pd", "class": "single",
            "doc": "reference pandas 2.3.3"},
    "p15": {"env": "p15", "setup": "import pandas as pd", "class": "single",
            "doc": "pandas 1.5.3 (Python 3.11, numpy<2)"},
    "p30": {"env": "p30", "setup": "import pandas as pd", "class": "single",
            "doc": "pandas 3.0.x latest"},
    "pyarrow_backend": {"env": "ref", "setup": PYARROW_SHIM, "class": "single",
                        "doc": "pandas 2.3.3 with readers forced to dtype_backend='pyarrow'"},
    "modin": {"env": "modin", "setup": MODIN_SETUP, "teardown": "import ray\nray.shutdown()",
              "class": "parallel", "threads": "default",
              "env_vars": {"MODIN_ENGINE": "ray", "RAY_ENABLE_MAC_LARGE_OBJECT_STORE": "1",
                           "RAY_DEDUP_LOGS": "0", "RAY_USAGE_STATS_ENABLED": "0"},
              "doc": "Modin 0.37 on Ray (local, num_cpus=8, object store 16 GB) over pandas 2.3.3"},
    "fireducks": {"env": "fireducks", "setup": "import fireducks.pandas as pd", "class": "parallel",
                  "threads": "default", "env_vars": {"FIREDUCKS_FLAGS": "-Wfallback"},
                  "doc": "FireDucks 1.4 over pandas 2.3.3; -Wfallback only makes fallbacks visible as warnings"},
    "bodo": {"env": "bodo", "setup": "import bodo.pandas as pd", "class": "parallel", "threads": "default",
             "env_vars": {"BODO_NUM_WORKERS": "1"},
             "doc": "Bodo DataFrames 2026.8 over pandas 2.3.3, single MPI worker (plan: MPI single process)"},
    "bodo_dw": {"env": "bodo", "setup": "import bodo.pandas as pd", "class": "parallel", "threads": "default",
                "doc": "Bodo DataFrames 2026.8 at its DEFAULT worker count (pilot variant, ledger item 2g: "
                       "results on battles.csv differ between 1 worker and the default)"},
    "dask": {"env": "dask", "setup": DASK_SETUP, "class": "parallel", "threads": "default",
             "evaluate_lazy": "return lazy.compute() if hasattr(lazy, 'compute') else lazy",
             "doc": "dask.dataframe over pandas 2.3.3 (coverage row only; not a drop-in API)"},
}

CONFORMANCE_ENGINES = ["ref", "pyarrow_backend", "modin", "fireducks", "bodo", "dask"]
DRIFT_ENGINES = ["p15", "ref", "p30"]


def parse_engine(name):
    """'ref#2' -> ('ref', 2). Replicates are separate runs of the same configuration."""
    if "#" in name:
        base, rep = name.split("#", 1)
        return base, int(rep)
    return name, 1


def engine_python(name):
    base, _ = parse_engine(name)
    return os.path.join(util.ENVS, ENGINES[base]["env"], "bin", "python")


def engine_spec(name):
    base, rep = parse_engine(name)
    e = dict(ENGINES[base])
    e["name"] = name
    e["base"] = base
    e["replicate"] = rep
    e.setdefault("teardown", "")
    e.setdefault("evaluate_lazy", "return lazy")
    e.setdefault("env_vars", {})
    e.setdefault("threads", "capped")
    return e


def env_lock(name):
    base, _ = parse_engine(name)
    lock = util.read_json(os.path.join(util.PROJ, "envs.lock.json"), {}) or {}
    return lock.get(ENGINES[base]["env"], {})


def child_env(name, base_env=None, cpus=None):
    """Environment variables for a child run of engine `name` (cpus: see PCONF_CPUS above)."""
    spec = engine_spec(name)
    env = dict(base_env if base_env is not None else os.environ)
    for k in list(env):
        if k.startswith("PYTHON") or k in ("VIRTUAL_ENV", "CONDA_PREFIX"):
            env.pop(k)
    env["PYTHONPATH"] = util.SRC
    env["PYTHONHASHSEED"] = "0"
    env["MPLBACKEND"] = "Agg"
    env["PYTHONUNBUFFERED"] = "1"
    if spec["threads"] == "default":
        for v in THREAD_VARS:
            env.pop(v, None)
    env.update(spec["env_vars"])
    if cpus is not None and spec["class"] == "parallel":
        env["PCONF_CPUS"] = str(cpus)
        if str(cpus) == "default":
            env.pop("BODO_NUM_WORKERS", None)
        else:
            n = str(int(cpus))
            for v in THREAD_VARS:
                env[v] = n if spec["base"] == "fireducks" else "1"
            if spec["env"] == "bodo":
                env["BODO_NUM_WORKERS"] = n
    return env

"""Executed by test_capture.py inside each engine environment:
    <env python> env_roundtrip_script.py <store> <engine-or-pandas>
Builds a fixed set of objects with plain pandas (and, if an engine is named, the same data through
the engine module), captures them and prints {name: record} as JSON on the last stdout line."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pconf.capture import Capturer  # noqa: E402

store, engine = sys.argv[1], sys.argv[2]


def objects(P):
    df = P.DataFrame({
        "i": np.array([3, 1, 2, 7], dtype="int64"),
        "f": np.array([0.5, np.nan, -1.25, 1e300]),
        "s": np.array(["a", None, "c", "d"], dtype=object),
        "b": np.array([True, False, True, False]),
    })
    out = {"df": df, "col_f": df["f"], "sum_f": df["f"].sum(), "len": len(df), "shape": df.shape,
           "desc": df[["i", "f"]].describe(), "gb": df.groupby("b")["i"].sum(), "srt": df.sort_values("i")}
    return out


cap = Capturer(store)
res = {}
plain = objects(pd)
for k, v in plain.items():
    res["pandas:" + k] = cap.capture(v)
# dtypes whose capture must be identical across pandas 1.5/2.x (explicit dtypes, no inference)
extra = {
    "Int64": pd.Series([1, None, 3], dtype="Int64"),
    "cat": pd.Series(pd.Categorical(["x", "y", "x"], categories=["x", "y"])),
    "dt_ns": pd.Series(np.array(["2020-01-01T00:00:00", "NaT"], dtype="datetime64[ns]")),
    "mi": pd.DataFrame({"a": [1, 1, 2], "b": ["u", "v", "u"], "v": [1.0, 2.0, 3.0]}).set_index(["a", "b"]),
    "ndarr": np.arange(6, dtype="int64").reshape(3, 2),
}
for k, v in extra.items():
    res["pandas:" + k] = cap.capture(v)
if engine != "pandas":
    setup = {
        "modin": "import ray\nray.init(num_cpus=2, include_dashboard=False, log_to_driver=False)\nimport modin.pandas as E",
        "fireducks": "import fireducks.pandas as E",
        "bodo": "import bodo.pandas as E",
        "dask": "import dask.dataframe as E",
    }[engine]
    ns = {}
    exec(setup, ns)
    E = ns["E"]
    if engine == "dask":
        ddf = E.from_pandas(plain["df"], npartitions=2)
        eng = {"df": ddf, "col_f": ddf["f"], "sum_f": ddf["f"].sum(), "srt": ddf.sort_values("i")}
    else:
        eng = objects(E)
    for k, v in eng.items():
        res["engine:" + k] = cap.capture(v)
    if engine == "modin":
        ray = __import__("ray")
        ray.shutdown()
print(json.dumps(res, default=str))
sys.stdout.flush()
os._exit(0)

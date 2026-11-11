"""Decisive follow-up check for root cause `engine_corr_wrong_values` (written 2026-10-04, F4 step 3).

PCONF_REPRO_KIND: engine
PCONF_REPRO_ENGINES: modin
The first probe (engine_corr_wrong_values.py) printed only the number of "1.0" substrings in the repr of the
correlation matrix (modin: 15), which cannot tell a correct matrix from a wrong one. This script builds the
same 4.4M x 25 frame (seed 0) and prints the largest deviation of the diagonal from 1 and the number of
entries outside [-1, 1] (with a 1e-9 slack), so pandas and Modin runs are directly comparable.

Run ONLY under the memory guard (the frame needs several GB):
  PCONF_REPRO_MODE=<pandas|modin> <env python> engine_corr_wrong_values_check.py
"""
import os
import warnings

warnings.simplefilter("ignore")
MODE = os.environ.get("PCONF_REPRO_MODE", "pandas")
if MODE == "modin":
    import ray
    ray.init(num_cpus=1, include_dashboard=False, log_to_driver=False)
    import modin.pandas as pd
else:
    import pandas as pd
import numpy as np
import pandas as _pandas

print("RESULT env: mode=%s pandas=%s" % (MODE, _pandas.__version__))
rng = np.random.default_rng(0)
n = 4_400_000
cols = {"c%d" % j: rng.integers(0, 50, n).astype("int64") for j in range(12)}
cols.update({"f%d" % j: rng.random(n) * 1e4 for j in range(12)})
cols["id"] = ["m%d" % (i % 1000) for i in range(n)]
d = pd.DataFrame(cols)
try:
    c = d.corr(numeric_only=True)
    if hasattr(c, "_to_pandas"):
        c = c._to_pandas()
    m = c.to_numpy(dtype="float64")
    diag = np.diag(m)
    print("RESULT shape: %s" % (m.shape,))
    print("RESULT max |diag - 1|: %.3e" % float(np.max(np.abs(diag - 1.0))))
    print("RESULT diagonal min/max: %r / %r" % (float(diag.min()), float(diag.max())))
    print("RESULT entries outside [-1, 1] (slack 1e-9): %d" % int(np.sum(np.abs(m) > 1.0 + 1e-9)))
    print("RESULT max |offdiag|: %.6f" % float(np.max(np.abs(m - np.diag(diag)))))
except Exception as e:  # report, do not hide
    print("RESULT corr: raised %s: %s" % (type(e).__name__, str(e).splitlines()[0][:160] if str(e) else ""))

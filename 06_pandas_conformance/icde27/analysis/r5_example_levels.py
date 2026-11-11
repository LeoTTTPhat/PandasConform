#!/usr/bin/env python3
"""A small executable example of the graded comparison and of the printed-form limit (review round R5; ICDE 2027
copy; written 2026-11-10).

Needs only the shared venv and this repository (no notebook, no Kaggle data, no engine environment): it builds a
reference frame and variants that each need one more relaxation, captures them with the harness's own encoder into a
temporary store, compares them with the comparator, and prints the first successful level, the row matching used and
the first failing check at each finer level. The last two cases show the printed-form limit of Section III: a list
holding a frame is compared by its printed form, so two lists whose frames differ only in rows that the printed form
omits compare equal, while the same frames compared directly differ. Writes icde27/analysis/r5_example_levels.json
(the same table). Seconds, below 0.5 GB.

    cd ..
    PYTHONPATH=06_pandas_conformance-ICDE/src .venv/bin/python 06_pandas_conformance-ICDE/icde27/analysis/r5_example_levels.py
"""
import json
import os
import shutil
import sys
import tempfile

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(PROJ, "src"))
from pconf import dfeq  # noqa: E402
from pconf.capture import Capturer  # noqa: E402

OUT = os.path.join(HERE, "r5_example_levels.json")


def frame():
    return pd.DataFrame({"k": np.array([3, 1, 2, 1], dtype="int64"),
                         "v": [0.5, 1.5, np.nan, 2.0],
                         "s": np.array(["b", "a", None, "c"], dtype=object),
                         "m": np.array([1, None, "x", 2.5], dtype=object)},   # mixed values stay object in pandas 3
                        index=pd.Index([10, 11, 12, 13], name="id"))


def cases():
    a = frame()
    yield "identical copy", a, a.copy(), "E0"
    yield "rows permuted (index carried)", a, a.iloc[[2, 0, 3, 1]], "E1"
    b = a.astype({"k": "float64"})
    yield "int64 column widened to float64", a, b, "E2"
    c = a.copy()
    c["v"] = c["v"] * (1 + 1e-12)
    yield "float values within 1e-9 relative", a, c, "E2"
    d = a.copy()
    d["m"] = np.array([1, np.nan, "x", 2.5], dtype=object)
    yield "None replaced by NaN in a mixed object column", a, d, "E3"
    e = a.reset_index(drop=True)
    yield "index labels dropped", a, e, "E4"
    f = a.copy()
    f.loc[11, "v"] = 1.75
    yield "one value changed", a, f, "DIFF"
    big = pd.DataFrame({"x": np.arange(200, dtype="int64")})
    big2 = big.copy()
    big2.loc[100, "x"] = -1       # a middle row: pandas' printed form shows only the first and last rows
    yield "list holding a 200-row frame, middle row changed (printed form)", [big], [big2], "E0"
    yield "the same two frames compared directly", big, big2, "DIFF"


def main():
    tmp = tempfile.mkdtemp(prefix="pconf_example_")
    try:
        cap = Capturer(tmp)
        rows = []
        for name, a, b, expected in cases():
            ra, rb = cap.capture(a), cap.capture(b)
            res = dfeq.compare(ra, rb, tmp)
            rows.append({"case": name, "level": res["level"], "expected": expected, "match": res.get("match") or "",
                         "first_failing_check": res.get("fails") or {}})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for r in rows:
        print("%-66s %-5s (expected %-4s) match=%-8s %s" % (r["case"], r["level"], r["expected"], r["match"],
                                                           json.dumps(r["first_failing_check"])))
    ok = all(r["level"] == r["expected"] for r in rows)
    with open(OUT + ".tmp", "w") as f:
        json.dump({"pandas": pd.__version__, "numpy": np.__version__, "all_as_expected": ok, "cases": rows}, f, indent=1)
    os.replace(OUT + ".tmp", OUT)
    print("all as expected:", ok)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

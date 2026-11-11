#!/usr/bin/env python3
"""Review R1 item B1(i): do the E1 ("modulo row order") outputs of sorting cells only reorder rows with tied
sort keys? (ICDE 2027 copy; written 2026-10-26.)

Read-only on results/, data/ and captures/ (the content-addressed value store); writes only
icde27/analysis/r1_sort_ties.json. Decoded objects are small; peak memory is far below 2 GB.

    cd ..
    /usr/bin/time -l .venv/bin/python 06_pandas_conformance/icde27/analysis/r1_sort_ties.py

Population: every output at level E1 in a cell whose class is E1 and whose operation families contain `sort`
(sort_values, sort_index, nlargest, nsmallest, rank), for the conf_1x engines and the drift pandas versions,
with the compare output selected as in analyze.py.
Check per output: decode the reference and engine values from the store (pconf.capture.decode_to_pandas), take
the sort keys from the cell code (by=, the first positional argument, columns= of nlargest/nsmallest, the index
for sort_index, the values of a Series), and test that the key sequences are identical position by position
(NaN equal to NaN). Identical key sequences with a different row order mean that only rows with tied keys moved.
When no key can be read from the code, the output is accepted only if some column (or the index, or the Series
values) is monotonic in the reference and identical position by position in the engine output; every other
output is listed for inspection.
"""
import ast
import collections
import importlib.util
import json
import os
import re
import sys

os.environ.setdefault("PCONF_DECODE_CACHE_GB", "0.2")
HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(PROJ, "src"))
from pconf import capture as C  # noqa: E402
from pconf import util  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

OUT = os.path.join(HERE, "r1_sort_ties.json")
LABELS = {("conf_1x", e) for e in ("pyarrow_backend", "modin", "fireducks", "bodo", "dask")} | {("drift", "p15"), ("drift", "p30")}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def literal(node):
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def sort_calls(code):
    """[(method, keys or None, by_index)] for every sort-like call in the cell code."""
    out = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return [("unparsed", None, False)]
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
            continue
        m = n.func.attr
        if m not in ("sort_values", "sort_index", "nlargest", "nsmallest"):
            continue
        kw = {k.arg: k.value for k in n.keywords if k.arg}
        keys = None
        if m == "sort_values":
            node = kw.get("by") or (n.args[0] if n.args else None)
            keys = literal(node) if node is not None else "__values__"
        elif m in ("nlargest", "nsmallest"):
            node = kw.get("columns") or (n.args[1] if len(n.args) > 1 else None)
            keys = literal(node) if node is not None else "__values__"
        out.append((m, keys, m == "sort_index"))
    return out


def same_seq(a, b):
    a, b = pd.Series(np.asarray(a, dtype=object)), pd.Series(np.asarray(b, dtype=object))
    if len(a) != len(b):
        return False
    both_na = a.isna() & b.isna()
    eq = (a == b) | both_na
    return bool(eq.all())


def monotonic(s):
    try:
        s = pd.Series(s)
        return bool(s.is_monotonic_increasing or s.is_monotonic_decreasing)
    except Exception:
        return False


def columns_of(x):
    """name -> 1-d sequence for a DataFrame (columns and index levels) or a Series (values and index)."""
    cols = {}
    if isinstance(x, pd.DataFrame):
        for j, c in enumerate(x.columns):
            cols[c if not isinstance(c, (list, dict)) else str(c)] = x.iloc[:, j].to_numpy()
    elif isinstance(x, pd.Series):
        cols["__values__"] = x.to_numpy()
    else:
        return None
    for k in range(x.index.nlevels):
        cols["__index%d__" % k] = x.index.get_level_values(k).to_numpy()
    return cols


# Outputs the automatic check cannot settle, inspected by hand on 2026-10-26 (decoded values; evidence recorded):
MANUAL = {
    ("fireducks", "snanilim/video-games-sales-analysis-and-visualization", 36, "_"): (
        "only tied keys reordered (manual)",
        "Index of the top-20 publishers sorted by count; positions 18-19 swapped ('505 Games', 'Microsoft Game Studios'), "
        "both with count 185 recomputed from the reference input `data`; the count sequences are identical"),
    ("modin", "snanilim/video-games-sales-analysis-and-visualization", 10, "_"): (
        "only tied keys reordered (manual)",
        "Index of years sorted by count; positions 28-29 swapped (1989, 1983), both with count 17 recomputed from the "
        "reference input `data`; the count sequences are identical"),
    ("modin", "kmader/analyzing-matches", 9, "worst_annot"): (
        "only tied keys reordered (manual)",
        "array taken from worst_annot_df, which the automatic check verifies as sorted on the same tied 'iou' keys"),
    ("modin", "dbatao/kernel2f80fc9d78", 28, "na_col_list"): (
        "not a sort reordering (manual)",
        "list of columns with missing values in the column order of `all_data`, whose inputs already differed "
        "(clean level None, so the cell is in no clean view); the sort in the cell applies to another expression"),
    ("p15", "taylorhickem/singapore-building-energy", 16, "usg"): (
        "not a sort reordering (manual)",
        "pandas 1.5.3 DataFrame built from a dict has another row order; the sort in the cell applies to `df` (E0)"),
}


def main():
    T = load_module("rootcause_taxonomy", os.path.join(PROJ, "scripts", "rootcause_taxonomy.py"))
    rows, per = [], collections.Counter()
    rec_cache = {}

    def rec(path):
        if path not in rec_cache:
            if len(rec_cache) > 16:
                rec_cache.clear()
            rec_cache[path] = json.load(open(os.path.join(PROJ, path)))
        return rec_cache[path]

    for campaign in ("conf_1x", "drift"):
        root, best = T.select_outputs(campaign, T.COMPARE)
        for (label, nb, sc), (_, r, p) in sorted(best.items()):
            if (campaign, label) not in LABELS:
                continue
            for c in r["cells"]:
                if c["cls"] != "E1" or "sort" not in (c.get("families") or []):
                    continue
                code = T.cell_code(nb, c["i"], expand=False)
                calls = sort_calls(code)
                ref, eng = rec(r["meta"]["ref_record"]), rec(r["meta"]["eng_record"])
                rc = {x.get("i"): x for x in ref["cells"]}.get(c["i"], {})
                ec = {x.get("i"): x for x in eng["cells"]}.get(c["i"], {})
                for name, o in sorted((c.get("outputs") or {}).items()):
                    if o.get("level") != "E1":
                        continue
                    row = {"campaign": campaign, "label": label, "nb": nb, "cell": c["i"], "output": name,
                           "calls": [[m, k if not isinstance(k, (set, frozenset)) else sorted(k), bi] for m, k, bi in calls]}
                    try:
                        ra = ref["objects"][rc["outputs"][name]]
                        ea = eng["objects"][ec["outputs"][name]]
                        a, b = C.decode_to_pandas(util.CAPTURES, ra), C.decode_to_pandas(util.CAPTURES, ea)
                    except Exception as ex:
                        row["verdict"] = "not decodable: %s" % type(ex).__name__
                        rows.append(row)
                        per[(label, row["verdict"])] += 1
                        continue
                    ca, cb = columns_of(a), columns_of(b)
                    if ca is None or cb is None:
                        row["verdict"] = "not a frame or series (%s)" % type(a).__name__
                    else:
                        ident = sorted(str(k) for k in ca if k in cb and same_seq(ca[k], cb[k]))
                        row["rows"] = int(len(a))
                        row["identical_columns"] = ident[:20]
                        keys = []
                        for m, k, by_index in calls:
                            if by_index:
                                keys.append(["__index0__"])
                            elif isinstance(k, str):
                                keys.append([k])
                            elif isinstance(k, (list, tuple)):
                                keys.append([str(x) for x in k])
                        known = [ks for ks in keys if all(x in ca for x in ks)]
                        if known:
                            ok = any(all(same_seq(ca[x], cb[x]) for x in ks) for ks in known)
                            row["keys"] = known
                            row["verdict"] = "only tied keys reordered" if ok else "key sequence differs"
                        else:
                            mono = [str(k) for k in ca if k in cb and monotonic(ca[k]) and same_seq(ca[k], cb[k])]
                            row["monotonic_identical"] = mono[:10]
                            row["verdict"] = ("only tied keys reordered (key inferred: a monotonic column is identical)"
                                              if mono else "keys not determined")
                    mk = (label, nb, c["i"], name)
                    if mk in MANUAL and not row["verdict"].startswith("only tied keys reordered"):
                        row["automatic_verdict"] = row["verdict"]
                        row["verdict"], row["manual_evidence"] = MANUAL[mk]
                    rows.append(row)
                    per[(label, row["verdict"])] += 1
    out = {"population": "outputs at E1 in E1 cells of the sort family (conf_1x engines, drift pandas versions)",
           "outputs": len(rows), "by_label_verdict": {"%s|%s" % k: v for k, v in sorted(per.items())}, "rows": rows}
    with open(OUT + ".tmp", "w") as f:
        json.dump(out, f, indent=1, default=str)
    os.replace(OUT + ".tmp", OUT)
    print(json.dumps(out["by_label_verdict"], indent=1))


if __name__ == "__main__":
    sys.exit(main())

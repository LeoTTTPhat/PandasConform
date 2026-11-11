#!/usr/bin/env python3
"""C2 adversarial capture corpus (review round R5, agent B1): writes the probe notebooks, their input and the expected
captures. Writes only work/r5_capture/c2/work/probes/nb/<nb>/ and icde27/analysis/r5_capture/c2_cases.json.

    python3 06_pandas_conformance-ICDE/icde27/analysis/r5_capture/c2_build.py

A difference is planted only under the alternative configurations through the helper `_alt()` (a function, never
captured itself; true when `pd` is not pandas 2.3.x: pandas 3.0.6, FireDucks, Dask). Each case names the cell where
the planted (or natural) difference arises, the output or reader where it should show, the truth, and the expected
outcome of the harness under the original encoder ("orig") and the exact encoder ("exact"), per alternative.
Outcome words: captured (reported at that cell with the class the contract gives, or E0 for a control), captured_late
(reported only at a later reader, as an input difference), flagged (reported but marked as not exact: printed-form
element in the R4 census sense, inexact element of the exact encoder, uncapturable input making the reader unclean),
missed (reported equal or not scored without a flag, a wrong attribution, or a difference reported where none exists).
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
NBROOT = os.path.join(PROJ, "work", "r5_capture", "c2", "work", "probes", "nb")

HEAD = ('import pandas as pd\nimport numpy as np\n\ndef _alt():\n'
        '    return pd.__name__ != "pandas" or not pd.__version__.startswith("2.3.")\n\n'
        'df = pd.read_csv("input/data.csv")')

NOTEBOOKS = {
    "c2_nested": [
        "import os",
        HEAD,
        'def _perturb(d):\n    d = d.copy()\n    if _alt():\n        d.loc[50, "b"] = d.loc[50, "b"] + 1.0\n    return d',
        'frames = [df.head(3), _perturb(df)]',
        'stats = {"m": df[["b"]] * (1.0 + (1e-7 if _alt() else 0.0))}',
        'parts = [df[["a"]].astype("Int64" if _alt() else "int64")]',
        'deep = [[[[[[1, 2 + int(_alt())]]]]]]',
        'tok = [["a,0:str:b"]] if _alt() else [["a", "b"]]',
        'same = [df.head(3), df.tail(2)]',
        'sframe = pd.DataFrame({"s": ["x", "y", "z"]})',
        'snest = [sframe]',
        'objs = [object()]',
    ],
    "c2_alias": [
        "import os",
        HEAD,
        'da = df.copy()',
        'db = da',
        'db.loc[0, "a"] = 99 if _alt() else 98',
        'sa = int(da["a"].sum())',
        'def bump(d):\n    d.loc[1, "a"] = 77 if _alt() else 76',
        'dc = df.copy()',
        'bump(dc)',
        'sc = int(dc["a"].sum())',
        'dd = df.copy()',
        'bump(dd)',
        'class Acc:\n    pass\n\nacc = Acc()\nacc.total = 0.0',
        'def add(v):\n    acc.total += v * (2 if _alt() else 1)',
        '_ = df["b"].apply(add)',
        'tot = acc.total',
        'log = []',
        '_ = df["b"].head(5).apply(lambda v: log.append(v * (2 if _alt() else 1)))',
        'slog = sum(log)',
    ],
    "c2_globals": [
        "import os",
        HEAD,
        'THRESH = 0.5 + (0.1 if _alt() else 0.0)',
        'def above(x):\n    return x > THRESH',
        'n_above = int(above(df["b"]).sum())',
        'def make_pred():\n    def pred(x):\n        return x > THRESH\n    return pred',
        'pred = make_pred()',
        'n_pred = int(pred(df["b"]).sum())',
        'counter = 0',
        'def tick():\n    global counter\n    counter += 2 if _alt() else 1',
        'tick()',
        'cval = counter',
        'globals()["dyn"] = float(df["b"].sum()) + (1.0 if _alt() else 0.0)',
        'dyn2 = dyn * 2',
        'exec("ex = float(df[\'b\'].sum()) + (1.0 if _alt() else 0.0)")',
        'ex2 = ex * 2',
        'gr = df["b"] * globals()["dyn"]',
    ],
    "c2_lazy_inplace": [
        "import os",
        HEAD,
        'm = df["b"].mean() + (1e-3 if _alt() else 0.0)',
        's2 = df["b"] * 2.0 * (1.0 + (1e-6 if _alt() else 0.0))',
        'ds = df.copy()',
        'ds.sort_values("a" if _alt() else "b", inplace=True)',
        'g = df.groupby("k" if not _alt() else "a")',
        'gsum = g["b"].sum()',
    ],
    "c2_printed_only": [
        "import os",
        HEAD,
        'class Box:\n    def __init__(self, v):\n        self.v = v\n\n    def __repr__(self):\n        return "Box()"',
        'boxes = [Box(1.0 if not _alt() else 2.0)]',
        'meth = [df.head]',
        'dt = df.dtypes',
        'rl = [range(3 + int(_alt()))]',
        'fl = [lambda x: x]',
    ],
    "c2_dask": [
        "import os",
        HEAD,
        'mean_b = df["b"].mean()',
        'summ = {"mean": df["b"].mean(), "max": df["a"].max()}',
        'pair = [df["b"].sum(), df["a"].sum()]',
        'ser = [df["b"] * 2]',
        'pl = {"m": df["b"].mean() + (0.5 if _alt() else 0.0)}',
    ],
}

# cases: id, notebook, cell where the difference arises, where it should show (cell, name), truth (the class the
# contract gives, or the attribution), and the expected result per harness ("orig" encoder, "exact" encoder) and
# alternative engine: verdict (correct, coarser = right direction but a coarser class, wrong = a difference reported
# as a match or the reverse, or a wrong attribution, late = seen only at a later reader as an input difference,
# unscored) and flag (none; printed = an element compared by its printed form, the R4 census definition; inexact =
# an element the exact encoder could not encode; uncapturable_input = the reader is unclean because an input cannot be
# serialized). Category: captured exactly = correct and no flag; flagged = any flag; missed = wrong or unscored
# without a flag; late and coarser are reported as such.
A2 = ("p30", "fireducks")
A3 = ("p30", "fireducks", "dask")


def V(verdict, flag="none"):
    return {"verdict": verdict, "flag": flag}


def same(orig, exact, engines=A2):
    return {"orig": {e: orig for e in engines}, "exact": {e: exact for e in engines}}


CASES = [
    {"id": "nested_hidden_row", "nb": "c2_nested", "show": [3, "frames"], "category": "nested containers",
     "truth": "DIFF: element 1 of the list differs in row 50, outside the printed head and tail",
     "expected": same(V("wrong", "printed"), V("correct"))},
    {"id": "nested_float_digits", "nb": "c2_nested", "show": [4, "stats"], "category": "nested containers",
     "truth": "DIFF: the frame in the dict differs at relative 1e-7 (beyond the 1e-9 tolerance), invisible at 6 printed decimals",
     "expected": same(V("wrong", "printed"), V("correct"))},
    {"id": "nested_dtype_only", "nb": "c2_nested", "show": [5, "parts"], "category": "nested containers",
     "truth": "E2: the frame in the list is Int64 instead of int64 with the same values (a widening)",
     "expected": {"orig": {"p30": V("wrong", "printed"), "fireducks": V("correct", "printed")},
                  "exact": {"p30": V("coarser"), "fireducks": V("coarser")}},
     "note": "orig under FireDucks reaches E2 only through the engine type name of the nested frame; the exact encoder "
             "compares nested values exactly (DIFF here) and the graded nested level comes from the nested records"},
    {"id": "nested_depth_cut", "nb": "c2_nested", "show": [6, "deep"], "category": "nested containers",
     "truth": "DIFF: the innermost element of a list nested 6 deep differs (the printed form stops at depth 4)",
     "expected": same(V("wrong", "printed"), V("correct"))},
    {"id": "nested_delimiter_collision", "nb": "c2_nested", "show": [7, "tok"], "category": "nested containers",
     "truth": 'DIFF: [["a,0:str:b"]] against [["a", "b"]] (one string against two), same printed form',
     "expected": same(V("wrong", "printed"), V("correct"))},
    {"id": "nested_control_equal", "nb": "c2_nested", "show": [8, "same"], "category": "nested containers (control)",
     "truth": "FireDucks: E0 (equal frames inside a list); pandas 3.0.6: E2 (its column labels have the str dtype)",
     "expected": {"orig": {"p30": V("wrong", "printed"), "fireducks": V("coarser", "printed")},
                  "exact": {"p30": V("coarser"), "fireducks": V("correct")}},
     "note": "the original encoder records the engine type name of nested frames, so equal frames reach only E2 under FireDucks"},
    {"id": "nested_natural_str_dtype", "nb": "c2_nested", "show": [10, "snest"],
     "category": "nested containers (natural pandas 3 change)",
     "truth": "pandas 3.0.6: E2 (the nested string frame gets the str dtype, object under 2.3.3); FireDucks: E0",
     "expected": {"orig": {"p30": V("wrong", "printed"), "fireducks": V("coarser", "printed")},
                  "exact": {"p30": V("coarser"), "fireducks": V("correct")}}},
    {"id": "nested_object_address", "nb": "c2_nested", "show": [11, "objs"], "category": "printed-form-only objects",
     "truth": "no value to compare: object() inside a list, whose repr holds a memory address",
     "expected": same(V("wrong", "printed"), V("wrong", "inexact")),
     "note": "both encoders report the address difference as DIFF"},
    {"id": "alias_visible", "nb": "c2_alias", "show": [4, "db"], "category": "mutable aliases",
     "truth": "DIFF at cell 4 for db (an alias of da, changed in row 0); da shows at its reader, cell 5, as an input difference",
     "expected": same(V("correct"), V("correct"))},
    {"id": "alias_function", "nb": "c2_alias", "show": [8, None], "reader": [9, "sc"], "category": "mutable aliases",
     "truth": "dc changes in cell 8 through the called function bump(); the AST of cell 8 shows no output",
     "expected": same(V("late"), V("late"))},
    {"id": "alias_function_no_reader", "nb": "c2_alias", "show": [11, None], "category": "mutable aliases",
     "truth": "dd changes in cell 11 through bump(); no later cell reads dd",
     "expected": same(V("unscored"), V("unscored"))},
    {"id": "attribute_side_effect", "nb": "c2_alias", "show": [14, None], "reader": [15, "tot"],
     "category": "in-place side effects",
     "truth": "apply(add) changes acc.total through a function; acc (a user-class object) cannot be serialized",
     "expected": same(V("late", "uncapturable_input"), V("late", "uncapturable_input"))},
    {"id": "apply_append", "nb": "c2_alias", "show": [17, None], "reader": [18, "slog"], "category": "in-place side effects",
     "truth": "a lambda passed to apply appends doubled values to log in cell 17",
     "expected": same(V("late"), V("late")),
     "note": "prediction revised before the run after a static check: the AST analysis ignores mutating calls inside "
             "a lambda, so log is not an output of cell 17; a reader cell (18) was added"},
    {"id": "hidden_global_traced", "nb": "c2_globals", "show": [2, "THRESH"], "reader": [4, "n_above"],
     "category": "hidden globals",
     "truth": "THRESH differs (cell 2); cell 4 calls above(), which reads it: cell 4 is not clean (inherited DIFF)",
     "expected": same(V("correct"), V("correct"))},
    {"id": "hidden_global_closure", "nb": "c2_globals", "show": [2, "THRESH"], "reader": [7, "n_pred"],
     "category": "hidden globals",
     "truth": "cell 7 calls the closure pred (returned by make_pred()), which reads THRESH: cell 7 should not be clean",
     "expected": same(V("wrong"), V("wrong")),
     "note": "globals are traced for functions defined in earlier cells, not for a closure bound to a variable: cell 7 "
             "counts as clean with an introduced DIFF"},
    {"id": "global_statement", "nb": "c2_globals", "show": [10, None], "reader": [11, "cval"], "category": "hidden globals",
     "truth": "tick() changes the global counter through a global statement in cell 10, which shows no output",
     "expected": same(V("late"), V("late"))},
    {"id": "dynamic_globals_store", "nb": "c2_globals", "show": [12, None], "reader": [13, "dyn2"],
     "category": "dynamic accesses", "truth": 'globals()["dyn"] = ... binds dyn in cell 12, invisible to the AST',
     "expected": same(V("late"), V("late"))},
    {"id": "dynamic_exec_store", "nb": "c2_globals", "show": [14, None], "reader": [15, "ex2"],
     "category": "dynamic accesses", "truth": "exec binds ex in cell 14, invisible to the AST",
     "expected": same(V("late"), V("late"))},
    {"id": "dynamic_globals_read", "nb": "c2_globals", "show": [12, None], "reader": [16, "gr"],
     "category": "dynamic accesses",
     "truth": 'cell 16 reads dyn through globals()["dyn"]: cell 16 should not be clean',
     "expected": same(V("wrong"), V("wrong")),
     "note": "dyn is not an input of cell 16, which counts as clean with an introduced DIFF"},
    {"id": "lazy_assigned_scalar", "nb": "c2_lazy_inplace", "show": [2, "m"], "category": "lazy values",
     "truth": "DIFF: an assigned, never displayed reduction differs by 1e-3", "expected": same(V("correct"), V("correct"))},
    {"id": "lazy_assigned_series", "nb": "c2_lazy_inplace", "show": [3, "s2"], "category": "lazy values",
     "truth": "DIFF: an assigned, never displayed Series differs at relative 1e-6", "expected": same(V("correct"), V("correct"))},
    {"id": "inplace_sort", "nb": "c2_lazy_inplace", "show": [5, "ds"], "category": "in-place side effects",
     "truth": "E1: an in-place sort on another key (same rows, other order); pandas 3.0.6: E2 (str column labels)",
     "expected": same(V("correct"), V("correct"))},
    {"id": "groupby_object", "nb": "c2_lazy_inplace", "show": [6, "g"], "reader": [7, "gsum"],
     "category": "objects without an encoding",
     "truth": "the GroupBy object (not serializable) groups by another key in cell 6; the aggregation in cell 7 differs",
     "expected": same(V("late", "uncapturable_input"), V("late", "uncapturable_input"))},
    {"id": "repr_hides_state", "nb": "c2_printed_only", "show": [3, "boxes"], "category": "printed-form-only objects",
     "truth": "DIFF: Box(1.0) against Box(2.0), both printed as Box()",
     "expected": same(V("wrong", "printed"), V("wrong", "inexact"))},
    {"id": "bound_method", "nb": "c2_printed_only", "show": [4, "meth"], "category": "printed-form-only objects",
     "truth": "df.head bound to the frame: the same function under pandas 3.0.6 with a frame that differs at E2 (str "
              "column labels): E2; another implementation under FireDucks: DIFF",
     "expected": {"orig": {"p30": V("wrong", "printed"), "fireducks": V("correct", "printed")},
                  "exact": {"p30": V("coarser"), "fireducks": V("correct")}}},
    {"id": "dtype_objects", "nb": "c2_printed_only", "show": [5, "dt"], "category": "printed-form-only objects (control)",
     "truth": "E0: df.dtypes with the same numeric dtypes (pandas 3.0.6: E0 or E2, its index holds the str labels)",
     "expected": same(V("correct", "printed"), V("correct"))},
    {"id": "range_in_list", "nb": "c2_printed_only", "show": [6, "rl"], "category": "printed-form-only objects",
     "truth": "DIFF: range(3) against range(4)", "expected": same(V("correct", "printed"), V("correct"))},
    {"id": "lambda_in_list", "nb": "c2_printed_only", "show": [7, "fl"], "category": "printed-form-only objects",
     "truth": "no value to compare: the same lambda inside a list, whose repr holds a memory address",
     "expected": same(V("wrong", "printed"), V("wrong", "inexact"))},
    {"id": "dask_lazy_scalar", "nb": "c2_dask", "show": [2, "mean_b"], "category": "lazy values",
     "truth": "E0 (or E2 if a partitioned sum rounds differently): an assigned lazy reduction",
     "expected": same(V("correct"), V("correct"), A3)},
    {"id": "dask_lazy_in_dict", "nb": "c2_dask", "show": [3, "summ"], "category": "lazy values inside containers",
     "truth": "E0 (or E2): lazy reductions inside a dict, equal after compute",
     "expected": {"orig": {"p30": V("correct"), "fireducks": V("correct"), "dask": V("wrong", "printed")},
                  "exact": {"p30": V("correct"), "fireducks": V("correct"), "dask": V("correct")}},
     "note": "the original encoder prints the uncomputed Dask scalar (a DIFF from representation only)"},
    {"id": "dask_lazy_in_list", "nb": "c2_dask", "show": [4, "pair"], "category": "lazy values inside containers",
     "truth": "E0 (or E2): lazy sums inside a list, equal after compute",
     "expected": {"orig": {"p30": V("correct"), "fireducks": V("correct"), "dask": V("wrong", "printed")},
                  "exact": {"p30": V("correct"), "fireducks": V("correct"), "dask": V("correct")}}},
    {"id": "dask_lazy_series_in_list", "nb": "c2_dask", "show": [5, "ser"], "category": "lazy values inside containers",
     "truth": "E0 (or E2): a lazy Series inside a list, equal after compute",
     "expected": {"orig": {"p30": V("correct", "printed"), "fireducks": V("coarser", "printed"), "dask": V("wrong", "printed")},
                  "exact": {"p30": V("correct"), "fireducks": V("correct"), "dask": V("correct")}}},
    {"id": "dask_planted_in_dict", "nb": "c2_dask", "show": [6, "pl"], "category": "lazy values inside containers",
     "truth": "DIFF: a lazy reduction plus 0.5 inside a dict",
     "expected": {"orig": {"p30": V("correct"), "fireducks": V("correct"), "dask": V("correct", "printed")},
                  "exact": {"p30": V("correct"), "fireducks": V("correct"), "dask": V("correct")}},
     "note": "orig under Dask reports DIFF only because a printed lazy scalar differs from a float"},
]


def main():
    import random
    rng = random.Random(20261110)
    rows = ["k,a,b"] + ["%d,%d,%.12f" % (i % 5, rng.randint(0, 1000), rng.random()) for i in range(100)]
    for nb, cells in NOTEBOOKS.items():
        d = os.path.join(NBROOT, nb)
        os.makedirs(os.path.join(d, "input"), exist_ok=True)
        with open(os.path.join(d, "input", "data.csv"), "w") as f:
            f.write("\n".join(rows) + "\n")
        doc = {"cells": [{"cell_type": "code", "source": c, "metadata": {}, "outputs": [], "execution_count": None}
                         for c in cells], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
        with open(os.path.join(d, "old.ipynb"), "w") as f:
            json.dump(doc, f, indent=1)
    sets = os.path.join(PROJ, "work", "r5_capture", "c2")
    with open(os.path.join(sets, "c2_set.json"), "w") as f:
        json.dump({"notebooks": ["probe:" + nb for nb in NOTEBOOKS if nb != "c2_dask"]}, f, indent=1)
    with open(os.path.join(sets, "c2_set_dask.json"), "w") as f:
        json.dump({"notebooks": ["probe:c2_dask"]}, f, indent=1)
    with open(os.path.join(HERE, "c2_cases.json"), "w") as f:
        json.dump({"written": "2026-11-10, before the C2 run (pandas 3.0.6 truths of four cases corrected before the "
                              "run, after a smoke test showed that pandas 3 column labels have the str dtype)", "notebooks": NOTEBOOKS, "cases": CASES,
                   "verdicts": ["correct", "coarser", "wrong", "late", "unscored"],
                   "flags": ["none", "printed", "inexact", "uncapturable_input"]}, f, indent=1)
    print("notebooks", len(NOTEBOOKS), "cases", len(CASES))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Cell overrides for A's scripts (review round R5, agent B1). Read-only on c1_cell_changes.csv and
work/r5_capture/compare/{graded,exact}; writes icde27/analysis/r5_capture/c1_overrides.json.

    python3 06_pandas_conformance-ICDE/icde27/analysis/r5_capture/c1_overrides.py

For every printed-form cell that the exact recapture changes and that has no run-to-run change (the cells
c1_analyze.py applies in its `exact_graded` and `exact_nested_e0` variants), the complete compare-cell fields of the new
comparison (cls, cls_raw, clean_level, clean_input, outputs with levels and failing checks, input_levels, unclean,
hidden_globals, eng_exc, eng_msg, flags, fallback, families), keyed "label|notebook|cell", so that a script built on
the original compare outputs (r1_cells.py, r3_sensitivity.py, r4_audit.py, rootcause_taxonomy.classify_cell) can
substitute them; `remove_in_strict` lists the cells that the `exact_graded_strict` variant removes.
"""
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
R5 = os.path.join(PROJ, "work", "r5_capture")
KEYS = ("i", "cls", "cls_raw", "clean_level", "clean_input", "outputs", "input_levels", "unclean", "hidden_globals",
        "inputs_from", "eng_exc", "eng_msg", "eng_origin", "flags", "fallback", "families")


def main():
    rows = list(csv.DictReader(open(os.path.join(HERE, "c1_cell_changes.csv"))))
    out = {"graded": {}, "nested_e0": {}, "remove_in_strict": []}
    cache = {}

    def cell(variant, label, nb, i):
        key = (variant, label, nb)
        if key not in cache:
            p = os.path.join(R5, "compare", variant, label, nb.replace("/", "__") + ".json")
            cache[key] = {c["i"]: c for c in json.load(open(p))["cells"]} if os.path.exists(p) else {}
        c = cache[key].get(int(i))
        return {k: c[k] for k in KEYS if c is not None and k in c} if c is not None else None

    for r in rows:
        k = "%s|%s|%s" % (r["label"], r["nb"], r["cell"])
        if r["removed_in_exact_graded_strict"] == "True":
            out["remove_in_strict"].append(k)
        if r["recaptured"] != "True" or r["run_to_run"] == "True":
            continue
        if r["encoding_effect"] == "True":
            out["graded"][k] = cell("graded", r["label"], r["nb"], r["cell"])
        if r["encoding_effect_x"] == "True":
            out["nested_e0"][k] = cell("exact", r["label"], r["nb"], r["cell"])
    with open(os.path.join(HERE, "c1_overrides.json"), "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    print(len(out["graded"]), "graded overrides,", len(out["nested_e0"]), "nested-E0 overrides,",
          len(out["remove_in_strict"]), "cells removed in the strict variant")


if __name__ == "__main__":
    main()

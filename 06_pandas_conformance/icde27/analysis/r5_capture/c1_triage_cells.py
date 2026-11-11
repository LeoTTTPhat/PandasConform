#!/usr/bin/env python3
"""Per-cell kinds of printed elements, from c1_triage.json (review round R5, agent B1). Read-only on c1_triage.json;
writes icde27/analysis/r5_capture/c1_triage_cells.json.

    python3 06_pandas_conformance-ICDE/icde27/analysis/r5_capture/c1_triage_cells.py

Each printed-form cell of the 688-cell census gets one kind, from the type names of its printed elements (both sides):
  containers of scalars only      nested lists, tuples, dicts or sets of exactly tagged scalars (the printed form is
                                  an exact encoding up to delimiter collisions);
  dtype objects (and scalar containers)  NumPy or pandas dtype objects (a `df.dtypes` Series), possibly with the above;
  frames, Series, arrays involved a pandas or NumPy object (or an engine frame, Series or lazy value) is printed:
                                  rows can be cut, floats are printed with 6 decimals, dtypes are not printed;
  other objects involved          any other object (bound methods, ranges, ...), or a container cut at depth 4.
Grouped by the cell's original class: matching (E0-E4), DIFF, other.
"""
import collections
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DT = re.compile(r"(DType|Dtype)$")
PN = re.compile(r"^(pandas|numpy|modin|fireducks|bodo|dask)\.")


def out_kinds(o):
    kinds = set()
    for ty in o["types"]:
        base = ty.split("<")[0]
        inner = re.findall(r"<(.*)>", ty)
        if inner:
            if "depth cut" in inner[0]:
                kinds.add("other")
                continue
            for pt in inner[0].split(","):
                kinds.add("dtype" if DT.search(pt) else ("frame_like" if PN.match(pt) else "other"))
        elif base in ("list", "dict", "tuple", "set", "frozenset"):
            kinds.add("container_scalars")
        elif DT.search(base):
            kinds.add("dtype")
        elif PN.match(base):
            kinds.add("frame_like")
        else:
            kinds.add("other")
    return kinds


def main():
    t = json.load(open(os.path.join(HERE, "c1_triage.json")))
    tot = collections.Counter()
    by_label = {}
    cells = []
    for lab, L in sorted(t["by_label"].items()):
        c = collections.Counter()
        for nb, N in sorted(L["notebooks"].items()):
            for cell in N["cells"]:
                ks = set()
                for o in cell["outputs"]:
                    ks |= out_kinds(o)
                if not ks:
                    continue
                if ks <= {"container_scalars"}:
                    k = "containers of scalars only"
                elif ks <= {"container_scalars", "dtype"}:
                    k = "dtype objects (and scalar containers)"
                elif "other" in ks:
                    k = "other objects involved"
                else:
                    k = "frames, Series, arrays involved"
                grp = "matching" if cell["cls"] in ("E0", "E1", "E2", "E3", "E4") else ("DIFF" if cell["cls"] == "DIFF" else "other")
                c[grp + "|" + k] += 1
                tot[grp + "|" + k] += 1
                cells.append([lab, nb, cell["i"], cell["cls"], k])
        by_label[lab] = dict(c)
    out = {"totals": dict(tot), "by_label": by_label, "cells": cells, "n_cells": len(cells)}
    with open(os.path.join(HERE, "c1_triage_cells.json"), "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    print(json.dumps(out["totals"], indent=1, sort_keys=True), out["n_cells"])


if __name__ == "__main__":
    main()

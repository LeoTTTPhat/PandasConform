#!/usr/bin/env python3
"""Review R1 item B5: evidence sheets for hand-attributing the unattributed introduced cells (2026-10-26).

Read-only on results/, data/ and captures/. Writes ONE file, given by --out, OUTSIDE the project (the sheets show
values captured from the Kaggle inputs, which the artifact does not redistribute); the hand attributions that the
sheets support are recorded, without data values, in icde27/analysis/r1_hand_attribution.json.

    cd ..
    .venv/bin/python 06_pandas_conformance/icde27/analysis/r1_unattributed_dump.py --out <scratch>/unattributed.md

Per cell: label, notebook, cell, class, clean level, engine exception, the cell code (with called user functions),
each output's level and failing checks, and for DataFrame/Series/scalar outputs a short side-by-side of the first
differing rows (reference vs engine, both decoded from the store).
"""
import argparse
import importlib.util
import json
import os
import sys

os.environ.setdefault("PCONF_DECODE_CACHE_GB", "0.2")
HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(PROJ, "src"))
from pconf import capture as C  # noqa: E402
from pconf import util  # noqa: E402

import pandas as pd  # noqa: E402

MAX_PREVIEW_VALUES = 200_000   # values decoded per previewed object; keeps a run far below 2 GB


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def preview(a, b, nmax=4):
    try:
        if isinstance(a, pd.Series):
            a, b = a.to_frame(), b.to_frame() if isinstance(b, pd.Series) else b
        if isinstance(a, pd.DataFrame) and isinstance(b, pd.DataFrame):
            lines = ["  shapes %s / %s; dtypes ref %s | eng %s" % (a.shape, b.shape, list(map(str, a.dtypes))[:6],
                                                                   list(map(str, b.dtypes))[:6])]
            n = min(len(a), len(b))
            shown = 0
            for k in range(n):
                ra, rb = a.iloc[k].tolist(), b.iloc[k].tolist()
                if [str(x) for x in ra] != [str(x) for x in rb] or str(a.index[k]) != str(b.index[k]):
                    lines.append("  row %d: ref idx=%r %r" % (k, a.index[k], [str(x)[:40] for x in ra][:8]))
                    lines.append("         eng idx=%r %r" % (b.index[k], [str(x)[:40] for x in rb][:8]))
                    shown += 1
                    if shown >= nmax:
                        break
            if not shown:
                lines.append("  (no differing row in the first %d rows by string form)" % n)
            return "\n".join(lines)
        return "  ref %r\n  eng %r" % (str(a)[:300], str(b)[:300])
    except Exception as e:
        return "  preview failed: %s" % e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.abspath(a.out).startswith(PROJ):
        raise SystemExit("write the evidence sheets outside the project (they contain captured values)")
    T = load_module("rootcause_taxonomy", os.path.join(PROJ, "scripts", "rootcause_taxonomy.py"))
    tax = json.load(open(os.path.join(PROJ, "results", "rootcause", "taxonomy_conf1x.json")))
    cells = tax["causes"]["unattributed"]["cells"]
    best = {c: T.select_outputs(c, T.COMPARE)[1] for c in ("conf_1x", "drift")}
    lines = []
    for k, (camp, label, nb, i, cls) in enumerate(sorted(cells, key=lambda x: (x[1], x[2], x[3]))):
        _, r, p = best[camp][(label, nb, 1.0)]
        c = next(x for x in r["cells"] if x["i"] == i)
        lines.append("\n## U%03d %s %s cell %d: %s (inputs equal at %s) fallback=%s" % (k + 1, label, nb, i, cls, c.get("clean_level"),
                                                                                          c.get("fallback")))
        if c.get("eng_exc"):
            lines.append("engine exception: %s: %s" % (c.get("eng_exc"), (c.get("eng_msg") or "")[:200]))
        lines.append("```\n" + T.cell_code(nb, i)[:1500] + "\n```")
        ref = json.load(open(os.path.join(PROJ, r["meta"]["ref_record"])))
        eng = json.load(open(os.path.join(PROJ, r["meta"]["eng_record"])))
        rc = {x.get("i"): x for x in ref["cells"]}.get(i, {})
        ec = {x.get("i"): x for x in eng["cells"]}.get(i, {})
        for name, o in sorted((c.get("outputs") or {}).items()):
            lines.append("- output `%s`: %s fails=%s %s" % (name, o.get("level"), json.dumps(o.get("fails") or {}),
                                                           o.get("reason") or ""))
            if o.get("level") in ("DIFF", "E4", "E3", "E2"):
                try:
                    ra = ref["objects"][rc["outputs"][name]]
                    ea = eng["objects"][ec["outputs"][name]]
                    nv = 1
                    for x in ((ra.get("meta") or {}).get("shape") or [1]):
                        nv *= max(int(x or 1), 1)
                    if nv > MAX_PREVIEW_VALUES:
                        lines.append("  (large object, %d values: no preview)" % nv)
                        continue
                    lines.append(preview(C.decode_to_pandas(util.CAPTURES, ra), C.decode_to_pandas(util.CAPTURES, ea)))
                except Exception as e:
                    lines.append("  (no preview: %s)" % type(e).__name__)
        ew = [w.get("category") for w in (ec.get("warnings") or [])]
        if ew:
            lines.append("engine warnings: %s" % ew[:6])
    with open(a.out, "w") as f:
        f.write("\n".join(lines))
    print("wrote %s (%d cells)" % (a.out, len(cells)))


if __name__ == "__main__":
    sys.exit(main())

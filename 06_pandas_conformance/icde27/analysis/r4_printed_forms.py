#!/usr/bin/env python3
"""Census of comparisons that fell back to a printed form (review round R4; ICDE 2027 copy; written 2026-11-10).

Read-only on results/{conf_1x,drift}/raw (compare outputs and run records), captures/cols (only the element-tag
column of the object-encoded blobs) and icde27/analysis/r1_hand_attribution.json; writes only
icde27/analysis/r4_printed_forms.json. Memory well below 2 GB.

    cd ..
    /usr/bin/time -l .venv/bin/python 06_pandas_conformance-ICDE/icde27/analysis/r4_printed_forms.py

src/pconf/capture.py encodes a column of mixed Python objects element by element ('obj' encoding: a tag, an exact
payload string and a type name per element). Two tags have no exact encoding and carry the element's printed form:
T_CONTAINER (a list, tuple, dict or set nested inside the value, including a frame inside a list or dict, whose
elements are printed) and T_OTHER (any other object, printed with repr, for example a bound method). The comparator
compares these payloads as strings, so for such an element no level finer than an exact text match is available.
For every scored cell (classes other than REF_ERR, NONDET, NOOUT and SETUP_ERR) of the seven configurations, an
output "uses a printed form" when its captured record on the reference side or the configuration's side holds such
an element (in a column, the index or a sub-column). Reported per configuration: scored cells and outputs, those
that use a printed form, their output levels (equal printed forms reach a level; differing ones give DIFF), the cell
classes, those in the clean@E2 view (clean level E0-E2, not after a timeout; the population of the paired
comparisons), and the 16 printed-form artifact cells of r1_hand_attribution.json as a check (all must be found).
An output flagged here holds at least one printed element; its level or DIFF may come from other elements.
"""
import collections
import glob
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "r4_printed_forms.json")
sys.path.insert(0, os.path.join(PROJ, "src"))
from pconf import capture, util  # noqa: E402

T_CONTAINER, T_OTHER = capture.T_CONTAINER, capture.T_OTHER


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    import pyarrow as pa
    R1 = load_module("r1_cells", os.path.join(HERE, "r1_cells.py"))
    T = load_module("rootcause_taxonomy", os.path.join(PROJ, "scripts", "rootcause_taxonomy.py"))
    hand = json.load(open(os.path.join(HERE, "r1_hand_attribution.json")))
    printed16 = {(r["label"], r["nb"], r["cell"]) for r in hand["rows"] if r["cause"] == "printed_form_comparison"}
    store = util.CAPTURES
    if not os.path.isdir(os.path.join(store, "cols")):
        raise SystemExit("no capture store at %s: the census reads the element tags of the captured blobs, which the "
                         "artifact does not redistribute (they hold values of the Kaggle inputs)" % store)
    tag_cache = {}
    missing_blobs = []

    def col_flags(c):
        """-> set of printed tags in an obj column descriptor (recursing into sub-columns)."""
        found = set()
        if c.get("enc") == "obj":
            h = c["h"]
            if h not in tag_cache:
                path = capture.blob_path(store, h)
                if not c.get("stored", True) or not os.path.exists(path):
                    tag_cache[h] = None
                    missing_blobs.append(h)
                else:
                    with pa.memory_map(path, "r") as src:
                        t = pa.ipc.open_file(src).read_all().column("t").to_numpy()
                    tag_cache[h] = {int(x) for x in set(t.tolist()) & {T_CONTAINER, T_OTHER}}
            found |= tag_cache[h] or set()
        for v in (c.get("x") or {}).values():
            if isinstance(v, dict) and "enc" in v:
                found |= col_flags(v)
        return found

    def rec_flags(rec):
        if not rec:
            return set()
        found = set()
        for c in (rec.get("cols") or []) + (rec.get("idx") or []):
            found |= col_flags(c)
        if rec.get("kind") == "scalar":
            t = (rec.get("meta") or {}).get("value", [None])[0]
            if t in (T_CONTAINER, T_OTHER):
                found.add(t)
        return found

    run_cache = {}

    def run_outputs(path):
        """run record -> {cell i: {output name: object record}}"""
        if path not in run_cache:
            r = json.load(open(os.path.join(PROJ, path)))
            objs = r.get("objects") or {}
            run_cache.clear()   # one engine record and one reference record at a time suffice per notebook
            run_cache[path] = {c["i"]: {n: (objs.get(h) if isinstance(h, str) else h) for n, h in (c.get("outputs") or {}).items()} for c in r["cells"]}
        return run_cache[path]

    res = {}
    found16 = set()
    for campaign, label in R1.LABELS:
        root, best = T.select_outputs(campaign, T.COMPARE)
        tot = collections.Counter()
        lv = collections.Counter()
        cls_pf = collections.Counter()
        tags = collections.Counter()
        cells_list = []
        for (lab, nb, sc), (_, r, p) in sorted(best.items()):
            if lab != label:
                continue
            m = r["meta"]
            eng = dict(run_outputs(m["eng_record"]))
            ref = run_outputs(m["ref_record"])
            t_idx = next((k for k, c in enumerate(r["cells"]) if c.get("cls") == "TIMEOUT" or c.get("cls_raw") == "TIMEOUT"), None)
            for k_cell, c in enumerate(r["cells"]):
                if c["cls"] in R1.EXCLUDED:
                    continue
                in_ce2 = c.get("clean_level") in ("E0", "E1", "E2") and not (t_idx is not None and k_cell > t_idx)
                tot["clean_E2_cells"] += in_ce2
                tot["scored_cells"] += 1
                pf_cell = False
                for name, o in (c.get("outputs") or {}).items():
                    tot["scored_outputs"] += 1
                    fl = rec_flags(eng.get(c["i"], {}).get(name)) | rec_flags(ref.get(c["i"], {}).get(name))
                    if fl:
                        pf_cell = True
                        tot["printed_form_outputs"] += 1
                        lv[o.get("level")] += 1
                        for t in fl:
                            tags["container" if t == T_CONTAINER else "other_object"] += 1
                if pf_cell:
                    tot["printed_form_cells"] += 1
                    cls_pf[c["cls"]] += 1
                    if in_ce2:
                        tot["printed_form_clean_E2_cells"] += 1
                        tot["printed_form_clean_E2_DIFF"] += c["cls"] == "DIFF"
                    cells_list.append([label, nb, c["i"], c["cls"]])
                    if (label, nb, c["i"]) in printed16:
                        found16.add((label, nb, c["i"]))
        if not tot["scored_cells"]:
            raise SystemExit("no per-cell compare outputs for %s (unpack the results first)" % label)
        res[label] = {"campaign": campaign, **dict(tot), "printed_form_output_levels": dict(lv),
                      "printed_form_cell_classes": dict(cls_pf), "printed_tags_in_outputs": dict(tags),
                      "printed_form_cell_share": round(tot["printed_form_cells"] / tot["scored_cells"], 4),
                      "cells": cells_list}
    assert found16 == printed16, sorted(printed16 - found16)
    tot_cells = sum(v["printed_form_cells"] for v in res.values())
    tot_scored = sum(v["scored_cells"] for v in res.values())
    out = {"definition": "an output uses a printed form when its captured record on the reference or the "
                         "configuration's side holds an element tagged T_CONTAINER or T_OTHER (compared as text)",
           "store": "captures/cols", "obj_columns_read": len(tag_cache), "obj_columns_missing": len(missing_blobs),
           "printed16_found": len(found16), "by_label": res,
           "totals": {"scored_cells": tot_scored, "printed_form_cells": tot_cells,
                      "printed_form_outputs": sum(v.get("printed_form_outputs", 0) for v in res.values()),
                      "printed_form_cells_equal": sum(n for v in res.values() for k, n in v["printed_form_cell_classes"].items()
                                                      if k in ("E0", "E1", "E2", "E3", "E4")),
                      "printed_form_cells_DIFF": sum(v["printed_form_cell_classes"].get("DIFF", 0) for v in res.values()),
                      "clean_E2_cells": sum(v["clean_E2_cells"] for v in res.values()),
                      "printed_form_clean_E2_cells": sum(v.get("printed_form_clean_E2_cells", 0) for v in res.values()),
                      "printed_form_clean_E2_DIFF": sum(v.get("printed_form_clean_E2_DIFF", 0) for v in res.values()),
                      "printed_form_outputs_DIFF": sum(v["printed_form_output_levels"].get("DIFF", 0) for v in res.values())}}
    with open(OUT + ".tmp", "w") as f:
        json.dump(out, f, indent=1)
    os.replace(OUT + ".tmp", OUT)
    print("obj columns read %d, missing %d; 16 artifact cells found %d" % (len(tag_cache), len(missing_blobs), len(found16)))
    for label, v in res.items():
        print("  %-16s scored %4d cells | printed-form cells %3d (%.1f%%; clean@E2 %d of %d, DIFF %d) classes %s | outputs %d levels %s tags %s" % (
            label, v["scored_cells"], v.get("printed_form_cells", 0), 100 * v["printed_form_cell_share"],
            v.get("printed_form_clean_E2_cells", 0), v["clean_E2_cells"], v.get("printed_form_clean_E2_DIFF", 0),
            v["printed_form_cell_classes"], v.get("printed_form_outputs", 0), v["printed_form_output_levels"],
            v["printed_tags_in_outputs"]))
    print("totals", out["totals"])


if __name__ == "__main__":
    sys.exit(main())

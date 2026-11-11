#!/usr/bin/env python3
"""Compare re-executed runs under both encodings with the EXISTING comparator (review round R5, agent B1).

Runs in the `ref` environment (where dfeq runs) with this folder's harness copy on the path:

    env PYTHONPATH=<r5_capture>/harness <project>/envs/ref/bin/python -B c1_compare.py --jobs jobs.json --out-root DIR

Each job: {"label", "nb", "ref": run record, "eng": run record, "last_cell": k or null, "store": capture store}.
For each job two derived run-record pairs are classified with pconf.classify.classify_run (classify.py and dfeq.py are
byte-identical to src/pconf; see harness_source_sha256_original.txt):
  orig   every captured entry replaced by the entry of the ORIGINAL encoder (capture_orig.py, a byte copy of
         src/pconf/capture.py) computed from the same value in the same run (inputs_orig / outputs_orig); values
         without nested elements have one entry, identical under both encoders;
  exact  the entries of the exact recursive encoder (capture.py of the copy: nested values tagged T_NESTED with the
         hash of their own exact record, compared as payload strings by the unchanged comparator);
  graded the exact entries, where a comparison that the unchanged comparator finds DIFF and that involves nested
         values is graded: differing aligned nested values are compared by the same comparator on their own exact
         records (recursively), and if all reach a level the pair is compared again with the engine's nested payloads
         replaced by the reference's; the level is the coarser of the two (function graded()). This applies the
         levels of the contract to nested values instead of requiring nested values to be E0-equal.
Cells after `last_cell` are dropped from both records (the runs stop there). No second reference run is passed, so
no cell is NONDET here; the original NONDET cells are excluded later, in the analysis.
"""
import argparse
import copy
import json
import os
import sys
import time

import numpy as np

from pconf import capture as C
from pconf import classify, dfeq, util

PSEUDO = ("dtype", "range", "slice", "method")
ORDER = {"E0": 0, "E1": 1, "E2": 2, "E3": 3, "E4": 4}
NESTED = {}          # hash -> nested record (both runs of the pair; content addressed)
_EXISTING = classify._compare_cached


def _obj_arrays(store, desc):
    d = C.load_blob(store, desc["h"])
    return d


def graded(ra, rb, store, depth=0):
    """Level of two exact records where nested values are graded by the comparator instead of compared by payload:
    each differing aligned nested pair gets its own (recursive) level; if all are levels, the pair is compared again
    with the engine's nested payloads replaced by the reference's (blob written to the store, content addressed),
    and the result is the coarser of that level and the nested levels. Anything else stays DIFF."""
    if ra.get("h") is not None and ra.get("h") == rb.get("h"):
        return "E0"
    if ra.get("kind") in PSEUDO or rb.get("kind") in PSEUDO:
        return "DIFF"
    lv = dfeq.compare(ra, rb, store)["level"]
    if lv != "DIFF" or depth >= 4:
        return lv
    if ra.get("kind") != rb.get("kind"):
        return "DIFF"
    ca = (ra.get("cols") or []) + (ra.get("idx") or [])
    cb = (rb.get("cols") or []) + (rb.get("idx") or [])
    if len(ca) != len(cb):
        return "DIFF"
    child_levels, new_cb, changed = [], [], False
    for x, y in zip(ca, cb):
        if x["h"] == y["h"] or x.get("enc") != "obj" or y.get("enc") != "obj":
            new_cb.append(y)
            continue
        dx, dy = _obj_arrays(store, x), _obj_arrays(store, y)
        tx, px, ty, py_ = dx["t"], dx["p"], dy["t"], np.array(dy["p"], dtype=object)
        if len(tx) != len(ty):
            return "DIFF"
        pos = [k for k in range(len(tx)) if tx[k] == C.T_NESTED and ty[k] == C.T_NESTED and px[k] != py_[k]]
        for k in pos:
            ha, hb = px[k].split("#", 1)[1], py_[k].split("#", 1)[1]
            na, nb_ = NESTED.get(ha), NESTED.get(hb)
            cl = graded(na, nb_, store, depth + 1) if na is not None and nb_ is not None else "DIFF"
            if cl not in ORDER:
                return "DIFF"
            child_levels.append(cl)
            py_[k] = px[k]
        if pos:
            arrays = {"t": dy["t"], "p": py_, "y": np.array(dy["y"], dtype=object)}
            aa, esc = C._to_arrow_arrays(arrays)
            hx = {kk: (vv["h"] if isinstance(vv, dict) and "h" in vv else vv) for kk, vv in (y.get("x") or {}).items()}
            h = C.column_hash("obj", y["dtype"], hx, aa)
            if not os.path.exists(C.blob_path(store, h)):
                C._write_blob(store, h, aa, {"enc": "obj", "dtype": y["dtype"], "x": y.get("x") or {}})
            y = dict(y, h=h, stored=True)
            changed = True
        new_cb.append(y)
    if not changed:
        return "DIFF"
    nc = len(rb.get("cols") or [])
    rb2 = dict(rb, cols=new_cb[:nc], idx=new_cb[nc:])
    rb2["h"] = C.Capturer._finish(None, rb2["kind"], rb2.get("meta"), rb2["cols"], rb2["idx"], rb2.get("info") or {})["h"]
    lv2 = graded(ra, rb2, store, depth + 1) if depth + 1 < 4 else dfeq.compare(ra, rb2, store)["level"]
    if lv2 not in ORDER:
        return "DIFF"
    return max([lv2] + child_levels, key=lambda L: ORDER[L])


_GRADED = {}


def _graded_cached(ra, ea, store):
    res = _EXISTING(ra, ea, store)
    if res.get("level") == "DIFF" and ra.get("h") is not None and ea.get("h") is not None and \
            ((ra.get("info") or {}).get("nested") or (ea.get("info") or {}).get("nested")):
        key = (ra["h"], ea["h"])
        if key not in _GRADED:
            try:
                _GRADED[key] = graded(ra, ea, store)
            except Exception as e:   # recorded, never hidden: the pair stays DIFF
                _GRADED[key] = "DIFF"
                print("graded error %s: %s" % (type(e).__name__, str(e)[:200]), file=sys.stderr)
        if _GRADED[key] != "DIFF":
            res = dict(res, level=_GRADED[key], graded_from="DIFF")
    return res


def derive(rec, variant, last_cell):
    r = dict(rec)
    cells = []
    for c in rec["cells"]:
        if last_cell is not None and c["i"] > last_cell:
            break
        c2 = dict(c)
        if variant == "orig":
            for k in ("inputs", "outputs"):
                alt = c.get(k + "_orig") or {}
                if k in c and alt:
                    d = dict(c[k])
                    d.update(alt)
                    c2[k] = d
        cells.append(c2)
    r["cells"] = cells
    return r


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--deadline-epoch", type=float, default=0, help="start no new job after this time (the rest stays to do)")
    a = ap.parse_args(argv)
    jobs = json.load(open(a.jobs))
    done = 0
    for j in jobs:
        if a.deadline_epoch and time.time() > a.deadline_epoch:
            print("deadline reached; %d jobs left" % (len(jobs) - jobs.index(j)), file=sys.stderr)
            break
        ref = util.read_json(j["ref"])
        eng = util.read_json(j["eng"])
        if ref is None or eng is None:
            print("missing record", j["label"], j["nb"], file=sys.stderr)
            continue
        for variant in ("orig", "exact", "graded"):
            out = os.path.join(a.out_root, variant, j["label"], util.nb_key(j["nb"]) + ".json")
            if os.path.exists(out):
                continue
            t0 = time.time()
            NESTED.clear()
            _GRADED.clear()
            if variant == "graded":
                NESTED.update(ref.get("nested") or {})
                NESTED.update(eng.get("nested") or {})
            # the comparator cache is keyed by (store, object hash, object hash), so results of the unchanged comparator
            # are shared across variants; the graded levels have their own cache (_GRADED, reset per pair)
            classify._compare_cached = _graded_cached if variant == "graded" else _EXISTING
            res = classify.classify_run(derive(ref, "exact" if variant == "graded" else variant, j.get("last_cell")),
                                        derive(eng, "exact" if variant == "graded" else variant, j.get("last_cell")),
                                        j["store"], ref2=None)
            res["meta"] = {"label": j["label"], "nb": j["nb"], "variant": variant, "last_cell": j.get("last_cell"),
                           "ref_record": j["ref"], "eng_record": j["eng"], "ref_status": ref.get("status"),
                           "eng_status": eng.get("status"), "compare_sha": util.compare_sha(),
                           "harness_sha": util.harness_sha(), "seconds": round(time.time() - t0, 3)}
            util.atomic_write_json(out, res)
            done += 1
    print(json.dumps({"jobs": len(jobs), "outputs_written": done}))


if __name__ == "__main__":
    sys.exit(main())

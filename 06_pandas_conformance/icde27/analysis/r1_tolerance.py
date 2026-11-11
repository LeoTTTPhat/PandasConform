#!/usr/bin/env python3
"""Review R1 item B1(iv): sensitivity of the clean@E2 shares to the float tolerance (ICDE 2027 copy; 2026-10-26).

Read-only on results/, data/ and captures/; writes only icde27/analysis/r1_tolerance.json. One object pair is
compared at a time with a 0.2 GB decode cache; objects above MAX_CELLS values are skipped and counted.

    cd ..
    /usr/bin/time -l .venv/bin/python 06_pandas_conformance/icde27/analysis/r1_tolerance.py

The comparator (src/pconf/dfeq.py, unchanged) is imported and only its float relation is replaced in this process:
_float_close and _tag_elem_equal get a relative tolerance rtol and an absolute tolerance atol. Settings: exact
(0, 0), 1e-12, the paper's 1e-9 (baseline; it must reproduce every stored level, otherwise the script stops),
1e-6, and pandas' assert_frame_equal default (rtol 1e-5, atol 1e-8).
Population: the cells of the clean@E2 view (as in analyze.py) of the five conf_1x engines and both drift pandas
versions whose class is E2, E3, E4 or DIFF. Re-compared outputs: those whose stored result used the tolerance
(float_err with a positive relative error) and those whose first failing check at E2 or E4 is a value check (a
looser tolerance might pass them). Every other output keeps its stored level, and the cell class is the coarsest
level over its outputs, as in classify.compare_outputs. The clean-level population is held fixed (the inputs are
not re-compared), so this is a first-order sensitivity of the outputs, not a re-run of the attribution.
"""
import collections
import importlib.util
import json
import math
import os
import sys
import time

os.environ["PCONF_DECODE_CACHE_GB"] = "0.2"
HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(PROJ, "src"))
from pconf import capture as C  # noqa: E402
from pconf import dfeq as D  # noqa: E402
from pconf import util  # noqa: E402

import numpy as np  # noqa: E402

OUT = os.path.join(HERE, "r1_tolerance.json")
LABELS = [("conf_1x", e) for e in ("pyarrow_backend", "modin", "fireducks", "bodo", "dask")] + [("drift", "p15"), ("drift", "p30")]
SETTINGS = [("exact", 0.0, 0.0), ("rtol_1e-12", 1e-12, 0.0), ("rtol_1e-9_paper", 1e-9, 0.0), ("rtol_1e-6", 1e-6, 0.0),
            ("assert_frame_equal_default", 1e-5, 1e-8)]
MAX_CELLS = 5_000_000
EXCLUDED = ("REF_ERR", "NONDET", "NOOUT", "SETUP_ERR")
ORDER = {"E0": 0, "E1": 1, "E2": 2, "E3": 3, "E4": 4, "DIFF": 5, "UNCOMPARABLE": 5, "ERR": 6}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def set_tolerance(rtol, atol):
    D.FLOAT_RTOL = rtol

    def _float_close(a, b):
        a = np.asarray(a, dtype=np.float64)
        b = np.asarray(b, dtype=np.float64)
        with np.errstate(invalid="ignore", over="ignore"):
            eq = a == b
            close = np.abs(a - b) <= atol + rtol * np.maximum(np.abs(a), np.abs(b))
        return eq | (close & np.isfinite(a) & np.isfinite(b))

    def _tag_elem_equal(ta, pa_, tb, pb_):
        if ta in (C.T_INT, C.T_FLOAT) and tb in (C.T_INT, C.T_FLOAT):
            if ta == C.T_INT and tb == C.T_INT:
                return int(pa_) == int(pb_)
            try:
                if ta == C.T_INT and abs(int(pa_)) > D.MAX_EXACT_INT:
                    return False
                if tb == C.T_INT and abs(int(pb_)) > D.MAX_EXACT_INT:
                    return False
                x, y = float(pa_), float(pb_)
            except ValueError:
                return False
            return x == y or math.isclose(x, y, rel_tol=rtol, abs_tol=atol)
        if ta == C.T_COMPLEX and tb == C.T_COMPLEX:
            x, y = complex(pa_), complex(pb_)
            return (math.isclose(x.real, y.real, rel_tol=rtol, abs_tol=atol)
                    and math.isclose(x.imag, y.imag, rel_tol=rtol, abs_tol=atol))
        return ta == tb and pa_ == pb_

    D._float_close = _float_close
    D._tag_elem_equal = _tag_elem_equal


def ncells(rec):
    sh = (rec.get("meta") or {}).get("shape") or [1]
    n = 1
    for x in sh:
        n *= max(int(x or 0), 1)
    return n


def candidate(o):
    lv = o.get("level")
    fe = o.get("float_err") or {}
    if lv in ("E2", "E3", "E4") and any((v or {}).get("max_rel_err", 0) > 0 for v in fe.values()):
        return True
    f = o.get("fails") or {}
    if lv in ("E3", "E4", "DIFF") and any(str(f.get(L, "")).startswith(("values", "scalar_value")) for L in ("E2", "E4")):
        return True
    return False


def main():
    t0 = time.time()
    T = load_module("rootcause_taxonomy", os.path.join(PROJ, "scripts", "rootcause_taxonomy.py"))
    rec_cache = {}

    def rec(path):
        if path not in rec_cache:
            if len(rec_cache) > 8:
                rec_cache.clear()
            rec_cache[path] = json.load(open(os.path.join(PROJ, path)))
        return rec_cache[path]

    res, mismatch, skipped, compared = {}, [], collections.Counter(), collections.Counter()
    moved = collections.defaultdict(collections.Counter)
    for campaign, label in LABELS:
        root, best = T.select_outputs(campaign, T.COMPARE)
        per_setting = {s[0]: collections.Counter() for s in SETTINGS}
        stored = collections.Counter()
        for (lab, nb, sc), (_, r, p) in sorted(best.items()):
            if lab != label:
                continue
            cl = r["cells"]
            t_idx = next((k for k, c in enumerate(cl) if c.get("cls") == "TIMEOUT" or c.get("cls_raw") == "TIMEOUT"), None)
            for k, c in enumerate(cl):
                if c["cls"] in EXCLUDED or (t_idx is not None and k > t_idx) or c.get("clean_level") not in ("E0", "E1", "E2"):
                    continue
                stored[c["cls"]] += 1
                outs = c.get("outputs") or {}
                cands = [n for n, o in outs.items() if c["cls"] in ("E2", "E3", "E4", "DIFF") and candidate(o)]
                if not cands:
                    for s in SETTINGS:
                        per_setting[s[0]][c["cls"]] += 1
                    continue
                ref, eng = rec(r["meta"]["ref_record"]), rec(r["meta"]["eng_record"])
                rc = {x.get("i"): x for x in ref["cells"]}.get(c["i"], {})
                ec = {x.get("i"): x for x in eng["cells"]}.get(c["i"], {})
                levels = {s[0]: {} for s in SETTINGS}
                ok = True
                for n in cands:
                    try:
                        ra, ea = ref["objects"][rc["outputs"][n]], eng["objects"][ec["outputs"][n]]
                    except (KeyError, TypeError):
                        ok = False
                        break
                    if max(ncells(ra), ncells(ea)) > MAX_CELLS:
                        ok = False
                        break
                    for name, rtol, atol in SETTINGS:
                        set_tolerance(rtol, atol)
                        lv = D.compare(ra, ea, util.CAPTURES)["level"]
                        levels[name][n] = lv
                    if levels["rtol_1e-9_paper"][n] != outs[n].get("level"):
                        mismatch.append([label, nb, c["i"], n, outs[n].get("level"), levels["rtol_1e-9_paper"][n]])
                    compared[label] += 1
                D._DECODE_CACHE.clear()
                D._DECODE_CACHE_BYTES[0] = 0
                if not ok:
                    skipped[label] += 1
                    for s in SETTINGS:
                        per_setting[s[0]][c["cls"]] += 1
                    continue
                for name, _, _ in SETTINGS:
                    lv_all = [levels[name].get(n, o.get("level")) for n, o in outs.items()]
                    lv_all = [x for x in lv_all if x in ORDER]
                    cls = max(lv_all, key=lambda x: ORDER[x]) if lv_all else c["cls"]
                    if c["cls"] == "ERR":
                        cls = "ERR"
                    per_setting[name][cls] += 1
                    if cls != c["cls"]:
                        moved[label]["%s:%s->%s" % (name, c["cls"], cls)] += 1
        n = sum(stored.values())
        res[label] = {"clean_E2_cells": n, "stored": dict(stored), "by_setting": {}}
        for name, _, _ in SETTINGS:
            cnt = per_setting[name]
            res[label]["by_setting"][name] = {
                "le_E2_pct": round(100 * sum(cnt[x] for x in ("E0", "E1", "E2")) / n, 3),
                "DIFF_pct": round(100 * cnt["DIFF"] / n, 3), "counts": dict(cnt)}
        res[label]["cells_moved"] = dict(moved[label])
        print(label, json.dumps({k: (v["le_E2_pct"], v["DIFF_pct"]) for k, v in res[label]["by_setting"].items()}),
              "compared outputs", compared[label], "skipped cells", skipped[label], flush=True)
    out = {"settings": [{"name": a, "rtol": b, "atol": c} for a, b, c in SETTINGS], "max_cells": MAX_CELLS,
           "baseline_mismatches": mismatch, "compared_outputs": dict(compared), "skipped_cells": dict(skipped),
           "by_label": res, "runtime_s": round(time.time() - t0, 1)}
    with open(OUT + ".tmp", "w") as f:
        json.dump(out, f, indent=1)
    os.replace(OUT + ".tmp", OUT)
    if mismatch:
        print("BASELINE MISMATCHES:", len(mismatch), mismatch[:5])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

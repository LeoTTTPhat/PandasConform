#!/usr/bin/env python3
"""C1 planning census: printed forms in cell OUTPUTS and INPUTS, per configuration (review round R5, agent B1).

Read-only on results/{conf_1x,drift}/raw and captures/cols; writes only icde27/analysis/r5_capture/c1_plan.json.

    cd ..
    .venv/bin/python 06_pandas_conformance-ICDE/icde27/analysis/r5_capture/c1_plan.py

Per scored cell of the seven configurations (r1_cells.py population) it records whether an output holds a printed
element (pf_out, the r4_printed_forms.py definition: tag T_CONTAINER or T_OTHER on either side) and which inputs
hold one (pf_in: the cell reads a value whose captured pre-cell record, on the reference or the configuration's side,
holds such an element; for the notebooks without input capture, the last captured value of the name). A cell whose
class or clean level can change under an exact encoding is pf_out or pf_in; every other cell keeps its class and clean
level when the run is repeated identically. For each configuration and notebook the script also sums the recorded
per-cell time (execution plus capture) up to the last such cell, to plan re-execution.
"""
import collections
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.dirname(HERE)
PROJ = os.path.dirname(os.path.dirname(ANALYSIS))
OUT = os.path.join(HERE, "c1_plan.json")
sys.path.insert(0, os.path.join(PROJ, "src"))
from pconf import capture, util  # noqa: E402

T_CONTAINER, T_OTHER = capture.T_CONTAINER, capture.T_OTHER
EXCLUDED = ("REF_ERR", "NONDET", "NOOUT", "SETUP_ERR")
LABELS = [("conf_1x", e) for e in ("pyarrow_backend", "modin", "fireducks", "bodo", "dask")] + [("drift", "p15"), ("drift", "p30")]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    import pyarrow as pa
    T = load_module("rootcause_taxonomy", os.path.join(PROJ, "scripts", "rootcause_taxonomy.py"))
    store = util.CAPTURES
    tag_cache = {}

    def col_pf(c):
        if c.get("enc") == "obj":
            h = c["h"]
            if h not in tag_cache:
                path = capture.blob_path(store, h)
                if not os.path.exists(path):
                    tag_cache[h] = False
                else:
                    with pa.memory_map(path, "r") as src:
                        t = pa.ipc.open_file(src).read_all().column("t").to_numpy()
                    tag_cache[h] = bool(set(t.tolist()) & {T_CONTAINER, T_OTHER})
            if tag_cache[h]:
                return True
        return any(col_pf(v) for v in (c.get("x") or {}).values() if isinstance(v, dict) and "enc" in v)

    def rec_pf(rec):
        if not isinstance(rec, dict):
            return False
        if rec.get("kind") == "scalar":
            return (rec.get("meta") or {}).get("value", [None])[0] in (T_CONTAINER, T_OTHER)
        return any(col_pf(c) for c in (rec.get("cols") or []) + (rec.get("idx") or []))

    rec_cache = {}

    def run_rec(path):
        if path not in rec_cache:
            if len(rec_cache) > 6:
                rec_cache.clear()
            rec_cache[path] = json.load(open(os.path.join(PROJ, path)))
        return rec_cache[path]

    def resolve(rec, v):
        return rec["objects"].get(v) if isinstance(v, str) else v

    res = {"by_label": {}}
    for campaign, label in LABELS:
        root, best = T.select_outputs(campaign, T.COMPARE)
        L = res["by_label"].setdefault(label, {"campaign": campaign, "notebooks": {}})
        for (lab, nb, sc), (_, r, p) in sorted(best.items()):
            if lab != label:
                continue
            m = r["meta"]
            eng, ref = run_rec(m["eng_record"]), run_rec(m["ref_record"])
            ecells = {c["i"]: c for c in eng["cells"]}
            rcells = {c["i"]: c for c in ref["cells"]}
            # last captured value per name (for inputs of runs without input capture)
            last_e, last_r = {}, {}
            t_idx = next((k for k, c in enumerate(r["cells"]) if c.get("cls") == "TIMEOUT" or c.get("cls_raw") == "TIMEOUT"), None)
            cum_e = cum_r = 0.0
            cells = []
            for k, c in enumerate(r["cells"]):
                i = c["i"]
                ce, cr = ecells.get(i, {}), rcells.get(i, {})
                cum_e += sum(float(ce.get(x) or 0) for x in ("wall_s", "t_capture_in", "t_capture_out"))
                cum_r += sum(float(cr.get(x) or 0) for x in ("wall_s", "t_capture_in", "t_capture_out"))
                pf_out = sorted(n for n in (c.get("outputs") or {})
                                if rec_pf(resolve(eng, (ce.get("outputs") or {}).get(n))) or rec_pf(resolve(ref, (cr.get("outputs") or {}).get(n))))
                names_in = set((c.get("input_levels") or {}).keys()) | set((ce.get("inputs") or {}).keys()) | set((cr.get("inputs") or {}).keys())
                if c.get("inputs_from") == "last_captured" or not (ce.get("inputs") or cr.get("inputs")):
                    names_in |= set(((ce.get("static") or {}).get("loads") or []))
                pf_in = []
                for n in sorted(names_in):
                    ve = (ce.get("inputs") or {}).get(n, last_e.get(n))
                    vr = (cr.get("inputs") or {}).get(n, last_r.get(n))
                    if rec_pf(resolve(eng, ve)) or rec_pf(resolve(ref, vr)):
                        pf_in.append(n)
                for src_c, last in ((ce, last_e), (cr, last_r)):
                    for kk in ("inputs", "outputs"):
                        for n, v in (src_c.get(kk) or {}).items():
                            if n != "__last__" and v not in ("absent",):
                                last[n] = v
                if c["cls"] in EXCLUDED:
                    continue
                post = t_idx is not None and k > t_idx
                in_ce2 = c.get("clean_level") in ("E0", "E1", "E2") and not post
                if pf_out or pf_in:
                    cells.append({"i": i, "k": k, "cls": c["cls"], "clean_level": c.get("clean_level"), "post_timeout": post,
                                  "in_clean_E2": in_ce2, "pf_out": pf_out, "pf_in": pf_in,
                                  "input_levels": {n: c.get("input_levels", {}).get(n) for n in pf_in},
                                  "cum_eng_s": round(cum_e, 2), "cum_ref_s": round(cum_r, 2)})
            if cells:
                L["notebooks"][nb] = {"ref_record": m["ref_record"], "eng_record": m["eng_record"],
                                      "eng_status": eng.get("status"), "ref_setup_s": ref.get("engine_setup_s"),
                                      "eng_setup_s": eng.get("engine_setup_s"),
                                      "eng_wall_s": eng.get("orchestrator_wall_s"), "ref_wall_s": ref.get("orchestrator_wall_s"),
                                      "capture_inputs": (eng.get("cfg") or {}).get("capture_inputs"), "n_cells": len(r["cells"]),
                                      "cells": cells}
    roll = {}
    for label, L in res["by_label"].items():
        cnt = collections.Counter()
        for nb, N in L["notebooks"].items():
            for c in N["cells"]:
                cnt["cells"] += 1
                cnt["pf_out"] += bool(c["pf_out"])
                cnt["pf_in_only"] += bool(c["pf_in"]) and not c["pf_out"]
                cnt["in_clean_E2"] += c["in_clean_E2"]
                cnt["pf_in_only_clean_E2"] += bool(c["pf_in"]) and not c["pf_out"] and c["in_clean_E2"]
        roll[label] = {"notebooks": len(L["notebooks"]), **dict(cnt),
                       "eng_s_to_last": round(sum(N["cells"][-1]["cum_eng_s"] for N in L["notebooks"].values()), 1),
                       "ref_s_to_last": round(sum(N["cells"][-1]["cum_ref_s"] for N in L["notebooks"].values()), 1)}
    res["rollup"] = roll
    with open(OUT + ".tmp", "w") as f:
        json.dump(res, f, indent=1, sort_keys=True)
    os.replace(OUT + ".tmp", OUT)
    for label, v in roll.items():
        print(label, json.dumps(v, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main())

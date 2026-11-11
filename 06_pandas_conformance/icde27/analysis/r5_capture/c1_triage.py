#!/usr/bin/env python3
"""C1 triage of the printed-form outputs (review round R5, agent B1; written 2026-11-10).

Read-only on results/{conf_1x,drift}/raw, captures/cols and icde27/analysis/r4_printed_forms.json; writes only
icde27/analysis/r5_capture/c1_triage.json. Memory below 2 GB.

    cd ..
    .venv/bin/python 06_pandas_conformance-ICDE/icde27/analysis/r5_capture/c1_triage.py

For every output that r4_printed_forms.py flags (an element tagged T_CONTAINER or T_OTHER on the reference or the
configuration's side), this script reads the printed elements themselves (tag, payload, type name) and sorts them:
  container_exact   T_CONTAINER whose printed form holds only exactly tagged scalars (no nested T_OTHER element,
                    no depth cut '...'): the text is an exact encoding up to delimiter collisions;
  pandas_numpy      T_OTHER (or a T_OTHER inside a container) whose type is a pandas or NumPy object or an engine
                    frame (DataFrame, Series, Index, ndarray, ...): an exact recursive encoding exists;
  other_object      any other T_OTHER element (methods, functions, estimators, plot objects, ...).
It also lists, per configuration and notebook, the printed-form cells, whether they are in the clean@E2 view, and
the wall time of the original reference and configuration runs, to plan the re-execution.
"""
import collections
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.dirname(HERE)
PROJ = os.path.dirname(os.path.dirname(ANALYSIS))
OUT = os.path.join(HERE, "c1_triage.json")
sys.path.insert(0, os.path.join(PROJ, "src"))
from pconf import capture, util  # noqa: E402

T_CONTAINER, T_OTHER = capture.T_CONTAINER, capture.T_OTHER
PANDAS_NUMPY = re.compile(r"^(pandas|numpy|modin|fireducks|bodo|dask)\.")
NESTED_OTHER = re.compile(r"(?:^|[\[\(\{,:])16:([A-Za-z_][\w\.]*):")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    import pyarrow as pa
    T = load_module("rootcause_taxonomy", os.path.join(PROJ, "scripts", "rootcause_taxonomy.py"))
    census = json.load(open(os.path.join(ANALYSIS, "r4_printed_forms.json")))
    store = util.CAPTURES
    blob_cache = {}

    def printed_elems(h):
        """obj blob -> list of (tag, type name, category, payload length) of its printed elements."""
        if h in blob_cache:
            return blob_cache[h]
        path = capture.blob_path(store, h)
        if not os.path.exists(path):
            blob_cache[h] = None
            return None
        with pa.memory_map(path, "r") as src:
            tb = pa.ipc.open_file(src).read_all()
        t = tb.column("t").to_numpy()
        sel = [i for i, x in enumerate(t.tolist()) if x in (T_CONTAINER, T_OTHER)]
        out = []
        if sel:
            p = tb.column("p").take(pa.array(sel)).to_pylist()
            y = tb.column("y").take(pa.array(sel)).to_pylist()
            for k, i in enumerate(sel):
                tag = int(t[i])
                pay = p[k] or ""
                if tag == T_CONTAINER:
                    inner = NESTED_OTHER.findall(pay)
                    if inner:
                        cat = "pandas_numpy" if all(PANDAS_NUMPY.match(x) for x in inner) else "other_object"
                        tn = y[k] + "<" + ",".join(sorted(set(inner))) + ">"
                    elif "..." in pay and re.search(r"(?:^|[\[\(\{,:])\.\.\.(?:$|[\]\)\},])", pay):
                        cat, tn = "other_object", y[k] + "<depth cut>"
                    else:
                        cat, tn = "container_exact", y[k]
                else:
                    tn = y[k]
                    cat = "pandas_numpy" if PANDAS_NUMPY.match(tn or "") and not tn.startswith(("numpy.dtype", "numpy.dtypes")) \
                        else "other_object"
                out.append((tag, tn, cat, len(pay)))
        blob_cache[h] = out
        return out

    def col_elems(c):
        found = []
        if c.get("enc") == "obj":
            e = printed_elems(c["h"])
            if e:
                found += e
        for v in (c.get("x") or {}).values():
            if isinstance(v, dict) and "enc" in v:
                found += col_elems(v)
        return found

    def rec_elems(rec):
        if not rec:
            return []
        found = []
        for c in (rec.get("cols") or []) + (rec.get("idx") or []):
            found += col_elems(c)
        if rec.get("kind") == "scalar":
            t, p, y = (rec.get("meta") or {}).get("value", [None, "", ""])
            if t in (T_CONTAINER, T_OTHER):
                found.append((t, y, "scalar_printed", len(p or "")))
        return found

    run_cache = {}

    def run_rec(path):
        if path not in run_cache:
            if len(run_cache) > 4:
                run_cache.clear()
            run_cache[path] = json.load(open(os.path.join(PROJ, path)))
        return run_cache[path]

    def outputs_of(rec):
        objs = rec.get("objects") or {}
        return {c["i"]: {n: (objs.get(h) if isinstance(h, str) else h) for n, h in (c.get("outputs") or {}).items()}
                for c in rec["cells"]}

    res = {"by_label": {}}
    tot_cat = collections.Counter()
    tot_type = collections.Counter()
    for campaign, label in [("conf_1x", e) for e in ("pyarrow_backend", "modin", "fireducks", "bodo", "dask")] + \
            [("drift", "p15"), ("drift", "p30")]:
        root, best = T.select_outputs(campaign, T.COMPARE)
        want = collections.defaultdict(set)
        for lab, nb, i, cls in census["by_label"][label]["cells"]:
            want[nb].add(i)
        L = res["by_label"].setdefault(label, {"campaign": campaign, "notebooks": {}})
        for (lab, nb, sc), (_, r, p) in sorted(best.items()):
            if lab != label or nb not in want:
                continue
            m = r["meta"]
            eng_rec, ref_rec = run_rec(m["eng_record"]), run_rec(m["ref_record"])
            eng_o, ref_o = outputs_of(eng_rec), outputs_of(ref_rec)
            t_idx = next((k for k, c in enumerate(r["cells"]) if c.get("cls") == "TIMEOUT" or c.get("cls_raw") == "TIMEOUT"), None)
            cells = []
            for k, c in enumerate(r["cells"]):
                if c["i"] not in want[nb]:
                    continue
                in_ce2 = c.get("clean_level") in ("E0", "E1", "E2") and not (t_idx is not None and k > t_idx)
                outs = []
                for name, o in (c.get("outputs") or {}).items():
                    ee = rec_elems(eng_o.get(c["i"], {}).get(name))
                    er = rec_elems(ref_o.get(c["i"], {}).get(name))
                    if not ee and not er:
                        continue
                    cats = sorted({x[2] for x in ee + er})
                    types = sorted({x[1] for x in ee + er})
                    for x in cats:
                        tot_cat[x] += 1
                    for x in types:
                        tot_type[x] += 1
                    outs.append({"name": name, "level": o.get("level"), "categories": cats, "types": types,
                                 "n_printed_ref": len(er), "n_printed_eng": len(ee),
                                 "max_payload": max([x[3] for x in ee + er] or [0])})
                cells.append({"i": c["i"], "cls": c["cls"], "clean_level": c.get("clean_level"), "in_clean_E2": in_ce2,
                              "outputs": outs})
            L["notebooks"][nb] = {"ref_record": m["ref_record"], "eng_record": m["eng_record"],
                                  "ref_wall_s": ref_rec.get("orchestrator_wall_s"), "eng_wall_s": eng_rec.get("orchestrator_wall_s"),
                                  "eng_status": eng_rec.get("status"), "n_cells_nb": len(r["cells"]),
                                  "capture_inputs": (eng_rec.get("cfg") or {}).get("capture_inputs"), "cells": cells}
    # roll-up
    roll = {}
    for label, L in res["by_label"].items():
        cnt = collections.Counter()
        for nb, N in L["notebooks"].items():
            for c in N["cells"]:
                cats = {x for o in c["outputs"] for x in o["categories"]}
                eq = c["cls"] in ("E0", "E1", "E2", "E3", "E4")
                key = ("equal" if eq else c["cls"]) + "|" + ("+".join(sorted(cats)) or "none")
                cnt[key] += 1
                cnt["cells"] += 1
                cnt["clean_E2_cells"] += c["in_clean_E2"]
        roll[label] = {"notebooks": len(L["notebooks"]), "ref_wall_s": round(sum(N["ref_wall_s"] or 0 for N in L["notebooks"].values()), 1),
                       "eng_wall_s": round(sum(N["eng_wall_s"] or 0 for N in L["notebooks"].values()), 1), **dict(cnt)}
    res["rollup"] = roll
    res["category_counts_outputs"] = dict(tot_cat)
    res["type_counts_outputs"] = dict(tot_type.most_common())
    with open(OUT + ".tmp", "w") as f:
        json.dump(res, f, indent=1, sort_keys=True)
    os.replace(OUT + ".tmp", OUT)
    for label, v in roll.items():
        print(label, json.dumps(v, sort_keys=True))
    print("categories", dict(tot_cat))
    print("types", tot_type.most_common(40))


if __name__ == "__main__":
    sys.exit(main())

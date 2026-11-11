#!/usr/bin/env python3
"""Printed-form uncertainty with dependent readers: exclusion view and bounds (review round R5; ICDE 2027 copy;
written 2026-11-10).

Read-only on results/{conf_1x,drift}/raw (compare outputs and run records), captures/cols (only the element-tag
column of object-encoded blobs, as r4_printed_forms.py), results/rootcause/*.json and
icde27/analysis/{r1_cells,r3_sensitivity,r4_audit,r4_printed_forms,r1_hand_attribution}.json; writes only
icde27/analysis/r5_uncertainty.json and r5_printed_flags.csv. Memory below 2 GB.

    cd ..
    /usr/bin/time -l .venv/bin/python 06_pandas_conformance-ICDE/icde27/analysis/r5_uncertainty.py

Why. src/pconf/capture.py encodes nested containers (a list, tuple, dict or set inside a value, including a frame
inside a list or dict) and objects without an exact encoding by their printed form (element tags T_CONTAINER and
T_OTHER), and the comparator compares those payloads as text. Such an object is "uncertain": equal text can hide
what the text does not print (for example omitted rows of a frame), and different text can come from
representation alone (the 16 known artifact cells). The uncertainty enters twice: in the class of the cell that
outputs the object, and in the clean level of every cell that reads it as an input (its "dependent readers"), which
decides the clean@E2 population and whether a cell is introduced. A reader's own outputs are compared exactly (or
are uncertain themselves), so the uncertainty does not pass further down the notebook.

Per comparison (configuration against its reference, for the 7 configurations on 102 notebooks) and cell, the
script mirrors src/pconf/classify.py classify_run to find the entries that were compared: the outputs, and the
inputs (pre-cell captures, or for the 10 notebooks without input capture the last captured values of the names the
cell loads, plus globals read by called user functions). An entry is uncertain if its object record on the
reference side or the configuration's side holds a T_CONTAINER or T_OTHER element (in a column, the index, a
sub-column, or a scalar). Flags per cell: out_match (an uncertain output reached a level E0-E4), out_diff (an
uncertain output is DIFF), in_match (an uncertain input agreed at E0-E4), in_diff (an uncertain input differed).

Views (pure introduced definition = exception off, r4_audit.py; NONDET, REF_ERR, NOOUT and SETUP_ERR excluded as in
the paper):
  base       as published (raw);
  certain    every cell with an uncertain output or input (either flag, either side) removed, in every view and,
             for paired contrasts, if it is uncertain in either of the two comparisons;
  certain_kind  as certain, but a DIFF cell is kept when its engine side holds an object of the engine's own package
             where the reference holds a value (for example an unevaluated Dask scalar): such outputs differ in kind
             whatever the printed text shows (no matching uncertain input either);
  bounds     matching printed forms treated as uncertain (they may hide a difference; differing ones stay as
             observed): outer bounds of each clean@E2 DIFF share and each paired difference over every resolution
             (a cell with out_match may be DIFF; a cell with in_match may be unclean, i.e. leave clean@E2), and of the
             notebooks with an introduced DIFF. The lower end of a share is reached by removing DIFF readers, the
             upper end by turning every out_match cell DIFF and removing non-DIFF readers; for paired differences the
             same per side (the outer bound ignores that one hidden difference does both, so it is conservative).
Consistency checks: the output flags reproduce r4_printed_forms.json (cells, equal cells, clean@E2 cells); the base
view reproduces summary.json, r1_cells.json pairwise contrasts and r4_audit.json exception-off notebook counts.
"""
import collections
import csv
import importlib.util
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "r5_uncertainty.json")
OUT_CSV = os.path.join(HERE, "r5_printed_flags.csv")
sys.path.insert(0, os.path.join(PROJ, "src"))
from pconf import capture, classify, util  # noqa: E402

T_CONTAINER, T_OTHER = capture.T_CONTAINER, capture.T_OTHER
LEVELS = ("E0", "E1", "E2", "E3", "E4")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R1 = load_module("r1_cells", os.path.join(HERE, "r1_cells.py"))
N_BOOT, SEED = R1.N_BOOT, R1.SEED
ENGINES, PANDAS, LABELS = R1.ENGINES, R1.PANDAS, R1.LABELS
EXCLUDED = R1.EXCLUDED
boot_share, stable_key = R1.boot_share, R1.stable_key


def main():
    import pyarrow as pa
    T = load_module("rootcause_taxonomy", os.path.join(PROJ, "scripts", "rootcause_taxonomy.py"))
    summary = json.load(open(os.path.join(PROJ, "results", "summary.json")))
    r1 = json.load(open(os.path.join(HERE, "r1_cells.json")))
    r4 = json.load(open(os.path.join(HERE, "r4_audit.json")))
    pfm = json.load(open(os.path.join(HERE, "r4_printed_forms.json")))
    hand = json.load(open(os.path.join(HERE, "r1_hand_attribution.json")))
    printed16 = {(r["label"], r["nb"], r["cell"]) for r in hand["rows"] if r["cause"] == "printed_form_comparison"}
    store = util.CAPTURES
    if not os.path.isdir(os.path.join(store, "cols")):
        raise SystemExit("no capture store at %s: this analysis reads the element tags of the captured blobs, which "
                         "the artifact does not redistribute (they hold values of the Kaggle inputs)" % store)

    tag_cache, type_cache, missing = {}, {}, []

    def col_flags(c):
        found = False
        if c.get("enc") == "obj":
            h = c["h"]
            if h not in tag_cache:
                path = capture.blob_path(store, h)
                if not c.get("stored", True) or not os.path.exists(path):
                    tag_cache[h] = False
                    missing.append(h)
                else:
                    with pa.memory_map(path, "r") as src:
                        tb = pa.ipc.open_file(src).read_all()
                    t = tb.column("t").to_numpy()
                    tag_cache[h] = bool(set(t.tolist()) & {T_CONTAINER, T_OTHER})
                    if tag_cache[h]:   # python type names of the printed elements (no values)
                        y = tb.column("y").to_pylist()
                        type_cache[h] = sorted({y[k] for k in range(len(y)) if int(t[k]) in (T_CONTAINER, T_OTHER)})
            found = found or tag_cache[h]
        for v in (c.get("x") or {}).values():
            if isinstance(v, dict) and "enc" in v:
                found = found or col_flags(v)
        return found

    def rec_types(rec):
        """python type names of the printed elements of an object record"""
        out = set()

        def walk(c):
            if c.get("enc") == "obj" and c.get("h") in type_cache:
                out.update(type_cache[c["h"]])
            for v in (c.get("x") or {}).values():
                if isinstance(v, dict) and "enc" in v:
                    walk(v)
        if isinstance(rec, dict):
            for c in (rec.get("cols") or []) + (rec.get("idx") or []):
                walk(c)
        return sorted(out)

    def rec_pf(rec):
        """object record (dict) -> holds a printed element"""
        if not isinstance(rec, dict):
            return False
        for c in (rec.get("cols") or []) + (rec.get("idx") or []):
            if col_flags(c):
                return True
        if rec.get("kind") == "scalar":
            t = (rec.get("meta") or {}).get("value", [None])[0]
            if t in (T_CONTAINER, T_OTHER):
                return True
        return False

    def resolve(run, v):
        if isinstance(v, str) and v in run["objects"]:
            return run["objects"][v]
        return v

    run_cache = {}

    def load_run(path):
        if path not in run_cache:
            if len(run_cache) > 8:
                run_cache.clear()
            run_cache[path] = json.load(open(os.path.join(PROJ, path)))
        return run_cache[path]

    def entries(ref, eng):
        """Mirror of classify.classify_run: cell i -> (outputs [(name, ref_entry, eng_entry)],
        inputs [(name, ref_entry, eng_entry)]) for the cells that were compared."""
        res = {}
        eng_cells = {c["i"]: c for c in eng.get("cells", [])}
        last_ref, last_eng, fn_defs = {}, {}, {}
        died = eng.get("status") != "completed"
        died_at = None
        for cr in ref.get("cells", []):
            i = cr["i"]
            ce = eng_cells.get(i)
            static = cr.get("static") or {}
            if cr["status"] in ("setup", "skipped", "empty", "setup_error"):
                classify._update_last(last_ref, cr)
                if ce is not None:
                    classify._update_last(last_eng, ce)
                continue
            if cr["status"] not in ("error", "timeout", "syntax_error"):
                hidden = classify._hidden_globals(static, fn_defs)
                hid = [(g, last_ref.get(g), last_eng.get(g)) for g in hidden if g in last_ref or g in last_eng]
                outs, ins = [], []
                if ce is None:
                    if died and died_at is None:
                        died_at = i
                        if cr.get("inputs") is None:
                            ins = [(n, last_ref.get(n), last_eng.get(n)) for n in (static.get("loads") or [])
                                   if n in last_ref or n in last_eng]
                        else:
                            ins = [(n, v, last_eng.get(n)) for n, v in sorted((cr.get("inputs") or {}).items())]
                else:
                    if cr.get("inputs") is None and ce.get("inputs") is None:
                        ins = [(n, last_ref.get(n), last_eng.get(n)) for n in (static.get("loads") or [])
                               if n in last_ref or n in last_eng]
                    else:
                        ri, ei = cr.get("inputs") or {}, ce.get("inputs") or {}
                        ins = [(n, ri.get(n), ei.get(n)) for n in sorted(set(ri) | set(ei))]
                    if ce["status"] not in ("timeout", "error", "syntax_error"):
                        ro, eo = cr.get("outputs") or {}, ce.get("outputs") or {}
                        outs = [(n, ro[n], eo.get(n)) for n in sorted(ro)]
                res[i] = (outs, ins + hid)
            elif ce is None and died and died_at is None:
                died_at = i
            for n, d in (static.get("fn_globals") or {}).items():
                fn_defs[n] = list(d)
            classify._update_last(last_ref, cr)
            if ce is not None:
                classify._update_last(last_eng, ce)
        return res

    # --- cells with kinds (as r4_audit.py) and printed-form flags ---------------------------------------------------
    cells, meta = {}, {}
    for campaign in ("conf_1x", "drift"):
        root, best = T.select_outputs(campaign, T.COMPARE)
        for (label, nb, sc), (_, r, p) in sorted(best.items()):
            if (campaign, label) not in LABELS:
                continue
            m = r["meta"]
            meta[(campaign, label, nb)] = m
            ref, eng = load_run(m["ref_record"]), load_run(m["eng_record"])
            ent = entries(ref, eng)
            cl = r["cells"]
            t_idx = next((k for k, c in enumerate(cl) if c.get("cls") == "TIMEOUT" or c.get("cls_raw") == "TIMEOUT"), None)
            for k, c in enumerate(cl):
                d = {"nb": nb, "i": c["i"], "cls": c["cls"], "clean": c.get("clean_level"),
                     "post_timeout": t_idx is not None and k > t_idx, "kind": None, "cause": None,
                     "out_match": False, "out_diff": False, "in_match": False, "in_diff": False,
                     "pf_outputs": [], "pf_inputs": []}
                if c["cls"] not in ("E0", "NOOUT", "REF_ERR", "NONDET"):
                    n = T.normalise_cell(campaign, label, nb, c)
                    n["code"] = T.cell_code(nb, c["i"])
                    d["cause"], d["kind"], _ = T.classify_cell(n)
                outs_cmp = c.get("outputs") or {}
                in_lv = c.get("input_levels") or {}
                o_ent, i_ent = ent.get(c["i"], ([], []))
                for name, rv, ev in o_ent:
                    if name not in outs_cmp:
                        continue   # not compared (modules, callables, uncapturable on both sides, absent)
                    if rec_pf(resolve(ref, rv)) or rec_pf(resolve(eng, ev)):
                        lv = outs_cmp[name].get("level")
                        d["pf_outputs"].append([name, lv])
                        d.setdefault("pf_types", []).append([rec_types(resolve(ref, rv)), rec_types(resolve(eng, ev))])
                        if lv in LEVELS:
                            d["out_match"] = True
                        else:
                            d["out_diff"] = True
                for name, rv, ev in i_ent:
                    if rec_pf(resolve(ref, rv)) or rec_pf(resolve(eng, ev)):
                        lv = in_lv.get(name, "E0")   # classify records only inputs that are not E0-equal
                        d["pf_inputs"].append([name, lv])
                        if lv in LEVELS:
                            d["in_match"] = True
                        else:
                            d["in_diff"] = True
                cells.setdefault((campaign, label), []).append(d)
    missing_labels = [lab for lab in LABELS if lab not in cells]
    if missing_labels:
        raise SystemExit("no per-cell compare outputs for %s (unpack the results first)" % missing_labels)

    def exc(c):
        return c["cause"] == "order_propagated"

    def kind_pure(c):
        return "introduced" if exc(c) else c["kind"]

    def unc(c):
        return c["out_match"] or c["out_diff"] or c["in_match"] or c["in_diff"]

    def unc_refined(label):
        def f(c):
            return unc(c) and not (c["cls"] == "DIFF" and engine_object(label, c) and not c["in_match"])
        return f

    def engine_object(label, c):
        """A DIFF output whose engine side holds an object of the engine's own package (an unevaluated or
        unconverted engine object, for example a lazy Dask scalar) where the reference holds none: the outputs
        differ in kind whatever the printed text shows."""
        pkg = {"dask": "dask", "modin": "modin", "fireducks": "fireducks", "bodo": "bodo"}.get(label)
        if not pkg:
            return False
        for (name, lv), (rt, et) in zip(c["pf_outputs"], c.get("pf_types", [])):
            if lv == "DIFF" and any(t.startswith(pkg) for t in et) and not any(t.startswith(pkg) for t in rt):
                return True
        return False

    checks = []
    # output flags must reproduce r4_printed_forms.json
    for (campaign, label), cl in sorted(cells.items()):
        sc = [c for c in cl if c["cls"] not in EXCLUDED]
        pf = [c for c in sc if c["out_match"] or c["out_diff"]]
        P = pfm["by_label"][label]
        checks.append(("r4pf %s printed_form_cells" % label, P.get("printed_form_cells", 0), len(pf)))
        checks.append(("r4pf %s cells list" % label, sorted([x[1], x[2]] for x in P["cells"]), sorted([c["nb"], c["i"]] for c in pf)))
        ce2 = [c for c in pf if c["clean"] in ("E0", "E1", "E2") and not c["post_timeout"]]
        checks.append(("r4pf %s clean_E2" % label, P.get("printed_form_clean_E2_cells", 0), len(ce2)))
        checks.append(("summary %s scored" % label, ((summary["campaigns"][campaign]["engines"][label]["views"]["all"]["cells"])), len(sc)))

    def ce2_cells(label, cl, drop):
        return [c for c in cl if c["cls"] not in EXCLUDED and not drop(c) and not c["post_timeout"]
                and c["clean"] in ("E0", "E1", "E2")]

    lab_campaign = {lab: camp for camp, lab in LABELS}

    def share(label, cl, drop, key):
        num, den = collections.Counter(), collections.Counter()
        for c in ce2_cells(label, cl, drop):
            den[c["nb"]] += 1
            num[c["nb"]] += c["cls"] == "DIFF"
        return boot_share(num, den, key)

    def no_drop(c):
        return False

    # --- per configuration: base and certain views -------------------------------------------------------------------
    by_label = {}
    for (campaign, label), cl in sorted(cells.items()):
        R = {}
        for vname, drop in (("base", no_drop), ("certain", unc), ("certain_kind", unc_refined(label))):
            sc = [c for c in cl if c["cls"] not in EXCLUDED and not drop(c)]
            d = share(label, cl, drop, "%s|clean_E2|DIFF" % label)
            nbs = sorted({c["nb"] for c in cl})
            ind = {nb: 0 for nb in nbs}
            for c in cl:
                if not drop(c) and kind_pure(c) == "introduced" and c["cls"] == "DIFF":
                    ind[c["nb"]] = 1
            nbi = boot_share(ind, {nb: 1 for nb in nbs}, "%s|nb|introduced_DIFF" % label)
            R[vname] = {"scored": len(sc), "scored_le_E2": sum(c["cls"] in ("E0", "E1", "E2") for c in sc),
                        "scored_E0": sum(c["cls"] == "E0" for c in sc),
                        "clean_E2": {"num": d["num"], "den": d["den"], "share": d["share"], "ci95": d["ci95"]},
                        "notebooks_introduced_DIFF_pure": {"num": nbi["num"], "ci95": nbi["ci95"]},
                        "notebooks_with_clean_E2_cells": len({c["nb"] for c in ce2_cells(label, cl, drop)})}
            R[vname]["scored_le_E2_share"] = round(R[vname]["scored_le_E2"] / len(sc), 6)
            R[vname]["scored_E0_share"] = round(R[vname]["scored_E0"] / len(sc), 6)
        sc_all = [c for c in cl if c["cls"] not in EXCLUDED]
        R["clean_E2_DIFF_uncertain"] = [{"nb": c["nb"], "cell": c["i"], "clean": c["clean"], "cause": c["cause"],
                                         "kind_pure": kind_pure(c), "pf_outputs": c["pf_outputs"], "pf_inputs": c["pf_inputs"],
                                         "printed_types_ref_eng": c.get("pf_types", []),
                                         "engine_object_in_place_of_value": engine_object(label, c),
                                         "code_reads_shape": ".shape" in (T.cell_code(c["nb"], c["i"]) or ""),
                                         "printed16": (label, c["nb"], c["i"]) in printed16}
                                        for c in ce2_cells(label, cl, no_drop) if c["cls"] == "DIFF" and unc(c)]
        R["clean_E2_DIFF_uncertain_engine_object"] = sum(x["engine_object_in_place_of_value"] for x in R["clean_E2_DIFF_uncertain"])
        R["clean_E2_DIFF_uncertain_engine_object_shape"] = sum(x["engine_object_in_place_of_value"] and x["code_reads_shape"]
                                                               for x in R["clean_E2_DIFF_uncertain"])
        R["uncertain_cells"] = {"scored": sum(unc(c) for c in sc_all),
                                "out_match": sum(c["out_match"] for c in sc_all), "out_diff": sum(c["out_diff"] for c in sc_all),
                                "in_match": sum(c["in_match"] for c in sc_all), "in_diff": sum(c["in_diff"] for c in sc_all),
                                "readers_only": sum((c["in_match"] or c["in_diff"]) and not (c["out_match"] or c["out_diff"]) for c in sc_all),
                                "clean_E2_removed": R["base"]["clean_E2"]["den"] - R["certain"]["clean_E2"]["den"],
                                "clean_E2_DIFF_removed": R["base"]["clean_E2"]["num"] - R["certain"]["clean_E2"]["num"]}
        # bounds of the clean@E2 DIFF share (base population), matching printed forms uncertain
        pop = ce2_cells(label, cl, no_drop)
        num, den = sum(c["cls"] == "DIFF" for c in pop), len(pop)
        a = sum(c["out_match"] and c["cls"] != "DIFF" for c in pop)              # may turn DIFF
        r_nd = sum(c["in_match"] and c["cls"] != "DIFF" and not (c["out_match"]) for c in pop)   # non-DIFF readers that may leave
        r_d = sum(c["in_match"] and c["cls"] == "DIFF" for c in pop)              # DIFF readers that may leave
        R["bounds_clean_E2_DIFF"] = {"observed": round(num / den, 6),
                                     "lower": round((num - r_d) / (den - r_d), 6),
                                     "upper": round((num + a) / (den - r_nd), 6),
                                     "cells_may_turn_DIFF": a, "readers_may_leave_nonDIFF": r_nd, "readers_may_leave_DIFF": r_d,
                                     "den": den}
        # bounds of the notebooks with an introduced DIFF (pure): lower = notebooks with an introduced DIFF whose
        # inputs carry no matching printed form; upper = add notebooks with a matching printed-form output in a cell
        # whose inputs agree at some level (it would be an introduced DIFF if the output differed)
        nb_obs = {c["nb"] for c in cl if kind_pure(c) == "introduced" and c["cls"] == "DIFF"}
        nb_low = {c["nb"] for c in cl if kind_pure(c) == "introduced" and c["cls"] == "DIFF" and not c["in_match"]}
        nb_up = nb_obs | {c["nb"] for c in cl if c["out_match"] and c["cls"] not in EXCLUDED and c["clean"] is not None
                          and c["cls"] in T.RANK and T.RANK[c["cls"]] < T.RANK["DIFF"]}
        R["bounds_notebooks_introduced_DIFF_pure"] = {"observed": len(nb_obs), "lower": len(nb_low), "upper": len(nb_up)}
        by_label[label] = R
        # base reproduces the published numbers
        sv = summary["campaigns"][campaign]["engines"][label]["views"]
        checks.append(("summary %s clean_E2 cells" % label, sv["clean_E2"]["cells"], R["base"]["clean_E2"]["den"]))
        checks.append(("summary %s clean_E2 DIFF" % label, sv["clean_E2"]["counts"]["DIFF"], R["base"]["clean_E2"]["num"]))
        checks.append(("r1 %s clean_E2 DIFF ci95" % label, r1["by_label"][label]["views"]["clean_E2"]["DIFF"]["ci95"],
                       R["base"]["clean_E2"]["ci95"]))
        checks.append(("r4 base off %s notebooks" % label,
                       r4["exception"]["by_variant"]["base"]["by_label"][label]["off"]["notebooks_introduced_DIFF"]["num"],
                       R["base"]["notebooks_introduced_DIFF_pure"]["num"]))

    # --- paired contrasts: base, certain, bounds ---------------------------------------------------------------------
    def paired(e, v, drop_e, drop_v):
        de = {(c["nb"], c["i"]): c for c in ce2_cells(e, cells[("conf_1x", e)], drop_e)}
        dv = {(c["nb"], c["i"]): c for c in ce2_cells(v, cells[("drift", v)], drop_v)}
        ok_nb = {nb for (camp, lab, nb), m in meta.items() if camp == "conf_1x" and lab == e
                 and os.path.basename(m.get("ref_record") or "") == os.path.basename((meta.get(("drift", v, nb)) or {}).get("ref_record") or "")}
        common = sorted(k for k in de if k in dv and k[0] in ok_nb)
        return common, de, dv

    def boot_pair(e, v, rows):
        by_nb = collections.defaultdict(lambda: [0, 0, 0])
        for nb, a, b in rows:
            x = by_nb[nb]
            x[0] += 1
            x[1] += a
            x[2] += b
        nbs = sorted(by_nb)
        n = np.array([by_nb[x][0] for x in nbs], float)
        a = np.array([by_nb[x][1] for x in nbs], float)
        b = np.array([by_nb[x][2] for x in nbs], float)
        rng = np.random.default_rng([SEED, stable_key("pair|%s|%s" % (e, v))])
        idx = rng.integers(0, len(nbs), size=(N_BOOT, len(nbs)))
        diff = (a[idx].sum(1) - b[idx].sum(1)) / n[idx].sum(1) * 100
        est = (a.sum() - b.sum()) / n.sum() * 100
        ci95 = [float(np.percentile(diff, 2.5)), float(np.percentile(diff, 97.5))]
        return {"cells": int(n.sum()), "notebooks": len(nbs), "engine_DIFF": int(a.sum()), "pandas_DIFF": int(b.sum()),
                "diff_pp": round(est, 3), "ci95_pp": [round(x, 3) for x in ci95],
                "reading": "more often" if ci95[0] > 0 else ("less often" if ci95[1] < 0 else "not distinguishable")}

    def mean_bound(vals_certain, vals_uncertain, maximize):
        """Outer bound of a mean over all subsets of vals_uncertain kept (vals_certain always kept)."""
        keep = list(vals_certain)
        pool = sorted(vals_uncertain, reverse=maximize)
        s, n = float(sum(keep)), len(keep)
        for x in pool:   # add in order while it moves the mean in the wanted direction
            if n == 0 or (x > s / n if maximize else x < s / n):
                s += x
                n += 1
            else:
                break
        return s / n * 100 if n else 0.0

    pairs = {}
    for e in ENGINES:
        for v in PANDAS:
            k = "%s-%s" % (e, v)
            common, de, dv = paired(e, v, no_drop, no_drop)
            base = boot_pair(e, v, [(x[0], de[x]["cls"] == "DIFF", dv[x]["cls"] == "DIFF") for x in common])
            q = r1["pairwise_vs_pandas_clean_E2"][k]
            checks.append(("r1 pair %s" % k, [q["cells"], q["notebooks"], q["diff_pp"], q["ci95_pp"]],
                           [base["cells"], base["notebooks"], base["diff_pp"], base["ci95_pp"]]))
            cc, de2, dv2 = paired(e, v, unc, unc)
            cert = boot_pair(e, v, [(x[0], de2[x]["cls"] == "DIFF", dv2[x]["cls"] == "DIFF") for x in cc])
            ck, de3, dv3 = paired(e, v, unc_refined(e), unc_refined(v))
            cert_kind = boot_pair(e, v, [(x[0], de3[x]["cls"] == "DIFF", dv3[x]["cls"] == "DIFF") for x in ck])
            # bounds: per cell contribution engine DIFF minus pandas DIFF (values -1, 0, +1)
            hi_cert, hi_unc, lo_cert, lo_unc = [], [], [], []
            for x in common:
                ce, cv = de[x], dv[x]
                a_obs, b_obs = int(ce["cls"] == "DIFF"), int(cv["cls"] == "DIFF")
                a_hi = 1 if ce["out_match"] else a_obs        # engine side hides a difference
                b_lo = b_obs                                    # pandas side as observed
                b_hi = 1 if cv["out_match"] else b_obs
                member_unc = ce["in_match"] or cv["in_match"]
                (hi_unc if member_unc else hi_cert).append(a_hi - b_lo)
                (lo_unc if member_unc else lo_cert).append(a_obs - b_hi)
            pairs[k] = {"base": base, "certain": cert, "certain_kind": cert_kind,
                        "bounds_pp": [round(mean_bound(lo_cert, lo_unc, False), 3), round(mean_bound(hi_cert, hi_unc, True), 3)],
                        "cells_uncertain_class": sum(de[x]["out_match"] or dv[x]["out_match"] for x in common),
                        "cells_uncertain_membership": sum(de[x]["in_match"] or dv[x]["in_match"] for x in common),
                        "cells_removed_certain": base["cells"] - cert["cells"]}

    bad = [c for c in checks if c[1] != c[2]]
    if bad:
        print(json.dumps([list(map(str, b)) for b in bad], indent=1)[:6000])
        raise SystemExit("consistency check failed (%d of %d)" % (len(bad), len(checks)))

    drop_in = ("modin", "fireducks", "pyarrow_backend")
    tot_sc = sum(len([c for c in cl if c["cls"] not in EXCLUDED]) for cl in cells.values())
    tot = {"scored_cells": tot_sc,
           "uncertain_scored_cells": sum(by_label[l]["uncertain_cells"]["scored"] for l in by_label),
           "printed_form_output_cells": sum(by_label[l]["uncertain_cells"]["scored"] - by_label[l]["uncertain_cells"]["readers_only"] for l in by_label),
           "out_match": sum(by_label[l]["uncertain_cells"]["out_match"] for l in by_label),
           "readers_only": sum(by_label[l]["uncertain_cells"]["readers_only"] for l in by_label),
           "in_match": sum(by_label[l]["uncertain_cells"]["in_match"] for l in by_label),
           "clean_E2_cells": sum(by_label[l]["base"]["clean_E2"]["den"] for l in by_label),
           "clean_E2_removed": sum(by_label[l]["uncertain_cells"]["clean_E2_removed"] for l in by_label)}
    readings = {
        "certain_drop_in_diff_range": [min(pairs["%s-%s" % (e, v)]["certain"]["diff_pp"] for e in drop_in for v in PANDAS),
                                       max(pairs["%s-%s" % (e, v)]["certain"]["diff_pp"] for e in drop_in for v in PANDAS)],
        "certain_drop_in_all_not_distinguishable": all(pairs["%s-%s" % (e, v)]["certain"]["reading"] == "not distinguishable"
                                                       for e in drop_in for v in PANDAS),
        "certain_readings": {k: p["certain"]["reading"] for k, p in pairs.items()},
        "bounds_drop_in_range": [min(pairs["%s-%s" % (e, v)]["bounds_pp"][0] for e in drop_in for v in PANDAS),
                                 max(pairs["%s-%s" % (e, v)]["bounds_pp"][1] for e in drop_in for v in PANDAS)],
        "certain_notebooks_introduced_DIFF_range": [min(by_label[l]["certain"]["notebooks_introduced_DIFF_pure"]["num"] for l in by_label),
                                                    max(by_label[l]["certain"]["notebooks_introduced_DIFF_pure"]["num"] for l in by_label)],
        "bounds_notebooks_introduced_DIFF_range": [min(by_label[l]["bounds_notebooks_introduced_DIFF_pure"]["lower"] for l in by_label),
                                                   max(by_label[l]["bounds_notebooks_introduced_DIFF_pure"]["upper"] for l in by_label)],
        "certain_pair_cells_range": [min(p["certain"]["cells"] for p in pairs.values()), max(p["certain"]["cells"] for p in pairs.values())]}
    out = {"generated_from": {"summary_generated_utc": summary["generated_utc"], "compare_tag": "d" + T.COMPARE,
                              "harness_tag": T.HARNESS, "bootstrap": r1["generated_from"]["bootstrap"],
                              "capture_store": "captures/cols", "obj_columns_read": len(tag_cache),
                              "obj_columns_missing": len(missing)},
           "definition": __doc__.split("Views")[0].strip().splitlines()[-1],
           "consistency_checks": {"n": len(checks), "mismatches": 0},
           "totals": tot, "by_label": by_label, "pairs": pairs, "readings": readings,
           "printed16_flagged": sum(1 for (lab, nb, i) in printed16 for c in cells[(lab_campaign[lab], lab)]
                                    if c["nb"] == nb and c["i"] == i and c["out_diff"])}
    with open(OUT + ".tmp", "w") as f:
        json.dump(out, f, indent=1)
    os.replace(OUT + ".tmp", OUT)
    # per-cell flags for the artifact ledger (scored cells with any flag)
    with open(OUT_CSV + ".tmp", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id", "campaign", "configuration", "nb", "cell", "cls", "clean_level", "out_match", "out_diff",
                    "in_match", "in_diff", "printed_outputs", "printed_inputs"])
        for (campaign, label), cl in sorted(cells.items()):
            for c in cl:
                if unc(c):
                    w.writerow(["%s|%s|%d" % (label, c["nb"], c["i"]), campaign, label, c["nb"], c["i"], c["cls"],
                                c["clean"] or "", int(c["out_match"]), int(c["out_diff"]), int(c["in_match"]),
                                int(c["in_diff"]), ";".join("%s=%s" % tuple(x) for x in c["pf_outputs"]),
                                ";".join("%s=%s" % tuple(x) for x in c["pf_inputs"])])
    os.replace(OUT_CSV + ".tmp", OUT_CSV)

    print("checks %d, mismatches 0; obj columns read %d, missing %d" % (len(checks), len(tag_cache), len(missing)))
    print("totals", tot)
    for lab in PANDAS + ENGINES:
        R = by_label[lab]
        b, c = R["base"], R["certain"]
        print("  %-16s unc %s | clean@E2 %d DIFF %.2f%% -> certain %d %.2f%% %s | bounds %.2f-%.2f%% | NB %d -> %d [bounds %d-%d] | <=E2 %.1f -> %.1f E0 %.1f -> %.1f"
              % (lab, R["uncertain_cells"], b["clean_E2"]["den"], 100 * b["clean_E2"]["share"], c["clean_E2"]["den"],
                 100 * c["clean_E2"]["share"], c["clean_E2"]["ci95"], 100 * R["bounds_clean_E2_DIFF"]["lower"],
                 100 * R["bounds_clean_E2_DIFF"]["upper"], b["notebooks_introduced_DIFF_pure"]["num"],
                 c["notebooks_introduced_DIFF_pure"]["num"], R["bounds_notebooks_introduced_DIFF_pure"]["lower"],
                 R["bounds_notebooks_introduced_DIFF_pure"]["upper"], 100 * b["scored_le_E2_share"],
                 100 * c["scored_le_E2_share"], 100 * b["scored_E0_share"], 100 * c["scored_E0_share"]))
    for k, p in pairs.items():
        print("  pair %-22s base %4d/%3d %+.2f %s | certain %4d/%3d %+.2f [%+.2f, %+.2f] %s | kind %+.2f [%+.2f, %+.2f] %s | bounds [%+.2f, %+.2f] | unc class %d memb %d"
              % (k, p["base"]["cells"], p["base"]["notebooks"], p["base"]["diff_pp"], p["base"]["reading"],
                 p["certain"]["cells"], p["certain"]["notebooks"], p["certain"]["diff_pp"], p["certain"]["ci95_pp"][0],
                 p["certain"]["ci95_pp"][1], p["certain"]["reading"], p["certain_kind"]["diff_pp"], p["certain_kind"]["ci95_pp"][0],
                 p["certain_kind"]["ci95_pp"][1], p["certain_kind"]["reading"], p["bounds_pp"][0], p["bounds_pp"][1],
                 p["cells_uncertain_class"], p["cells_uncertain_membership"]))
    print("readings", json.dumps(readings))


if __name__ == "__main__":
    sys.exit(main())

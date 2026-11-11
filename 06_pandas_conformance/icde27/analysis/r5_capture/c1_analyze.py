#!/usr/bin/env python3
"""C1 analysis: exact recapture of the printed-form comparisons (review round R5, agent B1).

Read-only on results/{conf_1x,drift}/raw, the project's analysis JSONs and work/r5_capture (new runs and their
comparisons); writes icde27/analysis/r5_capture/c1_results.json and c1_cell_changes.csv. Shared venv, < 2 GB.

    cd ..
    .venv/bin/python 06_pandas_conformance-ICDE/icde27/analysis/r5_capture/c1_analyze.py

Inputs: c1_plan.json (printed forms in outputs, pf_out, and inputs, pf_in), c1_selection.json (runs and stop cells),
r4_printed_forms.json (the 688-cell census), c1_nested_levels.json (graded levels of differing nested values, from
c1_nested_levels.py, optional), the original compare outputs, and the new comparisons
work/r5_capture/compare/{orig,exact}/<label>/<nb>.json (c1_compare.py: the same new runs classified with the
original encoder's entries and with the exact encoder's entries, by the unchanged comparator).

Per printed-form cell: o = original campaign, n = new run under the original encoder, g = new run under the exact
encoder with nested values graded by the comparator (primary), x = the same with nested values required to be
E0-equal (strict). run_to_run = n differs from o (class or clean level); encoding effect = g (or x) differs from n;
inexact = an element of a printed-form output or input that the exact encoder could not encode (either side).
Census categories (for the 688 cells, by original class; on g, and separately on x): exact match (same class as n),
exact match at a finer level, exact mismatch (now DIFF or another non-level class where n reached a level; for DIFF
cells: stays DIFF = a confirmed difference, reaches a level = the difference came from the printed form), not
exactly encodable, not recaptured (no run, beyond the stop cell, cell missing in the new runs, or run_to_run in its
class).

Principal comparisons (r1_cells.py population, bootstrap, seeds and keys; kinds from rootcause_taxonomy):
  published            original classes and clean levels (must reproduce r1_cells.json and r4_audit.json);
  exact_graded         printed-form cells with an encoding effect (g differs from n) and no run-to-run change take
                       the class, clean level, outputs and input levels of g; every other cell keeps the original;
  exact_nested_e0      the same with x;
  exact_graded_strict  as exact_graded, and printed-form cells that are not recaptured, remain inexact, or have both
                       a run-to-run change and an encoding effect leave every view (their printed-form readers are
                       printed-form cells themselves and follow the same rule);
  exclude_all_pf       every printed-form cell (pf_out or pf_in) leaves every view: the bound that certifies nothing.
"""
import collections
import csv
import glob
import importlib.util
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.dirname(HERE)
PROJ = os.path.dirname(os.path.dirname(ANALYSIS))
R5 = os.path.join(PROJ, "work", "r5_capture")
LEVELS = ["E0", "E1", "E2", "E3", "E4"]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R1 = load_module("r1_cells", os.path.join(ANALYSIS, "r1_cells.py"))
T = load_module("rootcause_taxonomy", os.path.join(PROJ, "scripts", "rootcause_taxonomy.py"))
N_BOOT, SEED, LABELS, EXCLUDED, FAIL = R1.N_BOOT, R1.SEED, R1.LABELS, R1.EXCLUDED, R1.FAIL
ENGINES, PANDAS = R1.ENGINES, R1.PANDAS
RANK = T.RANK


def nbkey(nb):
    return nb.replace("/", "__").replace(":", "__")


def manifest_records():
    out = {}
    for p in glob.glob(os.path.join(R5, "results", "r5c1_*", "raw", "campaign_h*.json")):
        m = json.load(open(p))
        for key, v in (m.get("runs") or {}).items():
            mode, eng, nb, scale, rep = key.split("|")
            if mode == "capture" and v.get("record"):
                out[(eng, nb)] = (v.get("status"), os.path.join(PROJ, v["record"]))
    return out


def main():
    bound_only = "--bound-only" in sys.argv   # census and exclusion bound from existing data only (c1_bound.json)
    sel = json.load(open(os.path.join(HERE, "c1_selection.json")))
    plan = json.load(open(os.path.join(HERE, "c1_plan.json")))
    census = json.load(open(os.path.join(ANALYSIS, "r4_printed_forms.json")))
    nested_path = os.path.join(HERE, "c1_nested_levels.json")
    nested = json.load(open(nested_path)) if os.path.exists(nested_path) else {"outputs": {}}
    recs = {} if bound_only else manifest_records()

    # ---------------- original cells (r4_audit.py population and kinds) -----------------------------------------
    orig, meta = {}, {}
    for campaign in ("conf_1x", "drift"):
        root, best = T.select_outputs(campaign, T.COMPARE)
        for (label, nb, sc), (_, r, p) in sorted(best.items()):
            if (campaign, label) not in LABELS:
                continue
            meta[(campaign, label, nb)] = r["meta"]
            orig[(label, nb)] = r["cells"]
    camp_of = {lab: camp for camp, lab in LABELS}

    def load_new(variant, label, nb):
        if bound_only:
            return None
        p = os.path.join(R5, "compare", variant, label, nbkey(nb) + ".json")
        if not os.path.exists(p):
            return None
        return {c["i"]: c for c in json.load(open(p))["cells"]}

    rec_cache = {}

    def rec(path):
        if path not in rec_cache:
            if len(rec_cache) > 8:
                rec_cache.clear()
            rec_cache[path] = json.load(open(path))
        return rec_cache[path]

    def inexact_in(record, i, names, kind):
        """names whose exact-encoder record (inputs or outputs of cell i) lists an inexact nested element."""
        if record is None:
            return []
        cell = next((c for c in record["cells"] if c["i"] == i), None)
        if cell is None:
            return []
        out = []
        for n in names:
            e = (cell.get(kind) or {}).get(n)
            if isinstance(e, str) and e in record["objects"]:
                if (record["objects"][e].get("info") or {}).get("nested_inexact"):
                    out.append(n)
        return out

    census_cells = {}
    for label, v in census["by_label"].items():
        for lab, nb, i, cls in v["cells"]:
            census_cells[(label, nb, i)] = cls

    # ---------------- per printed-form cell -------------------------------------------------------------------
    rows = []
    rr_all = collections.defaultdict(collections.Counter)   # run-to-run over every cell up to the stop cells
    for label, P in sorted(plan["by_label"].items()):
        S = sel["by_label"][label]
        for nb, N in sorted(P["notebooks"].items()):
            run = S["notebooks"].get(nb)
            ocells = {c["i"]: c for c in orig[(label, nb)]}
            ncells = load_new("orig", label, nb) if run else None
            xcells = load_new("exact", label, nb) if run else None
            gcells = load_new("graded", label, nb) if run else None
            eng_r = rec(recs[(label, nb)][1]) if run and (label, nb) in recs else None
            ref_r = rec(recs[("ref", nb)][1]) if run and ("ref", nb) in recs else None
            extra_cells = []   # non-printed-form cells whose class or clean level changes with the encoding
            if ncells is not None:
                for i, oc in ocells.items():
                    if i > run["stop"] or oc["cls"] in EXCLUDED:
                        continue
                    nc = ncells.get(i)
                    k = "pf" if any(c["i"] == i for c in N["cells"]) else "other"
                    rr_all[label]["cells_" + k] += 1
                    if nc is None:
                        rr_all[label]["missing_" + k] += 1
                    elif nc["cls"] != oc["cls"]:
                        rr_all[label]["cls_differs_" + k] += 1
                    elif nc.get("clean_level") != oc.get("clean_level"):
                        rr_all[label]["clean_differs_" + k] += 1
                    gc_ = (gcells or {}).get(i)
                    if k == "other" and nc is not None and gc_ is not None and \
                            (gc_["cls"] != nc["cls"] or gc_.get("clean_level") != nc.get("clean_level")):
                        rr_all[label]["encoding_effect_other"] += 1
                        t_idx = next((kk for kk, cc in enumerate(orig[(label, nb)]) if cc.get("cls") == "TIMEOUT" or cc.get("cls_raw") == "TIMEOUT"), None)
                        kpos = next(kk for kk, cc in enumerate(orig[(label, nb)]) if cc["i"] == i)
                        extra_cells.append({"i": i, "pf_out": [], "pf_in": ["(not a printed-form cell)"],
                                            "in_clean_E2": oc.get("clean_level") in ("E0", "E1", "E2") and not (t_idx is not None and kpos > t_idx),
                                            "post_timeout": t_idx is not None and kpos > t_idx})
            for c in list(N["cells"]) + extra_cells:
                i = c["i"]
                oc = ocells[i]
                tier = 1 if run and i in run["tier1_cells"] else (2 if run and i in run["tier2_covered"] else None)
                if tier is None:
                    tier = 1 if (nb in S["not_run"] and i in S["not_run"][nb].get("tier1_cells", [])) else 2
                row = {"label": label, "campaign": camp_of[label], "nb": nb, "cell": i, "tier": tier,
                       "pf_out": c["pf_out"], "pf_in": c["pf_in"], "census": (label, nb, i) in census_cells,
                       "o_cls": oc["cls"], "o_clean": oc.get("clean_level"), "in_clean_E2_orig": c["in_clean_E2"],
                       "post_timeout": c["post_timeout"], "recaptured": False, "why_not": None,
                       "n_cls": None, "n_clean": None, "x_cls": None, "x_clean": None, "g_cls": None, "g_clean": None,
                       "run_to_run": None, "encoding_effect": None, "encoding_effect_x": None, "inexact": [], "outputs": {}}
                if not run:
                    row["why_not"] = "not run (%s)" % ("budget" if S["not_run"].get(nb, {}).get("budget") else "tier-2 only, cost")
                elif i > run["stop"]:
                    row["why_not"] = "beyond stop cell"
                elif ncells is None or xcells is None or gcells is None:
                    row["why_not"] = "no new comparison (run missing)"
                elif i not in ncells or i not in xcells or i not in gcells:
                    row["why_not"] = "cell missing in the new runs"
                else:
                    nc, xc, gc = ncells[i], xcells[i], gcells[i]
                    row.update(n_cls=nc["cls"], n_clean=nc.get("clean_level"), x_cls=xc["cls"], x_clean=xc.get("clean_level"),
                               g_cls=gc["cls"], g_clean=gc.get("clean_level"))
                    row["run_to_run"] = (nc["cls"] != oc["cls"]) or (nc.get("clean_level") != oc.get("clean_level"))
                    row["encoding_effect"] = (gc["cls"] != nc["cls"]) or (gc.get("clean_level") != nc.get("clean_level"))
                    row["encoding_effect_x"] = (xc["cls"] != nc["cls"]) or (xc.get("clean_level") != nc.get("clean_level"))
                    names_out = sorted(set((nc.get("outputs") or {})) | set((xc.get("outputs") or {})))
                    for name in names_out:
                        row["outputs"][name] = [(oc.get("outputs") or {}).get(name, {}).get("level"),
                                                (nc.get("outputs") or {}).get(name, {}).get("level"),
                                                (gc.get("outputs") or {}).get(name, {}).get("level"),
                                                (xc.get("outputs") or {}).get(name, {}).get("level")]
                    inx = set(inexact_in(eng_r, i, c["pf_out"], "outputs")) | set(inexact_in(ref_r, i, c["pf_out"], "outputs"))
                    inx |= {"in:" + n for n in set(inexact_in(eng_r, i, c["pf_in"], "inputs")) | set(inexact_in(ref_r, i, c["pf_in"], "inputs"))}
                    row["inexact"] = sorted(inx)
                    row["recaptured"] = True
                    row["exact_clean_E2"] = gc.get("clean_level") in ("E0", "E1", "E2") and not c["post_timeout"]
                    row["new_orig_clean_E2"] = nc.get("clean_level") in ("E0", "E1", "E2") and not c["post_timeout"]
                    keys = ("cls", "cls_raw", "clean_level", "clean_input", "outputs", "input_levels", "fallback",
                            "families", "eng_exc", "eng_msg")
                    row["x_cell"] = {k: xc.get(k) for k in keys}
                    row["g_cell"] = {k: gc.get(k) for k in keys}
                rows.append(row)

    # ---------------- census categories (688 cells) ----------------------------------------------------------
    def category(r, which="g"):
        if not r["recaptured"]:
            return "not recaptured: " + r["why_not"]
        if r["n_cls"] != r["o_cls"]:
            return "not recaptured: run-to-run class change"
        if r["inexact"] and any(not x.startswith("in:") for x in r["inexact"]):
            return "not exactly encodable"
        o, x = r["n_cls"], r[which + "_cls"]
        if o in LEVELS:
            if x == o:
                return "exact match"
            if x in LEVELS:
                return "exact match, finer level" if RANK[x] < RANK[o] else "exact match, coarser level"
            return "exact mismatch (now %s)" % x
        if o == "DIFF":
            if x == "DIFF":
                return "exact mismatch (confirmed DIFF)"
            if x in LEVELS:
                return "exact match (DIFF came from the printed form; now %s)" % x
            return "now %s" % x
        return "%s -> %s" % (o, x)

    cens = {"matching": collections.Counter(), "DIFF": collections.Counter(), "other": collections.Counter()}
    cens_x = {"matching": collections.Counter(), "DIFF": collections.Counter(), "other": collections.Counter()}
    cens_by_label = collections.defaultdict(lambda: {"matching": collections.Counter(), "DIFF": collections.Counter(),
                                                     "other": collections.Counter()})
    cens_ce2 = {"matching": collections.Counter(), "DIFF": collections.Counter(), "other": collections.Counter()}
    seen = set()
    for r in rows:
        if not r["census"]:
            continue
        seen.add((r["label"], r["nb"], r["cell"]))
        grp = "matching" if r["o_cls"] in LEVELS else ("DIFF" if r["o_cls"] == "DIFF" else "other")
        cat = category(r)
        r["census_category"] = cat
        r["census_category_x"] = category(r, "x")
        cens[grp][cat] += 1
        cens_x[grp][r["census_category_x"]] += 1
        cens_by_label[r["label"]][grp][cat] += 1
        if r["in_clean_E2_orig"]:
            cens_ce2[grp][cat] += 1
    missing_census = sorted(k for k in census_cells if k not in seen)

    # ---------------- outputs with an exact mismatch: graded nested level -----------------------------------
    graded = collections.Counter()
    for r in rows:
        if not r["recaptured"] or r["run_to_run"]:
            continue
        for name, (lo, ln, lg, lx) in r["outputs"].items():
            if ln != lx or ln != lg:
                graded["orig %s -> graded %s, nested-E0 %s" % (ln, lg, lx)] += 1

    # ---------------- propagation: readers ------------------------------------------------------------------
    prop = collections.defaultdict(collections.Counter)
    for r in rows:
        if not r["pf_in"] or not r["recaptured"] or r["run_to_run"]:
            continue
        a, b = r["new_orig_clean_E2"], r["exact_clean_E2"]
        key = "stays in clean@E2" if a and b else "leaves clean@E2" if a and not b else "enters clean@E2" if b and not a else "stays out"
        prop[r["label"]][key] += 1
        if r["n_clean"] != r["x_clean"]:
            prop[r["label"]]["clean level changed"] += 1

    # ---------------- principal comparisons ------------------------------------------------------------------
    by_key = {(r["label"], r["nb"], r["cell"]): r for r in rows}

    def override(label, nb, c, variant):
        """-> (cell dict to use, keep flag)"""
        r = by_key.get((label, nb, c["i"]))
        if variant == "published" or r is None or c["cls"] == "NONDET":
            return c, True
        if variant == "exclude_all_pf":
            return c, False
        which = "x" if variant == "exact_nested_e0" else "g"
        eff = r["encoding_effect_x"] if which == "x" else r["encoding_effect"]
        applied = r["recaptured"] and not r["run_to_run"] and eff
        uncertain = (not r["recaptured"]) or bool(r["inexact"]) or (r["recaptured"] and r["run_to_run"] and eff)
        if variant == "exact_graded_strict" and uncertain:
            return c, False
        if applied:
            c2 = dict(c)
            c2.update({k: v for k, v in r[which + "_cell"].items() if k in ("cls", "clean_level", "clean_input", "outputs", "input_levels")})
            return c2, True
        return c, True

    res = {}
    for variant in (("published", "exclude_all_pf") if bound_only else
                    ("published", "exact_graded", "exact_nested_e0", "exact_graded_strict", "exclude_all_pf")):
        cells = {}
        for (label, nb), cl in sorted(orig.items()):
            campaign = camp_of[label]
            t_idx = next((k for k, c in enumerate(cl) if c.get("cls") == "TIMEOUT" or c.get("cls_raw") == "TIMEOUT"), None)
            for k, c0 in enumerate(cl):
                c, keep = override(label, nb, c0, variant)
                if not keep:
                    continue
                d = {"nb": nb, "i": c["i"], "cls": c["cls"], "clean": c.get("clean_level"),
                     "post_timeout": t_idx is not None and k > t_idx, "kind": None, "cause": None}
                if c["cls"] not in ("E0", "NOOUT", "REF_ERR", "NONDET"):
                    n = T.normalise_cell(campaign, label, nb, c)
                    n["code"] = T.cell_code(nb, c["i"])
                    d["cause"], d["kind"], _ = T.classify_cell(n)
                cells.setdefault(label, []).append(d)

        def view(cl, name):
            for c in cl:
                if c["cls"] in EXCLUDED:
                    continue
                if name == "all":
                    yield c
                elif not c["post_timeout"] and c["clean"] in ("E0", "E1", "E2"):
                    yield c

        V = res.setdefault(variant, {"by_label": {}, "pairs": {}})
        for label, cl in sorted(cells.items()):
            num, den = collections.Counter(), collections.Counter()
            for c in view(cl, "clean_E2"):
                den[c["nb"]] += 1
                num[c["nb"]] += c["cls"] == "DIFF"
            allv = list(view(cl, "all"))
            R = {"all_cells": len(allv), "all_DIFF": sum(c["cls"] == "DIFF" for c in allv),
                 "clean_E2_DIFF": R1.boot_share(num, den, "%s|clean_E2|DIFF" % label)}
            for exc_on in (True, False):
                ind = {}
                for nb in sorted({c["nb"] for c in cl}):
                    ind[nb] = any(c["cls"] == "DIFF" and (c["kind"] == "introduced" or (not exc_on and c["cause"] == "order_propagated"))
                                  for c in cl if c["nb"] == nb)
                R["notebooks_introduced_DIFF_" + ("heuristic" if exc_on else "pure")] = \
                    R1.boot_share({nb: int(x) for nb, x in ind.items()}, {nb: 1 for nb in ind}, "%s|nb|introduced_DIFF" % label)
            V["by_label"][label] = R

        def ce2(label):
            return {(c["nb"], c["i"]): c["cls"] == "DIFF" for c in view(cells[label], "clean_E2")}
        for e in ENGINES:
            de = ce2(e)
            for v in PANDAS:
                dv = ce2(v)
                ok_nb = {nb for (camp, lab, nb), m in meta.items() if camp == "conf_1x" and lab == e
                         and os.path.basename(m.get("ref_record") or "") == os.path.basename((meta.get(("drift", v, nb)) or {}).get("ref_record") or "")}
                common = sorted(k for k in de if k in dv and k[0] in ok_nb)
                by_nb = collections.defaultdict(lambda: [0, 0, 0])
                for k in common:
                    b = by_nb[k[0]]
                    b[0] += 1
                    b[1] += de[k]
                    b[2] += dv[k]
                nbs = sorted(by_nb)
                n = np.array([by_nb[x][0] for x in nbs], float)
                a = np.array([by_nb[x][1] for x in nbs], float)
                b = np.array([by_nb[x][2] for x in nbs], float)
                rng = np.random.default_rng([SEED, R1.stable_key("pair|%s|%s" % (e, v))])
                idx = rng.integers(0, len(nbs), size=(N_BOOT, len(nbs)))
                diff = (a[idx].sum(1) - b[idx].sum(1)) / n[idx].sum(1) * 100
                est = (a.sum() - b.sum()) / n.sum() * 100
                ci95 = [float(np.percentile(diff, 2.5)), float(np.percentile(diff, 97.5))]
                ci90 = [float(np.percentile(diff, 5)), float(np.percentile(diff, 95))]
                V["pairs"]["%s-%s" % (e, v)] = {
                    "cells": int(n.sum()), "notebooks": len(nbs), "engine_DIFF": int(a.sum()), "pandas_DIFF": int(b.sum()),
                    "diff_pp": round(est, 3), "ci95_pp": [round(x, 3) for x in ci95], "ci90_pp": [round(x, 3) for x in ci90],
                    "within_2pp": bool(ci90[0] > -2 and ci90[1] < 2), "within_1pp": bool(ci90[0] > -1 and ci90[1] < 1),
                    "reading": "more often" if ci95[0] > 0 else ("less often" if ci95[1] < 0 else "not distinguishable")}

    # consistency: the published variant reproduces r1_cells.json and r4_audit.json
    r1 = json.load(open(os.path.join(ANALYSIS, "r1_cells.json")))
    r4 = json.load(open(os.path.join(ANALYSIS, "r4_audit.json")))
    checks = []
    for k, p in res["published"]["pairs"].items():
        q = r1["pairwise_vs_pandas_clean_E2"][k]
        checks.append(("pair %s diff_pp" % k, q["diff_pp"], p["diff_pp"]))
        checks.append(("pair %s ci95" % k, q["ci95_pp"], p["ci95_pp"]))
        checks.append(("pair %s cells" % k, q["cells"], p["cells"]))
    for label, R in res["published"]["by_label"].items():
        checks.append(("%s clean_E2 DIFF" % label, r1["by_label"][label]["views"]["clean_E2"]["DIFF"]["share"],
                       R["clean_E2_DIFF"]["share"]))
        checks.append(("%s nb heuristic" % label, r1["by_label"][label]["notebooks"]["introduced_DIFF"]["num"],
                       R["notebooks_introduced_DIFF_heuristic"]["num"]))
        checks.append(("%s nb pure" % label, r4["exception"]["by_variant"]["base"]["by_label"][label]["off"]["notebooks_introduced_DIFF"]["num"],
                       R["notebooks_introduced_DIFF_pure"]["num"]))
    bad = [c for c in checks if c[1] != c[2]]
    if bad:
        print(json.dumps(bad, indent=1))
        raise SystemExit("published variant does not reproduce r1_cells.json / r4_audit.json")

    # ---------------- object-level determinism (original encoder hashes, new run against original run) ------
    det = collections.defaultdict(collections.Counter)

    def det_count(key, newp, oldp, stop):
        new, old = rec(newp), rec(oldp)
        oldc = {c["i"]: c for c in old["cells"]}
        for c in new["cells"]:
            if c["i"] > stop or c["i"] not in oldc:
                continue
            outs = dict(c.get("outputs") or {})
            outs.update(c.get("outputs_orig") or {})
            for name, h in outs.items():
                ho = (oldc[c["i"]].get("outputs") or {}).get(name)
                if not isinstance(h, str) or not isinstance(ho, str) or h in ("absent", "deleted") or ho in ("absent", "deleted"):
                    continue
                det[key]["outputs"] += 1
                det[key]["identical" if h == ho else "differ"] += 1

    ref_stop = json.load(open(os.path.join(HERE, "c1_streams", "job1_ref_stop.json")))
    ref_orig = {}
    for (campaign, label, nb), m in meta.items():
        if campaign == "conf_1x":
            ref_orig.setdefault(nb, os.path.join(PROJ, m["ref_record"]))
    for key, stop in sorted(ref_stop.items()):
        nb = key.split("|", 1)[1]
        if ("ref", nb) in recs and nb in ref_orig:
            det_count("ref", recs[("ref", nb)][1], ref_orig[nb], stop)
    for label, S in sorted(sel["by_label"].items()):
        for nb, run in sorted(S["notebooks"].items()):
            if (label, nb) in recs:
                m = meta[(camp_of[label], label, nb)]
                det_count("engine:" + label, recs[(label, nb)][1], os.path.join(PROJ, m["eng_record"]), run["stop"])

    out = {"definitions": __doc__.split("Per printed-form cell:")[1].strip(),
           "census_cells": len(census_cells), "census_cells_missing_in_plan": len(missing_census),
           "census_categories": {g: dict(v) for g, v in cens.items()},
           "census_categories_nested_e0": {g: dict(v) for g, v in cens_x.items()},
           "census_categories_clean_E2": {g: dict(v) for g, v in cens_ce2.items()},
           "census_categories_by_label": {lab: {g: dict(v) for g, v in d.items()} for lab, d in cens_by_label.items()},
           "exact_mismatch_outputs_graded": dict(graded),
           "run_to_run_all_cells": {lab: dict(v) for lab, v in rr_all.items()},
           "object_hash_determinism": {k: dict(v) for k, v in det.items()},
           "readers": {lab: dict(v) for lab, v in prop.items()},
           "pf_cells": len(rows), "pf_cells_recaptured": sum(r["recaptured"] for r in rows),
           "pf_cells_encoding_effect": sum(bool(r["encoding_effect"]) for r in rows),
           "pf_cells_run_to_run": sum(bool(r["run_to_run"]) for r in rows),
           "principal": res, "consistency_checks": len(checks)}
    if bound_only:
        pf = collections.Counter()
        for r in rows:
            pf["pf_cells"] += 1
            pf["pf_out_cells"] += bool(r["pf_out"])
            pf["pf_in_only_cells"] += bool(r["pf_in"]) and not r["pf_out"]
            pf["pf_cells_in_clean_E2"] += bool(r["in_clean_E2_orig"])
            pf["pf_in_only_cells_in_clean_E2"] += bool(r["pf_in"]) and not r["pf_out"] and bool(r["in_clean_E2_orig"])
        bound = {"definition": "every printed-form cell of the seven configurations (an output or an input whose captured "
                               "record holds an element tagged T_CONTAINER or T_OTHER, on either side) leaves every view; "
                               "computed from the stored records only, nothing recaptured",
                 "pf_cells": dict(pf), "pf_cells_by_label": {lab: sum(1 for r in rows if r["label"] == lab) for lab in sorted({r["label"] for r in rows})},
                 "principal": res, "consistency_checks": len(checks)}
        with open(os.path.join(HERE, "c1_bound.json"), "w") as f:
            json.dump(bound, f, indent=1, sort_keys=True, default=str)
        print(json.dumps(bound["pf_cells"], sort_keys=True))
        return 0
    with open(os.path.join(HERE, "c1_results.json") + ".tmp", "w") as f:
        json.dump(out, f, indent=1, sort_keys=True, default=str)
    os.replace(os.path.join(HERE, "c1_results.json") + ".tmp", os.path.join(HERE, "c1_results.json"))
    cols = ["label", "campaign", "nb", "cell", "tier", "census", "pf_out", "pf_in", "o_cls", "o_clean", "n_cls", "n_clean",
            "g_cls", "g_clean", "x_cls", "x_clean", "recaptured", "why_not", "run_to_run", "encoding_effect",
            "encoding_effect_x", "inexact", "census_category", "census_category_x", "applied_in_exact_graded",
            "removed_in_exact_graded_strict"]
    with open(os.path.join(HERE, "c1_cell_changes.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            applied = bool(r["recaptured"] and not r["run_to_run"] and r["encoding_effect"])
            removed = bool((not r["recaptured"]) or r["inexact"] or (r["recaptured"] and r["run_to_run"] and r["encoding_effect"]))
            vals = dict(r, applied_in_exact_graded=applied, removed_in_exact_graded_strict=removed,
                        pf_out=";".join(r["pf_out"]), pf_in=";".join(r["pf_in"]), inexact=";".join(r["inexact"]),
                        census_category=r.get("census_category", ""), census_category_x=r.get("census_category_x", ""))
            w.writerow([vals.get(c) for c in cols])
    print(json.dumps({k: out[k] for k in ("census_categories", "pf_cells", "pf_cells_recaptured", "pf_cells_encoding_effect",
                                          "pf_cells_run_to_run")}, indent=1, sort_keys=True))
    for variant in res:
        print(variant, {k: (p["diff_pp"], p["ci95_pp"], p["reading"]) for k, p in res[variant]["pairs"].items()})


if __name__ == "__main__":
    sys.exit(main())

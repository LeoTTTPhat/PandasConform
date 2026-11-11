#!/usr/bin/env python3
"""The exact-recapture basis of the notebook and contrast numbers (review round R5, pass 2; ICDE 2027 copy; written
2026-11-11).

The exact recapture of printed forms (icde27/analysis/r5_capture/, RESULTS.md section C1 part B) re-executed the
notebooks whose cells compare or read a printed form and encoded nested values exactly. Its per-cell overrides
(r5_capture/c1_overrides.json, "graded": the complete compare-cell fields of the 152 printed-form cells whose class or
clean level the recapture changes, nested values graded by the comparator; cells with a run-to-run change and cells
not recaptured keep their original fields) are applied here to the original compare outputs, and the paper's numbers
are recomputed on the pure definition (a cell whose grade worsens is introduced):

  * per configuration, notebooks with an introduced DIFF (all cells; and without the one known printed-form artifact
    that has no exact encoding), and with the heuristic of Section IV for comparison;
  * error-free and agreeing notebooks (definitions of r5_reliability.py), the failure decomposition by first failure,
    and the error-free notebooks with an introduced DIFF whose assigned cause a reproducer or probe confirms;
  * the ten paired clean@E2 DIFF contrasts pooled over cells (as r1_cells.py: same population rule, bootstrap seed and
    keys), and the paired notebook contrasts of agreeing notebooks against pandas 3.0.6.

Consistency checks: the same code without the overrides reproduces r5_reliability.json (error-free, agreeing,
introduced-DIFF notebooks, pooled contrasts) and r4_audit.json (pure notebook counts with all cells); with the
overrides it reproduces every number that r5_capture/c1_results.json principal.exact_graded reports (pure and heuristic
notebook counts, paired contrasts with cells, estimates and intervals).

Read-only on results/{conf_1x,drift}/raw (compare outputs, run records), results/summary.json, scripts/
rootcause_taxonomy.py, icde27/analysis/{r1_cells.py, r1_hand_attribution.json, r4_audit.json, r4_cell_flags.csv, r5_reliability.json,
r5_capture/c1_overrides.json, r5_capture/c1_results.json}; writes only icde27/analysis/r5_exact.json. Memory below 2 GB.

    cd ..
    .venv/bin/python 06_pandas_conformance-ICDE/icde27/analysis/r5_exact.py
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
OUT = os.path.join(HERE, "r5_exact.json")
OVR_KEYS = ("i", "cls", "cls_raw", "clean_level", "clean_input", "outputs", "input_levels", "unclean", "hidden_globals",
            "inputs_from", "eng_exc", "eng_msg", "eng_origin", "flags", "fallback", "families")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R1 = load_module("r1_cells", os.path.join(HERE, "r1_cells.py"))
N_BOOT, SEED = R1.N_BOOT, R1.SEED
ENGINES, PANDAS, LABELS = R1.ENGINES, R1.PANDAS, R1.LABELS
EXCLUDED, FAIL = R1.EXCLUDED, R1.FAIL
stable_key = R1.stable_key
UNSUPPORTED = {"engine_unsupported_api", "partitioned_type_inference", "lazy_partition_model"}
E2 = ("E0", "E1", "E2")


def main():
    T = load_module("rootcause_taxonomy", os.path.join(PROJ, "scripts", "rootcause_taxonomy.py"))
    rel = json.load(open(os.path.join(HERE, "r5_reliability.json")))
    r4 = json.load(open(os.path.join(HERE, "r4_audit.json")))
    c1 = json.load(open(os.path.join(HERE, "r5_capture", "c1_results.json")))
    ovr = json.load(open(os.path.join(HERE, "r5_capture", "c1_overrides.json")))["graded"]
    hand = json.load(open(os.path.join(HERE, "r1_hand_attribution.json")))
    printed16 = {(r["label"], r["nb"], r["cell"]) for r in hand["rows"] if r["cause"] == "printed_form_comparison"}
    evid = {}
    with open(os.path.join(HERE, "r4_cell_flags.csv")) as f:
        for row in csv.DictReader(f):
            evid[row["id"]] = row["cause_evidence"]

    cells = {"base": {}, "exact": {}}
    meta, runrec, applied = {}, {}, set()
    for campaign in ("conf_1x", "drift"):
        root, best = T.select_outputs(campaign, T.COMPARE)
        for (label, nb, sc), (_, r, p) in sorted(best.items()):
            if (campaign, label) not in LABELS:
                continue
            m = r["meta"]
            meta[(campaign, label, nb)] = m
            rr = json.load(open(os.path.join(PROJ, m["eng_record"])))
            runrec[(label, nb)] = {"status": rr.get("status"), "returncode": rr.get("returncode")}
            for basis in ("base", "exact"):
                cl = []
                for c in r["cells"]:
                    key = "%s|%s|%d" % (label, nb, c["i"])
                    if basis == "exact" and key in ovr:
                        c = dict({k: v for k, v in c.items() if k not in OVR_KEYS}, **ovr[key])
                        applied.add(key)
                    cl.append(c)
                t_idx = next((k for k, c in enumerate(cl) if c.get("cls") == "TIMEOUT" or c.get("cls_raw") == "TIMEOUT"), None)
                for k, c in enumerate(cl):
                    d = {"nb": nb, "i": c["i"], "cls": c["cls"], "clean": c.get("clean_level"),
                         "post_timeout": t_idx is not None and k > t_idx, "kind": None, "cause": None}
                    if c["cls"] not in ("E0", "NOOUT", "REF_ERR", "NONDET"):
                        n = T.normalise_cell(campaign, label, nb, c)
                        n["code"] = T.cell_code(nb, c["i"])
                        d["cause"], d["kind"], _ = T.classify_cell(n)
                    cells[basis].setdefault((campaign, label), []).append(d)
    lab_campaign = {lab: camp for camp, lab in LABELS}
    nbs_all = sorted({nb for (camp, lab, nb) in meta})
    assert len(nbs_all) == 102
    checks = [("overrides applied", len(ovr), len(applied))]

    def kind_pure(c):
        return "introduced" if c["cause"] == "order_propagated" else c["kind"]

    def compute(basis):
        C = cells[basis]
        outcome = {}
        for (campaign, label), cl in sorted(C.items()):
            by_nb = collections.defaultdict(list)
            for c in cl:
                by_nb[c["nb"]].append(c)
            O = {}
            for nb in nbs_all:
                allc = by_nb.get(nb, [])
                sc = [c for c in allc if c["cls"] not in EXCLUDED]
                st = meta[(campaign, label, nb)].get("eng_status")
                ef = st == "completed" and not any(c["cls"] in FAIL for c in allc)
                O[nb] = {"error_free": ef,
                         "agreeing": ef and all(c["cls"] in ("E0", "E1", "E2", "E3", "E4") for c in sc),
                         "introduced_DIFF_all": any(kind_pure(c) == "introduced" and c["cls"] == "DIFF" for c in allc),
                         "introduced_DIFF": any(kind_pure(c) == "introduced" and c["cls"] == "DIFF"
                                                and (label, nb, c["i"]) not in printed16 for c in allc),
                         "introduced_DIFF_heuristic_all": any(c["kind"] == "introduced" and c["cls"] == "DIFF" for c in allc),
                         "introduced_DIFF_heuristic": any(c["kind"] == "introduced" and c["cls"] == "DIFF"
                                                          and (label, nb, c["i"]) not in printed16 for c in allc)}
            outcome[label] = O

        def clean_set(label):
            camp = lab_campaign[label]
            return {(c["nb"], c["i"]): c["cls"] == "DIFF" for c in C[(camp, label)]
                    if c["cls"] not in EXCLUDED and not c["post_timeout"] and c["clean"] in E2}

        def contrast(e, v):
            de, dv = clean_set(e), clean_set(v)
            ok_nb = {nb for (camp, lab, nb), m in meta.items() if camp == "conf_1x" and lab == e
                     and os.path.basename(m.get("ref_record") or "") == os.path.basename((meta.get(("drift", v, nb)) or {}).get("ref_record") or "")}
            common = [k for k in sorted(de) if k in dv and k[0] in ok_nb]
            by_nb = collections.defaultdict(lambda: [0, 0, 0])
            for k in common:
                x = by_nb[k[0]]
                x[0] += 1
                x[1] += de[k]
                x[2] += dv[k]
            nbs = sorted(by_nb)
            n = np.array([by_nb[x][0] for x in nbs], float)
            a = np.array([by_nb[x][1] for x in nbs], float)
            b = np.array([by_nb[x][2] for x in nbs], float)
            rng = np.random.default_rng([SEED, stable_key("pair|%s|%s" % (e, v))])
            idx = rng.integers(0, len(nbs), size=(N_BOOT, len(nbs)))
            d = (a[idx].sum(1) - b[idx].sum(1)) / n[idx].sum(1) * 100
            est = (a.sum() - b.sum()) / n.sum() * 100
            ci95 = [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]
            ci90 = [float(np.percentile(d, 5)), float(np.percentile(d, 95))]
            return {"cells": int(n.sum()), "notebooks": len(nbs), "engine_DIFF": int(a.sum()), "pandas_DIFF": int(b.sum()),
                    "diff_pp": round(float(est), 3), "ci95_pp": [round(x, 3) for x in ci95], "ci90_pp": [round(x, 3) for x in ci90],
                    "within_2pp": bool(ci90[0] >= -2 and ci90[1] <= 2),
                    "reading": "more often" if ci95[0] > 0 else ("less often" if ci95[1] < 0 else "not distinguishable")}

        def nb_pair(e, v, key):
            a = np.array([outcome[e][nb][key] for nb in nbs_all], float)
            b = np.array([outcome[v][nb][key] for nb in nbs_all], float)
            rng = np.random.default_rng([SEED, stable_key("nbpair|%s|%s|%s" % (e, v, key))])
            idx = rng.integers(0, len(nbs_all), size=(N_BOOT, len(nbs_all)))
            d = (a[idx].mean(1) - b[idx].mean(1)) * 100
            ci = [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]
            return {"engine": int(a.sum()), "pandas": int(b.sum()), "diff_pp": round(float((a.mean() - b.mean()) * 100), 3),
                    "ci95_pp": [round(x, 3) for x in ci],
                    "reading": "more often" if ci[0] > 0 else ("less often" if ci[1] < 0 else "not distinguishable")}

        shares = {}
        for lab in PANDAS + ENGINES:
            cs = clean_set(lab)
            shares[lab] = {"clean_E2_cells": len(cs), "clean_E2_DIFF": sum(cs.values()),
                           "clean_E2_DIFF_share": round(sum(cs.values()) / len(cs), 6)}
        notebooks = {lab: {k: sum(outcome[lab][nb][k] for nb in nbs_all) for k in
                           ("error_free", "agreeing", "introduced_DIFF_all", "introduced_DIFF", "introduced_DIFF_heuristic_all",
                            "introduced_DIFF_heuristic")}
                     for lab in PANDAS + ENGINES}
        for lab in PANDAS + ENGINES:
            notebooks[lab]["introduced_DIFF_notebooks_all"] = sorted(nb for nb in nbs_all if outcome[lab][nb]["introduced_DIFF_all"])
        pairs = {"%s-%s" % (e, v): contrast(e, v) for e in ENGINES for v in PANDAS}
        nb_pairs = {"%s-%s" % (e, v): {k: nb_pair(e, v, k) for k in ("error_free", "agreeing")} for e in ENGINES for v in PANDAS}

        decomp = {}
        for (campaign, label), cl in sorted(C.items()):
            by_nb = collections.defaultdict(list)
            for c in cl:
                by_nb[c["nb"]].append(c)
            D = collections.Counter()
            for nb in nbs_all:
                if outcome[label][nb]["error_free"]:
                    continue
                first = next((c for c in by_nb.get(nb, []) if c["cls"] in FAIL), None)
                st = runrec[(label, nb)]
                if first is None or first["cls"] in ("CRASH", "NOTRUN", "KILLED", "SETUP_ERR"):
                    if st["status"] == "nb_crash":
                        cat = "dependency crash" if label == "bodo" and st["returncode"] == 14 else "native crash"
                    elif st["status"] == "nb_memory":
                        cat = "memory cap"
                    elif st["status"] == "nb_timeout":
                        cat = "time limit"
                    else:
                        cat = "other"
                elif first["cls"] == "MEMORY":
                    cat = "memory cap"
                elif first["cls"] == "TIMEOUT":
                    cat = "time limit"
                elif first["kind"] == "propagated":
                    cat = "error after an earlier difference"
                elif label in PANDAS:
                    cat = "API removed or changed by pandas" if first["kind"] == "introduced" else "other"
                elif first["cause"] in UNSUPPORTED:
                    cat = "unsupported API or execution model"
                elif first["kind"] == "introduced":
                    cat = "error on supported API"
                else:
                    cat = "other"
                D[cat] += 1
            decomp[label] = dict(D)
        # error-free notebooks with an introduced DIFF, and those where a reproducer or probe confirms an assigned cause
        # on this configuration (evidence of r4_cell_flags.csv; an overridden cell keeps the evidence of its original
        # cause, counted in confirmed_evidence_from_overridden_cells)
        confirmed = {}
        for (campaign, label), cl in sorted(C.items()):
            by_nb = collections.defaultdict(list)
            for c in cl:
                by_nb[c["nb"]].append(c)
            o = outcome[label]
            ef_diff = [nb for nb in nbs_all if o[nb]["error_free"] and o[nb]["introduced_DIFF"]]
            conf, from_ovr = [], 0
            for nb in ef_diff:
                ids = ["%s|%s|%d" % (label, nb, c["i"]) for c in by_nb[nb]
                       if kind_pure(c) == "introduced" and c["cls"] == "DIFF" and (label, nb, c["i"]) not in printed16]
                hit = [i for i in ids if ("confirms on this engine" in evid.get(i, "")) or ("differs on this configuration" in evid.get(i, ""))]
                if hit:
                    conf.append(nb)
                    if basis == "exact" and all(i in ovr for i in hit):
                        from_ovr += 1
            confirmed[label] = {"error_free_introduced_DIFF": len(ef_diff), "error_free_introduced_DIFF_reproduced_cause": len(conf),
                                "confirmed_evidence_from_overridden_cells": from_ovr}
        return {"clean_E2": shares, "notebooks": notebooks, "pairs": pairs, "notebook_pairs": nb_pairs,
                "failure_decomposition": decomp, "error_free_confirmed": confirmed}

    res = {b: compute(b) for b in ("base", "exact")}

    # --- consistency: base against r5_reliability.json and r4_audit.json ------------------------------------------
    B, X = res["base"], res["exact"]
    for lab in PANDAS + ENGINES:
        for k in ("error_free", "agreeing", "introduced_DIFF"):
            checks.append(("base %s %s" % (lab, k), rel["notebooks"][lab][k]["num"], B["notebooks"][lab][k]))
        checks.append(("base %s introduced_DIFF_all (r4 base off)" % lab,
                       r4["exception"]["by_variant"]["base"]["by_label"][lab]["off"]["notebooks_introduced_DIFF"]["num"],
                       B["notebooks"][lab]["introduced_DIFF_all"]))
        checks.append(("base %s failure decomposition" % lab, rel["failure_decomposition"][lab]["not_error_free"],
                       B["failure_decomposition"][lab]))
        checks.append(("base %s error-free confirmed" % lab,
                       [rel["failure_decomposition"][lab]["error_free_introduced_DIFF"], rel["failure_decomposition"][lab]["error_free_introduced_DIFF_reproduced_cause"]],
                       [B["error_free_confirmed"][lab]["error_free_introduced_DIFF"], B["error_free_confirmed"][lab]["error_free_introduced_DIFF_reproduced_cause"]]))
    for k, p in B["pairs"].items():
        q = rel["contrasts"][k]["pooled_E2"]
        checks.append(("base pair %s" % k, [q["cells"], q["diff_pp"], q["ci95_pp"], q["ci90_pp"]],
                       [p["cells"], p["diff_pp"], p["ci95_pp"], p["ci90_pp"]]))
    # --- consistency: exact against c1_results.json principal.exact_graded ----------------------------------------
    eg = c1["principal"]["exact_graded"]
    for lab in PANDAS + ENGINES:
        q = eg["by_label"][lab]
        checks.append(("exact %s introduced pure (c1)" % lab, q["notebooks_introduced_DIFF_pure"]["num"],
                       X["notebooks"][lab]["introduced_DIFF_all"]))
        checks.append(("exact %s introduced heuristic (c1)" % lab, q["notebooks_introduced_DIFF_heuristic"]["num"],
                       X["notebooks"][lab]["introduced_DIFF_heuristic_all"]))
        checks.append(("exact %s clean_E2 DIFF (c1)" % lab, [q["clean_E2_DIFF"]["num"], q["clean_E2_DIFF"]["den"]],
                       [X["clean_E2"][lab]["clean_E2_DIFF"], X["clean_E2"][lab]["clean_E2_cells"]]))
    for k, p in X["pairs"].items():
        q = eg["pairs"][k]
        checks.append(("exact pair %s (c1)" % k, [q["cells"], q["engine_DIFF"], q["pandas_DIFF"], q["diff_pp"], q["ci95_pp"], q["ci90_pp"], q["reading"]],
                       [p["cells"], p["engine_DIFF"], p["pandas_DIFF"], p["diff_pp"], p["ci95_pp"], p["ci90_pp"], p["reading"]]))
    bad = [c for c in checks if c[1] != c[2]]
    for b in bad:
        print("MISMATCH", b[0], json.dumps(b[1])[:300], json.dumps(b[2])[:300])

    known_inexact = sorted("%s|%s|%d" % x for x in printed16
                           if "%s|%s|%d" % x not in ovr)
    changed = {}
    for lab in PANDAS + ENGINES:
        changed[lab] = {k: [B["notebooks"][lab][k], X["notebooks"][lab][k]] for k in
                        ("error_free", "agreeing", "introduced_DIFF_all", "introduced_DIFF", "introduced_DIFF_heuristic_all",
                         "introduced_DIFF_heuristic")}
        changed[lab]["failure_decomposition"] = [B["failure_decomposition"][lab], X["failure_decomposition"][lab]]
        changed[lab]["error_free_confirmed"] = [B["error_free_confirmed"][lab], X["error_free_confirmed"][lab]]
        changed[lab]["failure_decomposition_unchanged"] = B["failure_decomposition"][lab] == X["failure_decomposition"][lab]
    drop_in = ("modin", "fireducks", "pyarrow_backend")
    readings = {
        "exact_introduced_DIFF_range_all": [min(X["notebooks"][l]["introduced_DIFF_all"] for l in PANDAS + ENGINES),
                                            max(X["notebooks"][l]["introduced_DIFF_all"] for l in PANDAS + ENGINES)],
        "exact_introduced_DIFF_range": [min(X["notebooks"][l]["introduced_DIFF"] for l in PANDAS + ENGINES),
                                        max(X["notebooks"][l]["introduced_DIFF"] for l in PANDAS + ENGINES)],
        "exact_introduced_DIFF_range_heuristic": [min(X["notebooks"][l]["introduced_DIFF_heuristic"] for l in PANDAS + ENGINES),
                                                  max(X["notebooks"][l]["introduced_DIFF_heuristic"] for l in PANDAS + ENGINES)],
        "base_introduced_DIFF_range_all": [min(B["notebooks"][l]["introduced_DIFF_all"] for l in PANDAS + ENGINES),
                                           max(B["notebooks"][l]["introduced_DIFF_all"] for l in PANDAS + ENGINES)],
        "base_introduced_DIFF_range": [min(B["notebooks"][l]["introduced_DIFF"] for l in PANDAS + ENGINES),
                                       max(B["notebooks"][l]["introduced_DIFF"] for l in PANDAS + ENGINES)],
        "exact_drop_in_diff_pp_range": [min(X["pairs"]["%s-%s" % (e, v)]["diff_pp"] for e in drop_in for v in PANDAS),
                                        max(X["pairs"]["%s-%s" % (e, v)]["diff_pp"] for e in drop_in for v in PANDAS)],
        "exact_readings": {k: p["reading"] for k, p in X["pairs"].items()},
        "exact_within_2pp": {k: p["within_2pp"] for k, p in X["pairs"].items()},
        "exact_agreeing_range_drop_in": [min(X["notebooks"][l]["agreeing"] for l in drop_in),
                                         max(X["notebooks"][l]["agreeing"] for l in drop_in)]}
    out = {"generated_from": {"compare_tag": "d" + T.COMPARE, "harness_tag": T.HARNESS,
                              "overrides": "icde27/analysis/r5_capture/c1_overrides.json graded (%d cells)" % len(ovr),
                              "bootstrap": {"resamples": N_BOOT, "seed": SEED, "unit": "notebook", "interval": "percentile"}},
           "consistency_checks": {"n": len(checks), "mismatches": len(bad)},
           "definitions": {"introduced_DIFF_all": "a notebook with a cell whose grade worsens to DIFF (pure definition), all cells",
                           "introduced_DIFF": "as introduced_DIFF_all, without the 16 printed-form cells of the single rater (in the exact basis only the one without an exact encoding still differs)",
                           "introduced_DIFF_heuristic_all": "as introduced_DIFF_all with the heuristic of Section IV (59 cells inherited)",
                           "introduced_DIFF_heuristic": "as introduced_DIFF with the heuristic of Section IV",
                           "error_free": "as r5_reliability.json", "agreeing": "as r5_reliability.json"},
           "known_artifacts_without_override": known_inexact,
           "base": B, "exact": X, "changed_base_to_exact": changed, "readings": readings}
    with open(OUT + ".tmp", "w") as f:
        json.dump(out, f, indent=1)
    os.replace(OUT + ".tmp", OUT)
    print("checks %d, mismatches %d" % (len(checks), len(bad)))
    for lab in PANDAS + ENGINES:
        print("  %-16s %s" % (lab, json.dumps(changed[lab])))
    for k in X["pairs"]:
        p, q = B["pairs"][k], X["pairs"][k]
        print("  %-22s base %4d %+5.2f %s | exact %4d %+5.2f %s %s %s" % (k, p["cells"], p["diff_pp"], p["ci95_pp"], q["cells"],
              q["diff_pp"], q["ci95_pp"], q["ci90_pp"], q["reading"]))
    for e in ENGINES:
        print("  nbpair agreeing %s-p30 base %s exact %s" % (e, json.dumps(B["notebook_pairs"]["%s-p30" % e]["agreeing"]),
                                                            json.dumps(X["notebook_pairs"]["%s-p30" % e]["agreeing"])))
    print("known artifacts without override:", known_inexact)
    print("readings", json.dumps(readings))
    if bad:
        raise SystemExit("consistency check failed (%d of %d)" % (len(bad), len(checks)))


if __name__ == "__main__":
    sys.exit(main())

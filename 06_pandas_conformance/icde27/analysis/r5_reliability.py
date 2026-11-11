#!/usr/bin/env python3
"""Unconditional notebook reliability beside the conditional DIFF comparison, contrast variants and the failure
decomposition (review round R5; ICDE 2027 copy; written 2026-11-10).

Read-only on results/{conf_1x,drift}/raw (compare outputs and run records), results/summary.json,
results/rootcause/{taxonomy_conf1x,paper_provenance}.json and icde27/analysis/{r1_cells,r1_hand_attribution,
r4_audit,r5_uncertainty}.json and r4_cell_flags.csv; writes only icde27/analysis/r5_reliability.json. Memory below
2 GB.

    cd ..
    /usr/bin/time -l .venv/bin/python 06_pandas_conformance-ICDE/icde27/analysis/r5_reliability.py

Common notebook outcomes (every configuration, the pandas versions included; per notebook of the 102):
  error-free     the run completed (no crash, memory stop, notebook timeout or setup error) and no scored cell has
                 a failure class (ERR, TIMEOUT, CRASH, KILLED, MEMORY, NOTRUN, SETUP_ERR): Table IV's OK column;
  agreeing       error-free and every scored cell equal to the reference at E4 or finer (no DIFF, no UNCOMPARABLE);
  agreeing_E2    error-free and every scored cell equal at E2 or finer.
Paired notebook contrasts: engine minus pandas version, share of the 102 notebooks with the outcome, percentile
interval over 10,000 notebook resamples.
Conditional DIFF contrasts (cells clean under both, as r1_cells.py): pooled over cells (the published estimand),
notebook-weighted (each notebook's paired DIFF difference with equal weight, over notebooks with at least one such
cell), on strictly clean cells (clean@E0 under both), and on the certain cells of r5_uncertainty.json.
Failure decomposition: each notebook that is not error-free counted once, by its first failure in cell order:
dependency crash (Bodo's legacy-JIT import with numba 0.65.1, the six nb_crash runs, return code 14), native crash
(FireDucks' segmentation fault), memory cap (summed process-tree RSS above 96 GB), time limit (600 s cell or 3,600 s
notebook timeout), and raised errors by the cell's kind and cause (rootcause_taxonomy rules): an API the engine does
not implement or whose execution model differs (unsupported API, Dask's partitioned inference and lazy partition
model), an error on supported API (engine error, errors on Arrow-backed data, other engine causes), an API removed or
changed by pandas, and an error raised on inputs that already differed (an earlier value or type difference made
visible as an error). Error-free notebooks are split into those without and with an introduced DIFF (pure
definition, the 16 printed-form cells excluded), and the latter by whether some introduced DIFF cell has a cause that
a reproducer or probe confirms on that configuration.
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
OUT = os.path.join(HERE, "r5_reliability.json")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R1 = load_module("r1_cells", os.path.join(HERE, "r1_cells.py"))
N_BOOT, SEED = R1.N_BOOT, R1.SEED
ENGINES, PANDAS, LABELS = R1.ENGINES, R1.PANDAS, R1.LABELS
EXCLUDED, FAIL = R1.EXCLUDED, R1.FAIL
boot_share, stable_key = R1.boot_share, R1.stable_key
UNSUPPORTED = {"engine_unsupported_api", "partitioned_type_inference", "lazy_partition_model"}
PANDAS_CHANGE_PREFIX = ("offset_alias_removed", "removed_deprecated_api", "int_key_positional_fallback_removed",
                        "setitem_incompatible_dtype_raises", "str_dtype_errors", "p3_stricter_validation",
                        "cow_chained_assignment")


def main():
    T = load_module("rootcause_taxonomy", os.path.join(PROJ, "scripts", "rootcause_taxonomy.py"))
    summary = json.load(open(os.path.join(PROJ, "results", "summary.json")))
    r1 = json.load(open(os.path.join(HERE, "r1_cells.json")))
    r4 = json.load(open(os.path.join(HERE, "r4_audit.json")))
    r5u = json.load(open(os.path.join(HERE, "r5_uncertainty.json")))
    hand = json.load(open(os.path.join(HERE, "r1_hand_attribution.json")))
    printed16 = {(r["label"], r["nb"], r["cell"]) for r in hand["rows"] if r["cause"] == "printed_form_comparison"}
    evid = {}
    with open(os.path.join(HERE, "r4_cell_flags.csv")) as f:
        for row in csv.DictReader(f):
            evid[row["id"]] = row["cause_evidence"]
    uncertain = set()
    with open(os.path.join(HERE, "r5_printed_flags.csv")) as f:
        for row in csv.DictReader(f):
            uncertain.add((row["configuration"], row["nb"], int(row["cell"])))

    cells, meta, runrec, example = {}, {}, {}, {}
    for campaign in ("conf_1x", "drift"):
        root, best = T.select_outputs(campaign, T.COMPARE)
        for (label, nb, sc), (_, r, p) in sorted(best.items()):
            if (campaign, label) not in LABELS:
                continue
            # the paper's example of a source and a manifestation (Section IV) and the one output above the matching
            # budget (Section IV), recorded here so that the number check needs no raw compare output
            if (label, nb) == ("pyarrow_backend", "pradeepjeya/allstate-encoding-high-cardinality-features"):
                xc = {c["i"]: c for c in r["cells"]}
                example["source_manifestation"] = {
                    "configuration": label, "nb": nb,
                    "cells": {str(i): {"cls": xc[i]["cls"], "clean_level": xc[i].get("clean_level")} for i in (0, 2, 3, 4)},
                    "manifestation_output": "catfeatures",
                    "manifestation_fail_E4": xc[2]["outputs"]["catfeatures"]["fails"]["E4"]}
            if (label, nb) == ("pyarrow_backend", "sudheer259/house-price-prediction"):
                mc = next(c for c in r["cells"] if c["i"] == 86)
                example["match_budget"] = {"configuration": label, "nb": nb, "cell": 86, "cls": mc["cls"],
                                           "clean_level": mc.get("clean_level"),
                                           "match_limit_levels": sorted({L for o in mc["outputs"].values() for L in (o.get("match_limit") or [])})}
            m = r["meta"]
            meta[(campaign, label, nb)] = m
            rr = json.load(open(os.path.join(PROJ, m["eng_record"])))
            runrec[(label, nb)] = {"status": rr.get("status"), "returncode": rr.get("returncode")}
            cl = r["cells"]
            t_idx = next((k for k, c in enumerate(cl) if c.get("cls") == "TIMEOUT" or c.get("cls_raw") == "TIMEOUT"), None)
            for k, c in enumerate(cl):
                d = {"nb": nb, "i": c["i"], "cls": c["cls"], "clean": c.get("clean_level"),
                     "post_timeout": t_idx is not None and k > t_idx, "kind": None, "cause": None}
                if c["cls"] not in ("E0", "NOOUT", "REF_ERR", "NONDET"):
                    n = T.normalise_cell(campaign, label, nb, c)
                    n["code"] = T.cell_code(nb, c["i"])
                    d["cause"], d["kind"], _ = T.classify_cell(n)
                cells.setdefault((campaign, label), []).append(d)
    lab_campaign = {lab: camp for camp, lab in LABELS}

    def kind_pure(c):
        return "introduced" if c["cause"] == "order_propagated" else c["kind"]

    checks = []
    nbs_all = sorted({nb for (camp, lab, nb) in meta})
    assert len(nbs_all) == 102

    # --- notebook outcomes ------------------------------------------------------------------------------------------
    outcome = {}
    for (campaign, label), cl in sorted(cells.items()):
        by_nb = collections.defaultdict(list)
        for c in cl:
            by_nb[c["nb"]].append(c)
        O = {}
        for nb in nbs_all:
            sc = [c for c in by_nb.get(nb, []) if c["cls"] not in EXCLUDED]
            st = meta[(campaign, label, nb)].get("eng_status")
            ef = st == "completed" and not any(c["cls"] in FAIL for c in by_nb.get(nb, []))
            O[nb] = {"error_free": ef,
                     "agreeing": ef and all(c["cls"] in ("E0", "E1", "E2", "E3", "E4") for c in sc),
                     "agreeing_E2": ef and all(c["cls"] in ("E0", "E1", "E2") for c in sc),
                     "introduced_DIFF": any(kind_pure(c) == "introduced" and c["cls"] == "DIFF"
                                            and (label, nb, c["i"]) not in printed16 for c in by_nb.get(nb, []))}
        outcome[label] = O
        checks.append(("r1 %s no_engine_failure" % label, r1["by_label"][label]["notebooks"]["no_engine_failure"]["num"],
                       sum(o["error_free"] for o in O.values())))
        checks.append(("r4 no_printed off %s notebooks" % label,
                       r4["exception"]["by_variant"]["no_printed"]["by_label"][label]["off"]["notebooks_introduced_DIFF"]["num"],
                       sum(o["introduced_DIFF"] for o in O.values())))

    def nb_share(label, key):
        ind = {nb: int(outcome[label][nb][key]) for nb in nbs_all}
        b = boot_share(ind, {nb: 1 for nb in nbs_all}, "%s|nb|%s" % (label, key))
        return {"num": b["num"], "share": b["share"], "ci95": b["ci95"]}

    def nb_pair(e, v, key):
        a = np.array([outcome[e][nb][key] for nb in nbs_all], float)
        b = np.array([outcome[v][nb][key] for nb in nbs_all], float)
        rng = np.random.default_rng([SEED, stable_key("nbpair|%s|%s|%s" % (e, v, key))])
        idx = rng.integers(0, len(nbs_all), size=(N_BOOT, len(nbs_all)))
        d = (a[idx].mean(1) - b[idx].mean(1)) * 100
        ci = [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]
        return {"engine": int(a.sum()), "pandas": int(b.sum()), "diff_pp": round(float((a.mean() - b.mean()) * 100), 3),
                "diff_notebooks": int(a.sum() - b.sum()), "ci95_pp": [round(x, 3) for x in ci],
                "both": int((a * b).sum()), "engine_only": int((a * (1 - b)).sum()), "pandas_only": int(((1 - a) * b).sum()),
                "reading": "more often" if ci[0] > 0 else ("less often" if ci[1] < 0 else "not distinguishable")}

    notebooks = {lab: {k: nb_share(lab, k) for k in ("error_free", "agreeing", "agreeing_E2", "introduced_DIFF")}
                 for lab in PANDAS + ENGINES}
    for lab in PANDAS + ENGINES:
        o = outcome[lab]
        notebooks[lab]["error_free_with_introduced_DIFF"] = sum(o[nb]["error_free"] and o[nb]["introduced_DIFF"] for nb in nbs_all)
        notebooks[lab]["error_free_without_introduced_DIFF"] = sum(o[nb]["error_free"] and not o[nb]["introduced_DIFF"] for nb in nbs_all)
    nb_pairs = {"%s-%s" % (e, v): {k: nb_pair(e, v, k) for k in ("error_free", "agreeing", "agreeing_E2")}
                for e in ENGINES for v in PANDAS}

    # --- conditional DIFF contrasts: pooled, notebook-weighted, strict, certain --------------------------------------
    def clean_set(label, levels, drop=None):
        camp = lab_campaign[label]
        return {(c["nb"], c["i"]): c["cls"] == "DIFF" for c in cells[(camp, label)]
                if c["cls"] not in EXCLUDED and not c["post_timeout"] and c["clean"] in levels
                and not (drop and (label, c["nb"], c["i"]) in drop)}

    def contrast(e, v, levels, weighting, drop=None):
        de, dv = clean_set(e, levels, drop), clean_set(v, levels, drop)
        ok_nb = {nb for (camp, lab, nb), m in meta.items() if camp == "conf_1x" and lab == e
                 and os.path.basename(m.get("ref_record") or "") == os.path.basename((meta.get(("drift", v, nb)) or {}).get("ref_record") or "")}
        common = [k for k in sorted(de) if k in dv and k[0] in ok_nb]
        if drop is not None:   # a cell uncertain in either comparison leaves the pair
            common = [k for k in common if (e, k[0], k[1]) not in drop and (v, k[0], k[1]) not in drop]
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
        if weighting == "pooled":
            d = (a[idx].sum(1) - b[idx].sum(1)) / n[idx].sum(1) * 100
            est = (a.sum() - b.sum()) / n.sum() * 100
        else:
            per = (a - b) / n
            d = per[idx].mean(1) * 100
            est = per.mean() * 100
        ci95 = [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]
        ci90 = [float(np.percentile(d, 5)), float(np.percentile(d, 95))]
        return {"cells": int(n.sum()), "notebooks": len(nbs), "engine_DIFF": int(a.sum()), "pandas_DIFF": int(b.sum()),
                "diff_pp": round(float(est), 3), "ci95_pp": [round(x, 3) for x in ci95], "ci90_pp": [round(x, 3) for x in ci90],
                "reading": "more often" if ci95[0] > 0 else ("less often" if ci95[1] < 0 else "not distinguishable")}

    E2 = ("E0", "E1", "E2")
    contrasts = {}
    for e in ENGINES:
        for v in PANDAS:
            k = "%s-%s" % (e, v)
            contrasts[k] = {"pooled_E2": contrast(e, v, E2, "pooled"),
                            "notebook_weighted_E2": contrast(e, v, E2, "notebook"),
                            "pooled_E0": contrast(e, v, ("E0",), "pooled"),
                            "pooled_E2_certain": contrast(e, v, E2, "pooled", drop=uncertain)}
            q = r1["pairwise_vs_pandas_clean_E2"][k]
            p = contrasts[k]["pooled_E2"]
            checks.append(("r1 pair %s" % k, [q["cells"], q["notebooks"], q["diff_pp"], q["ci95_pp"], q["ci90_pp"]],
                           [p["cells"], p["notebooks"], p["diff_pp"], p["ci95_pp"], p["ci90_pp"]]))
            u = r5u["pairs"][k]["certain"]
            pc = contrasts[k]["pooled_E2_certain"]
            checks.append(("r5u certain %s" % k, [u["cells"], u["notebooks"], u["diff_pp"], u["ci95_pp"]],
                           [pc["cells"], pc["notebooks"], pc["diff_pp"], pc["ci95_pp"]]))

    # --- failure decomposition ---------------------------------------------------------------------------------------
    cats = ("dependency crash", "native crash", "memory cap", "time limit", "unsupported API or execution model",
            "error on supported API", "API removed or changed by pandas", "error after an earlier difference", "other")
    decomp = {}
    for (campaign, label), cl in sorted(cells.items()):
        by_nb = collections.defaultdict(list)
        for c in cl:
            by_nb[c["nb"]].append(c)
        D = collections.Counter()
        detail = collections.defaultdict(list)
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
            else:   # ERR
                if first["kind"] == "propagated":
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
            detail[cat].append([nb, first["i"] if first else None, first["cls"] if first else st["status"],
                                first["cause"] if first else None, first["kind"] if first else None])
        o = outcome[label]
        ef_diff = [nb for nb in nbs_all if o[nb]["error_free"] and o[nb]["introduced_DIFF"]]
        confirmed = []
        for nb in ef_diff:
            ids = ["%s|%s|%d" % (label, nb, c["i"]) for c in by_nb[nb]
                   if kind_pure(c) == "introduced" and c["cls"] == "DIFF" and (label, nb, c["i"]) not in printed16]
            if any(("confirms on this engine" in evid.get(i, "")) or ("differs on this configuration" in evid.get(i, ""))
                   for i in ids):
                confirmed.append(nb)
        decomp[label] = {"not_error_free": dict(D), "first_failures": dict(detail),
                         "error_free": sum(o[nb]["error_free"] for nb in nbs_all),
                         "error_free_no_introduced_DIFF": sum(o[nb]["error_free"] and not o[nb]["introduced_DIFF"] for nb in nbs_all),
                         "error_free_introduced_DIFF": len(ef_diff),
                         "error_free_introduced_DIFF_reproduced_cause": len(confirmed)}
        assert sum(D.values()) + decomp[label]["error_free"] == 102, label
        checks.append(("decomp %s sums" % label, 102, sum(D.values()) + decomp[label]["error_free"]))

    bad = [c for c in checks if c[1] != c[2]]
    if bad:
        print(json.dumps([list(map(str, b)) for b in bad], indent=1)[:6000])
        raise SystemExit("consistency check failed (%d of %d)" % (len(bad), len(checks)))

    drop_in = ("modin", "fireducks", "pyarrow_backend")
    readings = {
        "notebook_weighted_drop_in_range": [min(contrasts["%s-%s" % (e, v)]["notebook_weighted_E2"]["diff_pp"] for e in drop_in for v in PANDAS),
                                            max(contrasts["%s-%s" % (e, v)]["notebook_weighted_E2"]["diff_pp"] for e in drop_in for v in PANDAS)],
        "notebook_weighted_readings": {k: c["notebook_weighted_E2"]["reading"] for k, c in contrasts.items()},
        "strict_E0_readings": {k: c["pooled_E0"]["reading"] for k, c in contrasts.items()},
        "error_free_vs_p30": {e: nb_pairs["%s-p30" % e]["error_free"]["reading"] for e in ENGINES},
        "agreeing_vs_p30": {e: nb_pairs["%s-p30" % e]["agreeing"]["reading"] for e in ENGINES}}
    out = {"generated_from": {"summary_generated_utc": summary["generated_utc"], "compare_tag": "d" + T.COMPARE,
                              "harness_tag": T.HARNESS, "bootstrap": r1["generated_from"]["bootstrap"]},
           "consistency_checks": {"n": len(checks), "mismatches": 0},
           "definitions": {"error_free": "run completed and no scored cell has a failure class (Table IV OK)",
                           "agreeing": "error-free and every scored cell equal at E4 or finer (no DIFF, no UNCOMPARABLE)",
                           "agreeing_E2": "error-free and every scored cell equal at E2 or finer",
                           "introduced_DIFF": "a cell whose grade worsens to DIFF (pure definition), the 16 printed-form cells excluded"},
           "notebooks": notebooks, "notebook_pairs": nb_pairs, "contrasts": contrasts, "failure_decomposition": decomp,
           "failure_categories": cats, "readings": readings, "examples": example}
    with open(OUT + ".tmp", "w") as f:
        json.dump(out, f, indent=1)
    os.replace(OUT + ".tmp", OUT)

    print("checks %d, mismatches 0" % len(checks))
    for lab in PANDAS + ENGINES:
        N = notebooks[lab]
        print("  %-16s error-free %3d %s | agreeing %3d %s | agreeing_E2 %3d | introDIFF %2d | EF+DIFF %2d"
              % (lab, N["error_free"]["num"], N["error_free"]["ci95"], N["agreeing"]["num"], N["agreeing"]["ci95"],
                 N["agreeing_E2"]["num"], N["introduced_DIFF"]["num"], N["error_free_with_introduced_DIFF"]))
    for k, p in nb_pairs.items():
        print("  nbpair %-22s EF %+5.1f %s %s | agree %+5.1f %s %s | agreeE2 %+5.1f %s"
              % (k, p["error_free"]["diff_pp"], p["error_free"]["ci95_pp"], p["error_free"]["reading"],
                 p["agreeing"]["diff_pp"], p["agreeing"]["ci95_pp"], p["agreeing"]["reading"],
                 p["agreeing_E2"]["diff_pp"], p["agreeing_E2"]["reading"]))
    for k, c in contrasts.items():
        print("  %-22s pooled %4d/%3d %+5.2f %s | nbw %3d %+5.2f [%+.2f, %+.2f] %s | E0 %4d/%3d %+5.2f [%+.2f, %+.2f] %s | certain %+5.2f %s"
              % (k, c["pooled_E2"]["cells"], c["pooled_E2"]["notebooks"], c["pooled_E2"]["diff_pp"], c["pooled_E2"]["reading"],
                 c["notebook_weighted_E2"]["notebooks"], c["notebook_weighted_E2"]["diff_pp"], c["notebook_weighted_E2"]["ci95_pp"][0],
                 c["notebook_weighted_E2"]["ci95_pp"][1], c["notebook_weighted_E2"]["reading"], c["pooled_E0"]["cells"],
                 c["pooled_E0"]["notebooks"], c["pooled_E0"]["diff_pp"], c["pooled_E0"]["ci95_pp"][0], c["pooled_E0"]["ci95_pp"][1],
                 c["pooled_E0"]["reading"], c["pooled_E2_certain"]["diff_pp"], c["pooled_E2_certain"]["reading"]))
    for lab in PANDAS + ENGINES:
        d = decomp[lab]
        print("  decomp %-16s EF %3d (noDIFF %3d, DIFF %2d, reproduced %2d) not-EF %s"
              % (lab, d["error_free"], d["error_free_no_introduced_DIFF"], d["error_free_introduced_DIFF"],
                 d["error_free_introduced_DIFF_reproduced_cause"], d["not_error_free"]))
    print("readings", json.dumps(readings))


if __name__ == "__main__":
    sys.exit(main())

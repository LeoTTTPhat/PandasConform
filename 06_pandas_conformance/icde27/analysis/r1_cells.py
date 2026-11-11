#!/usr/bin/env python3
"""Review R1 analyses on the stored per-cell results (ICDE 2027 copy; written 2026-10-26).

Read-only on results/ and data/; writes only icde27/analysis/r1_cells.json. Memory well below 2 GB.

    cd ..
    /usr/bin/time -l .venv/bin/python 06_pandas_conformance/icde27/analysis/r1_cells.py

Population and rules are those of analyze.py and scripts/rootcause_taxonomy.py, reused as modules:
  * one compare output per (label, notebook, scale), the one computed with ref#2 first, then the newest;
  * excluded cells: REF_ERR, NONDET, NOOUT, SETUP_ERR; post-timeout cascades leave the clean views;
  * views: all comparable cells; clean@E2 (clean_level E0..E2); clean@E3 (E0..E3); clean only at E3;
  * cell kinds (introduced / propagated / cascade / harness) and causes from rootcause_taxonomy.classify_cell,
    with the cell code attached exactly as its build() does; the per-label kind counts are checked against
    results/rootcause/taxonomy_conf1x.json and the clean@E2 class counts against results/summary.json, and the
    script stops on any mismatch.
Items (review R1, icde27/reviews/R1_independent.md):
  B1(ii)  E4 cells split by the first failing check at E3: index names or object names only, index values, other.
  B1(iii) DIFF cells split by the worst output's failing check at E4: value, dtype family, structure (kind, shape,
          labels), output missing in the engine.
  B1(v)   clean@E3 view: DIFF and ERR shares among cells whose inputs agree at E3 or finer, and only at E3.
  B2      engine against each pandas version on the cells clean@E2 under BOTH (pairwise, not the seven-way set):
          paired DIFF-share difference, notebook-cluster bootstrap 95% and 90% intervals, equivalence (two one-sided
          tests at 5%) within +-1 and +-2 percentage points.
  B3      notebook-level counts with 95% bootstrap intervals: notebooks with at least one introduced DIFF cell (a
          difference that the cell itself creates and that no relaxation removes; no error), with at least one
          introduced ERR cell, and notebooks that ran every cell without an engine-side failure.
  B4      ERR cells split into introduced, name-error cascades and errors on inputs that already differed.
  B7      warnings recorded in the run records for every cell of the causes Table II calls silent, engine and
          reference side, with the Copy-on-Write chained-assignment warning counted separately.
  B8      introduced cells grouped by mechanism: parallel or lazy execution, representation choice, missing or
          erroneous support, harness artefact, pandas evolution (our classification; see MECHANISM; every cause of a
          pandas version is pandas evolution).
  B10     macro (per-notebook mean) clean@E2 DIFF shares and the leave-one-notebook-out range of the pooled share.
"""
import collections
import glob
import importlib.util
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "r1_cells.json")
N_BOOT = 10000
SEED = 20261026
ENGINES = ["pyarrow_backend", "modin", "fireducks", "bodo", "dask"]
PANDAS = ["p15", "p30"]
LABELS = [("conf_1x", e) for e in ENGINES] + [("drift", p) for p in PANDAS]
EXCLUDED = ("REF_ERR", "NONDET", "NOOUT", "SETUP_ERR")
FAIL = ("ERR", "TIMEOUT", "CRASH", "KILLED", "MEMORY", "NOTRUN", "SETUP_ERR")
LEVELS = ["E0", "E1", "E2", "E3", "E4"]
COW_RX = re.compile(r"chained assignment|ChainedAssignment|SettingWithCopy", re.I)

# B8: mechanism behind each cause (our classification, from the cause definitions in Table II and the engines'
# documentation cited there); causes that are not listed are pandas-version causes ("pandas evolution"). The
# hand-attributed unattributed cells (r1_hand_attribution.json) use the same five classes.
MECHANISM = {
    # parallel or lazy execution: differences inherent in partitioned, parallel or deferred evaluation
    # representation choice: the engine returns another but design-inherent representation (types, sentinels, names)
    "approximate_quantile": "parallel or lazy execution",          # approximate quantile algorithms (Bodo, Dask)
    "float_rounding_within_tolerance": "parallel or lazy execution",  # parallel or vectorised float summation order
    "row_order_ties": "parallel or lazy execution",                # unstable or partition-order ties in sorts and groups
    "partitioned_type_inference": "parallel or lazy execution",    # per-partition dtype inference (Dask)
    "lazy_partition_model": "parallel or lazy execution",          # lazy, partitioned evaluation model (Dask)
    "arrow_backed_dtypes": "representation choice",  # Arrow-native result types
    "missing_sentinel_repr": "representation choice",  # None instead of NaN for strings (Arrow nulls)
    "index_not_preserved": "representation choice",
    "int_float_nullable_repr": "representation choice",
    "scalar_type_numpy": "representation choice",
    "axis_names_lost": "representation choice",
    "dtype_inference_differs": "representation choice",
    "na_comparison_masks": "representation choice",  # pd.NA three-valued comparisons on Arrow data
    "str_dtype_object_checks": "representation choice",
    "cow_chained_assignment": "representation choice",  # copy semantics (FireDucks)
    "chunked_csv_type_inference": "representation choice",
    # missing or erroneous support
    "engine_bug_error": "missing or erroneous support",
    "engine_unsupported_api": "missing or erroneous support",
    "arrow_dtype_errors": "missing or erroneous support",
    "engine_crash_timeout": "missing or erroneous support",
    "engine_bug_silent": "missing or erroneous support",
    "engine_corr_wrong_values": "missing or erroneous support",
    "cr_only_line_endings": "missing or erroneous support",
}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def boot_share(num_by_nb, den_by_nb, key, n_boot=N_BOOT):
    """Pooled share sum(num)/sum(den) with a percentile notebook-cluster bootstrap interval."""
    nbs = sorted(den_by_nb)
    num = np.array([num_by_nb.get(nb, 0) for nb in nbs], float)
    den = np.array([den_by_nb[nb] for nb in nbs], float)
    if not len(nbs) or den.sum() == 0:
        return None
    rng = np.random.default_rng([SEED, stable_key(key)])
    idx = rng.integers(0, len(nbs), size=(n_boot, len(nbs)))
    with np.errstate(invalid="ignore", divide="ignore"):
        bs = num[idx].sum(1) / den[idx].sum(1)
    bs = bs[np.isfinite(bs)]
    return {"share": round(float(num.sum() / den.sum()), 6), "num": int(num.sum()), "den": int(den.sum()),
            "notebooks": len(nbs), "ci95": [round(float(np.percentile(bs, 2.5)), 6), round(float(np.percentile(bs, 97.5)), 6)]}


def stable_key(s):
    import zlib
    return zlib.crc32(s.encode())


def main():
    T = load_module("rootcause_taxonomy", os.path.join(PROJ, "scripts", "rootcause_taxonomy.py"))
    summary = json.load(open(os.path.join(PROJ, "results", "summary.json")))
    tax = json.load(open(os.path.join(PROJ, "results", "rootcause", "taxonomy_conf1x.json")))
    out = {"generated_from": {"summary_generated_utc": summary["generated_utc"], "taxonomy_generated": tax["generated"],
                              "compare_tag": "d" + T.COMPARE, "harness_tag": T.HARNESS, "bootstrap": {"resamples": N_BOOT,
                              "seed": SEED, "unit": "notebook", "interval": "percentile"}}}
    cells = {}       # (campaign, label) -> list of cell dicts
    meta = {}        # (campaign, label, nb) -> compare meta
    for campaign in ("conf_1x", "drift"):
        root, best = T.select_outputs(campaign, T.COMPARE)
        for (label, nb, sc), (_, r, p) in sorted(best.items()):
            if (campaign, label) not in LABELS:
                continue
            meta[(campaign, label, nb)] = r["meta"]
            cl = r["cells"]
            t_idx = next((k for k, c in enumerate(cl) if c.get("cls") == "TIMEOUT" or c.get("cls_raw") == "TIMEOUT"), None)
            for k, c in enumerate(cl):
                d = {"nb": nb, "i": c["i"], "cls": c["cls"], "clean": c.get("clean_level"),
                     "post_timeout": t_idx is not None and k > t_idx, "outputs": c.get("outputs") or {},
                     "families": c.get("families") or [], "kind": None, "cause": None}
                if c["cls"] not in ("E0", "NOOUT", "REF_ERR", "NONDET"):
                    n = T.normalise_cell(campaign, label, nb, c)
                    n["code"] = T.cell_code(nb, c["i"])
                    cause, kind, why = T.classify_cell(n)
                    d["kind"], d["cause"] = kind, cause
                cells.setdefault((campaign, label), []).append(d)

    # --- consistency checks against the taxonomy and summary.json -----------------------------------------
    checks = []
    for (campaign, label), cl in cells.items():
        pe = tax["per_engine"].get("%s:%s" % (campaign, label), {})
        got = collections.Counter(c["kind"] for c in cl if c["kind"])
        for k in ("introduced", "propagated", "cascade", "harness"):
            checks.append(("taxonomy %s:%s %s" % (campaign, label, k), pe.get(k, 0), got.get(k, 0)))
        sv = summary["campaigns"][campaign]["engines"][label]["views"]["clean_E2"]["counts"]
        got2 = collections.Counter(c["cls"] for c in cl if c["cls"] not in EXCLUDED and not c["post_timeout"]
                                   and c["clean"] in ("E0", "E1", "E2"))
        for k in ("DIFF", "ERR", "E0", "E2"):
            checks.append(("summary %s:%s clean_E2 %s" % (campaign, label, k), sv.get(k, 0), got2.get(k, 0)))
    bad = [c for c in checks if c[1] != c[2]]
    out["consistency_checks"] = {"n": len(checks), "mismatches": [list(b) for b in bad]}
    if bad:
        print(json.dumps(out["consistency_checks"], indent=1))
        raise SystemExit("consistency check failed")

    def view(cl, name):
        for c in cl:
            if c["cls"] in EXCLUDED:
                continue
            if name == "all":
                yield c
                continue
            if c["post_timeout"]:
                continue
            if name == "clean_E2" and c["clean"] in ("E0", "E1", "E2"):
                yield c
            elif name == "clean_E3" and c["clean"] in ("E0", "E1", "E2", "E3"):
                yield c
            elif name == "clean_E3_only" and c["clean"] == "E3":
                yield c

    def share_of(cl, vname, pred, key):
        num, den = collections.Counter(), collections.Counter()
        for c in view(cl, vname):
            den[c["nb"]] += 1
            num[c["nb"]] += bool(pred(c))
        return boot_share(num, den, key)

    hand = {}
    hp = os.path.join(HERE, "r1_hand_attribution.json")
    if os.path.exists(hp):
        for r in json.load(open(hp))["rows"]:
            hand[(r["label"], r["nb"], r["cell"])] = r["mechanism"]
    res = {}
    for (campaign, label), cl in sorted(cells.items()):
        R = res.setdefault(label, {"campaign": campaign})
        # B1(v) clean@E3 view
        R["views"] = {}
        for vname in ("clean_E2", "clean_E3", "clean_E3_only"):
            R["views"][vname] = {cls: share_of(cl, vname, lambda c, k=cls: c["cls"] == k,
                                               "%s|%s|%s" % (label, vname, cls)) for cls in ("DIFF", "ERR")}
            R["views"][vname]["le_E2"] = share_of(cl, vname, lambda c: c["cls"] in ("E0", "E1", "E2"),
                                                  "%s|%s|leE2" % (label, vname))
        # B4 ERR decomposition (all comparable cells)
        errs = [c for c in view(cl, "all") if c["cls"] == "ERR"]
        R["err_decomposition_all"] = {
            "err_cells": len(errs),
            "introduced": sum(1 for c in errs if c["kind"] == "introduced"),
            "name_error_cascade": sum(1 for c in errs if c["cause"] == "cascade_undefined_name"),
            "on_inputs_that_differed": sum(1 for c in errs if c["kind"] == "propagated"),
            "other": sum(1 for c in errs if c["kind"] not in ("introduced", "propagated") and c["cause"] != "cascade_undefined_name"),
            "comparable_cells": sum(1 for _ in view(cl, "all"))}
        # B1(ii) E4 split (cells at E4 in the all view and in the clean@E2 view)
        def e4_reason(c):
            rs = set()
            for o in c["outputs"].values():
                if o.get("level") != "E4":
                    continue
                f = (o.get("fails") or {}).get("E3", "")
                rs.add("names" if f.startswith("names") else "index_values" if f.startswith("index") else "other:" + f.split(":")[0])
            return "index_values" if "index_values" in rs else ("names" if rs == {"names"} else ",".join(sorted(rs)))
        for vname in ("all", "clean_E2"):
            R.setdefault("e4_split", {})[vname] = dict(collections.Counter(e4_reason(c) for c in view(cl, vname) if c["cls"] == "E4"))
        # B1(iii) DIFF split by the worst output's failing check at E4
        def diff_reason(c):
            rs = []
            for o in c["outputs"].values():
                if o.get("level") != "DIFF":
                    continue
                if o.get("reason") in ("missing_in_engine", "absent_in_engine") or str(o.get("reason", "")).startswith("deleted"):
                    rs.append("missing output")
                    continue
                f = (o.get("fails") or {}).get("E4", "") or ""
                head = f.split(":")[0]
                if head in ("values", "scalar_value"):
                    rs.append("value")
                elif head in ("dtype_family", "scalar_family", "scalar_tag", "scalar_type", "tz", "dtype", "labels_dtype"):
                    rs.append("dtype family")
                elif head in ("kind", "shape", "labels", "ncols", "index", "array_type"):
                    rs.append("structure")
                else:
                    rs.append("other:" + head)
            order = ["value", "dtype family", "structure", "missing output"]
            for r_ in order:
                if r_ in rs:
                    return r_
            return rs[0] if rs else "no DIFF output"
        for vname in ("all", "clean_E2"):
            R.setdefault("diff_split", {})[vname] = dict(collections.Counter(diff_reason(c) for c in view(cl, vname) if c["cls"] == "DIFF"))
        # B3 notebook-level counts
        nbs = sorted({c["nb"] for c in cl})
        ind = {"introduced_DIFF": {}, "introduced_ERR": {}, "no_engine_failure": {}}
        for nb in nbs:
            cn = [c for c in cl if c["nb"] == nb]
            ind["introduced_DIFF"][nb] = any(c["kind"] == "introduced" and c["cls"] == "DIFF" for c in cn)
            ind["introduced_ERR"][nb] = any(c["kind"] == "introduced" and c["cls"] == "ERR" for c in cn)
            st = meta[(campaign, label, nb)].get("eng_status")
            ind["no_engine_failure"][nb] = st == "completed" and not any(c["cls"] in FAIL for c in cn)
        R["notebooks"] = {k: boot_share({nb: int(v) for nb, v in d.items()}, {nb: 1 for nb in d}, "%s|nb|%s" % (label, k))
                          for k, d in ind.items()}
        # B10 macro shares and leave-one-notebook-out (clean@E2 DIFF)
        num, den = collections.Counter(), collections.Counter()
        for c in view(cl, "clean_E2"):
            den[c["nb"]] += 1
            num[c["nb"]] += c["cls"] == "DIFF"
        per = [num[nb] / den[nb] for nb in den]
        tot_n, tot_d = sum(num.values()), sum(den.values())
        loo = [(tot_n - num[nb]) / (tot_d - den[nb]) for nb in den if tot_d - den[nb] > 0]
        R["clean_E2_DIFF_robustness"] = {"pooled": round(tot_n / tot_d, 6), "macro_mean_over_notebooks": round(float(np.mean(per)), 6),
                                         "notebooks": len(den), "leave_one_notebook_out_min_max": [round(min(loo), 6), round(max(loo), 6)]}
        # B8 mechanisms (introduced cells by mechanism)
        mech_of = (lambda cause: "pandas evolution") if label in PANDAS else \
            (lambda cause: MECHANISM.get(cause, "unattributed" if cause == "unattributed" else "pandas evolution"))
        mech = collections.Counter()
        for c in cl:
            if c["kind"] == "introduced":
                mech[mech_of(c["cause"])] += 1
        R["introduced_by_mechanism"] = dict(mech)
        mech_diff = collections.Counter(mech_of(c["cause"]) for c in cl if c["kind"] == "introduced" and c["cls"] == "DIFF")
        R["introduced_DIFF_by_mechanism"] = dict(mech_diff)
        # the same with the hand attributions of the unattributed cells (r1_hand_attribution.json), when present
        if hand:
            merged = collections.Counter()
            for c in cl:
                if c["kind"] == "introduced" and c["cls"] == "DIFF":
                    if c["cause"] == "unattributed":
                        merged[hand.get((label, c["nb"], c["i"]), "unattributed")] += 1
                    else:
                        merged[mech_of(c["cause"])] += 1
            R["introduced_DIFF_by_mechanism_with_hand"] = dict(merged)

    # --- B2 pairwise paired comparisons (engine vs pandas version on cells clean@E2 under both) ---------------
    def ce2(campaign, label):
        d = {}
        for c in view(cells[(campaign, label)], "clean_E2"):
            d[(c["nb"], c["i"])] = c["cls"] == "DIFF"
        return d
    pairs = {}
    for e in ENGINES:
        de = ce2("conf_1x", e)
        for v in PANDAS:
            dv = ce2("drift", v)
            # same reference record and the same cell list in both outputs (as for the seven-way view)
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
            rng = np.random.default_rng([SEED, stable_key("pair|%s|%s" % (e, v))])
            idx = rng.integers(0, len(nbs), size=(N_BOOT, len(nbs)))
            diff = (a[idx].sum(1) - b[idx].sum(1)) / n[idx].sum(1) * 100
            est = (a.sum() - b.sum()) / n.sum() * 100
            ci95 = [float(np.percentile(diff, 2.5)), float(np.percentile(diff, 97.5))]
            ci90 = [float(np.percentile(diff, 5)), float(np.percentile(diff, 95))]
            pairs["%s-%s" % (e, v)] = {
                "cells": int(n.sum()), "notebooks": len(nbs), "engine_DIFF_pct": round(a.sum() / n.sum() * 100, 3),
                "pandas_DIFF_pct": round(b.sum() / n.sum() * 100, 3), "diff_pp": round(est, 3),
                "ci95_pp": [round(x, 3) for x in ci95], "ci90_pp": [round(x, 3) for x in ci90],
                "equivalent_within_1pp": bool(ci90[0] > -1 and ci90[1] < 1),
                "equivalent_within_2pp": bool(ci90[0] > -2 and ci90[1] < 2),
                "reading": "more often" if ci95[0] > 0 else ("less often" if ci95[1] < 0 else "not distinguishable"),
                "notebooks_excluded_ref_mismatch": len({k[0] for k in de} - ok_nb)}
    out["pairwise_vs_pandas_clean_E2"] = pairs

    # --- B7 warnings for the silent causes -------------------------------------------------------------------
    sev = {k: (v.get("severity") or "") for k, v in tax["causes"].items()}
    silent = sorted(k for k, s in sev.items() if s == "silent_value_change")
    rec_cache = {}

    def rec_cells(path):
        if path not in rec_cache:
            if len(rec_cache) > 64:
                rec_cache.clear()
            r = json.load(open(os.path.join(PROJ, path)))
            rec_cache[path] = {c.get("i"): c for c in r.get("cells", [])}
        return rec_cache[path]

    warn = {}
    for cause in silent:
        for camp, lab, nb, i, cls in tax["causes"][cause]["cells"]:
            if (camp, lab) not in LABELS:
                continue
            m = meta[(camp, lab, nb)]
            ec = rec_cells(m["eng_record"]).get(i, {})
            rc = rec_cells(m["ref_record"]).get(i, {})
            ew, rw = ec.get("warnings") or [], rc.get("warnings") or []
            w = warn.setdefault(cause, {}).setdefault("%s:%s" % (camp, lab), collections.Counter())
            w["cells"] += 1
            w["engine_warned"] += bool(ew)
            w["reference_warned"] += bool(rw)
            w["engine_chained_assignment_warning"] += any(COW_RX.search((x.get("category") or "") + " " + (x.get("message") or "")) for x in ew)
            w["reference_chained_assignment_warning"] += any(COW_RX.search((x.get("category") or "") + " " + (x.get("message") or "")) for x in rw)
            for x in ew:
                w["engine_category:" + str(x.get("category"))] += 1
            for x in rw:
                w["reference_category:" + str(x.get("category"))] += 1
    out["warnings_silent_causes"] = {c: {k: dict(v) for k, v in d.items()} for c, d in warn.items()}
    out["by_label"] = res
    out["mechanism_classification"] = MECHANISM
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(out, f, indent=1, sort_keys=False)
    os.replace(tmp, OUT)
    print("checks %d, mismatches %d" % (len(checks), len(bad)))
    for lab, R in res.items():
        print(lab, "ERR", R["err_decomposition_all"], "nb", {k: (v["num"], v["ci95"]) for k, v in R["notebooks"].items()})


if __name__ == "__main__":
    sys.exit(main())

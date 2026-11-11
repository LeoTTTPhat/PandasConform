#!/usr/bin/env python3
"""Sensitivity and localization analyses for review round R3 (ICDE 2027 copy; written 2026-11-10).

Read-only on results/ and on the existing icde27/analysis/*.json; writes only icde27/analysis/r3_sensitivity.json.
Memory well below 2 GB (about the size of r1_cells.py).

    cd ..
    /usr/bin/time -l .venv/bin/python 06_pandas_conformance-ICDE/icde27/analysis/r3_sensitivity.py

Population, views, bootstrap and pairing are those of r1_cells.py (its constants and boot_share are imported) and
the cell kinds are those of scripts/rootcause_taxonomy.py. The baseline variant must reproduce r1_cells.json (views,
notebook counts, paired comparisons) and summary.json (cell and class counts); the script stops on any mismatch.

Variants (the removed cells or notebooks leave every configuration and every view):
  base         as published;
  no_printed   without the 16 DIFF cells whose difference comes from comparing a container that holds frames (or an
               object without an exact encoding) by its printed form (r1_hand_attribution.json, cause
               printed_form_comparison); the captures hold only that printed form, so these cells cannot be
               re-compared structurally without new runs;
  no_printed_readers  as no_printed, and the later cells that read a container of a printed-form cell and whose other
               inputs agree at E2 or finer count as clean@E2 (as if the container agreed at E2), with their own class;
               no_printed and this variant bracket a structural re-comparison of the containers;
  no_reduced   without the 10 notebooks that ran without pre-cell input capture
               (results/rootcause/paper_provenance.json corpus.input_over_capture_cap);
  no_both      both removals.
Per variant and configuration: scored cells and the DIFF share (all view), clean@E2 cells with the <=E2 and DIFF
shares and notebook-bootstrap 95% intervals, the ratio of the two DIFF shares, the paired DIFF difference against
each pandas version on the cells clean@E2 under both (90% and 95% intervals, +-1 and +-2 point readings),
notebooks with an introduced DIFF and without an engine-side failure, introduced cells and introduced DIFF cells,
and introduced DIFF cells by mechanism (rules alone and with the single-rater hand attribution).

Other items:
  localization  introduced cells and introduced DIFF cells by the clean level of their inputs: E0 = every captured
                input bit-identical; E1-E4 = the inputs agree only modulo row order, a widening or the float
                tolerance, the missing sentinel, or the index, so the cell may expose a difference that an earlier
                cell made; and the clean@E2 DIFF cells by clean level and kind;
  order_rule    the DIFF cells that rootcause_taxonomy.classify_cell counts as inherited although their class is
                coarser than their clean level (no cause rule matched and the inputs agree only at E1 or E4):
                clean levels, configurations, and how many have a positional operation in their code;
  strict_rule   notebooks with an introduced DIFF if those cells counted as introduced (the stated rule alone);
  downstream    later cells that read an output of a printed-form cell (they are inherited and outside clean@E2);
  hand          the hand-attributed cells by confidence, with and without the printed-form cells, and those in
                the 10 notebooks without pre-cell input capture;
  cause_evidence  causes that name a mechanism (not one of the five symptom-level groups) and how many a script
                reproduces;
  scale_paired  the 5x-minus-1x change of the DIFF share and of the share at E2 or finer over all scored cells of the
                conf_5x notebooks, paired by notebook (the pooled shares equal summary.json scale_effect), also without
                the notebooks in which the engine stopped at 5x.
"""
import collections
import importlib.util
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "r3_sensitivity.json")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R1 = load_module("r1_cells", os.path.join(HERE, "r1_cells.py"))
N_BOOT, SEED = R1.N_BOOT, R1.SEED
ENGINES, PANDAS, LABELS = R1.ENGINES, R1.PANDAS, R1.LABELS
EXCLUDED, FAIL, MECHANISM = R1.EXCLUDED, R1.FAIL, R1.MECHANISM
boot_share, stable_key = R1.boot_share, R1.stable_key
LEVELS = ["E0", "E1", "E2", "E3", "E4"]
POSITIONAL = re.compile(r"\.head\(|\.tail\(|\.iloc\[|\[\s*-?\d*\s*:\s*-?\d*\s*\]|\.nlargest\(|\.nsmallest\(")
VARIANTS = ("base", "no_printed", "no_printed_readers", "no_reduced", "no_both")


def main():
    T = load_module("rootcause_taxonomy", os.path.join(PROJ, "scripts", "rootcause_taxonomy.py"))
    summary = json.load(open(os.path.join(PROJ, "results", "summary.json")))
    tax = json.load(open(os.path.join(PROJ, "results", "rootcause", "taxonomy_conf1x.json")))
    prov = json.load(open(os.path.join(PROJ, "results", "rootcause", "paper_provenance.json")))
    r1 = json.load(open(os.path.join(HERE, "r1_cells.json")))
    hand = json.load(open(os.path.join(HERE, "r1_hand_attribution.json")))
    reduced = set(prov["corpus"]["input_over_capture_cap"]["notebooks"])
    printed = {(r["label"], r["nb"], r["cell"]) for r in hand["rows"] if r["cause"] == "printed_form_comparison"}
    hand_mech = {(r["label"], r["nb"], r["cell"]): r["mechanism"] for r in hand["rows"]}
    out = {"generated_from": {"summary_generated_utc": summary["generated_utc"], "taxonomy_generated": tax["generated"],
                              "r1_cells": "icde27/analysis/r1_cells.json", "compare_tag": "d" + T.COMPARE,
                              "harness_tag": T.HARNESS, "bootstrap": r1["generated_from"]["bootstrap"]},
           "removed": {"printed_form_cells": sorted(list(k) for k in printed), "reduced_capture_notebooks": sorted(reduced)}}
    assert len(printed) == 16 and len(reduced) == 10

    # --- cells, exactly as r1_cells.py loads them (plus the inputs and code needed below) -----------------------
    cells, meta = {}, {}
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
                     "input_levels": c.get("input_levels") or {}, "inputs_from": c.get("inputs_from"),
                     "kind": None, "cause": None, "code": None}
                if c["cls"] not in ("E0", "NOOUT", "REF_ERR", "NONDET"):
                    n = T.normalise_cell(campaign, label, nb, c)
                    n["code"] = T.cell_code(nb, c["i"])
                    d["cause"], d["kind"], _ = T.classify_cell(n)
                    d["code"] = n["code"]
                cells.setdefault((campaign, label), []).append(d)

    # later cells that read a DIFF output (container) of a printed-form cell, per configuration
    readers = {}
    for (campaign, label), cl in sorted(cells.items()):
        for c in cl:
            if (label, c["nb"], c["i"]) not in printed:
                continue
            names = {n for n, o in c["outputs"].items() if o.get("level") == "DIFF" and n != "__last__"}
            for c2 in cl:
                if c2["nb"] == c["nb"] and c2["i"] > c["i"] and names & set(c2["input_levels"]):
                    others = [l for n, l in c2["input_levels"].items() if n not in names]
                    readers.setdefault((label, c2["nb"], c2["i"]), {"names": set(), "others_le_E2": True})
                    readers[(label, c2["nb"], c2["i"])]["names"] |= names & set(c2["input_levels"])
                    if not all(l in ("E0", "E1", "E2") for l in others):
                        readers[(label, c2["nb"], c2["i"])]["others_le_E2"] = False
    RANK = T.RANK

    def clean_of(label, c, variant):
        if variant == "no_printed_readers" and readers.get((label, c["nb"], c["i"]), {}).get("others_le_E2"):
            return "E2"
        return c["clean"]

    def kind_of(label, c, variant):
        """The cell's kind; in no_printed_readers, a reader whose other inputs agree at E2 or finer gets the kind
        that its own class has with inputs clean at E2 (cascades and harness outcomes keep their kind)."""
        if variant == "no_printed_readers" and readers.get((label, c["nb"], c["i"]), {}).get("others_le_E2") \
                and c["kind"] not in ("cascade", "harness") and c["cls"] in RANK:
            return "introduced" if RANK[c["cls"]] > RANK["E2"] else ("propagated" if c["cls"] != "E0" else None)
        return c["kind"]

    missing = [lab for lab in LABELS if lab not in cells]
    if missing:
        raise SystemExit("no per-cell compare outputs for %s (unpack the results first)" % missing)

    def keep(label, c, variant):
        if variant in ("no_printed", "no_printed_readers", "no_both") and (label, c["nb"], c["i"]) in printed:
            return False
        if variant in ("no_reduced", "no_both") and c["nb"] in reduced:
            return False
        return True

    def view(label, cl, name, variant):
        for c in cl:
            if c["cls"] in EXCLUDED or not keep(label, c, variant):
                continue
            if name == "all":
                yield c
            elif not c["post_timeout"] and name == "clean_E2" and clean_of(label, c, variant) in ("E0", "E1", "E2"):
                yield c

    def share_of(label, cl, vname, pred, key, variant):
        num, den = collections.Counter(), collections.Counter()
        for c in view(label, cl, vname, variant):
            den[c["nb"]] += 1
            num[c["nb"]] += bool(pred(c))
        return boot_share(num, den, key)

    def mech_of(label, cause):
        if label in PANDAS:
            return "pandas evolution"
        return MECHANISM.get(cause, "unattributed" if cause == "unattributed" else "pandas evolution")

    # --- per variant and configuration ------------------------------------------------------------------------
    res = {}
    for variant in VARIANTS:
        V = res.setdefault(variant, {"by_label": {}, "pairs": {}})
        for (campaign, label), cl in sorted(cells.items()):
            R = V["by_label"].setdefault(label, {"campaign": campaign})
            allv = list(view(label, cl, "all", variant))
            R["all_cells"] = len(allv)
            R["all_DIFF"] = sum(c["cls"] == "DIFF" for c in allv)
            R["all_DIFF_share"] = round(R["all_DIFF"] / len(allv), 6)
            R["clean_E2"] = {"DIFF": share_of(label, cl, "clean_E2", lambda c: c["cls"] == "DIFF",
                                              "%s|clean_E2|DIFF" % label, variant),
                             "le_E2": share_of(label, cl, "clean_E2", lambda c: c["cls"] in ("E0", "E1", "E2"),
                                               "%s|clean_E2|leE2" % label, variant)}
            R["ratio_all_over_clean_E2_DIFF"] = round(R["all_DIFF_share"] / R["clean_E2"]["DIFF"]["share"], 3)
            kept = [c for c in cl if keep(label, c, variant)]
            R["introduced"] = sum(kind_of(label, c, variant) == "introduced" for c in kept)
            R["introduced_DIFF"] = sum(kind_of(label, c, variant) == "introduced" and c["cls"] == "DIFF" for c in kept)
            nbs = sorted({c["nb"] for c in kept})
            ind = {"introduced_DIFF": {}, "no_engine_failure": {}}
            for nb in nbs:
                cn = [c for c in kept if c["nb"] == nb]
                ind["introduced_DIFF"][nb] = any(kind_of(label, c, variant) == "introduced" and c["cls"] == "DIFF" for c in cn)
                st = meta[(campaign, label, nb)].get("eng_status")
                ind["no_engine_failure"][nb] = st == "completed" and not any(c["cls"] in FAIL for c in cn)
            R["notebooks"] = {k: boot_share({nb: int(v) for nb, v in d.items()}, {nb: 1 for nb in d}, "%s|nb|%s" % (label, k))
                              for k, d in ind.items()}
            rule, merged = collections.Counter(), collections.Counter()
            for c in kept:
                if kind_of(label, c, variant) == "introduced" and c["cls"] == "DIFF":
                    m = mech_of(label, c["cause"]) if c["kind"] == "introduced" else "reader of a printed-form container"
                    rule[m] += 1
                    merged[hand_mech.get((label, c["nb"], c["i"]), "unattributed") if c["cause"] == "unattributed" else m] += 1
            R["introduced_DIFF_by_mechanism_rules"] = dict(rule)
            R["introduced_DIFF_by_mechanism_with_hand"] = dict(merged)

        # paired comparisons, as r1_cells.py B2
        def ce2(campaign, label):
            return {(c["nb"], c["i"]): c["cls"] == "DIFF" for c in view(label, cells[(campaign, label)], "clean_E2", variant)}
        for e in ENGINES:
            de = ce2("conf_1x", e)
            for v in PANDAS:
                dv = ce2("drift", v)
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
                V["pairs"]["%s-%s" % (e, v)] = {
                    "cells": int(n.sum()), "notebooks": len(nbs), "engine_DIFF_pct": round(a.sum() / n.sum() * 100, 3),
                    "pandas_DIFF_pct": round(b.sum() / n.sum() * 100, 3), "diff_pp": round(est, 3),
                    "ci95_pp": [round(x, 3) for x in ci95], "ci90_pp": [round(x, 3) for x in ci90],
                    "equivalent_within_1pp": bool(ci90[0] > -1 and ci90[1] < 1),
                    "equivalent_within_2pp": bool(ci90[0] > -2 and ci90[1] < 2),
                    "reading": "more often" if ci95[0] > 0 else ("less often" if ci95[1] < 0 else "not distinguishable")}
        # summaries that the paper prints
        drop_in = ("modin", "fireducks", "pyarrow_backend")
        V["readings"] = {
            "drop_in_within_2pp_of_both": all(V["pairs"]["%s-%s" % (e, v)]["equivalent_within_2pp"] for e in drop_in for v in PANDAS),
            "drop_in_within_1pp_of_both": any(V["pairs"]["%s-%s" % (e, v)]["equivalent_within_1pp"] for e in drop_in for v in PANDAS),
            "readings": {k: p["reading"] for k, p in V["pairs"].items()},
            "drop_in_diff_pp_range": [float(min(V["pairs"]["%s-%s" % (e, v)]["diff_pp"] for e in drop_in for v in PANDAS)),
                                      float(max(V["pairs"]["%s-%s" % (e, v)]["diff_pp"] for e in drop_in for v in PANDAS))],
            "drop_in_ci90_extremes": [min(V["pairs"]["%s-%s" % (e, v)]["ci90_pp"][0] for e in drop_in for v in PANDAS),
                                      max(V["pairs"]["%s-%s" % (e, v)]["ci90_pp"][1] for e in drop_in for v in PANDAS)],
            "drop_in_max_abs_diff_pp": max(abs(V["pairs"]["%s-%s" % (e, v)]["diff_pp"]) for e in drop_in for v in PANDAS),
            "drop_in_all_not_distinguishable": all(V["pairs"]["%s-%s" % (e, v)]["reading"] == "not distinguishable" for e in drop_in for v in PANDAS),
            "drop_in_outside_2pp": sorted("%s-%s" % (e, v) for e in drop_in for v in PANDAS if not V["pairs"]["%s-%s" % (e, v)]["equivalent_within_2pp"]),
            "pair_cells_range": [min(p["cells"] for p in V["pairs"].values()), max(p["cells"] for p in V["pairs"].values())],
            "ratio_range_drop_in_and_pandas": [min(V["by_label"][x]["ratio_all_over_clean_E2_DIFF"] for x in drop_in + tuple(PANDAS)),
                                               max(V["by_label"][x]["ratio_all_over_clean_E2_DIFF"] for x in drop_in + tuple(PANDAS))],
            "introduced_DIFF_notebooks_range": [min(V["by_label"][x]["notebooks"]["introduced_DIFF"]["num"] for x in V["by_label"]),
                                                max(V["by_label"][x]["notebooks"]["introduced_DIFF"]["num"] for x in V["by_label"])],
            "notebooks": V["by_label"]["modin"]["notebooks"]["introduced_DIFF"]["den"]}

    # --- baseline must reproduce r1_cells.json and summary.json -------------------------------------------------
    checks = []
    B = res["base"]
    for label, R in B["by_label"].items():
        rl = r1["by_label"][label]
        for k in ("DIFF", "le_E2"):
            checks.append(("r1 %s clean_E2 %s" % (label, k), rl["views"]["clean_E2"][k], R["clean_E2"][k]))
        for k in ("introduced_DIFF", "no_engine_failure"):
            checks.append(("r1 %s notebooks %s" % (label, k), rl["notebooks"][k], R["notebooks"][k]))
        checks.append(("r1 %s mechanism with hand" % label, rl.get("introduced_DIFF_by_mechanism_with_hand"),
                       R["introduced_DIFF_by_mechanism_with_hand"]))
        checks.append(("r1 %s mechanism rules" % label, rl["introduced_DIFF_by_mechanism"], R["introduced_DIFF_by_mechanism_rules"]))
        sv = summary["campaigns"][R["campaign"]]["engines"][label]["views"]
        checks.append(("summary %s all cells" % label, sv["all"]["cells"], R["all_cells"]))
        checks.append(("summary %s all DIFF" % label, sv["all"]["counts"]["DIFF"], R["all_DIFF"]))
        checks.append(("summary %s clean_E2 cells" % label, sv["clean_E2"]["cells"], R["clean_E2"]["DIFF"]["den"]))
        checks.append(("summary %s clean_E2 DIFF" % label, sv["clean_E2"]["counts"]["DIFF"], R["clean_E2"]["DIFF"]["num"]))
        checks.append(("taxonomy %s introduced" % label, tax["per_engine"]["%s:%s" % (R["campaign"], label)]["introduced"], R["introduced"]))
    for k, p in B["pairs"].items():
        q = {kk: vv for kk, vv in r1["pairwise_vs_pandas_clean_E2"][k].items() if kk != "notebooks_excluded_ref_mismatch"}
        checks.append(("r1 pair %s" % k, q, p))
    bad = [c for c in checks if c[1] != c[2]]
    out["consistency_checks"] = {"n": len(checks), "mismatches": [list(b) for b in bad]}
    if bad:
        print(json.dumps(out["consistency_checks"], indent=1)[:4000])
        raise SystemExit("consistency check failed")
    out["variants"] = res

    # --- localization by input clean level ----------------------------------------------------------------------
    loc = {}
    for (campaign, label), cl in sorted(cells.items()):
        intro = [c for c in cl if c["kind"] == "introduced"]
        idiff = [c for c in intro if c["cls"] == "DIFF"]
        ce2diff = [c for c in view(label, cl, "clean_E2", "base") if c["cls"] == "DIFF"]
        loc[label] = {"introduced_by_clean": dict(collections.Counter(c["clean"] for c in intro)),
                      "introduced_DIFF_by_clean": dict(collections.Counter(c["clean"] for c in idiff)),
                      "introduced_DIFF_by_clean_no_printed": dict(collections.Counter(
                          c["clean"] for c in idiff if (label, c["nb"], c["i"]) not in printed)),
                      "clean_E2_DIFF_by_clean_and_kind": dict(collections.Counter(
                          "%s|%s" % (c["clean"], c["kind"]) for c in ce2diff))}
    # introduced cells of each cause by the clean level of their inputs (all seven configurations)
    by_cause = collections.defaultdict(collections.Counter)
    for (campaign, label), cl in sorted(cells.items()):
        for c in cl:
            if c["kind"] == "introduced":
                by_cause[c["cause"]]["%s|%s" % (c["clean"], c["cls"] if c["cls"] == "DIFF" else "other")] += 1
    groups = {"engines": ENGINES, "pandas": PANDAS}
    tot = {}
    for g, labs in groups.items():
        t = collections.Counter()
        t2 = collections.Counter()
        for lab in labs:
            t.update(loc[lab]["introduced_DIFF_by_clean"])
            t2.update(loc[lab]["introduced_DIFF_by_clean_no_printed"])
        tot[g] = {"introduced_DIFF": sum(t.values()), "introduced_DIFF_strict_clean": t.get("E0", 0),
                  "introduced_DIFF_by_clean": dict(t), "introduced_DIFF_no_printed": sum(t2.values()),
                  "introduced_DIFF_no_printed_strict_clean": t2.get("E0", 0)}
    out["localization"] = {"by_label": loc, "totals": tot,
                           "introduced_by_cause_clean_class": {k: dict(v) for k, v in sorted(by_cause.items())}}

    # causes that name a mechanism (not one of the symptom-level groups) and how many a script reproduces
    rc = prov["taxonomy"]["reproducer_coverage"]
    symptom = set(prov["taxonomy"]["engine_symptom_level_cells"])
    not_repro = set(rc["no_reproducer"]) | set(rc["engine_probe_not_reproduced_only"])
    n_causes = prov["taxonomy"]["root_causes"]
    out["cause_evidence"] = {"causes": n_causes, "symptom_level": sorted(symptom),
                             "mechanism_causes": n_causes - len(symptom),
                             "mechanism_causes_reproduced": n_causes - len(symptom) - len(not_repro - symptom),
                             "symptom_causes_reproduced": len(symptom) - len(not_repro & symptom),
                             "reproduced_total": rc["reproduced"]}
    assert out["cause_evidence"]["mechanism_causes_reproduced"] + out["cause_evidence"]["symptom_causes_reproduced"] == rc["reproduced"]

    # --- the order rule (DIFF cells counted as inherited although coarser than their clean level) ----------------
    oc = []
    for (campaign, label), cl in sorted(cells.items()):
        for c in cl:
            if c["cause"] == "order_propagated":
                oc.append({"campaign": campaign, "label": label, "nb": c["nb"], "i": c["i"], "clean": c["clean"],
                           "positional_op_in_code": bool(POSITIONAL.search(c["code"] or ""))})
    # the pilot cell of the taxonomy (bodo_dw) for completeness
    tax_order = tax["causes"]["order_propagated"]
    pilot_cells = [x for x in tax_order["cells"] if x[0] == "pilot"]
    if pilot_cells:
        root, best = T.select_outputs("pilot", T.COMPARE)
        for camp, lab, nb, i, cls in pilot_cells:
            for (label, nb2, sc), (_, r, p) in best.items():
                if label == lab and nb2 == nb:
                    c = next(x for x in r["cells"] if x["i"] == i)
                    oc.append({"campaign": camp, "label": lab, "nb": nb, "i": i, "clean": c.get("clean_level"),
                               "positional_op_in_code": bool(POSITIONAL.search(T.cell_code(nb, i)))})
    assert len(oc) == tax_order["n_cells"], (len(oc), tax_order["n_cells"])
    out["order_rule"] = {"cells": len(oc), "notebooks": len({x["nb"] for x in oc}),
                         "by_clean": dict(collections.Counter(x["clean"] for x in oc)),
                         "by_label": dict(collections.Counter(x["label"] for x in oc)),
                         "positional_op_in_code": sum(x["positional_op_in_code"] for x in oc),
                         "in_clean_E2_view": sum(x["clean"] in ("E0", "E1", "E2") for x in oc),
                         "rule": "rootcause_taxonomy.classify_cell: an introduced cell (class coarser than its clean level) "
                                 "that no cause rule matches, with class DIFF and clean level E1 or E4, is counted as propagated",
                         "list": oc}
    # notebooks with an introduced DIFF if these cells counted as introduced (the stated rule alone)
    strict = {}
    for (campaign, label), cl in sorted(cells.items()):
        nbs_rule = {c["nb"] for c in cl if c["kind"] == "introduced" and c["cls"] == "DIFF"}
        nbs_strict = nbs_rule | {c["nb"] for c in cl if c["cause"] == "order_propagated"}
        strict[label] = {"rule": len(nbs_rule), "stated_rule_alone": len(nbs_strict)}
    out["strict_rule_notebooks"] = strict

    # --- later cells that read an output of a printed-form cell ---------------------------------------------------
    down = []
    for (campaign, label), cl in sorted(cells.items()):
        for c in cl:
            if (label, c["nb"], c["i"]) not in printed:
                continue
            names = {n for n, o in c["outputs"].items() if o.get("level") == "DIFF" and n != "__last__"}
            for c2 in cl:
                if c2["nb"] == c["nb"] and c2["i"] > c["i"] and names & set(c2["input_levels"]):
                    others = {n: l for n, l in c2["input_levels"].items() if n not in names}
                    down.append({"label": label, "nb": c["nb"], "printed_cell": c["i"], "cell": c2["i"], "cls": c2["cls"],
                                 "clean": c2["clean"], "kind": c2["kind"], "names": sorted(names & set(c2["input_levels"])),
                                 "other_inputs_le_E2": all(l in ("E0", "E1", "E2") for l in others.values())})
    out["downstream_of_printed"] = {"cells": len({(d["label"], d["nb"], d["cell"]) for d in down}),
                                    "by_cls": dict(collections.Counter(d["cls"] for d in down)),
                                    "other_inputs_le_E2": sum(d["other_inputs_le_E2"] for d in down), "list": down}

    # --- hand attribution --------------------------------------------------------------------------------------
    rows = hand["rows"]
    np_rows = [r for r in rows if r["cause"] != "printed_form_comparison"]
    out["hand"] = {"cells": len(rows), "by_confidence": dict(collections.Counter(r["confidence"] for r in rows)),
                   "printed_form": len(rows) - len(np_rows),
                   "without_printed": {"cells": len(np_rows),
                                       "by_confidence": dict(collections.Counter(r["confidence"] for r in np_rows)),
                                       "attributed": sum(r["confidence"] != "undetermined" for r in np_rows)},
                   "in_reduced_capture_notebooks": sum(r["nb"] in reduced for r in rows),
                   "in_reduced_by_cause": dict(collections.Counter(r["cause"] for r in rows if r["nb"] in reduced))}
    rule_attr = tax["counts"]["by_kind"]["introduced"] - tax["causes"]["unattributed"]["n_cells"]
    out["attribution_counts"] = {"introduced": tax["counts"]["by_kind"]["introduced"],
                                 "rule_attributed": rule_attr,
                                 "unattributed_by_rules": tax["causes"]["unattributed"]["n_cells"],
                                 "introduced_without_printed": tax["counts"]["by_kind"]["introduced"] - len(printed)}
    # parallel-or-lazy counts of the paper (introduced DIFF), with and without hand attribution and printed cells
    pl = {}
    for lab in ENGINES:
        b = res["base"]["by_label"][lab]
        n = res["no_printed"]["by_label"][lab]
        pl[lab] = {"with_hand": b["introduced_DIFF_by_mechanism_with_hand"].get("parallel or lazy execution", 0),
                   "rules_only": b["introduced_DIFF_by_mechanism_rules"].get("parallel or lazy execution", 0),
                   "rules_unattributed": b["introduced_DIFF_by_mechanism_rules"].get("unattributed", 0),
                   "introduced_DIFF": b["introduced_DIFF"], "introduced_DIFF_no_printed": n["introduced_DIFF"],
                   "rules_unattributed_no_printed": n["introduced_DIFF_by_mechanism_rules"].get("unattributed", 0)}
    out["parallel_or_lazy"] = pl

    # --- scored cells in the reduced-capture notebooks ---------------------------------------------------------
    sc = {}
    for (campaign, label), cl in sorted(cells.items()):
        allv = [c for c in cl if c["cls"] not in EXCLUDED]
        sc[label] = {"scored": len(allv), "scored_in_reduced": sum(c["nb"] in reduced for c in allv),
                     "inputs_from_last_captured": sum(c["inputs_from"] == "last_captured" for c in allv)}
    out["reduced_capture_cells"] = sc

    # --- 1x against 5x on the conf_5x notebooks, paired by notebook (all scored cells, as summary.json scale_effect) --
    s30 = None
    sp = {}
    root5, best5 = T.select_outputs("conf_5x", T.COMPARE)
    excl5 = set(summary["campaigns"]["conf_5x"].get("notebooks_excluded", {}))
    for e in ("modin", "fireducks", "bodo"):
        per = {}
        for (label, nb, sc), (_, r, p) in best5.items():
            if label != e or nb in excl5:
                continue
            cl5 = [c for c in r["cells"] if c["cls"] not in EXCLUDED]
            per[nb] = {"5x": [len(cl5), sum(c["cls"] == "DIFF" for c in cl5), sum(c["cls"] in ("E0", "E1", "E2") for c in cl5)]}
        s30 = sorted(per)
        for c in cells[("conf_1x", e)]:
            if c["nb"] in per and c["cls"] not in EXCLUDED:
                v = per[c["nb"]].setdefault("1x", [0, 0, 0])
                v[0] += 1
                v[1] += c["cls"] == "DIFF"
                v[2] += c["cls"] in ("E0", "E1", "E2")
        stopped = sorted(nb for (label, nb, sc), (_, r, p) in best5.items()
                         if label == e and nb in per and r["meta"].get("eng_status") != "completed")

        def paired(nbs, key):
            a = np.array([per[nb]["1x"] for nb in nbs], float)
            b = np.array([per[nb]["5x"] for nb in nbs], float)
            rng = np.random.default_rng([SEED, stable_key(key)])
            idx = rng.integers(0, len(nbs), size=(N_BOOT, len(nbs)))
            res = {"notebooks": len(nbs)}
            for k, col in (("DIFF", 1), ("le_E2", 2)):
                d = (b[idx, col].sum(1) / b[idx, 0].sum(1) - a[idx, col].sum(1) / a[idx, 0].sum(1)) * 100
                est = (b[:, col].sum() / b[:, 0].sum() - a[:, col].sum() / a[:, 0].sum()) * 100
                res[k] = {"change_pp_5x_minus_1x": round(float(est), 3),
                          "ci95_pp": [round(float(np.percentile(d, 2.5)), 3), round(float(np.percentile(d, 97.5)), 3)]}
            return res, a, b
        nbs = [nb for nb in s30 if "1x" in per[nb]]
        res_e, a, b = paired(nbs, "scale|%s" % e)
        se = summary["scale_effect"][e]
        assert (int(a[:, 0].sum()), int(b[:, 0].sum())) == (se["1x"]["cells"], se["5x"]["cells"]), e
        assert abs(a[:, 1].sum() / a[:, 0].sum() - se["1x"]["share"]["DIFF"]) < 1e-6 and \
            abs(b[:, 2].sum() / b[:, 0].sum() - se["5x"]["cum_share"]["<=E2"]) < 1e-6, e
        res_e["notebooks_stopped_at_5x"] = stopped
        if stopped:
            res_e["without_stopped"] = paired([nb for nb in nbs if nb not in stopped], "scale|%s|completed" % e)[0]
        sp[e] = res_e
    out["scale_paired"] = {"definition": "all scored cells of the conf_5x notebooks at 5x (conf_5x) and 1x (conf_1x), pooled "
                                         "shares; percentile interval of the 5x-minus-1x change over notebook resamples "
                                         "(the same notebooks on both sides)", "by_engine": sp,
                           "all_intervals_contain_0": all(sp[e][k]["ci95_pp"][0] <= 0 <= sp[e][k]["ci95_pp"][1]
                                                          for e in sp for k in ("DIFF", "le_E2"))}

    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(out, f, indent=1)
    os.replace(tmp, OUT)

    # --- printout ----------------------------------------------------------------------------------------------
    print("checks %d, mismatches %d" % (len(checks), len(bad)))
    for variant in VARIANTS:
        V = res[variant]
        print("\n==", variant, "notebooks", V["readings"]["notebooks"])
        for lab in PANDAS + ENGINES:
            R = V["by_label"][lab]
            d = R["clean_E2"]["DIFF"]
            print("  %-16s all %4d DIFF %.1f%% | clean@E2 %4d DIFF %.1f%% [%.1f, %.1f] <=E2 %.1f%% | ratio %.2f | intro %4d introDIFF %3d | nb introDIFF %2d okNB %2d"
                  % (lab, R["all_cells"], 100 * R["all_DIFF_share"], d["den"], 100 * d["share"], 100 * d["ci95"][0], 100 * d["ci95"][1],
                     100 * R["clean_E2"]["le_E2"]["share"], R["ratio_all_over_clean_E2_DIFF"], R["introduced"], R["introduced_DIFF"],
                     R["notebooks"]["introduced_DIFF"]["num"], R["notebooks"]["no_engine_failure"]["num"]))
        for k, p in V["pairs"].items():
            print("  pair %-22s n %4d nb %3d diff %+.2f ci95 [%+.2f, %+.2f] ci90 [%+.2f, %+.2f] 2pp %s 1pp %s %s"
                  % (k, p["cells"], p["notebooks"], p["diff_pp"], p["ci95_pp"][0], p["ci95_pp"][1], p["ci90_pp"][0],
                     p["ci90_pp"][1], p["equivalent_within_2pp"], p["equivalent_within_1pp"], p["reading"]))
        print("  readings", {k: v for k, v in V["readings"].items() if k != "readings"})
    print("\nlocalization totals", json.dumps(out["localization"]["totals"]))
    for lab in PANDAS + ENGINES:
        print("  ", lab, out["localization"]["by_label"][lab]["introduced_DIFF_by_clean"],
              out["localization"]["by_label"][lab]["clean_E2_DIFF_by_clean_and_kind"])
    print("order rule", {k: v for k, v in out["order_rule"].items() if k != "list"})
    print("strict rule notebooks", out["strict_rule_notebooks"])
    print("downstream of printed", {k: v for k, v in out["downstream_of_printed"].items() if k != "list"})
    print("hand", out["hand"])
    print("attribution", out["attribution_counts"])
    print("parallel or lazy", out["parallel_or_lazy"])
    print("reduced-capture cells", out["reduced_capture_cells"])


if __name__ == "__main__":
    sys.exit(main())

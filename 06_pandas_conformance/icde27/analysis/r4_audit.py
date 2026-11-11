#!/usr/bin/env python3
"""Exception-off taxonomy view, full sensitivity table, membership lists, ordered cause rules and per-cell flags
(review round R4; ICDE 2027 copy; written 2026-11-10).

Read-only on results/, data/notebook_sets/timing30.json and icde27/analysis/{r1_cells,r3_sensitivity,
r1_hand_attribution}.json; writes only
icde27/analysis/r4_audit.json, r4_audit.md (the same content as tables) and r4_cell_flags.csv. Memory well below
2 GB (the loader of r3_sensitivity.py).

    cd ..
    /usr/bin/time -l .venv/bin/python 06_pandas_conformance-ICDE/icde27/analysis/r4_audit.py

Population, views, bootstrap and pairing are those of r1_cells.py and r3_sensitivity.py (same constants, same
bootstrap keys, so a variant and its exception-off twin use the same resamples); cell kinds and causes are those of
scripts/rootcause_taxonomy.py. The script stops unless its exception-on counts reproduce r3_sensitivity.json and
taxonomy_conf1x.json.

The exception. rootcause_taxonomy.classify_cell counts a cell as inherited (kind "propagated", cause
"order_propagated") when its class is coarser than its clean level (the grade worsens) but no curated entry and no
cause rule explains it, its class is DIFF and its inputs agree only at E1 or E4 (59 cells). Two views:
  exception on   the published, rule-driven view: those 59 cells are inherited;
  exception off  the pure "grade worsens" criterion: a non-E0 cell is introduced iff its class is coarser than the
                 finest level at which all its inputs agree; the 59 cells become introduced and unattributed.
Only quantities computed from kinds can change (introduced counts, notebooks with an introduced DIFF, cause and
mechanism shares, the introduced share of non-E0 cells, Table II's unattributed row, Fig. 4's markers); shares by
class, the clean@E0/E2/E3 views and every paired comparison use classes and clean levels only.

Outputs:
  exception      per artifact variant of r3_sensitivity.py (base, no_printed, no_printed_readers, no_reduced, no_both)
                 and per configuration, with the exception on and off: introduced cells, introduced DIFF cells,
                 notebooks with an introduced DIFF (95% notebook-bootstrap interval), the exception cells kept, and
                 the notebook ranges; totals over the taxonomy (with the pilot cell), localization (strictly clean
                 inputs among the engines' introduced DIFF cells), the introduced share of non-E0 cells, the
                 parallel-or-lazy shares, and the timing notebooks whose Fig. 4 marker would change;
  sensitivity    every contrast (5 engines x 2 pandas versions) in every variant: paired cells (denominator),
                 notebooks, engine and pandas DIFF counts (numerators) and shares, difference, 90% and 95% intervals,
                 reading; and per configuration the unpaired clean@E2 DIFF count, share and interval (recomputed
                 here and checked against r3_sensitivity.json);
  membership     the 16 printed-form cells, the 31 scored readers of their containers with the alternative
                 clean-status rule, the 10 notebooks without pre-cell input capture and the 59 exception cells, as
                 stable IDs (configuration | PandasBench notebook slug at commit ae70611 | 0-based index among the
                 notebook's code cells, empty code cells kept, as src/pconf/nbsource.py load_cells) with the
                 notebook file's SHA-256 from the run record;
  rules          the decision order of classify_cell, the ordered cause rules (index, cause, description, appended
                 for conf_1x) and the exception flag;
  replicate_stability  for the silent causes the paper names (and the single-rater behaviours it probes), the cells in
                 the 10 pilot notebooks of an engine with a replicate and those that differ between its two pilot runs;
  r4_cell_flags.csv  one row per cell whose grade worsens (2,206 cells of the taxonomy population: 7 configurations
                 on 102 notebooks and the pilot's bodo_dw): grade_worsens, assigned_by (curated / rule / none),
                 rule index and cause, exception_applied, kind with the exception on and off, single-rater cause and
                 confidence, cause evidence (reproducer or probe outcome on this configuration), symptom-level
                 flag, printed-form and reduced-capture flags.
"""
import collections
import csv
import importlib.util
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "r4_audit.json")
OUT_MD = os.path.join(HERE, "r4_audit.md")
OUT_CSV = os.path.join(HERE, "r4_cell_flags.csv")


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
VARIANTS = ("base", "no_printed", "no_printed_readers", "no_reduced", "no_both")
TIMING_ENGINES = ("modin", "fireducks", "bodo")


def main():
    T = load_module("rootcause_taxonomy", os.path.join(PROJ, "scripts", "rootcause_taxonomy.py"))
    summary = json.load(open(os.path.join(PROJ, "results", "summary.json")))
    tax = json.load(open(os.path.join(PROJ, "results", "rootcause", "taxonomy_conf1x.json")))
    prov = json.load(open(os.path.join(PROJ, "results", "rootcause", "paper_provenance.json")))
    probes = json.load(open(os.path.join(PROJ, "results", "rootcause", "engine_probe_outcomes.json")))
    kinds_pc = json.load(open(os.path.join(PROJ, "results", "rootcause", "conf1x_paper_counts.json")))["attribution_kinds"]
    r3 = json.load(open(os.path.join(HERE, "r3_sensitivity.json")))
    hand = json.load(open(os.path.join(HERE, "r1_hand_attribution.json")))
    timing30 = json.load(open(os.path.join(PROJ, "data", "notebook_sets", "timing30.json")))["notebooks"]
    reduced = set(prov["corpus"]["input_over_capture_cap"]["notebooks"])
    printed = {(r["label"], r["nb"], r["cell"]) for r in hand["rows"] if r["cause"] == "printed_form_comparison"}
    hand_row = {(r["label"], r["nb"], r["cell"]): r for r in hand["rows"]}
    hand_mech = {k: r["mechanism"] for k, r in hand_row.items()}
    assert len(printed) == 16 and len(reduced) == 10
    rule_index = {}
    for k, (cause, _pred, why) in enumerate(T.RULES):
        rule_index.setdefault((cause, why), k)
    n_appended_from = next(k for k, r in enumerate(T.RULES) if r[0] == "engine_crash_timeout")

    # --- cells, as r3_sensitivity.py loads them, plus the pilot's bodo_dw (taxonomy population) ---------------
    cells, meta, nbsha = {}, {}, {}
    pilot = []
    for campaign in ("conf_1x", "drift", "pilot"):
        root, best = T.select_outputs(campaign, T.COMPARE)
        for (label, nb, sc), (_, r, p) in sorted(best.items()):
            if campaign == "pilot":
                if label != "bodo_dw":
                    continue
            elif (campaign, label) not in LABELS:
                continue
            meta[(campaign, label, nb)] = r["meta"]
            cl = r["cells"]
            t_idx = next((k for k, c in enumerate(cl) if c.get("cls") == "TIMEOUT" or c.get("cls_raw") == "TIMEOUT"), None)
            for k, c in enumerate(cl):
                d = {"nb": nb, "i": c["i"], "cls": c["cls"], "clean": c.get("clean_level"),
                     "post_timeout": t_idx is not None and k > t_idx, "outputs": c.get("outputs") or {},
                     "input_levels": c.get("input_levels") or {}, "kind": None, "cause": None, "why": None,
                     "grade_worsens": False}
                if c["cls"] not in ("E0", "NOOUT", "REF_ERR", "NONDET"):
                    n = T.normalise_cell(campaign, label, nb, c)
                    n["code"] = T.cell_code(nb, c["i"])
                    d["cause"], d["kind"], d["why"] = T.classify_cell(n)
                    d["grade_worsens"] = T.introduced(n)
                if campaign == "pilot":
                    pilot.append(d)
                else:
                    cells.setdefault((campaign, label), []).append(d)
    missing = [lab for lab in LABELS if lab not in cells]
    if missing:
        raise SystemExit("no per-cell compare outputs for %s (unpack the results first)" % missing)
    # notebook file hashes from the run records (stable IDs)
    for (campaign, label, nb), m in meta.items():
        rec = m.get("eng_record")
        if rec and nb not in nbsha:
            try:
                nbsha[nb] = json.load(open(os.path.join(PROJ, rec))).get("nb_sha256")
            except (OSError, ValueError):
                pass

    def exc(c):
        return c["cause"] == "order_propagated"

    def kind(c, exception):
        return "introduced" if (not exception and exc(c)) else c["kind"]

    # readers of a printed-form container (as r3_sensitivity.py)
    readers = {}
    for (campaign, label), cl in sorted(cells.items()):
        for c in cl:
            if (label, c["nb"], c["i"]) not in printed:
                continue
            names = {n for n, o in c["outputs"].items() if o.get("level") == "DIFF" and n != "__last__"}
            for c2 in cl:
                if c2["nb"] == c["nb"] and c2["i"] > c["i"] and names & set(c2["input_levels"]):
                    others = [l for n, l in c2["input_levels"].items() if n not in names]
                    r = readers.setdefault((label, c2["nb"], c2["i"]), {"names": set(), "others_le_E2": True,
                                                                         "printed_cells": set(), "cell": c2})
                    r["names"] |= names & set(c2["input_levels"])
                    r["printed_cells"].add(c["i"])
                    if not all(l in ("E0", "E1", "E2") for l in others):
                        r["others_le_E2"] = False
    RANK = T.RANK

    def clean_of(label, c, variant):
        if variant == "no_printed_readers" and readers.get((label, c["nb"], c["i"]), {}).get("others_le_E2"):
            return "E2"
        return c["clean"]

    def kind_of(label, c, variant, exception):
        k = kind(c, exception)
        if variant == "no_printed_readers" and readers.get((label, c["nb"], c["i"]), {}).get("others_le_E2") \
                and c["kind"] not in ("cascade", "harness") and c["cls"] in RANK:
            return "introduced" if RANK[c["cls"]] > RANK["E2"] else ("propagated" if c["cls"] != "E0" else None)
        return k

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

    # --- A. exception on / off, per variant and configuration ----------------------------------------------------
    exc_res, checks = {}, []
    for variant in VARIANTS:
        V = exc_res.setdefault(variant, {"by_label": {}})
        for (campaign, label), cl in sorted(cells.items()):
            kept = [c for c in cl if keep(label, c, variant)]
            R = V["by_label"].setdefault(label, {"campaign": campaign})
            R["exception_cells_kept"] = sum(exc(c) for c in kept)
            for ex in (True, False):
                tag = "on" if ex else "off"
                ind = {}
                for nb in sorted({c["nb"] for c in kept}):
                    ind[nb] = int(any(kind_of(label, c, variant, ex) == "introduced" and c["cls"] == "DIFF"
                                      for c in kept if c["nb"] == nb))
                nbs = boot_share(ind, {nb: 1 for nb in ind}, "%s|nb|%s" % (label, "introduced_DIFF"))
                R[tag] = {"introduced": sum(kind_of(label, c, variant, ex) == "introduced" for c in kept),
                          "introduced_DIFF": sum(kind_of(label, c, variant, ex) == "introduced" and c["cls"] == "DIFF"
                                                 for c in kept),
                          "notebooks_introduced_DIFF": {"num": nbs["num"], "den": nbs["den"], "ci95": nbs["ci95"]},
                          "notebook_ids": sorted(nb for nb, v in ind.items() if v)}
            R["notebooks_changed"] = sorted(set(R["off"]["notebook_ids"]) - set(R["on"]["notebook_ids"]))
            # exception on must reproduce r3_sensitivity.json
            r3l = r3["variants"][variant]["by_label"][label]
            checks.append(("r3 %s %s introduced" % (variant, label), r3l["introduced"], R["on"]["introduced"]))
            checks.append(("r3 %s %s introduced_DIFF" % (variant, label), r3l["introduced_DIFF"], R["on"]["introduced_DIFF"]))
            checks.append(("r3 %s %s notebooks" % (variant, label), r3l["notebooks"]["introduced_DIFF"],
                           {k: v for k, v in boot_share({nb: int(nb in R["on"]["notebook_ids"]) for nb in
                                                         sorted({c["nb"] for c in kept})},
                                                        {nb: 1 for nb in sorted({c["nb"] for c in kept})},
                                                        "%s|nb|introduced_DIFF" % label).items()}))
        for tag in ("on", "off"):
            vals = [V["by_label"][x][tag]["notebooks_introduced_DIFF"]["num"] for x in V["by_label"]]
            V["notebooks_range_%s" % tag] = [min(vals), max(vals)]
    # strict_rule_notebooks of r3 (base, exception off) must match too
    for label, s in r3["strict_rule_notebooks"].items():
        checks.append(("r3 strict %s" % label, s["stated_rule_alone"],
                       exc_res["base"]["by_label"][label]["off"]["notebooks_introduced_DIFF"]["num"]))
    for (campaign, label), cl in sorted(cells.items()):
        key = "%s:%s" % (campaign, label)
        checks.append(("taxonomy %s introduced" % key, tax["per_engine"][key]["introduced"],
                       exc_res["base"]["by_label"][label]["on"]["introduced"]))
    pilot_exc = sum(exc(c) for c in pilot)
    pilot_intro = sum(c["kind"] == "introduced" for c in pilot)
    checks.append(("taxonomy pilot:bodo_dw introduced", tax["per_engine"]["pilot:bodo_dw"]["introduced"], pilot_intro))
    n_exc = sum(exc(c) for cl in cells.values() for c in cl) + pilot_exc
    checks.append(("taxonomy order_propagated cells", tax["causes"]["order_propagated"]["n_cells"], n_exc))

    # totals over the taxonomy population (7 configurations + pilot bodo_dw)
    intro_on = tax["counts"]["by_kind"]["introduced"]
    unattr_on = tax["causes"]["unattributed"]["n_cells"]
    totals = {"introduced": {"on": intro_on, "off": intro_on + n_exc},
              "assigned_by_rules_or_curated": intro_on - unattr_on,
              "unattributed_by_rules": {"on": unattr_on, "off": unattr_on + n_exc},
              "exception_cells": n_exc, "exception_cells_pilot": pilot_exc,
              "exception_cells_by_label": dict(collections.Counter(
                  [lab for (camp, lab), cl in cells.items() for c in cl if exc(c)] + ["bodo_dw"] * pilot_exc))}
    # localization: strictly clean inputs among the engines' introduced DIFF cells
    loc = {}
    for tag, ex in (("on", True), ("off", False)):
        t = collections.Counter()
        for lab in ENGINES:
            for c in cells[("conf_1x", lab)]:
                if kind(c, ex) == "introduced" and c["cls"] == "DIFF":
                    t[c["clean"]] += 1
        loc[tag] = {"introduced_DIFF": sum(t.values()), "strict_clean": t.get("E0", 0), "by_clean": dict(t)}
    checks.append(("r3 localization engines", r3["localization"]["totals"]["engines"]["introduced_DIFF"], loc["on"]["introduced_DIFF"]))
    # introduced share of non-E0 cells (conf1x_paper_counts.json attribution_kinds)
    ishare = {}
    for lab in ENGINES:
        a = kinds_pc[lab]
        e = sum(exc(c) for c in cells[("conf_1x", lab)])
        ishare[lab] = {"non_e0": a["non_e0_cells"], "on": round(a["introduced"] / a["non_e0_cells"], 4),
                       "off": round((a["introduced"] + e) / a["non_e0_cells"], 4), "exception_cells": e}
        checks.append(("paper_counts %s introduced" % lab, a["introduced"], exc_res["base"]["by_label"][lab]["on"]["introduced"]))
    # parallel-or-lazy shares (harness artifacts excluded): numerators unchanged, denominators grow
    pl = {}
    for lab in ENGINES:
        p = r3["parallel_or_lazy"][lab]
        np_on = exc_res["no_printed"]["by_label"][lab]["on"]["introduced_DIFF"]
        np_off = exc_res["no_printed"]["by_label"][lab]["off"]["introduced_DIFF"]
        checks.append(("r3 parallel_or_lazy %s denominator" % lab, p["introduced_DIFF_no_printed"], np_on))
        pl[lab] = {"parallel_or_lazy": p["with_hand"], "single_rater": p["with_hand"] - p["rules_only"],
                   "denominator_on": np_on, "denominator_off": np_off,
                   "share_on": round(p["with_hand"] / np_on, 4), "share_off": round(p["with_hand"] / np_off, 4)}
    drop_in = ("modin", "fireducks", "pyarrow_backend")
    pl_max = {"on": max(pl[x]["share_on"] for x in drop_in), "off": max(pl[x]["share_off"] for x in drop_in)}
    # Fig. 4: timing notebooks whose marker (engine introduces a DIFF cell in the conformance run) would change
    timing_nbs = sorted(timing30)
    assert len(timing_nbs) == 30
    fig4 = {}
    for e in TIMING_ENGINES:
        b = exc_res["base"]["by_label"][e]
        on, off = set(b["on"]["notebook_ids"]), set(b["off"]["notebook_ids"])
        fig4[e] = {"timing_notebooks": len(timing_nbs), "marked_on": len(on & set(timing_nbs)),
                   "marked_off": len(off & set(timing_nbs)), "changed": sorted((off - on) & set(timing_nbs))}

    # --- B. full sensitivity table (paired contrasts recomputed as r3_sensitivity.py and checked) -------------
    sens = {}
    for variant in VARIANTS:
        S = sens.setdefault(variant, {"pairs": {}, "by_label": {}})

        def ce2(campaign, label):
            return {(c["nb"], c["i"]): c["cls"] == "DIFF" for c in view(label, cells[(campaign, label)], "clean_E2", variant)}
        for (campaign, label), cl in sorted(cells.items()):
            num, den = collections.Counter(), collections.Counter()
            for c in view(label, cl, "clean_E2", variant):
                den[c["nb"]] += 1
                num[c["nb"]] += c["cls"] == "DIFF"
            bs = boot_share(num, den, "%s|clean_E2|DIFF" % label)
            allv = list(view(label, cl, "all", variant))
            S["by_label"][label] = {"scored": len(allv), "scored_DIFF": sum(c["cls"] == "DIFF" for c in allv),
                                    "clean_E2_cells": bs["den"], "clean_E2_DIFF": bs["num"],
                                    "clean_E2_DIFF_share": bs["share"], "clean_E2_DIFF_ci95": bs["ci95"],
                                    "notebooks_with_clean_E2_cells": sum(1 for v in den.values() if v)}
            checks.append(("r3 %s %s clean_E2 DIFF" % (variant, label),
                           r3["variants"][variant]["by_label"][label]["clean_E2"]["DIFF"], bs))
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
                row = {"cells": int(n.sum()), "notebooks": len(nbs), "engine_DIFF": int(a.sum()),
                       "pandas_DIFF": int(b.sum()), "engine_DIFF_pct": round(a.sum() / n.sum() * 100, 3),
                       "pandas_DIFF_pct": round(b.sum() / n.sum() * 100, 3), "diff_pp": round(est, 3),
                       "ci95_pp": [round(x, 3) for x in ci95], "ci90_pp": [round(x, 3) for x in ci90],
                       "inside_2pp_90": bool(ci90[0] > -2 and ci90[1] < 2),
                       "reading": "more often" if ci95[0] > 0 else ("less often" if ci95[1] < 0 else "not distinguishable")}
                S["pairs"]["%s-%s" % (e, v)] = row
                q = r3["variants"][variant]["pairs"]["%s-%s" % (e, v)]
                checks.append(("r3 %s pair %s-%s" % (variant, e, v),
                               [q["cells"], q["notebooks"], q["diff_pp"], q["ci95_pp"], q["ci90_pp"], q["reading"],
                                q["engine_DIFF_pct"], q["pandas_DIFF_pct"]],
                               [row["cells"], row["notebooks"], row["diff_pp"], row["ci95_pp"], row["ci90_pp"],
                                row["reading"], row["engine_DIFF_pct"], row["pandas_DIFF_pct"]]))

    bad = [c for c in checks if c[1] != c[2]]
    if bad:
        print(json.dumps([list(map(str, b)) for b in bad], indent=1)[:6000])
        raise SystemExit("consistency check failed (%d of %d)" % (len(bad), len(checks)))

    # --- C. membership lists with stable IDs ---------------------------------------------------------------------
    def sid(label, nb, i):
        return "%s|%s|%d" % (label, nb, i)
    lab_campaign = {lab: camp for camp, lab in LABELS}
    printed_list = []
    for (label, nb, i) in sorted(printed):
        c = next(x for x in cells[(lab_campaign[label], label)] if x["nb"] == nb and x["i"] == i)
        printed_list.append({"id": sid(label, nb, i), "label": label, "nb": nb, "cell": i, "nb_sha256": nbsha.get(nb),
                             "cls": c["cls"], "clean": c["clean"], "evidence": hand_row[(label, nb, i)]["evidence"],
                             "reduced_capture_notebook": nb in reduced})
    readers_list = []
    for (label, nb, i), r in sorted(readers.items(), key=lambda kv: kv[0]):
        c = r["cell"]
        readers_list.append({"id": sid(label, nb, i), "label": label, "nb": nb, "cell": i, "nb_sha256": nbsha.get(nb),
                             "reads_printed_cells": sorted(r["printed_cells"]), "names": sorted(r["names"]),
                             "cls": c["cls"], "clean": c["clean"], "kind": c["kind"],
                             "scored": c["cls"] not in EXCLUDED, "other_inputs_le_E2": r["others_le_E2"],
                             "post_timeout": c["post_timeout"],
                             "counted_clean_E2_in_no_printed_readers": bool(r["others_le_E2"] and c["cls"] not in EXCLUDED
                                                                           and not c["post_timeout"])})
    n_alt = sum(x["counted_clean_E2_in_no_printed_readers"] for x in readers_list)
    reduced_list = [{"nb": nb, "nb_sha256": nbsha.get(nb)} for nb in sorted(reduced)]
    exc_list = []
    for (campaign, label), cl in sorted(cells.items()):
        for c in cl:
            if exc(c):
                exc_list.append({"id": sid(label, c["nb"], c["i"]), "campaign": campaign, "label": label, "nb": c["nb"],
                                 "cell": c["i"], "nb_sha256": nbsha.get(c["nb"]), "cls": c["cls"], "clean": c["clean"],
                                 "in_clean_E2_view": c["clean"] in ("E0", "E1", "E2")})
    for c in pilot:
        if exc(c):
            exc_list.append({"id": sid("bodo_dw", c["nb"], c["i"]), "campaign": "pilot", "label": "bodo_dw", "nb": c["nb"],
                             "cell": c["i"], "nb_sha256": nbsha.get(c["nb"]), "cls": c["cls"], "clean": c["clean"],
                             "in_clean_E2_view": c["clean"] in ("E0", "E1", "E2")})
    positional = {(x["label"], x["nb"], x["i"]): x["positional_op_in_code"] for x in r3["order_rule"]["list"]}
    for x in exc_list:
        x["positional_op_in_code"] = positional[(x["label"], x["nb"], x["cell"])]
    assert len(exc_list) == n_exc == 59, len(exc_list)
    membership = {
        "id_format": "configuration|PandasBench notebook slug (repository commit ae70611)|0-based index among the "
                     "notebook's code cells (markdown and null-source cells dropped, empty code cells kept; "
                     "src/pconf/nbsource.py load_cells); nb_sha256 = SHA-256 of the notebook file in the run record",
        "printed_form_cells": printed_list,
        "printed_form_readers": {"rule": "no_printed_readers: a later cell of the same notebook and configuration that "
                                         "reads a DIFF output of a printed-form cell counts as clean@E2 (as if that "
                                         "container agreed at E2) when every other input agrees at E2 or finer; it keeps "
                                         "its own class, and its kind becomes introduced if that class is coarser than E2 "
                                         "(cascades and harness outcomes keep their kind); no_printed leaves these cells "
                                         "outside clean@E2 (their clean level is DIFF)",
                                 "readers": len(readers_list), "scored": sum(x["scored"] for x in readers_list),
                                 "counted_clean_E2_in_no_printed_readers": n_alt, "list": readers_list},
        "reduced_capture_notebooks": reduced_list,
        "exception_cells": exc_list}

    # --- D. ordered rules --------------------------------------------------------------------------------------
    rules = {"decision_order": [
        "1 NONDET (reference runs disagree): nondeterminism, excluded",
        "2 an engine against its own replicate: nondeterminism (UNCOMPARABLE: harness)",
        "3 MEMORY or NOTRUN: cascade (engine stop)",
        "4 ERR with NameError or UnboundLocalError: cascade (undefined name)",
        "5 UNCOMPARABLE: harness",
        "6 class not coarser than the clean level: inherited (propagated)",
        "7 curated table (21 cells): introduced, curated cause",
        "8 cause rules in order, first match wins: introduced, rule cause",
        "9 EXCEPTION (enabled in every published count): no curated entry and no rule matched, class DIFF, clean "
        "level E1 or E4: inherited (cause order_propagated)",
        "10 otherwise: introduced, unattributed"],
        "exception_enabled_in_published_counts": True,
        "exception_cells": n_exc,
        "cause_rules": [{"index": k, "cause": cause, "description": why, "appended_for_conf_1x": k >= n_appended_from}
                        for k, (cause, _p, why) in enumerate(T.RULES)],
        "curated_cells": len(T.CURATED)}
    assert sum(r["appended_for_conf_1x"] for r in rules["cause_rules"]) == prov["taxonomy"]["rules"]["appended"]

    # --- E. per-cell flags -------------------------------------------------------------------------------------
    symptom = set(prov["taxonomy"]["engine_symptom_level_cells"])

    def evidence(label, cause):
        if cause in (None, "unattributed", "order_propagated"):
            return "none"
        tc = tax["causes"].get(cause, {})
        out = []
        rd = tc.get("repro_differs_from_ref") or {}
        if rd.get(label):
            out.append("pandas reproducer differs on this configuration")
        elif any(rd.values()):
            out.append("pandas reproducer differs on another pandas configuration")
        eng = ((probes["causes"].get(cause) or {}).get("engines") or {})
        v = (eng.get(label) or {}).get("verdict")
        if v == "confirmed":
            out.append("engine probe confirms on this engine")
        elif v == "not_reproduced":
            out.append("engine probe does not reproduce on this engine")
        if v != "confirmed" and any((x or {}).get("verdict") == "confirmed" for x in eng.values()):
            out.append("engine probe confirms on another engine")
        return "; ".join(out) or "no reproducer or probe"

    flag_rows = []
    population = [(camp, lab, c) for (camp, lab), cl in sorted(cells.items()) for c in cl] + \
                 [("pilot", "bodo_dw", c) for c in pilot]
    for camp, lab, c in population:
        if not c["grade_worsens"] or c["cls"] in ("NONDET",):
            continue
        if c["kind"] not in ("introduced", "propagated"):
            continue   # cascades and harness outcomes are not localized
        why = c["why"] or ""
        if why.startswith("curated"):
            by, ridx, rcause = "curated", "", c["cause"]
        elif exc(c) or c["cause"] == "unattributed":
            by, ridx, rcause = "none", "", "unattributed"
        else:
            by, ridx, rcause = "rule", rule_index.get((c["cause"], why), ""), c["cause"]
        h = hand_row.get((lab, c["nb"], c["i"]))
        flag_rows.append({
            "id": sid(lab, c["nb"], c["i"]), "campaign": camp, "configuration": lab, "nb": c["nb"], "cell": c["i"],
            "cls": c["cls"], "clean_level": c["clean"], "grade_worsens": True, "assigned_by": by, "rule_index": ridx,
            "cause": rcause, "exception_applied": exc(c), "kind_exception_on": c["kind"],
            "kind_exception_off": kind(c, False), "single_rater_cause": h["cause"] if h else "",
            "single_rater_confidence": h["confidence"] if h else "",
            "cause_evidence": evidence(lab, rcause if by != "none" else None) if not h else "single rater only (no probe)",
            "symptom_level_group": rcause in symptom, "printed_form_artifact": (lab, c["nb"], c["i"]) in printed,
            "reduced_capture_notebook": c["nb"] in reduced})
    nf = collections.Counter((r["kind_exception_on"], r["kind_exception_off"]) for r in flag_rows)
    assert nf[("introduced", "introduced")] == intro_on and nf[("propagated", "introduced")] == n_exc, nf
    with open(OUT_CSV + ".tmp", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(flag_rows[0].keys()), lineterminator="\n")
        w.writeheader()
        for r in sorted(flag_rows, key=lambda r: (r["campaign"], r["configuration"], r["nb"], r["cell"])):
            w.writerow(r)
    os.replace(OUT_CSV + ".tmp", OUT_CSV)

    # --- F. replicate stability of the silent behaviours the paper names (pilot replicates, 10 notebooks) ---------
    pilot_nbs = set(json.load(open(os.path.join(PROJ, "data", "notebook_sets", "pilot.json")))["notebooks"])
    rep_diff, rep_unc = collections.defaultdict(set), collections.defaultdict(set)
    for cname, store in (("nondeterminism", rep_diff), ("capture_cap", rep_unc)):
        for camp, lab, nb, i, cls in tax["causes"][cname]["cells"]:
            if camp == "pilot" and "~vs~" in lab:
                store[lab.split("#")[0]].add((nb, i))
    replicated = sorted(rep_diff.keys() | rep_unc.keys() | {"modin", "fireducks", "bodo", "dask"})
    named = {c: [(lab, nb, i) for camp, lab, nb, i, cls in tax["causes"][c]["cells"] if camp == "conf_1x"]
             for c in ("cow_chained_assignment", "approximate_quantile", "engine_bug_silent", "axis_names_lost")}
    for c in ("apply_side_effects_lost", "stale_after_inplace_update", "unique_nunique_missing", "index_not_preserved"):
        named["single rater: " + c] = [(r["label"], r["nb"], r["cell"]) for r in hand["rows"] if r["cause"] == c]
    stab = {}
    for c, lst in named.items():
        inp = [x for x in lst if x[0] in replicated and x[1] in pilot_nbs]
        stab[c] = {"cells": len(lst), "in_pilot_notebooks_of_replicated_engines": len(inp),
                   "differ_between_replicate_runs": sorted("%s|%s|%d" % x for x in inp if (x[1], x[2]) in rep_diff[x[0]]),
                   "uncomparable_in_replicate": sorted("%s|%s|%d" % x for x in inp if (x[1], x[2]) in rep_unc[x[0]])}
    stability = {"definition": "cells of each named cause (conf_1x, and the single-rater cells) that lie in the 10 pilot "
                               "notebooks of an engine with a replicate (Modin, FireDucks, Bodo, Dask), and those of them "
                               "whose outputs differ between the engine's two pilot runs (taxonomy cause nondeterminism) "
                               "or were lost to capture in one of them (capture_cap)",
                 "replicated_engines": replicated, "by_cause": stab,
                 "in_pilot": sum(v["in_pilot_notebooks_of_replicated_engines"] for v in stab.values()),
                 "unstable": sum(len(v["differ_between_replicate_runs"]) for v in stab.values())}

    out = {"generated_from": {"summary_generated_utc": summary["generated_utc"], "taxonomy_generated": tax["generated"],
                              "r3_sensitivity": "icde27/analysis/r3_sensitivity.json", "compare_tag": "d" + T.COMPARE,
                              "harness_tag": T.HARNESS, "bootstrap": r3["generated_from"]["bootstrap"]},
           "consistency_checks": {"n": len(checks), "mismatches": 0},
           "exception": {"definition": "on: published rule-driven view (the 59 cells inherited); off: pure grade-worsens "
                                       "criterion (introduced iff the class is coarser than the clean level)",
                         "by_variant": exc_res, "totals": totals, "localization_engines": loc,
                         "introduced_share_non_e0": ishare, "parallel_or_lazy": pl, "parallel_or_lazy_max_drop_in": pl_max,
                         "fig4_timing_markers": fig4,
                         "unaffected": "shares by class (all scored cells), the clean@E0, clean@E2 and clean@E3 views, "
                                       "every paired comparison, first divergence, notebooks without an engine-side "
                                       "failure and introduced error cells (the exception applies to DIFF cells only): "
                                       "all use classes and clean levels, not kinds"},
           "sensitivity": sens, "membership": membership, "rules": rules, "replicate_stability": stability,
           "cell_flags": {"file": "icde27/analysis/r4_cell_flags.csv", "rows": len(flag_rows),
                          "kinds_on_off": {"%s->%s" % k: v for k, v in sorted(nf.items())}}}
    with open(OUT + ".tmp", "w") as f:
        json.dump(out, f, indent=1)
    os.replace(OUT + ".tmp", OUT)
    write_md(out)

    # --- printout ----------------------------------------------------------------------------------------------
    print("checks %d, mismatches 0" % len(checks))
    print("totals", json.dumps(totals))
    for variant in VARIANTS:
        V = exc_res[variant]
        print("== %s  notebooks on %s off %s" % (variant, V["notebooks_range_on"], V["notebooks_range_off"]))
        for lab in PANDAS + ENGINES:
            R = V["by_label"][lab]
            print("  %-16s exc %2d | intro %4d -> %4d | introDIFF %3d -> %3d | NB %2d %s -> %2d %s %s" % (
                lab, R["exception_cells_kept"], R["on"]["introduced"], R["off"]["introduced"], R["on"]["introduced_DIFF"],
                R["off"]["introduced_DIFF"], R["on"]["notebooks_introduced_DIFF"]["num"], R["on"]["notebooks_introduced_DIFF"]["ci95"],
                R["off"]["notebooks_introduced_DIFF"]["num"], R["off"]["notebooks_introduced_DIFF"]["ci95"], R["notebooks_changed"]))
    print("localization", loc)
    print("introduced share", ishare)
    print("parallel or lazy", pl, pl_max)
    print("fig4", fig4)
    print("readers", len(readers_list), "scored", sum(x["scored"] for x in readers_list), "alt clean", n_alt)
    print("flags", len(flag_rows), dict(nf))
    print("replicate stability", json.dumps({k: (v["cells"], v["in_pilot_notebooks_of_replicated_engines"], v["differ_between_replicate_runs"], v["uncomparable_in_replicate"]) for k, v in stability["by_cause"].items()}))


def fmt_ci(ci, scale=1.0, nd=1):
    return "[%s, %s]" % (("%%.%df" % nd) % (ci[0] * scale), ("%%.%df" % nd) % (ci[1] * scale))


def esc(s):
    """A Markdown table cell (IDs contain '|')."""
    return str(s).replace("|", "\\|")


def write_md(out):
    L = ["# Audit tables: inheritance exception, sensitivity contrasts, membership lists (generated by icde27/analysis/r4_audit.py; do not edit)", ""]
    ex = out["exception"]
    L += ["## 1. Inheritance exception on and off", "",
          "On: published rule-driven view (59 unexplained DIFF cells whose inputs agree only modulo row order or index "
          "count as inherited). Off: the pure criterion (introduced iff the cell's class is coarser than the finest "
          "level at which all its inputs agree). Unaffected: %s." % ex["unaffected"], ""]
    t = ex["totals"]
    L += ["Taxonomy totals (7 configurations on 102 notebooks plus the pilot's bodo_dw): introduced %d on, %d off; "
          "assigned by rules or the curated table %d (both); unattributed by the rules %d on, %d off; exception cells "
          "%d (%s)." % (t["introduced"]["on"], t["introduced"]["off"], t["assigned_by_rules_or_curated"],
                        t["unattributed_by_rules"]["on"], t["unattributed_by_rules"]["off"], t["exception_cells"],
                        ", ".join("%s %d" % kv for kv in sorted(t["exception_cells_by_label"].items()))), ""]
    for variant, V in ex["by_variant"].items():
        L += ["### Variant %s (notebooks with an introduced DIFF: %d-%d on, %d-%d off)" % (
            variant, V["notebooks_range_on"][0], V["notebooks_range_on"][1], V["notebooks_range_off"][0],
            V["notebooks_range_off"][1]), "",
              "| Configuration | Exception cells | Introduced on | off | Introduced DIFF on | off | Notebooks on [95%] | off [95%] | Notebooks added |",
              "|---|---:|---:|---:|---:|---:|---|---|---|"]
        for lab, R in V["by_label"].items():
            a, b = R["on"]["notebooks_introduced_DIFF"], R["off"]["notebooks_introduced_DIFF"]
            L.append("| %s | %d | %d | %d | %d | %d | %d %s | %d %s | %s |" % (
                lab, R["exception_cells_kept"], R["on"]["introduced"], R["off"]["introduced"], R["on"]["introduced_DIFF"],
                R["off"]["introduced_DIFF"], a["num"], fmt_ci(a["ci95"], 1, 0) if a["ci95"][1] > 1 else fmt_ci(a["ci95"], a["den"], 0),
                b["num"], fmt_ci(b["ci95"], 1, 0) if b["ci95"][1] > 1 else fmt_ci(b["ci95"], b["den"], 0),
                ", ".join(R["notebooks_changed"]) or "--"))
        L.append("")
    lo = ex["localization_engines"]
    L += ["Engines' introduced DIFF cells with bit-identical inputs: %d of %d on, %d of %d off." % (
        lo["on"]["strict_clean"], lo["on"]["introduced_DIFF"], lo["off"]["strict_clean"], lo["off"]["introduced_DIFF"]), ""]
    L += ["| Engine | Introduced share of non-E0 cells on | off | Parallel or lazy (single rater) | of introduced DIFF on | off |",
          "|---|---:|---:|---:|---:|---:|"]
    for lab in ex["introduced_share_non_e0"]:
        s, p = ex["introduced_share_non_e0"][lab], ex["parallel_or_lazy"][lab]
        L.append("| %s | %.1f%% | %.1f%% | %d (%d) | %d (%.1f%%) | %d (%.1f%%) |" % (
            lab, 100 * s["on"], 100 * s["off"], p["parallel_or_lazy"], p["single_rater"], p["denominator_on"],
            100 * p["share_on"], p["denominator_off"], 100 * p["share_off"]))
    L += ["", "Fig. 4 markers that would change with the exception off: " + "; ".join(
        "%s %d -> %d of %d (%s)" % (e, v["marked_on"], v["marked_off"], v["timing_notebooks"], ", ".join(v["changed"]) or "none")
        for e, v in ex["fig4_timing_markers"].items()), ""]
    L += ["## 2. Every paired contrast in every variant", "",
          "Paired on the cells clean@E2 under both configurations; DIFF counts are the numerators, cells the "
          "denominator; difference in percentage points (engine minus pandas) with notebook-bootstrap intervals "
          "(10,000 resamples). The exception does not enter these contrasts.", "",
          "| Variant | Contrast | Cells | Notebooks | Engine DIFF | pandas DIFF | Engine % | pandas % | Difference | 90% | 95% | Reading |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|"]
    for variant, S in out["sensitivity"].items():
        for k, p in S["pairs"].items():
            L.append("| %s | %s | %d | %d | %d | %d | %.2f | %.2f | %+.2f | [%+.2f, %+.2f] | [%+.2f, %+.2f] | %s |" % (
                variant, k, p["cells"], p["notebooks"], p["engine_DIFF"], p["pandas_DIFF"], p["engine_DIFF_pct"],
                p["pandas_DIFF_pct"], p["diff_pp"], p["ci90_pp"][0], p["ci90_pp"][1], p["ci95_pp"][0], p["ci95_pp"][1],
                p["reading"]))
    L += ["", "Unpaired clean@E2 DIFF shares per configuration:", "",
          "| Variant | Configuration | Scored cells | Scored DIFF | clean@E2 cells | clean@E2 DIFF | Share | 95% |",
          "|---|---|---:|---:|---:|---:|---:|---|"]
    for variant, S in out["sensitivity"].items():
        for lab, r in S["by_label"].items():
            L.append("| %s | %s | %d | %d | %d | %d | %.2f%% | %s%% |" % (
                variant, lab, r["scored"], r["scored_DIFF"], r["clean_E2_cells"], r["clean_E2_DIFF"],
                100 * r["clean_E2_DIFF_share"], fmt_ci(r["clean_E2_DIFF_ci95"], 100, 2)))
    m = out["membership"]
    L += ["", "## 3. Membership lists", "", "ID format: " + m["id_format"] + ".", "",
          "### 16 printed-form cells (removed in no_printed, no_printed_readers, no_both)", "",
          "| ID | nb SHA-256 | Class | Clean level | Evidence |", "|---|---|---|---|---|"]
    for x in m["printed_form_cells"]:
        L.append("| %s | %s | %s | %s | %s |" % (esc(x["id"]), (x["nb_sha256"] or "")[:16], x["cls"], x["clean"], esc(x["evidence"])))
    pr = m["printed_form_readers"]
    L += ["", "### Readers of their containers (%d cells, %d scored; %d count as clean@E2 in no_printed_readers)" % (
        pr["readers"], pr["scored"], pr["counted_clean_E2_in_no_printed_readers"]), "", "Rule: " + pr["rule"] + ".", "",
          "| ID | Reads printed cell(s) | Names | Class | Clean level | Other inputs <= E2 | Counted clean@E2 |",
          "|---|---|---|---|---|---|---|"]
    for x in pr["list"]:
        L.append("| %s | %s | %s | %s | %s | %s | %s |" % (esc(x["id"]), ", ".join(map(str, x["reads_printed_cells"])),
                                                       ", ".join(x["names"]), x["cls"], x["clean"] or "none (a container input is DIFF)", x["other_inputs_le_E2"],
                                                       x["counted_clean_E2_in_no_printed_readers"]))
    L += ["", "### 10 notebooks without pre-cell input capture (removed in no_reduced, no_both)", "",
          "| Notebook | nb SHA-256 |", "|---|---|"]
    for x in m["reduced_capture_notebooks"]:
        L.append("| %s | %s |" % (x["nb"], (x["nb_sha256"] or "")[:16]))
    L += ["", "### 59 exception cells (inherited with the exception on, introduced and unattributed with it off)", "",
          "| ID | Class | Clean level | In clean@E2 view | Positional operation in code |", "|---|---|---|---|---|"]
    for x in m["exception_cells"]:
        L.append("| %s | %s | %s | %s | %s |" % (esc(x["id"]), x["cls"], x["clean"], x["in_clean_E2_view"], x["positional_op_in_code"]))
    r = out["rules"]
    L += ["", "## 4. Classification order and cause rules", ""] + ["%s" % s for s in r["decision_order"]] + [
        "", "| Index | Cause | Description | Appended for conf_1x |", "|---:|---|---|---|"]
    for x in r["cause_rules"]:
        L.append("| %d | %s | %s | %s |" % (x["index"], x["cause"], x["description"].replace("|", "/"), x["appended_for_conf_1x"]))
    st = out["replicate_stability"]
    L += ["", "## 5. Replicate stability of the named silent behaviours", "", st["definition"] + ".", "",
          "| Cause | Cells | In pilot notebooks (replicated engine) | Differ between replicate runs | Lost to capture in a replicate |",
          "|---|---:|---:|---|---|"]
    for c, v in st["by_cause"].items():
        L.append("| %s | %d | %d | %s | %s |" % (c, v["cells"], v["in_pilot_notebooks_of_replicated_engines"],
                                               esc(", ".join(v["differ_between_replicate_runs"]) or "none"),
                                               esc(", ".join(v["uncomparable_in_replicate"]) or "none")))
    L += ["", "Per-cell flags: %s (%d rows; kinds on -> off: %s)." % (
        out["cell_flags"]["file"], out["cell_flags"]["rows"], out["cell_flags"]["kinds_on_off"]), ""]
    with open(OUT_MD + ".tmp", "w") as f:
        f.write("\n".join(L))
    os.replace(OUT_MD + ".tmp", OUT_MD)


if __name__ == "__main__":
    sys.exit(main())

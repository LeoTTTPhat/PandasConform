#!/usr/bin/env python3
"""D1 analysis: classify every disputed cell of d1_plan.json from the replay comparisons and recompute the principal
counts with the nondeterministic cells separated. Shared venv (numpy, for the paired bootstrap of paired.py).
Writes d1_results.json and prints the numbers RESULTS.md cites.   Usage: .venv/bin/python d1_analyze.py --tags d1b

vsref of a replayed notebook = work/r5_replay/compare/vsref/<engine>/<nb>.json when d1_compare.py produced it, else
(the replay is hash-identical to the original run, d1_hashcheck.json) the published compare output, which the
comparator would reproduce exactly. self = work/r5_replay/compare/self/<engine>/<nb>.json (class E0: bit-identical).
"""
import argparse
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import r5common as R  # noqa: E402

OUT = os.path.join(HERE, "d1_results.json")
CMP = os.path.join(R.WORK, "compare")
VALUE = {"E0", "E1", "E2", "E3", "E4"}
# notebooks whose code computes with the current date (datetime.datetime.today() in cells 11, 16, 17, 20): a replay on a
# later day changes those values for every configuration, pandas included (found while inspecting the self comparisons)
DATE_DEPENDENT = {"tunguz/fathers-day-specials-just-the-features"}
# paper numbers being recomputed (exception on): introduced DIFF without printed-form artifacts; Table IV NB
PAPER_CELLS = {"modin": 49, "fireducks": 58, "bodo": 80, "pyarrow_backend": 51, "dask": 46}
PAPER_NB_CORR = {"pyarrow_backend": 31, "modin": 34, "fireducks": 38, "bodo": 43, "dask": 24}
PAPER_NB_RAW = {"pyarrow_backend": 36, "modin": 36, "fireducks": 40, "bodo": 45, "dask": 24}


def category(vs, se):
    if vs is None:
        return "F"
    cls, clean = vs.get("cls"), vs.get("clean_level")
    if cls == "DIFF":
        if R.introduced(cls, clean):
            return "R-id" if (se is not None and se.get("cls") == "E0") else "R-var"
        return "M"
    if cls in VALUE:
        return "N"
    return "F"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", default="d1b")
    a = ap.parse_args()
    plan = R.read_json(os.path.join(HERE, "d1_plan.json"))
    hc = R.read_json(os.path.join(HERE, "d1_hashcheck.json"))
    identical = {(n["engine"], n["nb"]) for n in hc["notebooks"] if n["identical"]}
    runs = {}
    for tag in a.tags.split(","):
        for r in (R.read_json(os.path.join(HERE, "d1_run_%s.json" % tag)) or {}).get("results", []):
            if r.get("record"):
                runs[(r["engine"], r["nb"])] = r
    flags = R.cell_flags()
    kinds = {(r["configuration"], r["nb"], int(r["cell"])): r for r in flags if r["campaign"] == "conf_1x"}
    res = {"item": "D1", "tags": a.tags, "engines": {}, "cells": [], "notebook_level": []}
    nondet = set()          # (label, nb, i) with category M or N
    sd = R.read_json(os.path.join(HERE, "d1_selfdiff.json")) or {"cells": []}
    cat_by_cell = {(e_, nb_, i_): cat for e_, nb_, i_, cls_, cat in sd["cells"]}
    for eng, e in plan["engines"].items():
        meta = {n["nb"]: n for n in e["notebooks"] + e["controls"]}
        long_nbs = {n["nb"] for n in e["not_replayed_long"]}
        vs_by_nb, se_by_nb, orig_by_nb = {}, {}, {}
        for nb, m in meta.items():
            orig_by_nb[nb] = {c["i"]: c for c in R.read_json(os.path.join(R.PROJ, m["compare_output"]))["cells"]}
            if (eng, nb) not in runs:
                continue
            key = R.nb_key(nb) + ".json"
            pv = os.path.join(CMP, "vsref", eng, key)
            if os.path.exists(pv):
                vs_by_nb[nb] = {c["i"]: c for c in R.read_json(pv)["cells"]}
            elif (eng, nb) in identical:
                vs_by_nb[nb] = orig_by_nb[nb]
            ps = os.path.join(CMP, "self", eng, key)
            if os.path.exists(ps):
                se_by_nb[nb] = {c["i"]: c for c in R.read_json(ps)["cells"]}
        sc_ok = {(c["nb"], c["cell"]) for c in (R.read_json(os.path.join(HERE, "d1_shortcut.json")) or {"cells": []})["cells"]
                 if c["engine"] == eng and c["unchanged"]}
        cats = collections.Counter()
        cats_on = collections.Counter()
        cats_on_np = collections.Counter()
        for d in e["disputed_cells"]:
            nb, i = d["nb"], d["cell"]
            if nb in long_nbs:
                cat = "not replayed (long)"
            elif nb not in vs_by_nb and (nb, i) in sc_ok:
                cat = "R-id"          # d1_shortcut.py: every input of the comparator for this cell is unchanged
            elif nb not in vs_by_nb:
                cat = "pending comparison" if (eng, nb) in runs else "not replayed (budget or no record)"
            else:
                se_c = se_by_nb.get(nb, {}).get(i)
                if se_c is None and (eng, nb) in identical:
                    se_c = {"cls": "E0", "note": "hash-identical notebook"}
                cat = category(vs_by_nb[nb].get(i), se_c)
            vs = vs_by_nb.get(nb, {}).get(i) or {}
            se = se_by_nb.get(nb, {}).get(i) or {}
            row = dict(d, engine=eng, category=cat, replay_cls=vs.get("cls"), replay_clean=vs.get("clean_level"),
                       self_cls=se.get("cls"), self_fails={k: (v.get("fails") or {}).get("E0") for k, v in (se.get("outputs") or {}).items()
                                                           if v.get("level") != "E0"} if se else None)
            res["cells"].append(row)
            cats[cat] += 1
            if d["kind_exception_on"] == "introduced":
                cats_on[cat] += 1
                if not d["printed_form_artifact"]:
                    cats_on_np[cat] += 1
            if cat in ("M", "N"):
                nondet.add((eng, nb, i))
        # notebook level: self-disagreement and new introduced DIFF cells
        self_scored = self_diff = 0
        date_dep = {}
        self_classes = collections.Counter()
        self_detail = collections.Counter()
        new_cells = []
        per_nb = []
        for nb, m in sorted(meta.items()):
            if nb not in vs_by_nb:
                continue
            se = se_by_nb.get(nb)
            sc = df = 0
            if se is not None:
                for c in se.values():
                    if c["cls"] in ("NOOUT", "REF_ERR", "NONDET"):
                        continue
                    if (orig_by_nb[nb].get(c["i"]) or {}).get("cls") == "NONDET":
                        continue      # reference nondeterminism (ref vs ref#2), excluded for every engine as in the paper
                    sc += 1
                    df += c["cls"] != "E0"
                    if c["cls"] != "E0":
                        self_classes[c["cls"]] += 1
                        self_detail[cat_by_cell.get((eng, nb, c["i"]), "not classified")] += 1
            self_scored += sc
            self_diff += df
            for i, c in vs_by_nb[nb].items():
                if c.get("cls") == "DIFF" and R.introduced("DIFF", c.get("clean_level")):
                    o = orig_by_nb[nb].get(i) or {}
                    if not (o.get("cls") == "DIFF" and R.introduced("DIFF", o.get("clean_level"))):
                        new_cells.append({"nb": nb, "cell": i, "role": "control" if m["n_disputed"] == 0 else "disputed-notebook",
                                          "orig_cls": o.get("cls"), "orig_clean": o.get("clean_level"),
                                          "replay_clean": c.get("clean_level")})
            if df and nb in DATE_DEPENDENT:
                date_dep[eng] = date_dep.get(eng, 0) + df
            per_nb.append({"engine": eng, "nb": nb, "role": "control" if m["n_disputed"] == 0 else "disputed",
                           "self_scored": sc, "self_differing": df, "identical": (eng, nb) in identical,
                           "replay_status": runs[(eng, nb)].get("replay_record_status") or runs[(eng, nb)].get("status"),
                           "orig_status": m["orig_status"]})
        res["notebook_level"] += per_nb
        res["engines"][eng] = {
            "categories_pure": dict(cats), "categories_exception_on": dict(cats_on),
            "categories_exception_on_no_printed": dict(cats_on_np),
            "notebooks_replayed": sum(1 for p in per_nb if p["role"] == "disputed"),
            "controls_replayed": sum(1 for p in per_nb if p["role"] == "control"),
            "notebooks_identical": sum(1 for p in per_nb if p["identical"]),
            "self_scored_cells": self_scored, "self_differing_cells": self_diff, "self_differing_by_class": dict(self_classes),
            "self_differing_in_date_dependent_notebook": date_dep.get(eng, 0),
            "self_differing_detail": dict(self_detail),
            "self_differing_share": round(self_diff / self_scored, 5) if self_scored else None,
            "new_introduced_DIFF_cells": new_cells,
            "new_in_controls": sum(1 for c in new_cells if c["role"] == "control"),
            "new_in_disputed_notebooks": sum(1 for c in new_cells if c["role"] != "control")}
    # exploratory (decided after the design): do the engines' introduced failure cells (ERR, CRASH, TIMEOUT, MEMORY,
    # NOTRUN; pure criterion) recur in the replay?
    fail_rep = {}
    for eng, e in plan["engines"].items():
        meta = {n["nb"]: n for n in e["notebooks"] + e["controls"]}
        cnt = collections.Counter()
        changed = []
        for r in flags:
            if r["campaign"] != "conf_1x" or r["configuration"] != eng or r["cls"] not in R.FAIL or r["kind_exception_off"] != "introduced":
                continue
            nb, i = r["nb"], int(r["cell"])
            if (eng, nb) not in runs or nb not in meta:
                cnt["notebook not replayed"] += 1
                continue
            key = R.nb_key(nb) + ".json"
            pv = os.path.join(CMP, "vsref", eng, key)
            if os.path.exists(pv):
                cells_ = {c["i"]: c for c in R.read_json(pv)["cells"]}
            elif (eng, nb) in identical:
                cells_ = {c["i"]: c for c in R.read_json(os.path.join(R.PROJ, meta[nb]["compare_output"]))["cells"]}
            else:
                cnt["no comparison"] += 1
                continue
            rc = (cells_.get(i) or {}).get("cls")
            if rc == r["cls"]:
                cnt["same failure class"] += 1
            else:
                cnt["changed"] += 1
                changed.append([nb, i, r["cls"], rc])
        fail_rep[eng] = {"counts": dict(cnt), "changed": changed}
    res["exploratory_failure_cells"] = fail_rep
    for eng, v in res["engines"].items():
        det = v["self_differing_detail"]
        same = det.get("same failure in both runs (not a difference)", 0)
        token = det.get("token-only printed difference", 0)
        v["self_differing_excluding_same_failure"] = v["self_differing_cells"] - same
        v["self_differing_value_changes"] = v["self_differing_cells"] - same - token
        v["self_differing_value_share"] = round(v["self_differing_value_changes"] / v["self_scored_cells"], 5) if v["self_scored_cells"] else None
    # principal counts with M and N separated (exception on; printed-form artifacts excluded as in the paper)
    pc = {}
    for eng in plan["engines"]:
        rows = [r for r in flags if r["campaign"] == "conf_1x" and r["configuration"] == eng and r["cls"] == "DIFF"
                and r["kind_exception_on"] == "introduced"]
        np_rows = [r for r in rows if r["printed_form_artifact"] != "True"]
        keep = [r for r in np_rows if (eng, r["nb"], int(r["cell"])) not in nondet]
        keep_raw = [r for r in rows if (eng, r["nb"], int(r["cell"])) not in nondet]
        pc[eng] = {"introduced_DIFF_no_printed": {"paper": PAPER_CELLS[eng], "recount": len(np_rows), "without_nondet": len(keep)},
                   "notebooks_introduced_DIFF_no_printed": {"paper": PAPER_NB_CORR[eng], "recount": len({r["nb"] for r in np_rows}),
                                                             "without_nondet": len({r["nb"] for r in keep})},
                   "notebooks_introduced_DIFF_raw": {"paper": PAPER_NB_RAW[eng], "recount": len({r["nb"] for r in rows}),
                                                      "without_nondet": len({r["nb"] for r in keep_raw})}}
        pure = [r for r in flags if r["campaign"] == "conf_1x" and r["configuration"] == eng and r["cls"] == "DIFF"
                and r["kind_exception_off"] == "introduced"]
        pc[eng]["pure_view"] = {"introduced_DIFF": len(pure),
                                "without_nondet": sum(1 for r in pure if (eng, r["nb"], int(r["cell"])) not in nondet),
                                "notebooks": len({r["nb"] for r in pure}),
                                "notebooks_without_nondet": len({r["nb"] for r in pure if (eng, r["nb"], int(r["cell"])) not in nondet})}
    res["principal_counts"] = pc
    nb_range = lambda key, f: [min(pc[e][key][f] for e in pc), max(pc[e][key][f] for e in pc)]  # noqa: E731
    res["abstract_range_engines_no_printed"] = {"paper_engines": nb_range("notebooks_introduced_DIFF_no_printed", "paper"),
                                                "without_nondet": nb_range("notebooks_introduced_DIFF_no_printed", "without_nondet")}
    # shares and paired contrasts (paired.py reproduces r4_audit.json base exactly with no exclusion)
    import paired
    chk = paired.check_against_r4()
    base = paired.compute()
    excl = paired.compute(frozenset(nondet))
    res["paired_check_vs_r4"] = chk
    res["paired"] = {"base": base["pairs"], "without_nondet": excl["pairs"]}
    res["unpaired_clean_E2_DIFF"] = {"base": base["unpaired"], "without_nondet": excl["unpaired"]}
    res["nondet_cells"] = sorted([list(x) for x in nondet])
    R.write_json(OUT, res)
    # print
    print("paired check vs r4_audit:", chk["contrasts"], "contrasts,", len(chk["mismatches"]), "mismatches")
    tot = collections.Counter()
    for eng, v in res["engines"].items():
        tot.update(v["categories_pure"])
        print("%-16s pure %s | exc-on no-printed %s | self differing %d/%d (%.2f%%) | new introduced DIFF: controls %d, disputed nbs %d | nbs replayed %d (+%d controls), identical %d"
              % (eng, dict(v["categories_pure"]), dict(v["categories_exception_on_no_printed"]), v["self_differing_cells"],
                 v["self_scored_cells"], 100 * (v["self_differing_share"] or 0), v["new_in_controls"], v["new_in_disputed_notebooks"],
                 v["notebooks_replayed"], v["controls_replayed"], v["notebooks_identical"]))
    print("all engines pure:", dict(tot))
    for eng, v in res["engines"].items():
        if "self_differing_detail" in v:
            print("%-16s self-differing detail %s | value changes %d/%d (%.2f%%)" % (eng, v["self_differing_detail"],
                  v["self_differing_value_changes"], v["self_scored_cells"], 100 * (v["self_differing_value_share"] or 0)))
    for eng, v in pc.items():
        print("%-16s cells %s | NB corrected %s | NB raw %s | pure %s" % (eng, v["introduced_DIFF_no_printed"],
              v["notebooks_introduced_DIFF_no_printed"], v["notebooks_introduced_DIFF_raw"], v["pure_view"]))
    print("abstract range (engines, no printed):", res["abstract_range_engines_no_printed"])
    for eng, v in fail_rep.items():
        print("%-16s introduced failure cells in the replay: %s changed %s" % (eng, v["counts"], v["changed"][:4]))
    for k in sorted(base["pairs"]):
        b, x = base["pairs"][k], excl["pairs"][k]
        print("%-22s base %+.3f %s %s (%d/%d) -> without nondet %+.3f %s %s (%d/%d)" % (k, b["diff_pp"], b["ci95_pp"], b["reading"],
              b["engine_DIFF"], b["cells"], x["diff_pp"], x["ci95_pp"], x["reading"], x["engine_DIFF"], x["cells"]))
    for lab in ("pyarrow_backend", "modin", "fireducks", "bodo", "dask"):
        b, x = base["unpaired"][lab], excl["unpaired"][lab]
        print("%-16s clean@E2 DIFF %d/%d %.4f %s -> %d/%d %.4f %s" % (lab, b["num"], b["den"], b["share"], b["ci95"],
              x["num"], x["den"], x["share"], x["ci95"]))


if __name__ == "__main__":
    main()

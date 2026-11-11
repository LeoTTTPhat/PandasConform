#!/usr/bin/env python3
"""C2 analysis: the adversarial capture corpus through both harnesses (review round R5, agent B1).

Read-only on work/r5_capture/c2 (runs, captures and comparisons of c2_job.sh) and c2_cases.json; writes
icde27/analysis/r5_capture/c2_results.json and prints the per-case table. Shared venv, small.

    cd ..
    .venv/bin/python 06_pandas_conformance-ICDE/icde27/analysis/r5_capture/c2_analyze.py

Harness "orig" = the unmodified src/pconf (results_orig, its own compare with ref#2); "exact" = the C1 copy with the
exact encoder (results_exact, its own compare with ref#2: nested values must be E0-equal); "exact_graded" = the same
runs classified by c1_compare.py in the graded variant (nested values graded by the comparator; NONDET taken from
the exact harness's own compare); "exact_origenc" = the same runs classified with the original encoder's entries
(a check of the dual capture: it should give the original harness's results). For every case, engine and harness: the reported class at the cell where the difference arises
(output level, or the cell class when the case names no output), the reader's class, clean level and kind where the
case has a reader, the flags (printed: an element tagged T_CONTAINER/T_OTHER in the compared records, the R4 census
definition, checked in the blobs; inexact: an element the exact encoder left without an exact encoding;
uncapturable_input: the reader's inputs include a value that cannot be serialized; NONDET: ref and ref#2 disagree),
the verdict (correct; overstated = a coarser class than the truth, including DIFF for a pair equal at some level;
understated = a finer class than the truth, including a level for a DIFF; misattributed = a reader counted clean
with an introduced DIFF; late; unscored; n/a for cases without a value) and the category (captured exactly =
correct and no flag; flagged = any flag, UNCOMPARABLE included; missed = understated, misattributed or unscored
without a flag; overstated and late without a flag are reported as such).
TRUTH below restates the truths of c2_cases.json as classes (written with the cases, before the run), with one
correction after the run, from the record: FireDucks binds pandas' own NDFrame.head (method pseudo-record
"pandas.core.generic.NDFrame.head"), so its bound method on an equal frame is E0, not DIFF.
"""
import collections
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
C2 = os.path.join(PROJ, "work", "r5_capture", "c2")
sys.path.insert(0, os.path.join(PROJ, "src"))
from pconf import capture  # noqa: E402  (blob reading only)

ORDER = {"E0": 0, "E1": 1, "E2": 2, "E3": 3, "E4": 4, "DIFF": 5}
# truth per case: a class (or "A|B" when either is right), "NA" (no value), or a reader rule
TRUTH = {
    "nested_hidden_row": "DIFF", "nested_float_digits": "DIFF", "nested_dtype_only": "E2", "nested_depth_cut": "DIFF",
    "nested_delimiter_collision": "DIFF", "nested_control_equal": {"p30": "E2", "fireducks": "E0"},
    "nested_natural_str_dtype": {"p30": "E2", "fireducks": "E0"}, "nested_object_address": "NA",
    "alias_visible": "DIFF", "alias_function": "reader", "alias_function_no_reader": "unscored",
    "attribute_side_effect": "reader", "apply_append": "reader", "hidden_global_traced": "origin+reader",
    "hidden_global_closure": "origin+reader", "global_statement": "reader", "dynamic_globals_store": "reader",
    "dynamic_exec_store": "reader", "dynamic_globals_read": "origin+reader", "lazy_assigned_scalar": "DIFF",
    "lazy_assigned_series": "DIFF", "inplace_sort": {"p30": "E2", "fireducks": "E1"}, "groupby_object": "reader", "repr_hides_state": "DIFF",
    "bound_method": {"p30": "E2", "fireducks": "E0"}, "dtype_objects": {"p30": "E0|E2", "fireducks": "E0"}, "range_in_list": "DIFF",
    "lambda_in_list": "NA", "dask_lazy_scalar": "E0|E2", "dask_lazy_in_dict": "E0|E2", "dask_lazy_in_list": "E0|E2",
    "dask_lazy_series_in_list": "E0|E2", "dask_planted_in_dict": "DIFF",
}


def best_compare(results_root, engine, nb):
    ps = glob.glob(os.path.join(results_root, "c2", "raw", "compare__*", engine, "sf1", "probe__%s__*.json" % nb))
    ps = [p for p in ps if not p.endswith("noref2.json")] or ps
    if not ps:
        return None
    p = max(ps, key=os.path.getmtime)
    return json.load(open(p))


def c1_variant(variant, engine, nb, nondet_from):
    """c1_compare.py output for the exact-harness runs, with the NONDET marks of the exact harness's own compare."""
    p = os.path.join(C2, "compare_c1", variant, engine, "probe__%s.json" % nb)
    if not os.path.exists(p) or nondet_from is None:
        return None
    r = json.load(open(p))
    nd = {c["i"]: c for c in nondet_from["cells"] if c.get("cls") == "NONDET"}
    for c in r["cells"]:
        if c["i"] in nd:
            c["cls_raw"], c["cls"] = c["cls"], "NONDET"
    r["meta"]["ref_record"] = os.path.relpath(r["meta"]["ref_record"], PROJ) if os.path.isabs(r["meta"]["ref_record"]) else r["meta"]["ref_record"]
    r["meta"]["eng_record"] = os.path.relpath(r["meta"]["eng_record"], PROJ) if os.path.isabs(r["meta"]["eng_record"]) else r["meta"]["eng_record"]
    return r


def main():
    cases = json.load(open(os.path.join(HERE, "c2_cases.json")))["cases"]
    tag_cache = {}

    def printed_in(store, rec):
        if not isinstance(rec, dict):
            return False
        if rec.get("kind") == "scalar":
            return (rec.get("meta") or {}).get("value", [None])[0] in (capture.T_CONTAINER, capture.T_OTHER)

        def col(c):
            if c.get("enc") == "obj":
                key = (store, c["h"])
                if key not in tag_cache:
                    try:
                        t = capture.load_blob(store, c["h"])["t"]
                        tag_cache[key] = bool(set(t.tolist()) & {capture.T_CONTAINER, capture.T_OTHER})
                    except Exception:
                        tag_cache[key] = False
                if tag_cache[key]:
                    return True
            return any(col(v) for v in (c.get("x") or {}).values() if isinstance(v, dict) and "enc" in v)
        return any(col(c) for c in (rec.get("cols") or []) + (rec.get("idx") or []))

    def record_entry(rec, i, name):
        c = next((c for c in rec["cells"] if c["i"] == i), None)
        if c is None:
            return None
        e = (c.get("outputs") or {}).get(name)
        return rec["objects"].get(e) if isinstance(e, str) else e

    out = {"by_case": [], "summary": {}}
    summ = collections.defaultdict(collections.Counter)
    for harness in ("orig", "exact", "exact_graded", "exact_origenc"):
        base = "orig" if harness == "orig" else "exact"
        root = os.path.join(C2, "results_" + base)
        store = os.path.join(C2, "captures_" + base)
        for case in cases:
            engines = ("p30", "fireducks", "dask") if case["nb"] == "c2_dask" else ("p30", "fireducks")
            for eng in engines:
                cmp_ = best_compare(root, eng, case["nb"])
                if harness == "exact_graded":
                    cmp_ = c1_variant("graded", eng, case["nb"], cmp_)
                elif harness == "exact_origenc":
                    cmp_ = c1_variant("orig", eng, case["nb"], cmp_)
                row = {"case": case["id"], "category": case["category"], "harness": harness, "engine": eng}
                if cmp_ is None:
                    row.update(verdict="not run", flag=[], outcome="not run")
                    out["by_case"].append(row)
                    summ[harness + ":" + eng]["not run"] += 1
                    continue
                cells = {c["i"]: c for c in cmp_["cells"]}
                ref_rec = json.load(open(os.path.join(PROJ, cmp_["meta"]["ref_record"])))
                eng_rec = json.load(open(os.path.join(PROJ, cmp_["meta"]["eng_record"])))
                si, sname = case["show"]
                sc = cells.get(si, {})
                flags = []
                if sc.get("cls") == "NONDET":
                    flags.append("NONDET")
                rep = None
                if sname:
                    o = (sc.get("outputs") or {}).get(sname)
                    rep = o.get("level") if o else ("NONDET:" + str(sc.get("cls_raw")) if sc.get("cls") == "NONDET" else "missing")
                    if o is None and sc.get("cls") == "NONDET":
                        rep = sc.get("cls_raw")
                    for r in (ref_rec, eng_rec):
                        ent = record_entry(r, si, sname)
                        if harness == "exact_origenc":   # the original encoder's entry of the same value
                            cc = next((c for c in r["cells"] if c["i"] == si), {})
                            alt = (cc.get("outputs_orig") or {}).get(sname)
                            if alt is not None:
                                ent = r["objects"].get(alt) if isinstance(alt, str) else alt
                        if printed_in(store, ent):
                            if "printed" not in flags:
                                flags.append("printed")
                        if isinstance(ent, dict) and (ent.get("info") or {}).get("nested_inexact") and "inexact" not in flags:
                            flags.append("inexact")
                else:
                    rep = sc.get("cls")
                if rep == "UNCOMPARABLE" and "UNCOMPARABLE" not in flags:
                    flags.append("UNCOMPARABLE")
                row.update(show_cell=si, show_name=sname, reported=rep, show_cls=sc.get("cls"), show_cls_raw=sc.get("cls_raw"))
                truth = TRUTH[case["id"]]
                truth = truth.get(eng) if isinstance(truth, dict) else truth
                rd = case.get("reader")
                verdict = None
                if rd:
                    rc = cells.get(rd[0], {})
                    il = rc.get("input_levels") or {}
                    if any("uncapturable" in str(v) for v in il.values()):
                        flags.append("uncapturable_input")
                    if rc.get("cls") == "NONDET" and "NONDET" not in flags:
                        flags.append("NONDET")
                    rcls = rc.get("cls_raw") if rc.get("cls") == "NONDET" else rc.get("cls")
                    rclean = rc.get("clean_level")
                    row.update(reader_cell=rd[0], reader_cls=rcls, reader_clean=rclean, reader_inputs=il,
                               reader_kind=("introduced" if (rcls in ORDER and rclean is not None and ORDER[rcls] > ORDER.get(rclean, 9))
                                            else "inherited" if rcls in ORDER and rcls != "E0" else "equal"))
                    if truth == "reader":
                        if rcls == "DIFF" and rclean is None:
                            verdict = "late"
                        elif rcls == "DIFF":
                            verdict = "misattributed"
                        else:
                            verdict = "unscored"
                    else:  # origin+reader: the origin output must show the difference and the reader must not be clean
                        origin_ok = rep == "DIFF"
                        if rcls == "DIFF" and rclean is None:
                            verdict = "correct" if origin_ok else "late"
                        elif rcls == "DIFF":
                            verdict = "misattributed"
                        else:
                            verdict = "unscored"
                elif truth == "unscored":
                    verdict = "unscored" if rep in ("E0", "NOOUT", None) else "correct"
                elif truth == "NA" or rep == "UNCOMPARABLE":
                    verdict = "n/a"
                else:
                    ok = truth.split("|")
                    if rep in ok:
                        verdict = "correct"
                    elif rep in ORDER and all(t in ORDER for t in ok):
                        verdict = "overstated" if ORDER[rep] > max(ORDER[t] for t in ok) else "understated"
                    else:
                        verdict = "understated"
                flagged = [f for f in flags]
                if verdict == "n/a":
                    outcome = "flagged" if flagged else "missed (difference from representation)"
                elif flagged:
                    outcome = "flagged"
                elif verdict == "correct":
                    outcome = "captured exactly"
                elif verdict in ("understated", "misattributed", "unscored"):
                    outcome = "missed"
                else:
                    outcome = verdict
                exp = case["expected"]["orig" if harness in ("orig", "exact_origenc") else "exact"].get(eng, {})
                pv = {"wrong": ("understated", "misattributed", "overstated"), "coarser": ("overstated",)}.get(exp.get("verdict"), (exp.get("verdict"),))
                row.update(truth=truth, verdict=verdict, flag=flags, outcome=outcome, predicted=exp,
                           prediction_held=(harness in ("orig", "exact")) and (verdict in pv or (verdict == "n/a" and exp.get("verdict") == "wrong")) and
                           (exp.get("flag", "none") in flags or (exp.get("flag", "none") == "none" and not flags)))
                out["by_case"].append(row)
                summ[harness + ":" + eng][outcome] += 1
    out["summary"] = {k: dict(v) for k, v in summ.items()}
    out["predictions_held"] = sum(1 for r in out["by_case"] if r.get("prediction_held"))
    out["rows"] = len(out["by_case"])
    out["rows_predicted"] = sum(1 for r in out["by_case"] if r["harness"] in ("orig", "exact"))
    # dual-capture check: the original encoder's entries of the exact-harness runs give the original harness's result
    key = lambda r: (r["case"], r["engine"])
    o = {key(r): (r.get("reported"), r.get("reader_cls"), r.get("reader_clean")) for r in out["by_case"] if r["harness"] == "orig"}
    e = {key(r): (r.get("reported"), r.get("reader_cls"), r.get("reader_clean")) for r in out["by_case"] if r["harness"] == "exact_origenc"}
    out["dual_capture_check"] = {"rows": len(o), "same_result": sum(1 for k in o if e.get(k) == o[k]),
                                 "differ": sorted("%s/%s: %s vs %s" % (k[0], k[1], o[k], e.get(k)) for k in o if e.get(k) != o[k])}
    with open(os.path.join(HERE, "c2_results.json"), "w") as f:
        json.dump(out, f, indent=1, sort_keys=True, default=str)
    for r in out["by_case"]:
        print("%-5s %-9s %-27s reported=%-12s reader=%-18s verdict=%-8s flags=%-28s -> %s%s" % (
            r["harness"], r["engine"], r["case"], r.get("reported"),
            "%s/%s" % (r.get("reader_cls"), r.get("reader_clean")) if "reader_cell" in r else "-",
            r.get("verdict"), ",".join(r.get("flag") or []), r.get("outcome"),
            "" if r.get("prediction_held") else "   [prediction: %s]" % r.get("predicted")))
    print(json.dumps(out["summary"], indent=1, sort_keys=True))
    print("predictions held: %d of %d" % (out["predictions_held"], out["rows_predicted"]))
    print("dual capture check:", json.dumps(out["dual_capture_check"], indent=1))


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Machine-readable cell ledger, per-output relaxation evidence and run manifest of the artifact (review round R5;
ICDE 2027 copy; written 2026-11-10).

Read-only on results/{drift,conf_1x,conf_5x,pilot,timing,timing_bodo_r2}/raw (run records and compare outputs),
results/summary.json, the taxonomy rules (scripts/rootcause_taxonomy.py, which read notebook code and engine
messages) and icde27/analysis/{r4_audit.json,r4_cell_flags.csv,r5_printed_flags.csv,r5_claim_map.csv}; writes only
icde27/analysis/r5_cell_ledger.csv, r5_relaxations.csv, r5_run_manifest.csv and r5_ledger.json. About a minute,
below 2 GB.

    cd ..
    /usr/bin/time -l .venv/bin/python 06_pandas_conformance-ICDE/icde27/analysis/r5_ledger.py

r5_cell_ledger.csv, one row per code cell of the 7 configurations of the paper on 102 notebooks (pandas 1.5.3 and
3.0.6 against the drift reference, the pyarrow backend, Modin, FireDucks, Bodo with one worker and Dask against the
conf_1x reference); stable ID configuration|PandasBench slug (commit ae70611)|0-based code-cell index:
  cls, scored, exclusion (REF_ERR, NONDET, NOOUT, SETUP_ERR: excluded from every view), post_timeout (removed from the
  clean views), clean_level, clean_E0, clean_E2 (in the clean@E0 / clean@E2 views);
  serialization: exact, or printed_output_match / printed_output_diff / printed_input_match / printed_input_diff
  (r5_uncertainty.py flags; several joined by +);
  parents: the input names of the cell with the earlier cell that last bound each (name@cell, reference run);
  kind_pure (introduced, inherited, cascade, harness, nondet: the paper's definition), kind_heuristic (the
  alternative with 59 cells inherited), heuristic_exception;
  cause, assigned_by (rule, curated, none), rule_index, single_rater_cause, single_rater_confidence, cause_evidence
  (reproducer or probe outcome on this configuration), evidence_class (r5_evidence.py: documented, partly
  documented, conflicts with a compatibility claim, no applicable promise), printed16 (one of the 16 known printed-form
  artifact cells), match_budget_exceeded, n_outputs, first_failing_check (the coarsest output's check at E0).
r5_relaxations.csv, one row per compared output that is not E0-equal in a scored cell: the first successful level,
  the row matching used (identity, sort, matching), the first failing check at each finer level, the largest float
  error at the level reached, and the relaxations these show to be needed (row order: a permutation other than the
  identity; widening: a dtype or encoding check failed at a finer level; tolerance: a non-zero float error; sentinel:
  a sentinel check failed; index: an index or name check failed below E4). The comparator reports only the first
  failing check per level, so a relaxation not shown may still be needed: the vector is a lower bound.
r5_run_manifest.csv, one row per run record of the six campaigns: campaign, configuration, notebook, scale,
  repetition, mode, status, return code, fingerprint (package list, notebook, inputs, harness, configuration), the
  notebook, environment and harness hashes, versions, start time, wall time, peak memory, and whether a compare output
  of the paper (compare tag d92c8db54d45b) references the record. Released records keep the fingerprints, so a
  re-run can be matched record by record.
"""
import collections
import csv
import datetime
import glob
import hashlib
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
OUT_LEDGER = os.path.join(HERE, "r5_cell_ledger.csv")
OUT_RELAX = os.path.join(HERE, "r5_relaxations.csv")
OUT_RUNS = os.path.join(HERE, "r5_run_manifest.csv")
OUT_JSON = os.path.join(HERE, "r5_ledger.json")
LEVELS = ("E0", "E1", "E2", "E3", "E4")
DTYPE_CHECKS = ("dtype:", "dtype_family:", "encoding:", "encoding_dtype:", "labels_dtype:", "index:dtype", "scalar_type:",
                "scalar_family:", "int_not_representable")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R1 = load_module("r1_cells", os.path.join(HERE, "r1_cells.py"))
LABELS, EXCLUDED = R1.LABELS, R1.EXCLUDED


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def relax(o):
    """compare output entry -> (level, match, fails, max_rel_err, needed flags)"""
    lv = o.get("level")
    fails = o.get("fails") or {}
    match = o.get("match") or ""
    fe = o.get("float_err") or {}
    rel = max([float((v or {}).get("max_rel_err") or 0.0) for v in fe.values()] or [0.0])
    finer = [L for L in LEVELS if lv in LEVELS and LEVELS.index(L) < LEVELS.index(lv)]
    chk = [str(fails.get(L) or "") for L in finer]
    need = {"row_order": lv in LEVELS[1:] and match not in ("", "identity"),
            "widening": lv in LEVELS[2:] and any(c.startswith(DTYPE_CHECKS) for c in chk),
            "tolerance": lv in LEVELS[2:] and rel > 0,
            "sentinel": lv in LEVELS[3:] and any(c.startswith(("sentinel", "index:sentinel")) for c in chk),
            "index": lv == "E4" and str(fails.get("E3") or "").startswith(("index", "names", "labels"))}
    return lv, match, fails, rel, need


def main():
    T = load_module("rootcause_taxonomy", os.path.join(PROJ, "scripts", "rootcause_taxonomy.py"))
    r4 = json.load(open(os.path.join(HERE, "r4_audit.json")))
    hand = json.load(open(os.path.join(HERE, "r1_hand_attribution.json")))
    printed16 = {(r["label"], r["nb"], r["cell"]) for r in hand["rows"] if r["cause"] == "printed_form_comparison"}
    flags = {}
    with open(os.path.join(HERE, "r4_cell_flags.csv")) as f:
        for row in csv.DictReader(f):
            flags[row["id"]] = row
    pf = {}
    with open(os.path.join(HERE, "r5_printed_flags.csv")) as f:
        for row in csv.DictReader(f):
            pf[row["id"]] = row
    evc = {}
    with open(os.path.join(HERE, "r5_claim_map.csv")) as f:
        for row in csv.DictReader(f):
            evc[(row["cause"], row["configuration"])] = row["evidence_class"]
    nb_sha = {x["nb"]: x["nb_sha256"] for x in r4["membership"]["reduced_capture_notebooks"]}

    ledger, relax_rows, referenced = [], [], set()
    for campaign in ("conf_1x", "drift"):
        root, best = T.select_outputs(campaign, T.COMPARE)
        for (label, nb, sc), (_, r, p) in sorted(best.items()):
            if (campaign, label) not in LABELS:
                continue
            m = r["meta"]
            referenced.update(os.path.relpath(os.path.join(PROJ, x), PROJ) for x in (m.get("eng_record"), m.get("ref_record"), m.get("ref2_record")) if x)
            ref = json.load(open(os.path.join(PROJ, m["ref_record"])))
            eng = json.load(open(os.path.join(PROJ, m["eng_record"])))
            nb_sha.setdefault(nb, eng.get("nb_sha256"))
            # parents: the earlier cell (reference run) that last bound each input name
            last, parents = {}, {}
            for cr in ref.get("cells", []):
                st = cr.get("static") or {}
                names = set((cr.get("inputs") or {}).keys()) or set(st.get("loads") or [])
                parents[cr["i"]] = sorted("%s@%d" % (n_, last[n_]) for n_ in names if n_ in last)
                for n_ in list((cr.get("outputs") or {}).keys()) + list(st.get("stores") or []) + list(st.get("mutates") or []):
                    if n_ != "__last__":
                        last[n_] = cr["i"]
            cl = r["cells"]
            t_idx = next((k for k, c in enumerate(cl) if c.get("cls") == "TIMEOUT" or c.get("cls_raw") == "TIMEOUT"), None)
            for k, c in enumerate(cl):
                cid = "%s|%s|%d" % (label, nb, c["i"])
                kind = cause = why = None
                if c["cls"] not in ("E0", "NOOUT", "REF_ERR", "NONDET"):
                    n = T.normalise_cell(campaign, label, nb, c)
                    n["code"] = T.cell_code(nb, c["i"])
                    cause, kind, why = T.classify_cell(n)
                exc = cause == "order_propagated"
                kp = "introduced" if exc else kind
                kp, kind = ({"propagated": "inherited"}.get(kp, kp), {"propagated": "inherited"}.get(kind, kind))
                fl = flags.get(cid) or {}
                pfr = pf.get(cid)
                ser = "exact"
                if pfr:
                    ser = "+".join(x for x, y in (("printed_output_match", pfr["out_match"]), ("printed_output_diff", pfr["out_diff"]),
                                                  ("printed_input_match", pfr["in_match"]), ("printed_input_diff", pfr["in_diff"])) if y == "1")
                outs = c.get("outputs") or {}
                worst = None
                for name, o in sorted(outs.items()):
                    lv = o.get("level")
                    if worst is None or (lv in T.RANK and worst[1] in T.RANK and T.RANK[lv] > T.RANK[worst[1]]) or (lv not in T.RANK):
                        worst = (name, lv, (o.get("fails") or {}).get("E0", o.get("reason") or ""))
                    if c["cls"] not in EXCLUDED and lv not in (None, "E0"):
                        lv_, match, fails, rel, need = relax(o)
                        relax_rows.append({"id": cid, "output": name, "level": lv_, "match": match,
                                           "fail_E0": fails.get("E0", ""), "fail_E1": fails.get("E1", ""), "fail_E2": fails.get("E2", ""),
                                           "fail_E3": fails.get("E3", ""), "fail_E4": fails.get("E4", ""),
                                           "max_rel_float_err": "%.3g" % rel if rel else "",
                                           "needs_row_order": int(need["row_order"]), "needs_widening": int(need["widening"]),
                                           "needs_tolerance": int(need["tolerance"]), "needs_sentinel": int(need["sentinel"]),
                                           "needs_index": int(need["index"]),
                                           "match_budget_exceeded": int(bool(o.get("match_limit"))), "reason": o.get("reason") or ""})
                clean = c.get("clean_level")
                ledger.append({
                    "id": cid, "campaign": campaign, "configuration": label, "nb": nb, "cell": c["i"],
                    "cls": c["cls"], "scored": int(c["cls"] not in EXCLUDED),
                    "exclusion": c["cls"] if c["cls"] in EXCLUDED else "",
                    "post_timeout": int(t_idx is not None and k > t_idx), "clean_level": clean or "",
                    "clean_E0": int(c["cls"] not in EXCLUDED and not (t_idx is not None and k > t_idx) and clean == "E0"),
                    "clean_E2": int(c["cls"] not in EXCLUDED and not (t_idx is not None and k > t_idx) and clean in ("E0", "E1", "E2")),
                    "serialization": ser, "parents": ";".join(parents.get(c["i"], [])),
                    "kind_pure": kp or "", "kind_heuristic": kind or "", "heuristic_exception": int(exc),
                    "cause": "unattributed" if exc else (cause or ""),
                    "assigned_by": fl.get("assigned_by", ""), "rule_index": fl.get("rule_index", ""),
                    "single_rater_cause": fl.get("single_rater_cause", ""), "single_rater_confidence": fl.get("single_rater_confidence", ""),
                    "cause_evidence": fl.get("cause_evidence", ""),
                    "evidence_class": evc.get((cause, label), "") if kp == "introduced" and not exc else "",
                    "printed16": int((label, nb, c["i"]) in printed16),
                    "match_budget_exceeded": int(any(o.get("match_limit") for o in outs.values())),
                    "n_outputs": len(outs), "first_failing_check": (worst[2] if worst and worst[1] not in ("E0", None) else "")})
    # consistency with the published counts
    kc = collections.Counter(r["kind_pure"] for r in ledger if r["kind_pure"])
    kh = collections.Counter(r["kind_heuristic"] for r in ledger if r["kind_heuristic"])
    tot = r4["exception"]["totals"]
    pilot_intro = 65   # the pilot bodo_dw cells are in the taxonomy but not in this ledger (paper_provenance pilot_label_cells)
    checks = [("introduced pure (7 configurations) = taxonomy off minus pilot bodo_dw", tot["introduced"]["off"] - pilot_intro - tot["exception_cells_pilot"],
               kc["introduced"]),
              ("introduced heuristic = taxonomy on minus pilot", tot["introduced"]["on"] - pilot_intro, kh["introduced"]),
              ("printed-form flags carried", len(pf), sum(r["serialization"] != "exact" for r in ledger)),
              ("16 printed-form artifact cells", 16, sum(r["printed16"] for r in ledger)),
              ("one output above the matching budget", 1, sum(r["match_budget_exceeded"] for r in ledger))]
    bad = [c for c in checks if c[1] != c[2]]
    if bad:
        raise SystemExit("consistency check failed: %s" % bad)

    # run manifest
    runs = []
    for camp in ("drift", "conf_1x", "conf_5x", "pilot", "timing", "timing_bodo_r2"):
        for p in sorted(glob.glob(os.path.join(PROJ, "results", camp, "raw", "*__hd1c421ecb5ee", "*", "*", "*.json"))):
            if "/compare__" in p:
                continue
            try:
                rr = json.load(open(p))
            except (OSError, ValueError):
                continue
            rel = os.path.relpath(p, PROJ)
            runs.append({"campaign": camp, "configuration": rr.get("engine"), "nb": rr.get("nb"), "scale": rr.get("scale"),
                         "rep": rr.get("rep"), "mode": rr.get("mode"), "status": rr.get("status"), "returncode": rr.get("returncode"),
                         "fingerprint": rr.get("fingerprint"), "nb_sha256": rr.get("nb_sha256"),
                         "env_freeze_sha256": rr.get("env_freeze_sha256"), "harness_sha": rr.get("harness_sha"),
                         "python": rr.get("python"), "pandas": rr.get("pandas"), "numpy": rr.get("numpy"),
                         "started_utc": datetime.datetime.fromtimestamp(rr["started"], datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if rr.get("started") else "",
                         "wall_s": rr.get("wall_s"), "peak_tree_rss_gb": rr.get("peak_tree_rss_gb"), "n_cells": rr.get("n_cells"),
                         "record": rel, "referenced_by_paper_compare": int(rel in referenced)})
    for path, rows in ((OUT_LEDGER, ledger), (OUT_RELAX, relax_rows), (OUT_RUNS, runs)):
        with open(path + ".tmp", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
            w.writeheader()
            for r in rows:
                w.writerow(r)
        os.replace(path + ".tmp", path)
    need = collections.Counter()
    for r in relax_rows:
        for k_ in ("row_order", "widening", "tolerance", "sentinel", "index"):
            need[k_] += r["needs_" + k_]
    out = {"files": {os.path.basename(p): {"rows": len(rows), "sha256": sha256(p)}
                     for p, rows in ((OUT_LEDGER, ledger), (OUT_RELAX, relax_rows), (OUT_RUNS, runs))},
           "consistency_checks": {"n": len(checks), "mismatches": 0},
           "ledger": {"cells": len(ledger), "scored": sum(r["scored"] for r in ledger), "kind_pure": dict(kc),
                      "serialization_flagged": sum(r["serialization"] != "exact" for r in ledger)},
           "relaxations": {"outputs": len(relax_rows), "by_level": dict(collections.Counter(r["level"] for r in relax_rows)),
                           "needed": dict(need)},
           "runs": {"records": len(runs), "by_campaign": dict(collections.Counter(r["campaign"] for r in runs)),
                    "referenced_by_paper_compare": sum(r["referenced_by_paper_compare"] for r in runs)}}
    with open(OUT_JSON + ".tmp", "w") as f:
        json.dump(out, f, indent=1)
    os.replace(OUT_JSON + ".tmp", OUT_JSON)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    sys.exit(main())

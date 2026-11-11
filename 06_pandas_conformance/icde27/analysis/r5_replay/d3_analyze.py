#!/usr/bin/env python3
"""D3 analysis: combine the mechanical checks into per-cell verdicts, agreement per stratum, every disagreement, and
the corrected parallel-or-lazy shares. Stdlib only. Writes d3_results.json.   Usage: python3 d3_analyze.py

N2 outcome per cell: "vanishes" (no longer DIFF against the reference under the serial variant: class E0-E4),
"persists" (still an introduced DIFF), "inconclusive" (failed, not run, inherited DIFF, uncomparable), "untested".
Agreement with the attribution: for a parallel-or-lazy cause, vanishes = agree, persists = disagree; for any other
cause, persists = agree, vanishes = disagree (the difference goes away without parallel or partitioned execution
although it is attributed to something else). Bodo's row-order cells: Bodo already ran with one worker, so worker
pinning cannot remove them: "persists (1 worker)" by construction (disagree with the parallel label).
N3/N1/N6/N7: confirmed = agree, not confirmed = disagree. N8 (by construction) and N9 (localization only) are reported
separately and do not enter the agreement rates.
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import r5common as R  # noqa: E402

OUT = os.path.join(HERE, "d3_results.json")
CMP = os.path.join(R.WORK, "compare", "serial")
VALUE = {"E0", "E1", "E2", "E3", "E4"}
PAPER_DEN = {"modin": 49, "fireducks": 58, "bodo": 80, "pyarrow_backend": 51, "dask": 46}   # introduced DIFF, no printed
D2_CASE_CELL = {}


def n2_outcome(orig_cls, sc):
    """N2 outcome of one cell from its original class and its class under the serial variant.
    DIFF cells (P, Q and every DIFF cell): vanishes = no longer DIFF (E0-E4); persists = again an introduced DIFF.
    Cells of class E1-E4: vanishes = a finer class under the serial variant; persists = the same or a coarser class.
    Failure cells (ERR, ...): vanishes = a value class (E0-E4) under the serial variant; persists = the same failure."""
    if sc is None:
        return "inconclusive", "cell not in serial comparison"
    s_cls, s_clean = sc["cls"], sc.get("clean_level")
    if orig_cls == "DIFF":
        if s_cls in VALUE:
            return "vanishes", s_cls
        if s_cls == "DIFF" and R.introduced("DIFF", s_clean):
            return "persists", "DIFF, clean %s" % s_clean
        return "inconclusive", "%s, clean %s" % (s_cls, s_clean)
    if orig_cls in R.RANK:          # E1-E4
        if s_cls in VALUE and R.RANK[s_cls] < R.RANK[orig_cls]:
            return "vanishes", "%s -> %s" % (orig_cls, s_cls)
        if s_cls in R.RANK and R.RANK[s_cls] >= R.RANK[orig_cls]:
            return "persists", "%s -> %s" % (orig_cls, s_cls)
        return "inconclusive", "%s -> %s" % (orig_cls, s_cls)
    if s_cls in VALUE:
        return "vanishes", "%s -> %s" % (orig_cls, s_cls)
    if s_cls == orig_cls:
        return "persists", "%s again" % s_cls
    return "inconclusive", "%s -> %s" % (orig_cls, s_cls)


def _group(rows):
    g = collections.defaultdict(collections.Counter)
    for r in rows:
        g[r["cause"]][r["outcome"]] += 1
    return g


def main():
    plan = R.read_json(os.path.join(HERE, "d3_plan.json"))
    run = R.read_json(os.path.join(HERE, "d3_run_d3n2.json")) or {"results": []}
    checks = R.read_json(os.path.join(HERE, "d3_checks.json")) or {"N3": {}, "N1": {}, "N6": {}}
    d2 = R.read_json(os.path.join(HERE, "d2_results.json")) or {"cases": []}
    import d2_cases
    d2_by_cell = {}
    for case in d2_cases.CASES:
        for cfg in case["configs"]:
            d2_by_cell[(cfg, case["nb"], case["cell"])] = case["id"]
    d2_verdict = {}
    for e in d2["cases"]:
        for cfg, v in e["configs"].items():
            d2_verdict[(cfg, e["nb"], e["cell"])] = v["verdict"]
    ran = {(r["variant"], r["nb"]): r for r in run["results"]}
    serial = {}
    for (variant, nb), r in ran.items():
        p = os.path.join(CMP, variant, R.nb_key(nb) + ".json")
        if os.path.exists(p):
            serial[(variant, nb)] = {c["i"]: c for c in R.read_json(p)["cells"]}
    per_cell = []
    for c in plan["cells"]:
        parallel = c["parallel_lazy"]
        v = {"id": c["id"], "strata": c["strata"], "label": c["label"], "nb": c["nb"], "cell": c["cell"], "cls": c["cls"],
             "clean_level": c["clean_level"], "assigned_by": c["assigned_by"], "cause": c["cause"], "parallel_lazy": parallel,
             "tests": {}}
        if "N2" in c["tests"]:
            variant = plan["serial_variant"][c["label"]]
            if c["label"] == "bodo" and c["cause"] == "row_order_ties":
                out, detail = "persists (1 worker)", "Bodo ran with one worker in conf_1x"
            elif (variant, c["nb"]) not in ran or ran[(variant, c["nb"])]["status"] not in ("completed", "nb_crash", "nb_memory", "nb_timeout"):
                out, detail = "untested", "serial run %s" % (ran.get((variant, c["nb"])) or {}).get("status", "not run")
            elif (variant, c["nb"]) not in serial:
                out, detail = "untested", "no comparison output"
            else:
                sc = serial[(variant, c["nb"])].get(c["cell"])
                out, detail = n2_outcome(c["cls"], sc)
            if out == "persists" and c["cause"] == "lazy_partition_model":
                out = "persists (laziness not neutralized)"     # amendment 2: serial execution keeps laziness
                agree = None
            elif out.startswith("persists"):
                agree = not parallel
            elif out == "vanishes":
                agree = parallel
            else:
                agree = None
            v["tests"]["N2"] = {"variant": variant, "outcome": out, "detail": detail, "agree": agree}
        for k in ("N3", "N1", "N6"):
            if k in c["tests"]:
                x = checks.get(k, {}).get(c["id"])
                if x is None:
                    v["tests"][k] = {"outcome": "untested", "agree": None}
                else:
                    v["tests"][k] = dict(x, outcome=x["verdict"],
                                         agree=True if x["verdict"] == "confirmed" else (False if x["verdict"] == "not confirmed" else None))
        if "N7" in c["tests"]:
            dv = d2_verdict.get((c["label"], c["nb"], c["cell"]))
            if dv is None and c["label"] == "bodo_dw":
                dv = d2_verdict.get(("bodo_dw", c["nb"], c["cell"]))
            agree = None if dv is None else (True if dv.startswith("confirmed") else (False if dv.startswith(("capture", "not reproduced")) else None))
            v["tests"]["N7"] = {"outcome": dv or "untested", "agree": agree}
        if "N8" in c["tests"]:
            v["tests"]["N8"] = {"outcome": "consistent by construction", "agree": None}
        if "N9" in c["tests"]:
            v["tests"]["N9"] = {"outcome": "localization certain (inputs bit-identical)", "agree": None}
        ag = [t["agree"] for k, t in v["tests"].items() if k not in ("N8", "N9") and t.get("agree") is not None]
        if not ag:
            v["overall"] = "untested" if not [k for k in v["tests"] if k not in ("N8", "N9")] else "inconclusive"
        elif all(ag):
            v["overall"] = "agree"
        elif not any(ag):
            v["overall"] = "disagree"
        else:
            v["overall"] = "mixed"
        per_cell.append(v)
    by_id = {v["id"]: v for v in per_cell}
    strata = {}
    for s, ids in plan["strata"].items():
        cnt = collections.Counter(by_id[i]["overall"] for i in ids)
        tests = {}
        for k in ("N2", "N3", "N1", "N6", "N7", "N8", "N9"):
            tc = collections.Counter(by_id[i]["tests"][k]["outcome"] for i in ids if k in by_id[i]["tests"])
            if tc:
                tests[k] = dict(tc)
        a_, d_ = cnt["agree"], cnt["disagree"] + cnt["mixed"]
        strata[s] = {"cells": len(ids), "overall": dict(cnt), "by_test": tests,
                     "agreement": round(a_ / (a_ + d_), 3) if (a_ + d_) else None, "decided": a_ + d_}
    # corrected parallel-or-lazy shares (paper denominators)
    pl = {}
    for eng, den in PAPER_DEN.items():
        P = [by_id[i] for i in plan["strata"]["P"] if by_id[i]["label"] == eng]
        Q = [by_id[i] for i in plan["strata"]["Q"] if by_id[i]["label"] == eng]
        out = lambda v: v["tests"].get("N2", {}).get("outcome", "untested")  # noqa: E731
        lo = sum(1 for v in P if out(v) == "vanishes")
        refuted = sum(1 for v in P if out(v) in ("persists", "persists (1 worker)"))
        q_v = sum(1 for v in Q if out(v) == "vanishes")
        up = len(P) - refuted + q_v
        pl[eng] = {"paper": [len(P), den], "paper_share": round(len(P) / den, 4), "P_vanish": lo, "P_persist": refuted,
                   "P_inconclusive_or_untested": len(P) - lo - refuted, "Q_cells": len(Q), "Q_vanish": q_v,
                   "interval_cells": [lo, up], "interval_share": [round(lo / den, 4), round(up / den, 4)]}
    # exploratory extension (d3_ext_plan.json): Modin serial variant on the other notebooks with Modin introduced DIFF
    ext_plan = R.read_json(os.path.join(HERE, "d3_ext_plan.json"))
    ext_run = R.read_json(os.path.join(HERE, "d3_run_ext.json")) or {"results": []}
    ext = None
    if ext_plan:
        eran = {r["nb"]: r for r in ext_run["results"]}
        rows = []
        for c in ext_plan["cells"]:
            p = os.path.join(CMP, "modin_serial", R.nb_key(c["nb"]) + ".json")
            r = eran.get(c["nb"])
            if r is None or not os.path.exists(p) or r["status"] not in ("completed", "nb_crash", "nb_memory", "nb_timeout"):
                out = "untested"
                det = (r or {}).get("status", "not run")
            else:
                sc = {x["i"]: x for x in R.read_json(p)["cells"]}.get(c["cell"])
                out, det = n2_outcome("DIFF", sc)
            rows.append(dict(c, outcome=out, detail=det))
        cnt = collections.Counter(r["outcome"] for r in rows)
        m = pl["modin"]
        n_other = PAPER_DEN["modin"] - m["paper"][0] - m["Q_cells"]          # Modin DIFF cells outside the P notebooks
        lo = m["P_vanish"] + m["Q_vanish"] + cnt["vanishes"]
        up = lo + m["P_inconclusive_or_untested"] + (n_other - cnt["vanishes"] - cnt["persists"])
        ext = {"label": "exploratory (decided after the N2 results)", "cells": rows, "outcomes": dict(cnt),
               "by_cause": {k: dict(v) for k, v in _group(rows).items()},
               "modin_partitioned_share_cells": [lo, up], "modin_partitioned_share": [round(lo / PAPER_DEN["modin"], 4),
                                                                                       round(up / PAPER_DEN["modin"], 4)],
               "note": "lower: Modin introduced DIFF cells (exception on, no printed forms) that vanish under modin_serial "
                       "(P, Q and extension); upper: plus cells not tested or inconclusive"}
    drop_in = ("modin", "fireducks", "pyarrow_backend", "bodo")
    res = {"item": "D3", "method": __doc__.strip(), "strata": strata, "parallel_or_lazy": pl, "exploratory_modin_extension": ext,
           "max_drop_in_upper_share": max(pl[e]["interval_share"][1] for e in drop_in),
           "max_drop_in_paper_share": max(pl[e]["paper_share"] for e in drop_in),
           "disagreements": [v for v in per_cell if v["overall"] in ("disagree", "mixed")], "cells": per_cell}
    R.write_json(OUT, res)
    for s, x in strata.items():
        print("%s cells %3d overall %s agreement %s (decided %d) tests %s" % (s, x["cells"], x["overall"], x["agreement"], x["decided"], x["by_test"]))
    for e, x in pl.items():
        print("%-16s paper %s=%.3f | P vanish %d persist %d other %d | Q vanish %d of %d | interval %s %s" % (
            e, x["paper"], x["paper_share"], x["P_vanish"], x["P_persist"], x["P_inconclusive_or_untested"], x["Q_vanish"],
            x["Q_cells"], x["interval_cells"], x["interval_share"]))
    print("max drop-in upper share", res["max_drop_in_upper_share"], "paper", res["max_drop_in_paper_share"])
    print("disagreements:", len(res["disagreements"]))
    if ext:
        print("exploratory Modin extension:", ext["outcomes"], ext["by_cause"], "Modin share", ext["modin_partitioned_share_cells"], ext["modin_partitioned_share"])


if __name__ == "__main__":
    main()

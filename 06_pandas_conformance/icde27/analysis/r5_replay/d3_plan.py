#!/usr/bin/env python3
"""D3 (mechanical attribution audit): write the pre-declared strata, samples and test assignment d3_plan.json BEFORE
any D3 check runs. Stdlib only.   Usage: python3 d3_plan.py

Strata (cells of r4_cell_flags.csv; the paper's exception-on view, kind_exception_on == introduced):
  P  census: conf_1x engine introduced DIFF cells (not printed-form artifacts) counted as parallel or lazy execution in
     the paper (rule or curated cause in r1_cells.MECHANISM's parallel group, or single-rater mechanism "parallel or lazy
     execution"): Modin 18, FireDucks 14, Bodo 12, pyarrow backend 4, Dask 27.
  Q  cluster sample: the other conf_1x introduced DIFF cells (not printed-form) of the same engine in the notebooks of P.
  C  census: the 21 curated cells.
  S  census: the 117 cells the rules leave unattributed (single-rater attributions).
  R  stratified random sample: rule-assigned introduced engine cells (conf_1x and pilot labels) of causes outside the
     parallel group: up to 3 cells per cause, random.Random("20261110|<cause>").
  H  census: conf_1x cells of the high-impact causes named in the abstract, findings and lessons: FireDucks chained
     assignment, Modin and Bodo silent engine errors (value_counts/pivot_table/stale head), Modin corr values, lost axis
     or Series names (DIFF cells), dtype-name checks, Arrow-backed dtypes in Bodo and Dask (DIFF cells).
Tests (mechanical; no language model):
  N2  serial-execution counterfactual (new captured runs of whole notebooks with the parallel or partitioned execution
      switched off: Modin Python engine with 1 partition, Dask synchronous scheduler with one partition per CSV read,
      FireDucks 1 thread, pyarrow backend 1 Arrow thread, Bodo exact quantiles); applies to P and Q (and any audited cell
      in those notebooks).
  N3  cross-configuration injection (existing records): the engine's output is compared with a configuration that has
      ONLY the claimed mechanism: pandas with Arrow-backed dtypes (pyarrow backend) for Arrow causes and dtype-name
      checks of Bodo and Dask; pandas 3.0.6 (Copy-on-Write) for FireDucks' chained assignment.
  N1  single-mechanism sufficiency (stored values, cells of class E1-E4): only the claimed mechanism's relaxation is
      applied to both captured values; confirmed if that alone makes them equal.
  N6  printed-form census (cells the single rater calls a harness artefact): confirmed if r4_printed_forms.json lists the
      cell among the cells whose differing printed forms made it DIFF (an encoding fact, independent of the rater).
  N7  uncaptured replay on the notebook (D2): for the cells that are D2 cases, the D2 verdict.
  N8  by construction: pyarrow-backend cells with an Arrow-family cause (that configuration differs from the reference
      only by dtype_backend='pyarrow' in the readers), reported separately from tested mechanisms.
  N9  localization only (not the mechanism): the cell's inputs are bit-identical to the reference (clean level E0), so
      the cell itself introduces the difference, whatever its cause.
"""
import collections
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r5common as R  # noqa: E402

OUT = os.path.join(R.HERE, "d3_plan.json")
SEED = "20261110"
HIGH_IMPACT = {"cow_chained_assignment", "engine_bug_silent", "engine_corr_wrong_values", "axis_names_lost",
               "str_dtype_object_checks", "arrow_backed_dtypes", "approximate_quantile"}
N3_PARTNER = {("arrow_backed_dtypes", "bodo"): "pyarrow_backend", ("arrow_backed_dtypes", "dask"): "pyarrow_backend",
              ("arrow_dtype_errors", "bodo"): "pyarrow_backend", ("str_dtype_object_checks", "bodo"): "pyarrow_backend",
              ("str_dtype_object_checks", "dask"): "pyarrow_backend", ("na_comparison_masks", "bodo"): "pyarrow_backend",
              ("cow_chained_assignment", "fireducks"): "p30"}
# N1: mechanism -> single relaxation (d3_checks.py implements each on decoded captured values)
N1_RELAX = {"row_order_ties": "sort_rows", "float_rounding_within_tolerance": "float_tol", "arrow_backed_dtypes": "canon_dtype",
            "int_float_nullable_repr": "canon_dtype", "scalar_type_numpy": "canon_dtype", "dtype_inference_differs": "canon_dtype",
            "str_default_dtype": "canon_dtype", "missing_sentinel_repr": "unify_missing", "index_not_preserved": "drop_index",
            "axis_names_lost": "drop_names", "value_counts_naming": "drop_names", "partitioned_type_inference": "canon_dtype"}
ARROW_FAMILY = {"arrow_backed_dtypes", "arrow_dtype_errors", "str_dtype_object_checks", "na_comparison_masks",
                "arrow_int_keeps_type", "arrow_nan_not_null"}
SERIAL_VARIANT = {"modin": "modin_serial", "dask": "dask_serial", "fireducks": "fireducks_1t",
                  "pyarrow_backend": "pyarrow_1t", "bodo": "bodo_exactq"}


def main():
    flags = R.cell_flags()
    hand = R.hand_rows()
    cells = []
    for r in flags:
        if r["kind_exception_on"] != "introduced":
            continue
        key = (r["configuration"], r["nb"], int(r["cell"]))
        h = hand.get(key)
        cause = r["cause"] if r["assigned_by"] in ("rule", "curated") else (h["cause"] if h else "unattributed")
        mech = h["mechanism"] if (r["assigned_by"] == "none" and h) else None
        parallel = (r["assigned_by"] in ("rule", "curated") and r["cause"] in R.PARALLEL_LAZY_CAUSES) or \
                   (r["assigned_by"] == "none" and mech == "parallel or lazy execution")
        cells.append({"id": r["id"], "campaign": r["campaign"], "label": r["configuration"], "nb": r["nb"],
                      "cell": int(r["cell"]), "cls": r["cls"], "clean_level": r["clean_level"],
                      "assigned_by": r["assigned_by"], "cause": cause, "single_rater_mechanism": mech,
                      "single_rater_confidence": h["confidence"] if h else None, "parallel_lazy": parallel,
                      "printed": r["printed_form_artifact"] == "True", "reduced_capture": r["reduced_capture_notebook"] == "True"})
    eng_conf = lambda c: c["campaign"] == "conf_1x" and c["label"] in R.ENGINES  # noqa: E731
    P = [c for c in cells if eng_conf(c) and c["cls"] == "DIFF" and not c["printed"] and c["parallel_lazy"]]
    p_nbs = collections.defaultdict(set)
    for c in P:
        p_nbs[c["label"]].add(c["nb"])
    Q = [c for c in cells if eng_conf(c) and c["cls"] == "DIFF" and not c["printed"] and not c["parallel_lazy"]
         and c["nb"] in p_nbs[c["label"]]]
    C = [c for c in cells if c["assigned_by"] == "curated"]
    S = [c for c in cells if c["assigned_by"] == "none"]
    by_cause = collections.defaultdict(list)
    for c in cells:
        if c["assigned_by"] == "rule" and c["campaign"] in ("conf_1x", "pilot") and c["cause"] not in R.PARALLEL_LAZY_CAUSES:
            by_cause[c["cause"]].append(c)
    Rs = []
    for cause in sorted(by_cause):
        lst = sorted(by_cause[cause], key=lambda c: c["id"])
        Rs += random.Random("%s|%s" % (SEED, cause)).sample(lst, min(3, len(lst)))
    H = [c for c in cells if eng_conf(c) and c["cause"] in HIGH_IMPACT and
         (c["cause"] not in ("axis_names_lost", "arrow_backed_dtypes") or c["cls"] == "DIFF")]
    strata = {"P": P, "Q": Q, "C": C, "S": S, "R": Rs, "H": H}
    # tests per cell
    import d2_cases
    d2_cells = {(cfg, c["nb"], c["cell"]) for c in d2_cases.CASES for cfg in c["configs"]}
    d2_cells |= {("bodo_dw", "shashi772/data-cleaning-challenge-parsing-dates", 0)}
    audited = {}
    for s, lst in strata.items():
        for c in lst:
            a = audited.setdefault(c["id"], dict(c, strata=[]))
            a["strata"].append(s)
    for a in audited.values():
        t = []
        if a["campaign"] == "conf_1x" and a["label"] in SERIAL_VARIANT and a["nb"] in p_nbs.get(a["label"], set()):
            t.append("N2")
        if (a["cause"], a["label"]) in N3_PARTNER:
            t.append("N3")
        if a["cls"] in ("E1", "E2", "E3", "E4") and a["cause"] in N1_RELAX:
            t.append("N1")
        if a["cause"] == "printed_form_comparison":
            t.append("N6")
        if (a["label"], a["nb"], a["cell"]) in d2_cells:
            t.append("N7")
        if a["label"] == "pyarrow_backend" and a["cause"] in ARROW_FAMILY:
            t.append("N8")
        if a["clean_level"] == "E0":
            t.append("N9")
        a["tests"] = t
    n2_runs = sorted({(SERIAL_VARIANT[c["label"]], c["label"], c["nb"]) for c in P})
    plan = {"item": "D3", "created_before_any_check": True, "seed": SEED, "strata_sizes": {s: len(v) for s, v in strata.items()},
            "strata": {s: [c["id"] for c in v] for s, v in strata.items()}, "cells": sorted(audited.values(), key=lambda a: a["id"]),
            "n2_runs": [{"variant": v, "engine": e, "nb": nb} for v, e, nb in n2_runs], "n3_partner": {"%s|%s" % k: v for k, v in N3_PARTNER.items()},
            "n1_relax": N1_RELAX, "serial_variant": SERIAL_VARIANT,
            "P_by_engine": dict(collections.Counter(c["label"] for c in P)),
            "Q_by_engine": dict(collections.Counter(c["label"] for c in Q))}
    tests = collections.Counter(t for a in audited.values() for t in a["tests"])
    untested = sum(1 for a in audited.values() if not [t for t in a["tests"] if t != "N9"])
    print("strata", plan["strata_sizes"], "audited cells", len(audited), "tests", dict(tests), "no mechanical test", untested)
    print("P by engine", plan["P_by_engine"], "Q by engine", plan["Q_by_engine"], "N2 runs", len(n2_runs))
    for s, lst in strata.items():
        tt = collections.Counter(tuple(audited[c["id"]]["tests"]) for c in lst)
        print("  %s: %s" % (s, dict(tt)))
    if os.path.exists(OUT):
        print("d3_plan.json exists; not overwritten (pre-declared)")
        return
    R.write_json(OUT, plan)
    print("wrote", OUT, R.sha256_file(OUT))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Judge the guarded engine probes (plan.md Final-wave F4 step 3, 2026-10-04).

Inputs (read-only):
  results/rootcause/engine_probe_results.json   38 engine probe runs (run_engine_probes.py, guarded)
  results/rootcause/repro_runs.json             reference (pandas 2.3.3) output of the 27 pandas reproducers
  results/rootcause/engine_corr_check.log       guarded follow-up check of engine_corr_wrong_values (pandas and Modin), if present
Writes:
  results/rootcause/engine_probe_ref_runs.json  reference-mode output of the engine-only reproducers (run here: each <1 s,
                                                <200 MB; engine_corr_wrong_values is NOT run here, it needs the guard)
  results/rootcause/engine_probe_outcomes.json  per cause and engine: probe RESULT lines, reference lines, per-check
                                                equality, and the verdict (confirmed / not_reproduced / inconclusive)
Verdicts are curated by reading each probe's lines against the reference lines; VERDICTS below records each
decision and its reason. Usage (from the project folder): ../.venv/bin/python scripts/engine_probe_outcomes.py
"""
import json
import os
import re
import subprocess
import time

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RC = os.path.join(PROJ, "results", "rootcause")
ENGINE_ONLY = ["approximate_quantile", "axis_names_lost", "engine_bug_error", "engine_bug_silent", "engine_unsupported_api",
               "index_not_preserved", "int_float_nullable_repr", "lazy_partition_model", "missing_sentinel_repr",
               "partitioned_type_inference"]

C, N, I = "confirmed", "not_reproduced", "inconclusive"
VERDICTS = {
    ("approximate_quantile", "bodo"): (C, "quantile(0.99) 464.213 vs exact 460.454; 1,974,328 vs 1,980,000 rows below it"),
    ("approximate_quantile", "bodo_dw"): (C, "quantile(0.99) 479.366 vs exact 460.454; 1,984,070 vs 1,980,000 rows below it"),
    ("approximate_quantile", "dask"): (C, "quantile(0.99) 461.344 vs exact 460.454; 1,980,198 vs 1,980,000 rows below it"),
    ("arrow_backed_dtypes", "bodo"): (C, "string, int64[pyarrow], double[pyarrow]; <NA> sentinels (ref: object, int64, float64; nan)"),
    ("arrow_backed_dtypes", "dask"): (C, "text column is 'string' (ref object); the sentinel check raised in the probe (no .iloc on a Dask Series)"),
    ("arrow_dtype_errors", "bodo"): (C, "all three checks raise (ArrowInvalid on '8+', boolean value of NA ambiguous twice); ref raises none"),
    ("arrow_dtype_errors", "fireducks"): (C, "setting '8+' into an int column raises ArrowInvalid (ref upcasts); the two NA checks match ref"),
    ("axis_names_lost", "bodo"): (C, "crosstab columns name None (ref 'Q2'); iloc[0] name matches"),
    ("axis_names_lost", "modin"): (C, "crosstab columns name 'col_0' (ref 'Q2'); iloc[0] name matches"),
    ("cow_chained_assignment", "fireducks"): (C, "none of the three chained assignments writes through (ref pandas 2.3.3 writes through)"),
    ("engine_bug_error", "bodo"): (C, "str.split(' ').str[0] raises TypeError 'BodoStringMethods' object is not subscriptable"),
    ("engine_bug_error", "bodo_dw"): (C, "as bodo; groupby results also come back in another group order"),
    ("engine_bug_error", "modin"): (C, "Series.filter(regex=...) raises ValueError 'No axis named columns'"),
    ("engine_bug_error", "fireducks"): (N, "all four checks equal ref"),
    ("engine_bug_silent", "modin"): (C, "value_counts of a cut result drops the empty bin (7 vs 8 entries); pivot_table(aggfunc='size') "
                                        "returns a DataFrame (ref Series)"),
    ("engine_bug_silent", "bodo"): (N, "value_counts(cut) raises BodoLibNotImplementedException instead of differing silently; the stale "
                                       "head() check never ran (str[0] raised first); the bodo_dw read_csv row loss is not covered by this probe"),
    ("engine_bug_silent", "bodo_dw"): (N, "as bodo"),
    ("engine_unsupported_api", "dask"): (C, "drop(inplace=True), pd.cut and iloc row selection are unsupported"),
    ("engine_unsupported_api", "bodo"): (C, "to_datetime(infer_datetime_format=True) raises TypeError (ref accepts it)"),
    ("engine_unsupported_api", "fireducks"): (C, "groupby sum over a string column raises 'agg function failed' (ref concatenates)"),
    ("float_rounding_within_tolerance", "modin"): (C, "corr diagonal 1.0000000000000073 and off-diagonal ...910692 (ref 1.0, ...912874)"),
    ("float_rounding_within_tolerance", "fireducks"): (C, "corr off-diagonal ...912835 (ref ...912874); mean ...4993097 (ref ...4993096)"),
    ("index_not_preserved", "bodo"): (C, "groupby(as_index=False).mean().sort_values keeps a 0,1,2 index (ref 2,0,1); filters and sort keep it"),
    ("index_not_preserved", "bodo_dw"): (C, "as bodo, with another group order"),
    ("index_not_preserved", "fireducks"): (C, "as bodo"),
    ("index_not_preserved", "dask"): (N, "filters and sort keep the index; groupby(as_index=False) is unsupported (TypeError)"),
    ("int_float_nullable_repr", "modin"): (N, "both checks equal ref"),
    ("int_float_nullable_repr", "fireducks"): (N, "both checks equal ref"),
    ("lazy_partition_model", "dask"): (C, "shape is a lazy Scalar, formatting a lazy mean raises, apply without meta fails"),
    ("missing_sentinel_repr", "fireducks"): (C, "missing string read as None (ref nan)"),
    ("partitioned_type_inference", "dask"): (C, "read_csv raises 'Mismatched dtypes' at compute"),
    ("partitioned_type_inference", "modin"): (N, "column read as 200,001 str values, as ref"),
    ("row_order_ties", "modin"): (C, "value_counts().nlargest(10) labels in another tie order (ref n161, n289, n035, ...)"),
    ("row_order_ties", "fireducks"): (C, "value_counts().nlargest(10) labels in another tie order"),
    ("row_order_ties", "bodo"): (C, "nlargest tie order, sort_values tie order and groupby group order all differ"),
    ("str_dtype_object_checks", "bodo"): (C, "dtype == 'object' and select_dtypes('object') select no column (ref ['city'])"),
    ("str_dtype_object_checks", "dask"): (C, "as bodo"),
    ("engine_corr_wrong_values", "modin"): (N, "the probe printed only the number of '1.0' substrings (15), which cannot decide; the "
                                                "guarded follow-up (engine_corr_wrong_values_check.py, 2026-10-04) on the same synthetic "
                                                "4.4M-row frame finds max |diag - 1| = 9.6e-14 and 0 entries outside [-1, 1] for Modin "
                                                "(pandas: exactly 1.0, 0): out-of-range correlations not reproduced, only last-ulp noise"),
}


def result_lines(text):
    return [l for l in (text or "").splitlines() if l.startswith("RESULT") and not l.startswith("RESULT env")]


def check_map(lines):
    out = {}
    for l in lines:
        m = re.match(r"RESULT (.*?): (.*)$", l)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def run_ref(cause):
    e = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    e.update({"PCONF_REPRO_MODE": "pandas", "OMP_NUM_THREADS": "1", "PYTHONHASHSEED": "0"})
    t0 = time.time()
    p = subprocess.run([os.path.join(PROJ, "envs/ref/bin/python"), cause + ".py"], cwd=os.path.join(RC, "repro"),
                       capture_output=True, text=True, timeout=120, env=e)
    return {"rc": p.returncode, "wall_s": round(time.time() - t0, 2), "result_lines": result_lines(p.stdout)}


def corr_followup():
    path = os.path.join(RC, "engine_corr_check.log")
    if not os.path.exists(path):
        return None
    runs, cur = {}, None
    for l in open(path):
        m = re.match(r"===== .* mode=(\w+)", l)
        if m:
            cur = m.group(1)
            runs[cur] = []
        elif cur and l.startswith("RESULT") and not l.startswith("RESULT env"):
            runs[cur].append(l.rstrip("\n"))
    return runs


def main():
    probes = json.load(open(os.path.join(RC, "engine_probe_results.json")))
    repro = json.load(open(os.path.join(RC, "repro_runs.json")))
    ref_runs = {c: run_ref(c) for c in ENGINE_ONLY}
    with open(os.path.join(RC, "engine_probe_ref_runs.json"), "w") as f:
        json.dump({"generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "env": "envs/ref (pandas 2.3.3), PCONF_REPRO_MODE=pandas",
                   "runs": ref_runs}, f, indent=1)
    causes = {}
    for p in sorted(probes.values(), key=lambda x: (x["cause"], x["engine"])):
        cause, eng = p["cause"], p["engine"]
        ref_lines = (ref_runs.get(cause) or {}).get("result_lines") or (repro.get(cause, {}).get("ref") or {}).get("result_lines", [])
        ref_lines = [l for l in ref_lines if not l.startswith("RESULT env")]
        el, rl = check_map(result_lines(p["output_tail"])), check_map(ref_lines)
        verdict, why = VERDICTS.get((cause, eng), (I, "no verdict recorded"))
        causes.setdefault(cause, {"engines": {}})["engines"][eng] = {
            "status": p["status"], "returncode": p["returncode"], "seconds": p["seconds"],
            "probe_lines": result_lines(p["output_tail"]), "ref_lines": ref_lines,
            "check_equal_to_ref": {k: (el[k] == rl.get(k)) if k in rl else None for k in el},
            "verdict": verdict, "reason": why}
    fu = corr_followup()
    if fu is not None and "engine_corr_wrong_values" in causes:
        ent = causes["engine_corr_wrong_values"]["engines"]["modin"]
        ent["followup"] = {"log": "results/rootcause/engine_corr_check.log", "lines": fu}
    for cause, d in causes.items():
        v = [x["verdict"] for x in d["engines"].values()]
        d["verdict"] = C if C in v else (I if I in v else N)
        d["confirmed_engines"] = sorted(e for e, x in d["engines"].items() if x["verdict"] == C)
    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "script": "scripts/engine_probe_outcomes.py",
           "probes": len(probes), "causes": causes,
           "summary": {k: sum(1 for d in causes.values() for x in d["engines"].values() if x["verdict"] == k) for k in (C, N, I)},
           "causes_by_verdict": {k: sorted(c for c, d in causes.items() if d["verdict"] == k) for k in (C, N, I)}}
    with open(os.path.join(RC, "engine_probe_outcomes.json") + ".tmp", "w") as f:
        json.dump(out, f, indent=1)
    os.replace(os.path.join(RC, "engine_probe_outcomes.json") + ".tmp", os.path.join(RC, "engine_probe_outcomes.json"))
    print(json.dumps({"summary": out["summary"], "causes_by_verdict": out["causes_by_verdict"]}, indent=1))


if __name__ == "__main__":
    main()

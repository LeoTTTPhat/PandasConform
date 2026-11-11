#!/usr/bin/env python3
"""Generate the LaTeX rows of Table 1 (root causes) from results/rootcause/taxonomy_conf1x.json (2026-10-04).

Usage (from the project folder): ../.venv/bin/python scripts/table1_tex.py [taxonomy_conf1x]
Writes results/rootcause/table1_<name>.tex; paste the rows into paper/main.tex (tab:rootcauses).
Fields: n_cells, n_strict_clean_cells, n_notebooks, by_engine, severity, documented_level, repro_runs,
engine_probe_outcome (F4). Rows sorted by cells; non-determinism last. A configuration that comes from the
10-notebook pilot (only bodo_dw until its conf_1x compare exists) carries a dagger; a row resting only on
pilot configurations carries a dagger on its label.
"""
import collections
import json
import os
import sys

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = sys.argv[1] if len(sys.argv) > 1 else "taxonomy_conf1x"
LABEL = {
    "str_default_dtype": r"pandas 3 default \texttt{str} dtype",
    "value_counts_naming": r"\texttt{value\_counts} result naming (2.0)",
    "float_rounding_within_tolerance": r"float rounding differences",
    "arrow_backed_dtypes": r"Arrow-backed result dtypes",
    "engine_bug_error": r"engine error on supported API",
    "engine_unsupported_api": r"API not implemented by engine",
    "str_dtype_object_checks": r"\texttt{dtype == 'object'} or dtype-name checks",
    "index_not_preserved": r"row index not preserved",
    "cow_chained_assignment": r"Copy-on-Write chained assignment",
    "int_float_nullable_repr": r"int64 instead of float64 slice",
    "offset_alias_removed": r"removed offset aliases (3.0)",
    "row_order_ties": r"row order of ties",
    "lazy_partition_model": r"lazy partition model",
    "numeric_dtype_preservation": r"narrow numeric dtypes kept (2.0)",
    "approximate_quantile": r"approximate quantiles",
    "engine_bug_silent": r"engine returns other value",
    "removed_deprecated_api": r"removed deprecated APIs (3.0)",
    "get_dummies_bool": r"\texttt{get\_dummies} bool (2.0)",
    "arrow_dtype_errors": r"errors on Arrow-backed data",
    "read_csv_none_as_na": r"\texttt{read\_csv} 'None' as NA (2.0)",
    "merge_row_order": r"merge row order (2.2)",
    "missing_sentinel_repr": r"None instead of NaN for strings",
    "datetime_resolution_inference": r"microsecond datetime inference (3.0)",
    "axis_names_lost": r"axis or Series names lost",
    "int_key_positional_fallback_removed": r"\texttt{Series[int]} positional fallback removed",
    "partitioned_type_inference": r"partitioned dtype inference",
    "describe_datetime_numeric": r"\texttt{describe} of datetimes (2.0)",
    "setitem_incompatible_dtype_raises": r"incompatible setitem raises",
    "str_dtype_na_semantics": r"\texttt{str} dtype missing values",
    "engine_corr_wrong_values": r"Modin \texttt{corr} values differ",
    "str_dtype_errors": r"\texttt{str} dtype errors",
    "api_added_later": r"API absent in 1.5",
    "loc_setitem_inplace": r"\texttt{loc} setitem in place (2.0)",
    "numeric_only_default": r"\texttt{numeric\_only} default (2.0)",
    "p3_stricter_validation": r"stricter argument validation (3.0)",
    "read_csv_big_int_python_ints": r"big integers as Python ints (3.0)",
    "str_replace_regex_default": r"\texttt{str.replace} regex default",
    "to_datetime_consistent_format": r"\texttt{to\_datetime} single format",
    "na_comparison_masks": r"\texttt{pd.NA} in comparison filters",
    "chunked_csv_type_inference": r"chunked CSV type inference",
    "scalar_type_numpy": r"NumPy scalar instead of \texttt{int}",
    "dtype_inference_differs": r"other inferred dtype",
    "engine_crash_timeout": r"engine crash or cell timeout",
    "cr_only_line_endings": r"CR-only line endings",
    "nondeterminism": r"non-determinism (excluded)",
}
SHORT = {"pyarrow_backend": "PA", "modin": "Mo", "fireducks": "FD", "bodo": "Bo", "bodo_dw": "BoD", "dask": "Da",
         "p15": "p1.5", "p30": "p3.0", "ref": "ref"}
KIND = {"silent_value_change": "silent", "representation_only": "repr.", "error": "error", "excluded": "excl."}
DOC = {"yes": "yes", "partial": "part.", "no": "no", "not_searched": "n.s."}
PROBE = {"confirmed": r"E\checkmark", "not_reproduced": r"E$\times$", "inconclusive": "E?"}


def configs(by_engine):
    agg = collections.Counter()
    pilot = set()
    for k, v in by_engine.items():
        camp, lab = k.split(":", 1)
        rep = "~vs~" in lab
        base = lab.split("~vs~")[0]
        name = SHORT.get(base.split("#")[0], base) + ("\\#2" if rep else "")
        if camp == "pilot":
            pilot.add(name)
        agg[name] += v
    parts = ["%s%s %d" % (n, "$^\\dagger$" if n in pilot else "", v)
             for n, v in sorted(agg.items(), key=lambda kv: (-kv[1], kv[0]))]
    only_pilot = all(n in pilot for n in agg)
    return ", ".join(parts), only_pilot


def repro(c):
    p = "P" if c.get("repro_runs") else ""
    o = c.get("engine_probe_outcome")
    e = PROBE[o["verdict"]] if o else ""
    return "+".join(x for x in (p, e) if x) or "--"


def main():
    t = json.load(open(os.path.join(PROJ, "results", "rootcause", NAME + ".json")))
    roots = [c for c in t["causes"].values() if c.get("family") not in ("not_a_root_cause", "nondeterminism") and c["cause"] != "unattributed"]
    roots.sort(key=lambda c: (-c["n_cells"], -c["n_notebooks"], c["cause"]))
    lines = []
    for c in roots:
        cfg, only_pilot = configs(c["by_engine"])
        lab = LABEL[c["cause"]] + ("$^\\dagger$" if only_pilot else "")
        lines.append("%s & %s & %s & %d & %d & %d & %s & %s \\\\" % (
            lab, KIND.get(c.get("severity"), ""), DOC.get(c.get("documented_level"), "no"), c["n_cells"],
            c["n_strict_clean_cells"], c["n_notebooks"], cfg, repro(c)))
    u = t["causes"].get("unattributed")
    lines.append("\\midrule")
    if u:
        cfg, _ = configs(u["by_engine"])
        lines.append("unattributed & -- & -- & %d & %d & %d & %s & -- \\\\" % (u["n_cells"], u["n_strict_clean_cells"], u["n_notebooks"], cfg))
    nd = t["causes"]["nondeterminism"]
    cfg, _ = configs(nd["by_engine"])
    lines.append("%s & excl. & no & %d & %d & %d & %s & -- \\\\" % (LABEL["nondeterminism"], nd["n_cells"], nd["n_strict_clean_cells"],
                                                                   nd["n_notebooks"], cfg))
    out = os.path.join(PROJ, "results", "rootcause", "table1_%s.tex" % NAME)
    with open(out, "w") as f:
        f.write("%% generated by scripts/table1_tex.py from results/rootcause/%s.json (%s)\n" % (NAME, t["generated"]))
        f.write("\n".join(lines) + "\n")
    print("wrote", out, len(roots), "cause rows")


if __name__ == "__main__":
    main()

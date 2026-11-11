#!/usr/bin/env python3
"""Root-cause taxonomy (plan.md Section 8, Table 1; RQ2/RQ3).

Reads ONLY finished outputs (read-only):
  * compare outputs  results/<campaign>/raw/compare__h<harness>__d<compare>/<engine>/sf1/*.json
    (one per (label, notebook, scale), selected with the same rule as `orchestrate summarize`:
    the output computed with ref#2 first, then the newest)
  * notebook cell sources (data/PandasBench via pconf.datasets/nbsource, read-only) so that
    rules can look at the code of the divergent cell and of the user functions it calls
  * results/rootcause/repro_runs.json (written by the `run-repros` sub-command below)
and writes results/rootcause/taxonomy.json and taxonomy.md.

Unit of attribution: an *introduced* divergence, i.e. a non-E0 cell whose class is coarser than
the level at which its inputs were already equal (classify.clean_level). Example: a p30 cell with
E2-equal inputs that becomes DIFF introduced a new divergence; a cell with E2 inputs that stays E2
merely propagates the str dtype. Every introduced cell gets exactly ONE cause (first matching rule
below, ordered from specific to generic); cells no rule explains are reported as `unattributed`.
Propagated cells, cascades (NameError after a failed cell, NOTRUN after a memory stop) and harness
outcomes (capped capture) are counted separately and are not root causes.
The rules are heuristics over the comparator's first failing check per level, the exception type
and message, and the cell code; every cause lists example cells that were inspected by hand
(see taxonomy.md) and `attribution` says which rule fired.

Usage (from ../06_pandas_conformance):
  ../.venv/bin/python scripts/rootcause_taxonomy.py build                    # drift + pilot (current)
  ../.venv/bin/python scripts/rootcause_taxonomy.py build --preset conf1x --out-name taxonomy_conf1x
        # drift + conf_1x (+ pilot replicates); run only after conf_1x compare is complete
        # (post_campaign.sh conf_1x check file n_problems 0); outputs_used per label is reported
  ../.venv/bin/python scripts/rootcause_taxonomy.py build --source conf_1x:modin,fireducks --out-name taxonomy_conf1x
  ../.venv/bin/python scripts/rootcause_taxonomy.py run-repros               # pandas-only reproducers
"""
import argparse
import collections
import glob
import json
import os
import re
import subprocess
import sys
import time

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJ, "src"))
from pconf import datasets, nbsource  # noqa: E402  (read-only use: notebook sources)

OUT_DIR = os.path.join(PROJ, "results", "rootcause")
HARNESS = "hd1c421ecb5ee"
COMPARE = "92c8db54d45b"
LEVELS = ["E0", "E1", "E2", "E3", "E4"]
RANK = {"E0": 0, "E1": 1, "E2": 2, "E3": 3, "E4": 4, "DIFF": 5, "UNCOMPARABLE": 5,
        "ERR": 6, "TIMEOUT": 6, "CRASH": 6, "KILLED": 6, "SETUP_ERR": 6, "MEMORY": 6, "NOTRUN": 6}
ENGINE_LABELS = ["pyarrow_backend", "modin", "fireducks", "bodo", "bodo_dw", "dask"]
REPLICATES = ["modin#2~vs~modin", "fireducks#2~vs~fireducks", "bodo#2~vs~bodo", "dask#2~vs~dask"]
PRESETS = {
    # complete outputs on 2026-10-04: drift (102 notebooks) and the 10-notebook pilot
    "current": [("drift", ["p15", "p30", "ref#2"]), ("pilot", ENGINE_LABELS + REPLICATES)],
    # once conf_1x compare is complete: engines from conf_1x (102 notebooks), replicates from pilot
    "conf1x": [("drift", ["p15", "p30", "ref#2"]), ("conf_1x", ENGINE_LABELS + ["ref#2"]), ("pilot", REPLICATES)],
}
CAMPAIGN_NOTE = {"pilot": "PILOT: 10 notebooks only (data/notebook_sets/pilot.json); not a claim",
                 "drift": "drift: 102 notebooks", "conf_1x": "conf_1x: 102 notebooks"}

PANDAS_VERSION = {"p15": "1.5.3", "p30": "3.0.6", "ref": "2.3.3", "pyarrow_backend": "2.3.3 (dtype_backend='pyarrow')"}

U_PD = "https://pandas.pydata.org/docs/"
URL = {
    "w300": U_PD + "whatsnew/v3.0.0.html",
    "w220": U_PD + "whatsnew/v2.2.0.html",
    "w210": U_PD + "whatsnew/v2.1.0.html",
    "w200": U_PD + "whatsnew/v2.0.0.html",
    "mig_str": U_PD + "user_guide/migration-3-strings.html",
    "cow": U_PD + "user_guide/copy_on_write.html",
    "pyarrow": U_PD + "user_guide/pyarrow.html",
    "missing": U_PD + "user_guide/missing_data.html",
    "dask_csv": "https://docs.dask.org/en/stable/generated/dask.dataframe.read_csv.html",
    "dask_quant": "https://docs.dask.org/en/stable/generated/dask.dataframe.Series.quantile.html",
    "dask_idx": "https://docs.dask.org/en/stable/dataframe-indexing.html",
    "dask_str_pr": "https://github.com/dask/dask/pull/10400",
    "modin_api": "https://modin.readthedocs.io/en/latest/supported_apis/dataframe_supported.html",
    "fd_compat": "https://fireducks-dev.github.io/docs/user-guide/04-compatibility/",
    "read_csv": U_PD + "reference/api/pandas.read_csv.html",
}

# ----------------------------------------------------------------------------------------------
# Cause catalogue. severity: silent_value_change | representation_only | error
# documented: list of {url, quote} verified with WebFetch on 2026-10-04 (see taxonomy.md), [] if
# no documentation was found (= undocumented).
# ----------------------------------------------------------------------------------------------
CAUSES = {
    # ---- pandas version drift ------------------------------------------------------------------
    "str_default_dtype": dict(
        family="pandas3", severity="representation_only",
        title="pandas 3 default `str` dtype replaces object for text (dtype strings, `.dtypes`/repr output)",
        documented=[{"url": URL["w300"], "quote": "Dedicated string data type by default"},
                    {"url": URL["mig_str"], "quote": "migration guide for the new string data type"}],
        repro="str_default_dtype.py"),
    "str_dtype_object_checks": dict(
        family="string_dtype", severity="silent_value_change",
        title="code that selects columns by `dtype == 'object'` / `select_dtypes('object')` / `include='O'` "
              "(or, since 2026-10-04, by NumPy dtype names such as `dtype in ['int64', 'float64']`) "
              "selects different columns when strings are not object dtype",
        documented=[{"url": URL["mig_str"], "quote": "Checking the dtype ... will no longer work in pandas 3+"}],
        repro="str_dtype_object_checks.py"),
    "str_dtype_errors": dict(
        family="pandas3", severity="error",
        title="operations that raise on the pandas 3 `str` dtype (mixed-dtype sort of `.dtypes`, numeric "
              "reductions, categorical dtype mismatch, non-string setitem)",
        documented=[{"url": URL["mig_str"], "quote": "setitem operations will now raise an error for non-string data; prod() raising for string data"}],
        repro="str_dtype_errors.py"),
    "cow_chained_assignment": dict(
        family="pandas3", severity="silent_value_change",
        title="Copy-on-Write: chained assignment and inplace methods on a column selection no longer modify the parent",
        documented=[{"url": URL["cow"], "quote": "chained assignment will consistently never work"},
                    {"url": URL["w300"], "quote": "Consistent copy/view behaviour with Copy-on-Write"}],
        repro="cow_chained_assignment.py"),
    "removed_deprecated_api": dict(
        family="pandas3", severity="error",
        title="APIs deprecated in 2.x and removed in 3.0 (fillna(method=/downcast=), to_datetime(infer_datetime_format=), "
              "pd.value_counts, DataFrame.applymap, Index.sort)",
        documented=[{"url": URL["w300"], "quote": "Removed deprecated keyword method on Series.fillna(), DataFrame.fillna(); "
                                                   "Removed DataFrame.applymap; Removed pandas.value_counts; Removed Index.sort()"},
                    {"url": URL["w210"], "quote": "Deprecated the downcast keyword in ... Series.fillna(), DataFrame.fillna()"},
                    {"url": URL["w200"], "quote": "Deprecated argument infer_datetime_format in to_datetime() and read_csv()"}],
        repro="removed_deprecated_api.py"),
    "offset_alias_removed": dict(
        family="pandas3", severity="error",
        title="frequency aliases M, H, AS removed in pandas 3 (ME, h, YS)",
        documented=[{"url": URL["w300"], "quote": "Enforced deprecation of string AS denoting frequency in YearBegin; "
                                                   "strings H, BH, and CBH denoting frequencies in Hour; MonthEnd M -> ME"}],
        repro="offset_alias_removed.py"),
    "int_key_positional_fallback_removed": dict(
        family="pandas3", severity="error",
        title="Series[int] on a non-integer index no longer falls back to position (KeyError)",
        documented=[{"url": URL["w300"], "quote": "Changed behavior of Series.__getitem__() and Series.__setitem__() to always "
                                                   "treat integer keys as labels, never as positional"}],
        repro="int_key_positional_fallback_removed.py"),
    "setitem_incompatible_dtype_raises": dict(
        family="pandas3", severity="error",
        title="setting a value of an incompatible dtype raises instead of upcasting (PDEP-6)",
        documented=[{"url": URL["w300"], "quote": "Enforce banning of upcasting in in-place setitem-like operations; see PDEP6"},
                    {"url": URL["w210"], "quote": "Deprecated silent upcasting in setitem-like Series operations"}],
        repro="setitem_incompatible_dtype_raises.py"),
    "datetime_resolution_inference": dict(
        family="pandas3", severity="silent_value_change",
        title="pandas 3 infers microsecond (not nanosecond) resolution when parsing strings",
        documented=[{"url": URL["w300"], "quote": "The new default resolution when parsing strings is microseconds"}],
        repro="datetime_resolution_inference.py"),
    "str_dtype_na_semantics": dict(
        family="pandas3", severity="silent_value_change",
        title="missing values under the pandas 3 `str` dtype: astype(str) keeps NaN (2.x wrote 'nan'), str accessor "
              "results on missing entries differ",
        documented=[{"url": URL["mig_str"], "quote": "astype(str) preserving missing values; The missing value sentinel is now always NaN"}],
        documented_note="astype(str) documented; str.split/str.contains on missing entries not described explicitly",
        repro="str_dtype_na_semantics.py"),
    "read_csv_big_int_python_ints": dict(
        family="pandas3", severity="silent_value_change",
        title="pandas 3 read_csv parses integers beyond int64 as Python ints; a chunk holding one such value turns "
              "zero-padded code strings ('0078700802378') into ints (2.3.3 kept the chunk as strings)",
        documented=[{"url": URL["w300"], "quote": "Bug in read_csv() with c and python engines reading big integers as strings. Now reads them as python integers. (GH 51295)"}],
        documented_note="the change is documented as a bug fix; its effect on leading-zero codes is not",
        repro="read_csv_big_int_python_ints.py"),
    "p3_stricter_validation": dict(
        family="pandas3", severity="error",
        title="pandas 3 raises on argument combinations 2.3.3 accepted (drop(index=..., axis=1))",
        documented=[], repro="p3_stricter_validation.py"),
    "describe_datetime_numeric": dict(
        family="pandas2", severity="silent_value_change",
        title="pandas 2.0 describe() always summarises datetime columns as numeric (1.5: object-style summary or excluded)",
        documented=[{"url": URL["w200"], "quote": "Removed argument datetime_is_numeric from DataFrame.describe() ... datetime data will always be summarized as numeric data"}],
        repro="describe_datetime_numeric.py"),
    "to_datetime_consistent_format": dict(
        family="pandas2", severity="silent_value_change",
        title="pandas 2.0 to_datetime infers ONE format from the first value (1.5 guessed per element); errors='coerce' yields more NaT",
        documented=[{"url": URL["w200"], "quote": "Datetimes are now parsed with a consistent format"}],
        repro="to_datetime_consistent_format.py"),
    "value_counts_naming": dict(
        family="pandas2", severity="representation_only",
        title="pandas 2.0: value_counts result is named 'count'/'proportion' and its index carries the column name "
              "(renames/reset_index then produce different labels)",
        documented=[{"url": URL["w200"], "quote": "Value counts sets the resulting name to count"}],
        repro="value_counts_naming.py"),
    "get_dummies_bool": dict(
        family="pandas2", severity="representation_only",
        title="pandas 2.0: get_dummies returns bool instead of uint8",
        documented=[{"url": URL["w200"], "quote": "Default value of dtype in get_dummies() is changed to bool from uint8"}],
        repro="get_dummies_bool.py"),
    "numeric_dtype_preservation": dict(
        family="pandas2", severity="representation_only",
        title="pandas 2.0 keeps narrow numeric dtypes (int32 datetime fields, Index of int32/uint32/float32) where 1.5 widened",
        documented=[{"url": URL["w200"], "quote": "Index can now hold numpy numeric dtypes; datetime fields are now int32"}],
        repro="numeric_dtype_preservation.py"),
    "read_csv_none_as_na": dict(
        family="pandas2", severity="silent_value_change",
        title="pandas 2.0 read_csv parses the string 'None' as missing",
        documented=[{"url": URL["w200"], "quote": "Added \"None\" to default na_values in read_csv()"}],
        repro="read_csv_none_as_na.py"),
    "merge_row_order": dict(
        family="pandas2", severity="silent_value_change",
        title="pandas 2.2: merge/join row order follows the documented sort rules (inner keeps left order)",
        documented=[{"url": URL["w220"], "quote": "merge() and DataFrame.join() now consistently follow documented sort behavior"}],
        repro="merge_row_order.py"),
    "numeric_only_default": dict(
        family="pandas2", severity="silent_value_change",
        title="pandas 2.0: numeric_only defaults to False (1.5 silently dropped nuisance columns in groupby/DataFrame reductions)",
        documented=[{"url": URL["w200"], "quote": "Changed default of numeric_only in various DataFrameGroupBy methods; all methods now default to numeric_only=False"}],
        repro="numeric_only_default.py"),
    "str_replace_regex_default": dict(
        family="pandas2", severity="silent_value_change",
        title="pandas 2.0: Series.str.replace default regex=False (1.5: regex=True)",
        documented=[{"url": URL["w200"], "quote": "Change the default argument of regex for Series.str.replace() from True to False"}],
        repro="str_replace_regex_default.py"),
    "loc_setitem_inplace": dict(
        family="pandas2", severity="representation_only",
        title="pandas 2.0: df.loc[:, col] = values sets in place (keeps the old dtype) instead of replacing the column",
        documented=[{"url": URL["w200"], "quote": "Changed behavior in setting values with df.loc[:, foo] = bar ... now always attempt to set values inplace"}],
        repro="loc_setitem_inplace.py"),
    "api_added_later": dict(
        family="pandas2", severity="error",
        title="pandas 1.5 lacks an API that notebooks written for 2.x use (read_csv(date_format=))",
        documented=[{"url": URL["w200"], "quote": "read_csv(), read_table(), read_fwf() and read_excel() now accept date_format"}],
        repro="api_added_later.py"),
    "float_rounding_within_tolerance": dict(
        family="numeric", severity="silent_value_change",
        title="float rounding differences, mostly last-ulp and within the 1e-9 relative tolerance (read_csv float "
              "parsing in pandas 1.5, corr/describe/mean summation order in parallel engines); DIFF when the "
              "difference sits inside a Python list or is amplified beyond the tolerance",
        documented=[{"url": URL["modin_api"], "quote": "Correlation floating point precision may slightly differ from pandas"}],
        documented_note="documented for Modin corr only; pandas 1.5 vs 2.x parsing and FireDucks/Bodo summation not found",
        repro="float_rounding_within_tolerance.py"),
    "row_order_ties": dict(
        family="order", severity="silent_value_change",
        title="different order of rows (ties in sort_values/value_counts, merge/groupby output order); "
              "equal as multisets (E1) or different after head()/[:n] truncation",
        documented=[{"url": URL["modin_api"], "quote": "Order of indexes that have the same sort key is not guaranteed"},
                    {"url": URL["fd_compat"], "quote": "The order of rows in merge/join results may not match the order in pandas"}],
        documented_note="documented for Modin sort_values and FireDucks merge/join; not for pandas 3 tie order or Bodo group order",
        repro="row_order_ties.py"),
    # ---- engines -------------------------------------------------------------------------------
    "arrow_backed_dtypes": dict(
        family="engine_dtype", severity="representation_only",
        title="engine returns pyarrow-backed dtypes (string[pyarrow], large_string, int64[pyarrow], double[pyarrow]) "
              "with pd.NA where pandas returns numpy/object dtypes",
        documented=[{"url": URL["pyarrow"], "quote": "These readers can return PyArrow-backed data by specifying the parameter dtype_backend=\"pyarrow\""},
                    {"url": URL["dask_str_pr"], "quote": "Convert to pyarrow strings if proper dependencies are installed"}],
        documented_note="documented for pandas' dtype_backend and Dask (merged PR); Bodo's arrow dtypes not found in its docs",
        repro="arrow_backed_dtypes.py"),
    "arrow_dtype_errors": dict(
        family="engine_dtype", severity="error",
        title="errors caused by arrow-backed data: strict typing on setitem ('8+' into int64), pd.NA in a boolean context, "
              ".str accessor / numpy calls on arrow scalars",
        documented=[{"url": URL["missing"], "quote": "it is ambiguous to convert NA to a boolean value"}],
        documented_note="pd.NA boolean semantics documented; strict arrow setitem typing not found",
        repro="arrow_dtype_errors.py"),
    "missing_sentinel_repr": dict(
        family="engine_dtype", severity="representation_only",
        title="missing strings come back as None instead of NaN (equal at E3)",
        documented=[], repro="missing_sentinel_repr.py"),
    "int_float_nullable_repr": dict(
        family="engine_dtype", severity="representation_only",
        title="integer column with missing values elsewhere: engine returns int64 for a NaN-free slice/aggregate where pandas returns float64",
        documented=[], repro="int_float_nullable_repr.py"),
    "index_not_preserved": dict(
        family="engine_index", severity="representation_only",
        title="engine does not preserve the pandas row index (filters/sort/groupby as_index=False/partition-local RangeIndex)",
        documented=[], repro="index_not_preserved.py"),
    "axis_names_lost": dict(
        family="engine_index", severity="representation_only",
        title="axis or Series names lost (crosstab columns name, iloc row Series name)",
        documented=[], repro="axis_names_lost.py"),
    "approximate_quantile": dict(
        family="engine_numeric", severity="silent_value_change",
        title="quantile/percentile computed approximately; threshold filters keep different rows",
        documented=[{"url": URL["dask_quant"], "quote": "Approximate quantiles of Series"}],
        documented_note="documented for Dask; for Bodo the quantile hypothesis is from the cell code and must be confirmed by the probe",
        repro="approximate_quantile.py"),
    "partitioned_type_inference": dict(
        family="engine_partition", severity="error",
        title="per-partition / sample-based dtype inference in read_csv (Dask: Mismatched dtypes at compute; Modin: mixed int/str object column)",
        documented=[{"url": URL["dask_csv"], "quote": "Dask dataframe tries to infer the dtype of each column by reading a sample from the start of the file"}],
        documented_note="documented for Dask; Modin's mixed-type column not found in its docs (silent value change there)",
        repro="partitioned_type_inference.py"),
    "lazy_partition_model": dict(
        family="engine_partition", severity="error",
        title="lazy/partitioned execution model (unknown partition lengths -> shape NaN, unknown divisions, metadata inference, lazy scalars)",
        documented=[{"url": URL["dask_idx"], "quote": "Dask DataFrame does not track the length of partitions"}],
        repro="lazy_partition_model.py"),
    "engine_unsupported_api": dict(
        family="engine_api", severity="error",
        title="pandas API not implemented by the engine (Dask: inplace=, cut, pivot, crosstab, iloc rows, read_excel; Bodo: "
              "infer_datetime_format, groupby key types; FireDucks: groupby sum of strings)",
        documented=[{"url": URL["dask_idx"], "quote": "DataFrame.iloc() only supports indexers where the row indexer is slice(None)"}],
        documented_note="documented for Dask iloc only; the other gaps were not found in the engines' docs",
        repro="engine_unsupported_api.py"),
    "engine_bug_error": dict(
        family="engine_api", severity="error",
        title="engine raises where pandas succeeds on supported API (Bodo `_plan`, BodoStringMethods subscript, "
              "'an integer is required'; Modin Series.filter, RayTaskError; FireDucks materialisation errors)",
        documented=[{"url": URL["fd_compat"], "quote": "the timing of errors and warnings in FireDucks is different from that in pandas"}],
        documented_note="FireDucks documents deferred error timing only; the errors themselves are undocumented",
        repro="engine_bug_error.py"),
    "engine_corr_wrong_values": dict(
        family="engine_numeric", severity="silent_value_change",
        title="Modin DataFrame.corr returns values that differ beyond the 1e-9 tolerance (rule: Modin DIFF in a cell calling corr); "
              "on deffro/eda-is-fun, corr(numeric_only=True) on a 4.4M-row frame returns out-of-range correlations (diagonal 5.38, 8.41)",
        documented=[], repro="engine_corr_wrong_values.py"),
    "engine_bug_silent": dict(
        family="engine_api", severity="silent_value_change",
        title="engine returns a different value without error (Modin pd.value_counts(pd.cut) drops a bin, pivot_table(aggfunc='size') "
              "returns a DataFrame; Bodo head() after column changes shows stale columns)",
        documented=[], repro="engine_bug_silent.py"),
    # ---- added 2026-10-04 while curating the conf_1x unattributed cells (plan.md Ledger) ----------
    # doc_searched=False: no documentation search was made for the cause; the paper prints "n.s.".
    "na_comparison_masks": dict(
        family="engine_dtype", severity="silent_value_change",
        title="missing values in Arrow-backed columns propagate through comparisons (pd.NA), so a filter such as "
              "df[df.c != 'x'] drops rows whose value is missing (NumPy NaN compares unequal and keeps them)",
        documented=[{"url": URL["missing"], "quote": "In equality and comparison operations, NA also propagates. This deviates "
                                                     "from the behaviour of np.nan, where comparisons with np.nan always return False."}],
        documented_note="pd.NA comparison semantics documented (verified with WebFetch 2026-10-04); the effect on filters is not spelled out",
        repro=None),
    "chunked_csv_type_inference": dict(
        family="numeric", severity="silent_value_change",
        title="pandas' C parser infers types per chunk (low_memory), so a column mixes ints and strings from a chunk "
              "boundary (row 4096 x k) on; engines infer one type for the whole column",
        documented=[{"url": URL["read_csv"], "quote": "Internally process the file in chunks, resulting in lower memory use while "
                                                      "parsing, but possibly mixed type inference."}],
        documented_note="documented as pandas behaviour (verified with WebFetch 2026-10-04); the engines' whole-column inference not searched",
        repro=None),
    "scalar_type_numpy": dict(
        family="engine_dtype", severity="representation_only",
        title="engine returns a NumPy scalar (numpy.int64) where pandas returns a Python int (nunique, len-like results)",
        documented=[], doc_searched=False, repro=None),
    "dtype_inference_differs": dict(
        family="engine_dtype", severity="representation_only",
        title="engine infers another NumPy or nullable dtype for the same values (object vs float64/bool/int64, UInt32 vs uint32, "
              "DatetimeArray vs ndarray); equal at E2",
        documented=[], doc_searched=False, repro=None),
    "engine_crash_timeout": dict(
        family="engine_api", severity="error",
        title="engine process crashed (Bodo legacy JIT import with numba 0.65.1; FireDucks segmentation fault) or a cell "
              "exceeded the 600 s timeout",
        documented=[], doc_searched=False, repro=None),
    "cr_only_line_endings": dict(
        family="engine_api", severity="silent_value_change",
        title="CSV file with carriage-return-only line endings: Modin reads 1 row where pandas reads 38",
        documented=[], doc_searched=False, repro=None),
    # ---- not root causes -------------------------------------------------------------------------
    "nondeterminism": dict(family="nondeterminism", severity="excluded",
                           title="output differs between two runs of the same configuration (ref vs ref#2 -> NONDET for every engine; "
                                 "engine vs its own replicate)", documented=[], repro=None),
}
NON_ROOT = {
    "cascade_undefined_name": "NameError/UnboundLocalError after an earlier cell failed (cascade)",
    "capture_cap": "output above the capture cap (hash only): UNCOMPARABLE",
    "resource_memory_cap": "engine stop: the running cell (MEMORY at the 96 GB per-notebook cap) and the cells after a memory stop, an engine crash or a notebook timeout (NOTRUN)",
    "propagated": "class not coarser than the input level: divergence inherited from an earlier cell",
    "order_propagated": "DIFF in a cell whose inputs differ only in row order or index (E1/E4): head()/[:n]/lists expose "
                        "the earlier order difference; attributed to the cell that reordered",
}

# Hand-inspected cells (values decoded from the captures on 2026-10-04 with envs/ref; see taxonomy.md).
# key: (base engine label, notebook, cell) -> (cause, evidence)
CURATED = {
    ("p30", "yonelanuba/elo-merchant-by-yonela", 138): ("datetime_resolution_inference",
        "astype(int) of a datetime64[us] column: 1523404800000000 (p30) vs 1523404800000000000 (ref)"),
    ("p30", "yonelanuba/elo-merchant-by-yonela", 139): ("datetime_resolution_inference", "same as cell 138 on test_app"),
    ("p30", "j0thu777/onlineretailanalysis", 20): ("datetime_resolution_inference",
        "column holds a bound method whose repr ends dtype='datetime64[us]' vs [ns]"),
    ("p30", "chinstan/notebook249b4f3f5b", 2): ("read_csv_big_int_python_ints",
        "column 'code': ref '0078700802378' (str), p30 78700802378 (int) from row 4096 on; 36,427 of 134,754 rows. "
        "Re-read of the raw input (usecols=['code']): ref 98,304 int + 36,427 str, p30 134,731 int"),
    ("p30", "luizep/movieslens20m", 13): ("str_dtype_na_semantics",
        "genres str.split(...).tolist() + stack().unique(): p30 keeps a 'nan' genre (21 vs 20 rows)"),
    ("p30", "vinothsuku/osic-pulmonary-fibrosis-simple-eda", 7): ("str_default_dtype",
        "groupby().unique() cells hold ArrowStringArray (dtype str) instead of object ndarray"),
    ("p30", "saniaks/melbourne-house-price-eda", 26): ("p3_stricter_validation",
        "df.drop(index=9968, axis=1, errors='ignore') raises 'Cannot specify both axis and index/columns' only in p30"),
    ("p15", "luizep/movieslens20m", 35): ("float_rounding_within_tolerance",
        "list of (genre, mean, std) tuples; means differ at ~1e-16 (3.0742707534010454 vs 3.074270753401045); lists are compared exactly"),
    ("p15", "ukveteran/sarima-time-series-eda-predict-jma-sao-paulo", 4): ("to_datetime_consistent_format",
        "to_datetime(errors='coerce') then dropna: 13 rows (ref) vs 36 rows (p15)"),
    ("bodo", "corazzon/how-to-use-pandas-filter-in-survey-eda", 33): ("row_order_ties",
        "groupby('Q2').count(): Bodo returns groups unsorted (Man, Woman, ...) and labels the NaN column 'nan'"),
    ("bodo_dw", "corazzon/how-to-use-pandas-filter-in-survey-eda", 33): ("row_order_ties", "as bodo"),
    ("bodo", "yonelanuba/elo-merchant-by-yonela", 20): ("index_not_preserved",
        "train.drop(train[mask].index, inplace=True): Bodo's filtered index labels differ, so different rows are dropped"),
    ("bodo_dw", "yonelanuba/elo-merchant-by-yonela", 20): ("index_not_preserved", "as bodo"),
    ("p30", "willkoehrsen/start-here-a-gentle-introduction", 9): ("str_default_dtype",
        "app_train.dtypes.value_counts(): index holds dtype objects (str vs object), so labels differ"),
    ("p15", "penny8/my-sub1", 22): ("float_rounding_within_tolerance",
        "1-ulp differences in parsed coordinates amplified by the bearing formula (99.97019564714782 vs 99.97019564715572); "
        "some rows exceed the 1e-9 relative tolerance"),
    ("p15", "penny8/my-sub1", 23): ("float_rounding_within_tolerance", "as cell 22 on test"),
    ("dask", "sabya40/data-cleaning-and-pandas-for-beginners", 13): ("lazy_partition_model",
        "read_csv('fkartDataset.csv') raises IsADirectoryError: an earlier dask to_csv wrote one file per partition into a directory"),
    ("bodo_dw", "shashi772/data-cleaning-challenge-parsing-dates", 0): ("engine_bug_silent",
        "read_csv with default workers returns 1692 of 1693 rows (catalog) and 1507 of 1508 (volcanos); 1 worker reads all"),
    # conf_1x curation, 2026-10-04 (evidence = the comparator's failing check plus the cell code; not decoded values)
    ("modin", "danielresende/game-of-thrones-battles", 2): ("cr_only_line_endings",
        "battles = read_csv(battles.csv): shape [38, 25] (ref) vs [1, 25] (modin); the file uses CR-only line endings "
        "(smoke campaign, plan.md Ledger 2026-10-02)"),
    ("modin", "christophriley/intro-machine-learning", 7): ("engine_bug_silent",
        "trainData.groupby(['Sex', 'Survived'])['Survived'].count(): shape [4] (ref) vs [0] (modin), an empty result"),
    ("modin", "christophriley/intro-machine-learning", 8): ("engine_bug_silent",
        "df[cols].corrwith(df.Survived).round(4) * 100: Series (ref) vs DataFrame (modin)"),
}

# ----------------------------------------------------------------------------------------------
# Rules: (cause_id, predicate(cell) -> bool, short description). First match wins.
# cell fields: eng (base label), cls, clean, outs [{name, level, fails{L: check}, reason, error}],
#              exc, msg, code (cell + bodies of user functions it calls)
# ----------------------------------------------------------------------------------------------
STR_OBJ = r"(object/str\b|str/object\b)"
ARROWISH = r"\[pyarrow\]|large_string|/string\b|string\[python\]|/string$|object/string"
_B = r"\[(?:[^\[\]\n]|\[(?:[^\[\]\n]|\[[^\[\]\n]*\])*\])+\]"   # one subscript, up to 2 nested levels
COW_PATTERNS = [
    # chained setitem: x[a][b] = v, x[a].loc[b] = v, x.loc[a][b] += v, x[a].iloc[i] = v
    r"\b\w+(?:\.\w+)?" + _B + r"(?:\.(?:loc|iloc|at|iat))?" + _B + r"\s*(?:[+\-*/]?=)(?!=)",
    r"\b\w+\.(?:loc|iloc)" + _B + _B + r"\s*(?:[+\-*/]?=)(?!=)",
    # inplace method on a column selection: x[c].fillna(..., inplace=True), x.c.replace(..., inplace=True)
    r"\b\w+(?:" + _B + r"|\.\w+)\.(?:fillna|replace|dropna|interpolate|clip|where|mask|ffill|bfill|update)\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*?inplace\s*=\s*True",
]
OBJ_CHECK = (r"dtypes?\s*[!=]=\s*['\"](?:object|O)['\"]|dtypes?\s*[!=]=\s*(?:np\.)?object\b|select_dtypes\([^)]*(?:object|['\"]O['\"])"
             r"|include\s*=\s*\[?\s*['\"]O['\"]|describe\(\s*include")


def _any(outs, rx, levels=("E0",), only_bad=True):
    for o in outs:
        if only_bad and o["level"] == "E0":
            continue
        for L in levels:
            v = (o.get("fails") or {}).get(L)
            if v and re.search(rx, v):
                return True
    return False


def _fail_at(o, L):
    return (o.get("fails") or {}).get(L) or ""


def _worst_fail(outs):
    """Check that made the worst output fail at the level just below its class (why it is not finer)."""
    bad = [o for o in outs if o["level"] not in ("E0",)]
    if not bad:
        return ""
    o = max(bad, key=lambda x: RANK.get(x["level"], 5))
    lv = o["level"]
    if lv in LEVELS:
        return _fail_at(o, LEVELS[LEVELS.index(lv) - 1])
    return _fail_at(o, "E4") or o.get("reason") or ""


def code_has(c, rx):
    return re.search(rx, c["code"], re.M) is not None


def msg_has(c, rx):
    return re.search(rx, (c.get("msg") or "") + " " + (c.get("exc") or ""), re.S) is not None


def is_(c, *engines):
    return c["eng"] in engines


ENG = ("pyarrow_backend", "modin", "fireducks", "bodo", "bodo_dw", "dask")
ARROW_ENG = ("pyarrow_backend", "bodo", "bodo_dw", "dask", "p30")


def R(cause, pred, why):
    return (cause, pred, why)


RULES = [
    # pandas 3 errors
    R("offset_alias_removed", lambda c: is_(c, "p30") and c["cls"] == "ERR" and msg_has(c, r"Invalid frequency"), "msg 'Invalid frequency'"),
    R("removed_deprecated_api", lambda c: is_(c, "p30") and c["cls"] == "ERR" and msg_has(
        c, r"unexpected keyword argument '(method|downcast|infer_datetime_format)'|has no attribute '(value_counts|applymap|sort)'"),
      "msg names a removed keyword/attribute"),
    R("int_key_positional_fallback_removed", lambda c: is_(c, "p30") and c["cls"] == "ERR" and (c.get("exc") or "").endswith("KeyError")
      and re.fullmatch(r"'?-?\d+'?", (c.get("msg") or "").strip() or "x") is not None, "KeyError on an integer key"),
    R("setitem_incompatible_dtype_raises", lambda c: is_(c, "p30") and c["cls"] == "ERR" and msg_has(c, r"Invalid value '"),
      "TypeError 'Invalid value ... for dtype'"),
    R("cow_chained_assignment", lambda c: c["eng"] in ("p30", "fireducks") and c["cls"] in ("DIFF", "ERR", "E3", "E4")
      and any(re.search(p, c["code"]) for p in COW_PATTERNS), "chained assignment / inplace-on-selection in the cell or a called function"),
    R("str_dtype_na_semantics", lambda c: is_(c, "p30") and c["cls"] == "DIFF" and _any(c["outs"], r"missing_mask", ("E4",))
      and code_has(c, r"astype\(\s*(str|'str'|\"str\")\s*\)|\.str\.(split|contains|extract|match|startswith|endswith|replace)\("),
      "missing mask differs after astype(str) / str accessor"),
    R("str_dtype_errors", lambda c: is_(c, "p30") and c["cls"] == "ERR" and msg_has(
        c, r"StringDtype|string dtype|numpy\.str_|expected string or bytes-like object|dtype of categories must be the same|'str' and"),
      "error message mentions the string dtype"),
    # pandas 1.5 (p15) vs 2.x
    R("api_added_later", lambda c: is_(c, "p15") and c["cls"] == "ERR" and msg_has(c, r"unexpected keyword argument"), "unknown keyword in 1.5"),
    R("get_dummies_bool", lambda c: is_(c, "p15") and (code_has(c, r"get_dummies") and (_any(c["outs"], r"bool/uint8|bool/int", LEVELS + ["E4"]) or c["cls"] == "DIFF" and not c["outs"])),
      "get_dummies + bool/uint8"),
    R("value_counts_naming", lambda c: is_(c, "p15") and code_has(c, r"value_counts") and c["cls"] in ("E2", "E3", "E4", "DIFF")
      and (_any(c["outs"], r"names:|labels|^values", LEVELS)), "value_counts in cell + name/label check"),
    R("read_csv_none_as_na", lambda c: is_(c, "p15") and c["cls"] == "DIFF" and code_has(c, r"read_(csv|table)\(")
      and _any(c["outs"], r"missing_mask", ("E4",)), "read_csv cell, missing mask differs (input columns hold the string 'None')"),
    R("merge_row_order", lambda c: is_(c, "p15") and c["cls"] in ("E1", "E4", "DIFF") and code_has(c, r"\bmerge\(|\.join\("), "merge/join in cell"),
    R("loc_setitem_inplace", lambda c: is_(c, "p15") and code_has(c, r"\.loc\[\s*:\s*,") and _any(c["outs"], r"object/datetime|datetime64\[ns\]/object", ("E0",)),
      "df.loc[:, col] = ... and object vs datetime dtype"),
    R("describe_datetime_numeric", lambda c: is_(c, "p15") and c["cls"] == "DIFF" and code_has(c, r"\.describe\(\s*\)"), "describe() in cell"),
    R("to_datetime_consistent_format", lambda c: is_(c, "p15") and c["cls"] == "DIFF" and code_has(c, r"to_datetime\("), "to_datetime in cell"),
    R("str_replace_regex_default", lambda c: is_(c, "p15") and c["cls"] == "DIFF" and code_has(c, r"\.str\.replace\("), "str.replace in cell"),
    R("numeric_only_default", lambda c: is_(c, "p15") and c["cls"] == "DIFF" and code_has(c, r"groupby\([^)]*\)\.(sum|mean|median|std|var|prod)\(\s*\)")
      and _any(c["outs"], r"shape|labels", ("E4",)), "groupby reduction without numeric_only, shape differs"),
    R("numeric_dtype_preservation", lambda c: is_(c, "p15") and _any(c["outs"], r"int32/int64|int64/int32|uint32/uint64|int64/object|object/int64|float32/float64|uint8/int64", ("E0",)),
      "narrow numeric dtype in 2.x"),
    # engines: specific errors first
    R("partitioned_type_inference", lambda c: (is_(c, "dask") and c["cls"] == "ERR" and msg_has(c, r"Mismatched dtypes"))
      or (is_(c, "modin") and _any(c["outs"], r"encoding:col\d+:str/obj|encoding:col\d+:obj/str", ("E0",))),
      "Dask 'Mismatched dtypes' / Modin mixed str/obj encoding"),
    R("engine_unsupported_api", lambda c: c["eng"] in ("dask", "bodo", "bodo_dw", "fireducks", "modin") and c["cls"] == "ERR" and msg_has(
        c, r"NotImplementedError|BodoLibNotImplementedException|has no attribute '(cut|pivot|crosstab|read_excel|sort_values)'|"
           r"unexpected keyword argument|does not support item assignment|sample does not support|agg function failed"),
      "NotImplemented / missing attribute or keyword"),
    R("lazy_partition_model", lambda c: is_(c, "dask") and (
        (c["cls"] == "ERR" and msg_has(c, r"Metadata inference|unknown division|chunk sizes are unknown|Scalar\.__format__|duplicate labels|tuple index out of range"))
        or (c["cls"] == "DIFF" and code_has(c, r"\.shape\b") and not _any(c["outs"], r"shape:", ("E0",)))), "dask lazy/partition error or shape"),
    R("arrow_dtype_errors", lambda c: c["eng"] in ("pyarrow_backend", "bodo", "bodo_dw", "fireducks") and c["cls"] == "ERR" and msg_has(
        c, r"ArrowInvalid|boolean value of NA is ambiguous|Can only use \.str accessor|'float' object has no attribute 'shape'|Could not convert"),
      "arrow conversion / pd.NA error"),
    R("engine_bug_error", lambda c: c["eng"] in ("modin", "fireducks", "bodo", "bodo_dw", "dask") and c["cls"] == "ERR", "other engine error"),
    R("approximate_quantile", lambda c: c["eng"] in ("bodo", "bodo_dw", "dask") and c["cls"] == "DIFF"
      and code_has(c, r"quantile\(|percentile\(|describe\(") and not code_has(c, OBJ_CHECK), "quantile/percentile/describe in cell or called function"),
    R("str_dtype_object_checks", lambda c: c["eng"] in ARROW_ENG and c["cls"] in ("DIFF", "E4", "E3") and code_has(c, OBJ_CHECK),
      "dtype=='object' / select_dtypes('object') / include='O'"),
    R("engine_corr_wrong_values", lambda c: is_(c, "modin") and c["cls"] == "DIFF" and code_has(c, r"\.corr\("), "Modin corr DIFF"),
    R("engine_bug_silent", lambda c: (is_(c, "modin") and c["cls"] == "DIFF" and code_has(c, r"pivot_table\(|value_counts\("))
      or (c["eng"] in ("bodo", "bodo_dw") and c["cls"] == "DIFF" and code_has(c, r"^\s*\w+\.head\(\s*\d*\s*\)\s*$") and _any(c["outs"], r"shape:|labels", ("E4",))),
      "Modin pivot_table/value_counts DIFF, Bodo stale head()"),
    # representation-level causes
    R("datetime_resolution_inference", lambda c: is_(c, "p30") and (_any(c["outs"], r"datetime64\[ns\]/datetime64\[(us|ms|s)\]", ("E0",))
      or (c["cls"] == "DIFF" and code_has(c, r"DatetimeIndex\([^)]*\)\.\w+\s*$"))), "ns vs us dtype"),
    R("datetime_resolution_inference", lambda c: is_(c, "p30") and c["cls"] == "DIFF" and code_has(c, r"\.describe\(")
      and _any(c["outs"], r"^values", ("E4",)), "describe() of datetime/timedelta columns: mean at us instead of ns (inspected: yuliagm c8, xokent c5)"),
    R("str_default_dtype", lambda c: is_(c, "p30") and c["cls"] == "DIFF" and code_has(c, r"\.unique\(\)")
      and not _any(c["outs"], r"shape", ("E4",)), "unique() returns ArrowStringArray (dtype str) instead of an object ndarray"),
    R("row_order_ties", lambda c: c["cls"] == "E1" or (c["cls"] in ("E4", "DIFF") and c["eng"] in ("p30", "p15", "modin")
      and code_has(c, r"value_counts|nlargest|nsmallest|sort_values|\.mode\(") and not code_has(c, r"\.dtypes")
      and _any(c["outs"], r"index:values|^values", ("E3", "E4"))),
      "E1, or order-sensitive op (value_counts/sort/nlargest) with label/value mismatch at E3/E4"),
    R("row_order_ties", lambda c: c["eng"] in ENG and c["cls"] == "DIFF" and code_has(c, r"\bmerge\(|\.join\(")
      and code_has(c, r"\[:\d+\]|\.head\(|\.tail\(") and _any(c["outs"], r"^values", ("E4",)),
      "merge result order differs and head()/[:n] shows different rows"),
    R("float_rounding_within_tolerance", lambda c: c["cls"] == "E2" and _any(c["outs"], r"^values:|^scalar_value", ("E0",))
      and not _any(c["outs"], r"dtype|labels_dtype", ("E0",)), "E2 reached, E0 fails on values only"),
    R("int_float_nullable_repr", lambda c: c["eng"] in ENG and _any(c["outs"], r"float64/int(64|32)\b|int(64|32)/float64", ("E0",)), "float64 vs int"),
    R("arrow_backed_dtypes", lambda c: c["eng"] in ("pyarrow_backend", "bodo", "bodo_dw", "dask") and c["cls"] in ("E2", "E3", "E4")
      and _any(c["outs"], ARROWISH, ("E0",)), "arrow dtype in E0 failing check"),
    R("missing_sentinel_repr", lambda c: c["cls"] == "E3" and c["eng"] in ENG, "E3 on values (None vs NaN)"),
    R("axis_names_lost", lambda c: c["eng"] in ENG and _any(c["outs"], r"^names:", LEVELS), "names check"),
    R("index_not_preserved", lambda c: c["eng"] in ENG and c["cls"] == "E4" and _any(c["outs"], r"index:values", ("E3",)), "index values differ only"),
    R("str_default_dtype", lambda c: is_(c, "p30") and (
        (c["cls"] in ("E2", "E3", "E4") and _any(c["outs"], STR_OBJ, ("E0",)))
        or (c["cls"] == "DIFF" and code_has(c, r"\.dtypes\s*(\.T)?\s*$|\bstr\(\w+\[")
            and _any(c["outs"], STR_OBJ + r"|scalar_value", ("E0",)))),
      "object/str dtype only (or .dtypes / str() output)"),
    # ---- appended 2026-10-04 for conf_1x (they only see cells no earlier rule matched, so drift attributions are unchanged)
    R("engine_crash_timeout", lambda c: c["eng"] in ENG and c["cls"] in ("CRASH", "TIMEOUT", "KILLED"),
      "engine CRASH/TIMEOUT cell with clean inputs"),
    R("arrow_dtype_errors", lambda c: c["eng"] in ("pyarrow_backend", "bodo", "bodo_dw") and c["cls"] == "ERR" and msg_has(
        c, r"must contain a symbolic group name|for dtype '(?:large_)?string\[pyarrow\]'|NAType|ArrowExtensionArray|ArrowDtype|"
           r"date_cols are numpy arrays"),
      "error message names an Arrow type, pd.NA, or str.extract's named-group requirement for Arrow strings"),
    R("str_dtype_object_checks", lambda c: c["eng"] in ARROW_ENG and c["cls"] in ("ERR", "DIFF", "E4", "E3") and code_has(
        c, OBJ_CHECK + r"|exclude\s*=\s*\[?\s*['\"]O['\"]|dtypes?\s+in\s+\[\s*['\"](?:int|float)|col_type\s+in\s+numerics"),
      "dtype=='object' / include or exclude 'O' / dtype in [numpy dtype names] on Arrow-backed columns"),
    R("na_comparison_masks", lambda c: c["eng"] in ("pyarrow_backend", "bodo", "bodo_dw", "dask") and c["cls"] == "DIFF"
      and _any(c["outs"], r"^shape:\[(\d+)", ("E4",)) and code_has(c, r"!=\s*['\"]"),
      "row count of a != filter differs on Arrow-backed data"),
    R("chunked_csv_type_inference", lambda c: c["eng"] in ENG and c["cls"] == "DIFF" and code_has(c, r"read_(csv|table)\(")
      and any(int(m) > 0 and int(m) % 4096 == 0 for o in c["outs"] for m in re.findall(r"row=(\d+)", _fail_at(o, "E4"))),
      "read_csv cell; values first differ at a multiple of 4096 rows"),
    R("arrow_backed_dtypes", lambda c: c["eng"] in ("pyarrow_backend", "bodo", "bodo_dw", "dask") and c["cls"] == "DIFF"
      and code_has(c, r"\.dtypes\s*(\.T)?\s*$|\bstr\(\w+\[|\.unique\(\)") and not _any(c["outs"], r"shape", ("E4",)),
      ".dtypes listing / str() / unique() of Arrow-backed columns (values differ only in their dtype text or array type)"),
    R("scalar_type_numpy", lambda c: c["eng"] in ENG and c["cls"] == "E2" and _any(c["outs"], r"scalar_type:int/numpy\.int64", ("E0",)),
      "E2; E0 fails on scalar type int vs numpy.int64"),
    R("dtype_inference_differs", lambda c: c["eng"] in ENG and c["cls"] in ("E2", "DIFF") and _any(
        c["outs"], r"^dtype:col\d+:(object|bool|int64|float64|UInt32|uint32)/(object|bool|int64|float64|UInt32|uint32)$|^array_type:",
        ("E0",)) and not _any(c["outs"], r"^values|^shape|^labels|missing_mask", ("E4",)),
      "E0 fails on a NumPy/nullable dtype or array type only"),
]


def attribute(cell):
    for cause, pred, why in RULES:
        try:
            if pred(cell):
                return cause, why
        except Exception as e:  # a rule bug must not hide a cell
            return "unattributed", "rule_error:%s:%s" % (cause, e)
    return "unattributed", "no rule matched"


# ----------------------------------------------------------------------------------------------
# reading outputs
# ----------------------------------------------------------------------------------------------
_CODE = {}
_DEFS = {}


def _cells(nb):
    if nb not in _CODE:
        try:
            _CODE[nb] = nbsource.load_cells(datasets.notebook_file(nb))
        except Exception:
            _CODE[nb] = []
        defs = {}
        for src in _CODE[nb]:
            for m in re.finditer(r"^def\s+(\w+)\s*\(", src, re.M):
                body = src[m.start():]
                nl = body.find("\n")
                nxt = re.search(r"^\S", body[nl + 1:], re.M) if nl >= 0 else None
                defs[m.group(1)] = body[: nl + 1 + nxt.start()] if nxt else body
        _DEFS[nb] = defs
    return _CODE[nb]


def cell_code(nb, i, expand=True):
    cells = _cells(nb)
    src = cells[i] if 0 <= i < len(cells) else ""
    if not expand:
        return src
    extra = []
    for name, body in _DEFS.get(nb, {}).items():
        if re.search(r"\b%s\s*\(" % re.escape(name), src) and not re.search(r"^def\s+%s\b" % re.escape(name), src, re.M):
            extra.append(body)
    return src + ("\n# --- called user functions ---\n" + "\n".join(extra) if extra else "")


def select_outputs(campaign, compare_tag):
    root = os.path.join(PROJ, "results", campaign, "raw", "compare__%s__d%s" % (HARNESS, compare_tag))
    best = {}
    for p in glob.glob(os.path.join(root, "*", "*", "*.json")):
        if os.path.basename(p).startswith(".tmp"):
            continue
        try:
            with open(p) as f:
                r = json.load(f)
        except (OSError, ValueError):
            continue
        ref = r["meta"].get("ref") or "ref"
        label = r["meta"]["engine"] if ref == "ref" else "%s~vs~%s" % (r["meta"]["engine"], ref)
        key = (label, r["meta"]["nb"], r["meta"].get("scale"))
        rank = (r["meta"].get("ref2_record") is not None, os.path.getmtime(p))
        if key not in best or rank > best[key][0]:
            best[key] = (rank, r, p)
    return root, best


def normalise_cell(campaign, label, nb, c):
    outs = []
    for n, o in sorted((c.get("outputs") or {}).items()):
        outs.append({"name": n, "level": o.get("level"), "fails": o.get("fails") or {}, "reason": o.get("reason"),
                     "error": (o.get("error") or "")[:200]})
    exc, msg = c.get("eng_exc"), c.get("eng_msg")
    base = label.split("#")[0].split("~")[0]
    return {"campaign": campaign, "label": label, "eng": base, "nb": nb, "i": c["i"], "cls": c["cls"],
            "cls_raw": c.get("cls_raw"), "clean": c.get("clean_level"), "clean_input": bool(c.get("clean_input")),
            "outs": outs, "exc": exc, "msg": (msg or "")[:300], "fallback": bool(c.get("fallback")),
            "families": c.get("families")}


def introduced(c):
    if c["cls"] not in RANK:
        return False
    return c["clean"] is not None and RANK[c["cls"]] > RANK.get(c["clean"], 9)


def classify_cell(c):
    """-> (cause, kind, why). kind: introduced | propagated | cascade | harness | nondet"""
    if c["cls"] == "NONDET":
        return "nondeterminism", "nondet", "NONDET (ref vs ref#2)"
    if "~vs~" in c["label"]:
        if c["cls"] == "UNCOMPARABLE":
            return "capture_cap", "harness", "replicate output not capturable"
        return "nondeterminism", "nondet", "engine vs its own replicate"
    if c["cls"] in ("MEMORY", "NOTRUN"):
        return "resource_memory_cap", "cascade", c["cls"]
    if c["cls"] == "ERR" and re.search(r"NameError|UnboundLocalError", c.get("exc") or ""):
        return "cascade_undefined_name", "cascade", c.get("msg", "")[:60]
    if c["cls"] == "UNCOMPARABLE":
        return "capture_cap", "harness", "capped/uncapturable output"
    key = (c["label"], c["nb"], c["i"])
    if not introduced(c):
        return "propagated", "propagated", "class %s not coarser than inputs %s" % (c["cls"], c["clean"])
    if key in CURATED:
        return CURATED[key][0], "introduced", "curated: " + CURATED[key][1]
    cause, why = attribute(c)
    if cause == "unattributed" and c["cls"] == "DIFF" and c["clean"] in ("E1", "E4"):
        return "order_propagated", "propagated", "inputs equal only modulo row order/index (%s)" % c["clean"]
    return cause, "introduced", why


def _repro_diff(rr):
    """Per pandas environment: does the reproducer print something different from ref (env line excluded)?"""
    if not rr or "ref" not in rr:
        return None
    base = [l for l in rr["ref"].get("result_lines", []) if not l.startswith("RESULT env")]
    return {env: [l for l in r.get("result_lines", []) if not l.startswith("RESULT env")] != base
            for env, r in rr.items() if env != "ref"}


def build(sources, compare_tag, out_name, repro_runs_path):
    t0 = time.time()
    meta_sources, cells, nondet_seen = [], [], set()
    for campaign, labels in sources:
        root, best = select_outputs(campaign, compare_tag)
        used = collections.Counter()
        for (label, nb, sc), (_, r, p) in sorted(best.items()):
            if label not in labels:
                continue
            used[label] += 1
            for c in r["cells"]:
                if c["cls"] in ("E0", "NOOUT", "REF_ERR"):
                    continue
                if label == "ref#2" and c["cls"] != "NONDET":
                    continue
                if c["cls"] == "NONDET" and label != "ref#2" and "ref#2" in labels:
                    continue  # NONDET is decided from ref vs ref#2 and is identical for every engine: count once
                if label == "ref#2":
                    if (nb, c["i"]) in nondet_seen:
                        continue  # conf_1x and drift share the same ref/ref#2 records (adopted): count once
                    nondet_seen.add((nb, c["i"]))
                cells.append(normalise_cell(campaign, label, nb, c))
        meta_sources.append({"campaign": campaign, "compare_root": os.path.relpath(root, PROJ),
                             "labels": labels, "outputs_used": dict(used), "note": CAMPAIGN_NOTE.get(campaign, campaign)})
    # attribute
    by_cause = collections.defaultdict(list)
    kinds = collections.Counter()
    per_engine = collections.defaultdict(collections.Counter)
    for c in cells:
        c["code"] = cell_code(c["nb"], c["i"])
        cause, kind, why = classify_cell(c)
        c["cause"], c["kind"], c["why"] = cause, kind, why
        kinds[kind] += 1
        per_engine["%s:%s" % (c["campaign"], c["label"])][kind if kind != "introduced" else "introduced"] += 1
        if kind == "introduced":
            per_engine["%s:%s" % (c["campaign"], c["label"])]["introduced:" + cause] += 1
        by_cause[cause].append(c)
    repro_runs = {}
    if repro_runs_path and os.path.exists(repro_runs_path):
        with open(repro_runs_path) as f:
            repro_runs = json.load(f)
    todo = {e["cause"]: e for e in write_probes_todo()["probes"]}

    def summarise(cause, lst):
        intro = [c for c in lst if c["kind"] in ("introduced", "nondet", "cascade", "harness") or c["cause"] == "order_propagated"]
        eng = collections.Counter("%s:%s" % (c["campaign"], c["label"]) for c in intro)
        nbs = sorted({c["nb"] for c in intro})
        ex = []
        seen = set()
        for c in sorted(intro, key=lambda x: (x["campaign"] != "drift", x["label"], x["nb"], x["i"])):
            k = (c["label"], c["nb"])
            if k in seen:
                continue
            seen.add(k)
            ex.append({"campaign": c["campaign"], "engine": c["label"], "nb": c["nb"], "cell": c["i"], "cls": c["cls"],
                       "inputs_equal_at": c["clean"], "check": _worst_fail(c["outs"]) or ((c.get("exc") or "") + ": " + (c.get("msg") or "")[:120]),
                       "rule": c["why"]})
        d = {"cause": cause, "n_cells": len(intro), "n_strict_clean_cells": sum(1 for c in intro if c["clean_input"]),
             "n_notebooks": len(nbs), "by_engine": dict(sorted(eng.items())),
             "by_class": dict(collections.Counter(c["cls"] for c in intro)),
             "observed_severity": dict(collections.Counter(
                 "DIFF_not_equal_at_E4" if c["cls"] == "DIFF" else "equal_at_E1_to_E4" if c["cls"] in LEVELS
                 else "nondet" if c["cls"] == "NONDET" else "error" for c in intro)),
             "notebooks": nbs, "examples": ex[:8],
             "cells": [[c["campaign"], c["label"], c["nb"], c["i"], c["cls"]] for c in intro]}
        if cause in CAUSES:
            meta = CAUSES[cause]
            d.update({"title": meta["title"], "family": meta["family"], "severity": meta["severity"],
                      "documented": bool(meta["documented"]), "doc_refs": meta["documented"],
                      "documented_level": (("partial" if meta.get("documented_note") else "yes") if meta["documented"]
                                           else ("not_searched" if meta.get("doc_searched") is False else "no")),
                      "engine_probe_outcome": PROBE_OUTCOMES.get(cause),
                      "documented_note": meta.get("documented_note"),
                      "reproducer": ("results/rootcause/repro/" + meta["repro"]) if meta.get("repro") else None,
                      "repro_runs": repro_runs.get(cause), "repro_differs_from_ref": _repro_diff(repro_runs.get(cause)),
                      "engine_probe_pending": cause in todo,
                      "engine_probe_engines": ENGINE_PROBES.get(cause, [])})
        else:
            d.update({"title": NON_ROOT.get(cause, cause), "family": "not_a_root_cause", "severity": None,
                      "documented": None})
        return d

    causes = {k: summarise(k, v) for k, v in by_cause.items() if k != "propagated"}
    # propagated cells: per engine count only
    out = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "script": "scripts/rootcause_taxonomy.py",
        "harness_tag": HARNESS, "compare_tag": "d" + compare_tag,
        "sources": meta_sources,
        "unit": "introduced divergence: non-E0 cell whose class is coarser than the level at which its inputs were equal "
                "(classify.clean_level); one cause per cell, first matching rule",
        "counts": {"non_e0_cells": len(cells), "by_kind": dict(kinds)},
        "per_engine": {k: dict(sorted(v.items())) for k, v in sorted(per_engine.items())},
        "causes": dict(sorted(causes.items(), key=lambda kv: -kv[1]["n_cells"])),
        "rules": [{"cause": c, "rule": w} for c, _, w in RULES],
        "runtime_s": round(time.time() - t0, 1),
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    jp = os.path.join(OUT_DIR, out_name + ".json")
    tmp = jp + ".tmp"
    with open(tmp, "w") as f:
        json.dump(out, f, indent=1, sort_keys=False, default=str)
    os.replace(tmp, jp)
    write_md(out, os.path.join(OUT_DIR, out_name + ".md"))
    print("wrote %s (%d non-E0 cells; kinds %s; %d causes) in %.1fs" % (jp, len(cells), dict(kinds), len(causes), time.time() - t0))
    return out


# ----------------------------------------------------------------------------------------------
# Markdown + LaTeX
# ----------------------------------------------------------------------------------------------
SEV_TEX = {"silent_value_change": "silent", "representation_only": "repr.", "error": "error", "excluded": "excl."}
SHORT = {"pyarrow_backend": "PA", "modin": "Mo", "fireducks": "FD", "bodo": "Bo", "bodo_dw": "BoD", "dask": "Da",
         "p15": "p1.5", "p30": "p3.0", "ref#2": "ref"}


def _tex(s):
    return (s.replace("\\", "\\textbackslash{}").replace("_", "\\_").replace("%", "\\%").replace("&", "\\&")
             .replace("#", "\\#").replace("$", "\\$").replace("{", "\\{").replace("}", "\\}").replace("~", "\\textasciitilde{}"))


def _eng_short(by_engine):
    agg = collections.Counter()
    for k, v in by_engine.items():
        lab = k.split(":", 1)[1]
        lab = lab.split("~vs~")[0]
        agg[SHORT.get(lab, lab)] += v
    return ", ".join("%s %d" % (k, v) for k, v in sorted(agg.items(), key=lambda kv: -kv[1]))


def write_md(t, path):
    L = []
    L.append("# Root-cause taxonomy (plan Section 8, Table 1)\n")
    L.append("Generated %s by `%s` (harness %s, compare %s). Rerun: `../.venv/bin/python scripts/rootcause_taxonomy.py build`.\n"
             % (t["generated"], t["script"], t["harness_tag"], t["compare_tag"]))
    L.append("**Sources.**")
    for s in t["sources"]:
        L.append("- `%s` (%s): labels %s; outputs used %s." % (s["campaign"], s["note"], ", ".join(s["labels"]),
                                                               json.dumps(s["outputs_used"])))
    L.append("\n**Unit.** %s. Cells whose divergence is inherited from an earlier cell are `propagated` and are not attributed again. "
             "Pilot rows describe 10 notebooks and are a pilot, not a claim.\n" % t["unit"])
    L.append("**Counts.** %d non-E0 cells; by kind %s.\n" % (t["counts"]["non_e0_cells"], json.dumps(t["counts"]["by_kind"])))
    L.append("**How causes were assigned.** Ordered rules over the comparator's first failing check per level, the exception "
             "type and message, and the cell code (plus the bodies of user functions the cell calls); %d hand-inspected cells are "
             "fixed in `CURATED` with the decoded values as evidence. Every rule is listed in taxonomy.json (`rules`); each "
             "example below names the rule that fired. Rules are heuristics: counts are per introduced cell, one cause per cell.\n"
             % len(CURATED))
    L.append("**How documentation was verified (2026-10-04).** Every URL was fetched with WebFetch and the quoted sentence was "
             "found on the page. For the long pandas release notes (v2.0.0, v3.0.0) WebFetch returns a truncated page, so the "
             "quotes were also checked by a full-text search of the downloaded HTML. `documented: no` means no statement was found "
             "in the engine's or pandas' documentation by these searches; it is not proof of absence.\n")
    L.append("**Limitations.** Engine reproducers were written but not run (they start Ray, MPI or thread pools); they are listed "
             "in `probes_todo.json` for a guarded probes campaign. The Bodo part of `approximate_quantile` is a hypothesis from "
             "the cell code (quantile/percentile thresholds) until its probe runs. Engine rows come from the 10-notebook pilot; "
             "rerun with `--preset conf1x` once conf_1x compare is complete.\n")
    L.append("## Table 1 (root causes; counts are introduced cells)\n")
    L.append("| cause | severity | documented | cells | strict-clean | notebooks | engines (cells) | example (engine nb cell) | reproducer |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    roots = [c for c in t["causes"].values() if c["family"] not in ("not_a_root_cause",)]
    others = [c for c in t["causes"].values() if c["family"] == "not_a_root_cause"]
    for c in roots:
        ex = c["examples"][0] if c["examples"] else None
        exs = "%s %s c%d" % (ex["engine"], ex["nb"], ex["cell"]) if ex else ""
        doc = (c.get("documented_level") + ": " + ", ".join(r["url"] for r in c.get("doc_refs") or [])) if c.get("documented") else "no"
        L.append("| `%s` | %s | %s | %d | %d | %d | %s | %s | %s |" % (
            c["cause"], c.get("severity"), doc, c["n_cells"], c["n_strict_clean_cells"], c["n_notebooks"],
            _eng_short(c["by_engine"]), exs, (c.get("reproducer") or "").replace("results/rootcause/", "")))
    L.append("\nNot root causes (reported separately):\n")
    L.append("| category | cells | notebooks | engines |")
    L.append("|---|---|---|---|")
    for c in others:
        L.append("| `%s`: %s | %d | %d | %s |" % (c["cause"], c["title"], c["n_cells"], c["n_notebooks"], _eng_short(c["by_engine"])))
    prop = sum(v.get("propagated", 0) for v in t["per_engine"].values())
    L.append("| `propagated`: %s | %d | | |" % (NON_ROOT["propagated"], prop))
    # per engine
    L.append("\n## Per engine (non-E0 cells by kind)\n")
    L.append("| campaign:engine | introduced | propagated | cascade | harness | nondet | unattributed |")
    L.append("|---|---|---|---|---|---|---|")
    for k, v in t["per_engine"].items():
        L.append("| %s | %d | %d | %d | %d | %d | %d |" % (k, v.get("introduced", 0), v.get("propagated", 0), v.get("cascade", 0),
                                                         v.get("harness", 0), v.get("nondet", 0), v.get("introduced:unattributed", 0)))
    # per cause details
    L.append("\n## Causes in detail\n")
    for c in roots:
        L.append("### `%s` (%s)\n" % (c["cause"], c.get("severity")))
        L.append("%s.\n" % c["title"])
        L.append("- Cells %d (strict-clean %d), notebooks %d, by class %s; observed severity per cell %s." % (
            c["n_cells"], c["n_strict_clean_cells"], c["n_notebooks"], json.dumps(c["by_class"]), json.dumps(c["observed_severity"])))
        L.append("- Engines: %s." % json.dumps(c["by_engine"]))
        if c.get("documented"):
            for r in c["doc_refs"]:
                L.append("- Documented: <%s> (\"%s\")." % (r["url"], r["quote"]))
        else:
            L.append("- Documented: no documentation found (searched 2026-10-04).")
        if c.get("documented_note"):
            L.append("- Note: %s." % c["documented_note"])
        for ex in c["examples"][:4]:
            L.append("- Example: %s `%s` cell %d, %s (inputs equal at %s), check `%s`." % (
                ex["engine"], ex["nb"], ex["cell"], ex["cls"], ex["inputs_equal_at"], str(ex["check"]).replace("|", "/")[:140]))
        if c.get("reproducer"):
            rr = c.get("repro_runs")
            if rr:
                L.append("- Reproducer `%s`, run in pandas environments (differs from ref: %s):" % (
                    c["reproducer"], json.dumps(c.get("repro_differs_from_ref"))))
                for env, res in rr.items():
                    L.append("  - %s: rc %s, %.2f s, max RSS %.0f MB: `%s`" % (env, res.get("rc"), res.get("wall_s", 0),
                                                                               res.get("maxrss_mb", 0), (res.get("summary") or "")[:200].replace("|", "/")))
            if c.get("engine_probe_pending"):
                L.append("- Engine reproducer pending for %s: listed in `results/rootcause/probes_todo.json` (not run: starts worker pools)."
                         % ", ".join(c.get("engine_probe_engines") or []))
            elif c.get("reproducer") and c.get("engine_probe_pending"):
                pass
        L.append("")
    # LaTeX
    L.append("## LaTeX rows for Table 1\n")
    L.append("Columns: cause & severity & documented & cells & notebooks & engines (cells). Pilot engine counts are from 10 notebooks.\n")
    L.append("```latex")
    for c in roots:
        L.append("%s & %s & %s & %d & %d & %s \\\\" % (
            _tex(c["cause"].replace("_", " ")), SEV_TEX.get(c.get("severity"), ""), c.get("documented_level") or "no",
            c["n_cells"], c["n_notebooks"], _tex(_eng_short(c["by_engine"]))))
    L.append("```\n")
    with open(path + ".tmp", "w") as f:
        f.write("\n".join(L) + "\n")
    os.replace(path + ".tmp", path)


# ----------------------------------------------------------------------------------------------
# engine reproducers: written, NOT run here (they start Ray / MPI / thread pools). They are listed in
# results/rootcause/probes_todo.json for a later guarded probes campaign.
# ----------------------------------------------------------------------------------------------
ENGINE_PROBES = {
    "str_dtype_object_checks": ["bodo", "dask"],
    "cow_chained_assignment": ["fireducks"],
    "arrow_backed_dtypes": ["bodo", "dask"],
    "arrow_dtype_errors": ["bodo", "fireducks"],
    "row_order_ties": ["modin", "fireducks", "bodo"],
    "float_rounding_within_tolerance": ["modin", "fireducks"],
    "missing_sentinel_repr": ["fireducks"],
    "int_float_nullable_repr": ["modin", "fireducks"],
    "index_not_preserved": ["bodo", "bodo_dw", "fireducks", "dask"],
    "axis_names_lost": ["modin", "bodo"],
    "approximate_quantile": ["bodo", "bodo_dw", "dask"],
    "partitioned_type_inference": ["dask", "modin"],
    "lazy_partition_model": ["dask"],
    "engine_unsupported_api": ["dask", "bodo", "fireducks"],
    "engine_bug_error": ["bodo", "bodo_dw", "modin", "fireducks"],
    "engine_corr_wrong_values": ["modin"],
    "engine_bug_silent": ["modin", "bodo", "bodo_dw"],
}
# Outcome of the guarded engine probes (F4), written by scripts/engine_probe_outcomes.py; {} if not yet judged.
_PO = os.path.join(OUT_DIR, "engine_probe_outcomes.json")
PROBE_OUTCOMES = {}
if os.path.exists(_PO):
    with open(_PO) as _f:
        PROBE_OUTCOMES = {k: {"verdict": v["verdict"], "by_engine": {e: x["verdict"] for e, x in v["engines"].items()}}
                          for k, v in json.load(_f)["causes"].items()}
ENGINE_ENV = {"modin": ("envs/modin/bin/python", "modin", {"RAY_ENABLE_MAC_LARGE_OBJECT_STORE": "1", "RAY_USAGE_STATS_ENABLED": "0"}),
              "fireducks": ("envs/fireducks/bin/python", "fireducks", {"FIREDUCKS_FLAGS": "-Wfallback"}),
              "bodo": ("envs/bodo/bin/python", "bodo", {"BODO_NUM_WORKERS": "1"}),
              "bodo_dw": ("envs/bodo/bin/python", "bodo", {}),
              "dask": ("envs/dask/bin/python", "dask", {})}


def write_probes_todo():
    probes = []
    for cause, engines in sorted(ENGINE_PROBES.items()):
        script = "results/rootcause/repro/%s.py" % CAUSES[cause]["repro"].replace(".py", "")
        for e in engines:
            py, mode, extra = ENGINE_ENV[e]
            envs = " ".join("%s=%s" % kv for kv in sorted(extra.items()))
            probes.append({"cause": cause, "engine": e, "script": script,
                           "command": "cd %s/results/rootcause/repro && env PCONF_REPRO_MODE=%s %s %s/%s %s.py"
                                      % (PROJ, mode, envs, PROJ, py, cause),
                           "status": "pending"})
    guard = ("cd .. && python3 tools/memory_guard.py --limit-gb 120 --wait-lock 14400 "
             "--state runs/06_pandas_conformance_rootcause_probes.json -- bash %s/results/rootcause/run_engine_probes.sh" % PROJ)
    doc = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "why_not_run": "engine reproducers start worker pools (Ray, MPI, thread pools); per the task they run only in a later guarded probes campaign",
           "guarded_command": guard,
           "note": "run_engine_probes.sh is to be written by the probes stage from the 'command' fields (one line each, "
                   "outputs appended to results/rootcause/engine_probe_runs.log); engine_corr_wrong_values builds a 4.4M x 25 frame (several GB)",
           "probes": probes}
    path = os.path.join(OUT_DIR, "probes_todo.json")
    with open(path + ".tmp", "w") as f:
        json.dump(doc, f, indent=1)
    os.replace(path + ".tmp", path)
    return doc


# ----------------------------------------------------------------------------------------------
# pandas-only reproducers
# ----------------------------------------------------------------------------------------------
PANDAS_ENVS = {"ref": ("envs/ref/bin/python", None), "p15": ("envs/p15/bin/python", None),
               "p30": ("envs/p30/bin/python", None), "pyarrow_backend": ("envs/ref/bin/python", "pyarrow_backend")}


def run_repros(names=None, timeout=60):
    repro_dir = os.path.join(OUT_DIR, "repro")
    results = {}
    files = sorted(glob.glob(os.path.join(repro_dir, "*.py")))
    for p in files:
        cause = os.path.splitext(os.path.basename(p))[0]
        with open(p) as f:
            head = f.read(2000)
        if "PCONF_REPRO_KIND: pandas" not in head:
            continue
        if names and cause not in names:
            continue
        results[cause] = {}
        for env, (py, mode) in PANDAS_ENVS.items():
            e = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
            e.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
                      "VECLIB_MAXIMUM_THREADS": "1", "PYTHONHASHSEED": "0", "PCONF_REPRO_MODE": mode or "pandas"})
            t0 = time.time()
            try:
                pr = subprocess.run(["/usr/bin/time", "-l", os.path.join(PROJ, py), p], capture_output=True, text=True,
                                    timeout=timeout, env=e, cwd=repro_dir)
                rc, out, err = pr.returncode, pr.stdout, pr.stderr
            except subprocess.TimeoutExpired:
                rc, out, err = "timeout", "", ""
            wall = time.time() - t0
            m = re.search(r"(\d+)\s+maximum resident set size", err)
            rss = int(m.group(1)) / 1e6 if m else None
            lines = [l for l in out.splitlines() if l.startswith("RESULT")]
            results[cause][env] = {"rc": rc, "wall_s": round(wall, 2), "maxrss_mb": round(rss, 1) if rss else None,
                                   "result_lines": lines, "summary": " ; ".join(l[7:] for l in lines)[:600],
                                   "stderr_tail": "\n".join(l for l in err.splitlines() if "resident" not in l and not re.match(r"^\s+\d+\s", l))[-400:]}
            print("%-38s %-16s rc=%s %.2fs %sMB %s" % (cause, env, rc, wall, results[cause][env]["maxrss_mb"],
                                                       results[cause][env]["summary"][:120]))
    path = os.path.join(OUT_DIR, "repro_runs.json")
    old = {}
    if os.path.exists(path):
        with open(path) as f:
            old = json.load(f)
    old.update(results)
    with open(path + ".tmp", "w") as f:
        json.dump(old, f, indent=1, sort_keys=True)
    os.replace(path + ".tmp", path)
    print("wrote", path)


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--preset", default="current", choices=sorted(PRESETS))
    b.add_argument("--source", action="append", default=None,
                   help="CAMPAIGN:label1,label2 (repeatable; replaces the preset)")
    b.add_argument("--compare-tag", default=COMPARE, help="compare tag without the leading d")
    b.add_argument("--out-name", default="taxonomy")
    r = sub.add_parser("run-repros")
    r.add_argument("--only", default=None)
    r.add_argument("--timeout", type=float, default=60)
    a = ap.parse_args(argv)
    if a.cmd == "build":
        if a.source:
            sources = [(s.split(":", 1)[0], s.split(":", 1)[1].split(",")) for s in a.source]
        else:
            sources = [(camp, list(labels)) for camp, labels in PRESETS[a.preset]]
            if a.preset == "conf1x":
                # bodo_dw is the last step of the main batch; until its conf_1x compare exists, keep its PILOT outputs
                # (10 notebooks, marked as pilot) so that bodo_dw causes are not silently dropped.
                bdw = glob.glob(os.path.join(PROJ, "results", "conf_1x", "raw", "compare__%s__d%s" % (HARNESS, a.compare_tag),
                                             "bodo_dw", "*", "*.json"))
                if not bdw:
                    for camp, labels in sources:
                        if camp == "pilot":
                            labels.append("bodo_dw")
        for camp, _ in sources:
            root = os.path.join(PROJ, "results", camp, "raw", "compare__%s__d%s" % (HARNESS, a.compare_tag))
            if not os.path.isdir(root):
                raise SystemExit("missing compare outputs: %s (has the compare step of %s completed?)" % (root, camp))
        build(sources, a.compare_tag, a.out_name, os.path.join(OUT_DIR, "repro_runs.json"))
    else:
        run_repros(a.only.split(",") if a.only else None, a.timeout)
    return 0


if __name__ == "__main__":
    sys.exit(main())

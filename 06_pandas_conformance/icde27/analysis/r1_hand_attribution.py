#!/usr/bin/env python3
"""Review R1 item B5: hand attribution of the 117 cells the rule-based taxonomy leaves unattributed (2026-10-26).

Writes icde27/analysis/r1_hand_attribution.json (no captured values). Read-only otherwise; tiny memory.

    cd ..
    .venv/bin/python 06_pandas_conformance/icde27/analysis/r1_hand_attribution.py

Method. The cells are those of results/rootcause/taxonomy_conf1x.json causes.unattributed (117: 111 DIFF, 4 E2,
2 ERR). For each cell, icde27/analysis/r1_unattributed_dump.py printed an evidence sheet (the cell code with called
user functions, every output's level and failing checks, the first differing rows of both values decoded from the
store, and the engine's warnings); targeted follow-ups decoded single columns, column labels or cell inputs and
read neighbouring cells (scratch tool, values shown on screen only). One rater, the AI agent that prepared the
ICDE revision (see the paper's AI-content acknowledgement), assigned one cause per cell, reusing a Table II cause
when it fits, and recorded the evidence without data values. Confidence: `verified` = the
evidence shows the mechanism (for example the frame equals the reference while its head() differs, or the column
labels change type); `likely` = the symptom matches a verified sibling cell or a documented behaviour but this cell
was not checked separately; `undetermined` = symptom only. This is a single-rater attribution that no
second rater has checked.
"""
import collections
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "r1_hand_attribution.json")

# cause -> (title, mechanism). Mechanisms: parallel or lazy execution; representation choice; missing or erroneous
# support; harness artefact; pandas evolution.
CAUSES = {
    "stale_after_inplace_update": ("results computed from data as it was before an in-place update", "missing or erroneous support"),
    "cow_chained_assignment": ("in-place method on a column selection does not write through", "representation choice"),
    "printed_form_comparison": ("container or object value compared by its printed form", "harness artefact"),
    "str_of_missing_sentinel": ("str() of a missing value gives 'nan', 'None' or '<NA>'", "representation choice"),
    "arrow_int_keeps_type": ("Arrow integer column keeps its type when filled with a float (truncation)", "representation choice"),
    "arrow_nan_not_null": ("Arrow float column keeps NaN distinct from null (fillna leaves NaN)", "representation choice"),
    "row_order_ties": ("order of tied sort or count keys exposed by head() or slicing", "parallel or lazy execution"),
    "dask_value_counts_order": ("value_counts not ordered by count", "parallel or lazy execution"),
    "biased_skew": ("skewness without the sample-size correction", "missing or erroneous support"),
    "integer_labels_as_strings": ("integer column labels become strings", "representation choice"),
    "tz_dropped_at_parse": ("time zone dropped when parsing dates", "missing or erroneous support"),
    "index_not_preserved": ("filter result carries positions instead of index labels", "representation choice"),
    "lazy_partition_model": ("lazy value used where a computed value is expected", "parallel or lazy execution"),
    "dask_api_semantics": ("constructor returns a Series for DataFrame(Series)", "missing or erroneous support"),
    "read_csv_none_as_na": ("the string 'None' is kept as text where pandas reads it as missing", "missing or erroneous support"),
    "unique_nunique_missing": ("unique() drops or nunique() counts missing values", "missing or erroneous support"),
    "groupby_median_other_value": ("group-by median returns another value", "missing or erroneous support"),
    "loc_setitem_inplace": ("loc[:, col] = replaces the column instead of setting values in place", "missing or erroneous support"),
    "unstack_labels_as_lists": ("unstack produces one-element list labels", "missing or erroneous support"),
    "float_rounding_amplified": ("float summation differences amplified by round()", "parallel or lazy execution"),
    "float_rounding_within_tolerance": ("float rounding within the tolerance", "parallel or lazy execution"),
    "nested_list_as_array": ("list values returned as NumPy arrays", "representation choice"),
    "fill_value_coerced": ("fill value coerced to the column's string type", "representation choice"),
    "float32_promoted": ("float32 arithmetic carried out in float64", "representation choice"),
    "corr_infinite_values": ("corr returns NaN where pandas skips infinite values", "missing or erroneous support"),
    "describe_datetime_numeric": ("describe() leaves out datetime columns", "missing or erroneous support"),
    "partitioned_type_inference": ("mixed-type column inferred per partition", "parallel or lazy execution"),
    "concat_sort_ignored": ("concat(sort=True) does not sort the columns", "missing or erroneous support"),
    "apply_side_effects_lost": ("side effects of functions passed to apply are lost", "parallel or lazy execution"),
    "get_dummies_sep_ignored": ("str.get_dummies ignores the separator", "missing or erroneous support"),
    "concat_unnamed_labels": ("concat of unnamed Series gives other column labels", "missing or erroneous support"),
    "melt_category_dtype": ("melt keeps a categorical variable column (pandas 1.5.3)", "pandas evolution"),
    "str_dtype_object_checks": ("dtype-name check selects other columns", "representation choice"),
    "arrow_backed_dtypes": ("Arrow-typed columns change which columns describe() covers", "representation choice"),
    "arrow_dtype_errors": ("error on Arrow-backed data", "missing or erroneous support"),
    "undetermined": ("mechanism not determined", "undetermined"),
}

V, L, U = "verified", "likely", "undetermined"
# (label, notebook, cell): (cause, confidence, evidence without data values)
H = {
    ("bodo", "artgor/eda-and-models", 34): ("stale_after_inplace_update", V, "the frame equals the reference (clean input); its head() shows values from before the column assignment of the previous cell"),
    ("bodo", "ayushsingh5941/tweet-disaster-or-not", 9): ("cow_chained_assignment", V, "fillna(inplace=True) on a column selection inside a user function; missing values remain"),
    ("bodo", "ayushsingh5941/tweet-disaster-or-not", 10): ("cow_chained_assignment", V, "same function on the test frame; missing values remain"),
    ("bodo", "balajivenkat96/solar-plants", 18): ("printed_form_comparison", V, "dict of frames compared as text; dates render with a time part"),
    ("bodo", "blaskowitz100/feature-engineering-based-on-the-suprise-me", 1): ("printed_form_comparison", V, "dict of frames compared as text"),
    ("bodo", "brianmendieta/data-cleaning-plus-eda", 15): ("undetermined", U, "str.extract result differs after a str.replace in the previous cell; not resolved"),
    ("bodo", "ersinsen/fraud-3-eda", 17): ("str_of_missing_sentinel", L, "suffix column built from str(x) of missing values (verified for FireDucks and the pyarrow backend on the same column)"),
    ("bodo", "gmanish/help-ngo-country-clustering", 9): ("stale_after_inplace_update", L, "the frame equals the reference; head() shows the untransformed column values"),
    ("bodo", "jackwatson99/pima-indians-diabetes-rf-81", 6): ("arrow_int_keeps_type", V, "replace(0, mean) keeps int64[pyarrow] and truncates the mean"),
    ("bodo", "jagangupta/stop-the-s-toxic-comments-eda", 12): ("integer_labels_as_strings", V, "crosstab column labels 0/1 become the strings '0'/'1'; the list of crosstabs differs in print"),
    ("bodo", "jagangupta/stop-the-s-toxic-comments-eda", 14): ("integer_labels_as_strings", V, "crosstab column labels become strings"),
    ("bodo", "julieberteaux/workshop-2", 10): ("cow_chained_assignment", V, "fillna(-1, inplace=True) on a column selection; missing values remain"),
    ("bodo", "kenjee/titanic-project-example", 13): ("integer_labels_as_strings", V, "pivot_table column labels become strings"),
    ("bodo", "kenjee/titanic-project-example", 14): ("str_of_missing_sentinel", V, "str(x)[0] of a missing value gives '<' instead of 'n'"),
    ("bodo", "kwullum/when-do-traffic-related-deaths-occur", 4): ("stale_after_inplace_update", V, "the assigned frame equals the reference (E2); its head() shows the column before map()"),
    ("bodo", "luizep/movieslens20m", 10): ("biased_skew", V, "ratio to the pandas value is 1 + 1.5/n for n rows, the sample-size correction"),
    ("bodo", "mahtieu/nyc-taxi-fare-prediction-data-expl-xgboost", 2): ("tz_dropped_at_parse", V, "parse_dates gives naive timestamps where pandas keeps UTC"),
    ("bodo", "nadare/feature-engenieering-with-pivot-table", 3): ("integer_labels_as_strings", V, "pivot_table column labels become strings"),
    ("bodo", "nadare/feature-engenieering-with-pivot-table", 12): ("integer_labels_as_strings", V, "pivot_table column labels become strings"),
    ("bodo", "paramarthasengupta/plotly-eda-top-movies-of-20th-century", 10): ("row_order_ties", V, "sort on a key with ties, then the first 20 rows"),
    ("bodo", "salmaneunus/student-s-performance-quantitative-visual-eda", 16): ("printed_form_comparison", V, "list holding a Series compared as text; dtype names differ"),
    ("bodo", "santhoshrao1995/assi01-santhosh-19101036", 2): ("cow_chained_assignment", V, "replace(inplace=True) on a column selection; values not replaced"),
    ("bodo", "shunjiangxu/blood-is-thicker-than-water-friendship-forever", 1): ("printed_form_comparison", V, "list of frames compared as text; sentinel and float formatting differ"),
    ("bodo", "snanilim/video-games-sales-analysis-and-visualization", 2): ("index_not_preserved", V, "filter result's index holds positions, so drop() removes other rows"),
    ("bodo", "sudheer259/house-price-prediction", 82): ("integer_labels_as_strings", V, "DataFrame(Series) column label 0 becomes '0'"),
    ("bodo", "taylorhickem/singapore-building-energy", 3): ("printed_form_comparison", V, "dict holding frames compared as text; the printed type name differs"),
    ("dask", "akshaypetkar/supermarket-sales-analysis", 18): ("dask_api_semantics", V, "DataFrame(Series) returns a Series"),
    ("dask", "akshaypetkar/supermarket-sales-analysis", 19): ("dask_api_semantics", V, "DataFrame(Series) returns a Series"),
    ("dask", "blaskowitz100/feature-engineering-based-on-the-suprise-me", 1): ("lazy_partition_model", V, "dict holds lazy frames that are never computed"),
    ("dask", "jackwatson99/pima-indians-diabetes-rf-81", 6): ("lazy_partition_model", V, "replace() inserts the lazy mean expression as a value"),
    ("dask", "luckygemini/notebook5d5fc80c9f", 4): ("lazy_partition_model", V, "str() of a lazy scalar"),
    ("dask", "luizep/movieslens20m", 10): ("biased_skew", V, "same value as Bodo and the pyarrow backend; ratio 1 + 1.5/n"),
    ("dask", "madseth/customer-shopping-trends-dataset-eda", 19): ("dask_value_counts_order", V, "value_counts ordered by label, so head(10) keeps other labels"),
    ("dask", "salmaneunus/student-s-performance-quantitative-visual-eda", 16): ("lazy_partition_model", V, "list holds a lazy Series"),
    ("dask", "yashjaiswal1097/911-emergency-calls-kernel", 3): ("dask_value_counts_order", V, "value_counts ordered by label"),
    ("dask", "yashjaiswal1097/911-emergency-calls-kernel", 4): ("dask_value_counts_order", V, "value_counts ordered by label"),
    ("fireducks", "ashukr/first-step-ingestion-to-prediction", 1): ("read_csv_none_as_na", V, "the text 'None' stays a string in a column where pandas reads it as missing"),
    ("fireducks", "beratozmen/clash-of-clans-exploratory-data-analysis", 7): ("unique_nunique_missing", V, "unique() leaves out the missing value"),
    ("fireducks", "blaskowitz100/feature-engineering-based-on-the-suprise-me", 13): ("groupby_median_other_value", L, "the merged group-by median column differs; min, mean, max and count agree"),
    ("fireducks", "charulatashelar/indian-startup-funding-exploratory-data-analysis", 9): ("loc_setitem_inplace", V, "loc[:, col] = to_datetime(...) gives datetime64 where pandas keeps object"),
    ("fireducks", "danielresende/game-of-thrones-battles", 5): ("stale_after_inplace_update", V, "two .at assignments in an earlier cell are visible in the captured frame but not in this group-by"),
    ("fireducks", "danielresende/game-of-thrones-battles", 7): ("stale_after_inplace_update", V, "same frame, another group-by"),
    ("fireducks", "danielresende/game-of-thrones-battles", 8): ("stale_after_inplace_update", V, "boolean filter returns the row as before the .at assignments"),
    ("fireducks", "dbatao/kernel2f80fc9d78", 3): ("read_csv_none_as_na", V, "the text 'None' stays a string"),
    ("fireducks", "ersinsen/fraud-3-eda", 17): ("str_of_missing_sentinel", V, "str(x) of a missing value gives 'None' instead of 'nan'"),
    ("fireducks", "grudd0/mass-shooting-analysis", 22): ("unstack_labels_as_lists", V, "unstack produces one-element list column labels"),
    ("fireducks", "grudd0/mass-shooting-analysis", 43): ("str_of_missing_sentinel", L, "astype(str) of missing values in a concatenated text column"),
    ("fireducks", "guyalmog/hr-analytics-predicting-employees-attrition", 6): ("float_rounding_amplified", L, "round(mean(axis=1), 2) differs in the last digit"),
    ("fireducks", "j0thu777/onlineretailanalysis", 27): ("float_rounding_within_tolerance", V, "group means differ in the last digits"),
    ("fireducks", "jagangupta/stop-the-s-toxic-comments-eda", 31): ("nested_list_as_array", L, "list-valued column from re.findall (arrays verified in a sibling cell)"),
    ("fireducks", "jyotsananegi/melbourne-housing-snapshot-eda", 4): ("unique_nunique_missing", V, "nunique() is one higher for every column with missing values"),
    ("fireducks", "kenjee/titanic-project-example", 14): ("str_of_missing_sentinel", V, "str(x)[0] of a missing value gives 'N' instead of 'n'"),
    ("fireducks", "kmader/analyzing-matches", 12): ("printed_form_comparison", V, "list of frames compared as text; the frames are E2"),
    ("fireducks", "luckygemini/notebook5d5fc80c9f", 6): ("nested_list_as_array", V, "str.split returns arrays instead of lists"),
    ("fireducks", "maxiaoyue/data-cleaning-challenge-handling-missing-values", 0): ("read_csv_none_as_na", V, "the text 'None' stays a string"),
    ("fireducks", "maxiaoyue/data-cleaning-challenge-handling-missing-values", 22): ("fill_value_coerced", L, "fillna(0) on a string column stores the fill value with another encoding"),
    ("fireducks", "maxiaoyue/data-cleaning-challenge-handling-missing-values", 28): ("row_order_ties", L, "sort on a key with ties, then order-dependent bfill/ffill"),
    ("fireducks", "nadare/feature-engenieering-with-pivot-table", 16): ("float32_promoted", V, "float32 computation returned as float64"),
    ("fireducks", "nandhuelan/ott-platforms", 11): ("nested_list_as_array", L, "list-valued columns from str.split"),
    ("fireducks", "nihhaar/etltransform", 4): ("float_rounding_amplified", V, "round(mean, 3) differs by one in the last digit"),
    ("fireducks", "paramarthasengupta/plotly-eda-top-movies-of-20th-century", 10): ("row_order_ties", V, "sort on a key with ties, then the first 20 rows"),
    ("fireducks", "paramarthasengupta/plotly-eda-top-movies-of-20th-century", 13): ("row_order_ties", V, "sort on tied counts, then the first 10 rows"),
    ("fireducks", "paramarthasengupta/plotly-eda-top-movies-of-20th-century", 18): ("unique_nunique_missing", L, "a per-group nunique differs (plus tied order in the top rows)"),
    ("fireducks", "paramarthasengupta/plotly-eda-top-movies-of-20th-century", 20): ("row_order_ties", V, "tied counts decide which 10 directors are kept"),
    ("fireducks", "paramarthasengupta/plotly-eda-top-movies-of-20th-century", 24): ("row_order_ties", V, "sort on tied counts, then the first 10 rows"),
    ("fireducks", "sal001/beginner-s-note-top-12-by-single-linear-model", 1): ("read_csv_none_as_na", V, "the text 'None' stays a string"),
    ("fireducks", "saniaks/melbourne-house-price-eda", 31): ("corr_infinite_values", V, "a column with infinite values gives a NaN row where pandas returns finite correlations"),
    ("fireducks", "shivavashishtha/zomato-eda-tutorial", 69): ("nested_list_as_array", L, "list-valued column from str.split"),
    ("fireducks", "shunjiangxu/blood-is-thicker-than-water-friendship-forever", 1): ("printed_form_comparison", V, "list of frames compared as text"),
    ("fireducks", "sudheer259/house-price-prediction", 2): ("read_csv_none_as_na", V, "the text 'None' stays a string"),
    ("fireducks", "sudheer259/house-price-prediction", 127): ("read_csv_none_as_na", V, "the text 'None' stays a string"),
    ("fireducks", "sunnybiswas/eda-on-airline-dataset", 17): ("row_order_ties", V, "value_counts with tied counts, then head(20)"),
    ("fireducks", "vbmokin/automatic-eda-with-pandas-profiling-2-9-09-2020", 7): ("groupby_median_other_value", V, "group median differs from both the median and the mean of the group recomputed from the reference input"),
    ("fireducks", "willkoehrsen/start-here-a-gentle-introduction", 10): ("unique_nunique_missing", V, "nunique() is one higher for columns with missing values"),
    ("fireducks", "xokent/cyber-security-attack-eda", 5): ("describe_datetime_numeric", V, "describe() leaves out the datetime column"),
    ("modin", "balajivenkat96/solar-plants", 21): ("printed_form_comparison", L, "dict of Series compared as text"),
    ("modin", "charulatashelar/indian-startup-funding-exploratory-data-analysis", 9): ("loc_setitem_inplace", V, "loc[:, col] = to_datetime(...) gives datetime64 where pandas keeps object"),
    ("modin", "chinstan/notebook249b4f3f5b", 2): ("partitioned_type_inference", L, "mixed-type object column parsed differently"),
    ("modin", "dbatao/kernel2f80fc9d78", 22): ("concat_sort_ignored", V, "concat(sort=True) keeps the original column order"),
    ("modin", "guyalmog/hr-analytics-predicting-employees-attrition", 6): ("float_rounding_amplified", L, "round(mean(axis=1), 2) differs in the last digit"),
    ("modin", "j0thu777/onlineretailanalysis", 20): ("printed_form_comparison", V, "a bound method (not called) stored as values, compared as text"),
    ("modin", "j0thu777/onlineretailanalysis", 27): ("float_rounding_within_tolerance", V, "group means differ in the last digits"),
    ("modin", "jirakst/book-recommendation", 2): ("partitioned_type_inference", L, "mixed-type object column parsed differently"),
    ("modin", "loveall/favorita-analytics", 5): ("float_rounding_within_tolerance", V, "group sums differ in the last digits"),
    ("modin", "loveall/favorita-analytics", 10): ("float_rounding_within_tolerance", V, "group sums differ in the last digits"),
    ("modin", "luizep/movieslens20m", 13): ("get_dummies_sep_ignored", V, "str.get_dummies yields one column per distinct string instead of per separated token"),
    ("modin", "nihhaar/etltransform", 4): ("float_rounding_amplified", V, "round(mean, 3) differs by one in the last digit"),
    ("modin", "nihhaar/etltransform", 7): ("undetermined", U, "group-by on pd.cut bins returns smaller sums; not resolved"),
    ("modin", "shivavashishtha/zomato-eda-tutorial", 33): ("apply_side_effects_lost", V, "apply() extends a global list in workers; the driver's list keeps 5 of the reference's elements"),
    ("modin", "shivavashishtha/zomato-eda-tutorial", 39): ("apply_side_effects_lost", V, "same pattern; 8 elements remain"),
    ("modin", "yonelanuba/elo-merchant-by-yonela", 25): ("concat_unnamed_labels", V, "concat of two unnamed Series yields duplicate labels after rename"),
    ("modin", "yonelanuba/elo-merchant-by-yonela", 75): ("apply_side_effects_lost", V, "a function passed to apply mutates list elements; the mutation is lost"),
    ("modin", "yonelanuba/elo-merchant-by-yonela", 80): ("apply_side_effects_lost", V, "same function on the test frame"),
    ("p15", "xokent/cyber-security-attack-eda", 7): ("melt_category_dtype", V, "melt keeps a categorical variable column under pandas 1.5.3"),
    ("pyarrow_backend", "blaskowitz100/feature-engineering-based-on-the-suprise-me", 1): ("printed_form_comparison", V, "dict of frames compared as text"),
    ("pyarrow_backend", "chinstan/notebook249b4f3f5b", 7): ("arrow_backed_dtypes", L, "describe() covers fewer columns: all-missing columns get a non-numeric Arrow type"),
    ("pyarrow_backend", "ersinsen/fraud-3-eda", 17): ("str_of_missing_sentinel", V, "str(x) of a missing value gives '<NA>' instead of 'nan'"),
    ("pyarrow_backend", "grudd0/mass-shooting-analysis", 43): ("str_of_missing_sentinel", L, "astype(str) of missing values in a concatenated text column"),
    ("pyarrow_backend", "jackwatson99/pima-indians-diabetes-rf-81", 6): ("arrow_int_keeps_type", V, "replace(0, mean) keeps int64[pyarrow] and truncates the mean"),
    ("pyarrow_backend", "kenjee/titanic-project-example", 14): ("str_of_missing_sentinel", V, "str(x)[0] of a missing value gives '<' instead of 'n'"),
    ("pyarrow_backend", "kmader/analyzing-matches", 12): ("printed_form_comparison", V, "list of frames compared as text; the frames are E2"),
    ("pyarrow_backend", "luizep/movieslens20m", 10): ("biased_skew", V, "same value as Bodo and Dask; ratio 1 + 1.5/n"),
    ("pyarrow_backend", "maxiaoyue/data-cleaning-challenge-handling-missing-values", 28): ("row_order_ties", L, "sort on a key with ties, then order-dependent bfill/ffill"),
    ("pyarrow_backend", "paramarthasengupta/plotly-eda-top-movies-of-20th-century", 10): ("row_order_ties", V, "sort on a key with ties, then the first 20 rows"),
    ("pyarrow_backend", "penny8/my-sub1", 19): ("printed_form_comparison", V, "list of Series compared as text; float formatting and dtype names differ"),
    ("pyarrow_backend", "penny8/my-sub1", 20): ("printed_form_comparison", V, "list of Series compared as text"),
    ("pyarrow_backend", "pmr3508f20977e697/poverty-level-pmr3508-2018-f20977e697", 4): ("str_dtype_object_checks", L, "select_dtypes('float') finds fewer columns because integral columns with missing values stay integer-typed"),
    ("pyarrow_backend", "salmaneunus/student-s-performance-quantitative-visual-eda", 16): ("printed_form_comparison", V, "list holding a Series compared as text; dtype names differ"),
    ("pyarrow_backend", "salmaneunus/student-s-performance-quantitative-visual-eda", 30): ("biased_skew", V, "agg 'skew' ratio 1 + 1.5/n"),
    ("pyarrow_backend", "shunjiangxu/blood-is-thicker-than-water-friendship-forever", 1): ("printed_form_comparison", V, "list of frames compared as text"),
    ("pyarrow_backend", "sudheer259/house-price-prediction", 9): ("arrow_int_keeps_type", V, "fillna(mean) on an integer-typed Arrow column truncates the mean"),
    ("pyarrow_backend", "sudheer259/house-price-prediction", 130): ("arrow_int_keeps_type", V, "fillna(mean) on integer-typed Arrow columns truncates the means"),
    ("pyarrow_backend", "sunnybiswas/eda-on-airline-dataset", 17): ("row_order_ties", V, "value_counts with tied counts, then head(20)"),
    ("pyarrow_backend", "taylorhickem/singapore-building-energy", 3): ("printed_form_comparison", V, "dict holding frames compared as text"),
    ("pyarrow_backend", "wyl4417/machine-learning-and-how-it-affects-you", 6): ("arrow_dtype_errors", L, "pivot_table with a lambda aggregate raises KeyError on Arrow-typed data"),
    ("pyarrow_backend", "wyl4417/machine-learning-and-how-it-affects-you", 14): ("arrow_dtype_errors", L, "same pattern"),
    ("pyarrow_backend", "xingobar/computer-science-data-visualization", 9): ("arrow_nan_not_null", V, "to_numeric(errors='coerce') leaves NaN that fillna(0) does not fill"),
}


def main():
    tax = json.load(open(os.path.join(PROJ, "results", "rootcause", "taxonomy_conf1x.json")))
    cells = tax["causes"]["unattributed"]["cells"]
    keys = {(lab, nb, i): (camp, cls) for camp, lab, nb, i, cls in cells}
    missing = sorted(set(keys) - set(H))
    extra = sorted(set(H) - set(keys))
    if missing or extra:
        raise SystemExit("attribution table does not match the unattributed cells: missing %s extra %s" % (missing, extra))
    rows = []
    for k, (cause, conf, ev) in sorted(H.items()):
        assert cause in CAUSES, cause
        camp, cls = keys[k]
        rows.append({"campaign": camp, "label": k[0], "nb": k[1], "cell": k[2], "cls": cls, "cause": cause,
                     "mechanism": CAUSES[cause][1], "confidence": conf, "evidence": ev})
    by = lambda f: dict(collections.Counter(f(r) for r in rows).most_common())
    out = {"method": __doc__.split("Method.")[1].strip(), "cells": len(rows),
           "by_class": by(lambda r: r["cls"]), "by_confidence": by(lambda r: r["confidence"]),
           "by_mechanism": by(lambda r: r["mechanism"]), "by_cause": by(lambda r: r["cause"]),
           "DIFF_by_mechanism": dict(collections.Counter(r["mechanism"] for r in rows if r["cls"] == "DIFF").most_common()),
           "by_label_mechanism": {lab: dict(collections.Counter(r["mechanism"] for r in rows if r["label"] == lab))
                                  for lab in sorted({r["label"] for r in rows})},
           "causes": {k: {"title": v[0], "mechanism": v[1], "cells": sum(1 for r in rows if r["cause"] == k),
                          "labels": dict(collections.Counter(r["label"] for r in rows if r["cause"] == k))}
                      for k, v in CAUSES.items() if any(r["cause"] == k for r in rows)},
           "rows": rows}
    with open(OUT + ".tmp", "w") as f:
        json.dump(out, f, indent=1)
    os.replace(OUT + ".tmp", OUT)
    print(json.dumps({k: out[k] for k in ("cells", "by_class", "by_confidence", "by_mechanism", "DIFF_by_mechanism")}, indent=1))
    print(json.dumps(out["by_cause"], indent=0))


if __name__ == "__main__":
    main()

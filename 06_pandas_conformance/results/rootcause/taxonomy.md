# Root-cause taxonomy (plan Section 8, Table 1)

Generated 2026-10-04T01:08:25 by `scripts/rootcause_taxonomy.py` (harness hd1c421ecb5ee, compare d92c8db54d45b). Rerun: `../.venv/bin/python scripts/rootcause_taxonomy.py build`.

**Sources.**
- `drift` (drift: 102 notebooks): labels p15, p30, ref#2; outputs used {"p15": 102, "p30": 102, "ref#2": 102}.
- `pilot` (PILOT: 10 notebooks only (data/notebook_sets/pilot.json); not a claim): labels pyarrow_backend, modin, fireducks, bodo, bodo_dw, dask, modin#2~vs~modin, fireducks#2~vs~fireducks, bodo#2~vs~bodo, dask#2~vs~dask; outputs used {"bodo": 10, "bodo#2~vs~bodo": 10, "bodo_dw": 10, "dask": 10, "dask#2~vs~dask": 10, "fireducks": 10, "fireducks#2~vs~fireducks": 10, "modin": 10, "modin#2~vs~modin": 10, "pyarrow_backend": 10}.

**Unit.** introduced divergence: non-E0 cell whose class is coarser than the level at which its inputs were equal (classify.clean_level); one cause per cell, first matching rule. Cells whose divergence is inherited from an earlier cell are `propagated` and are not attributed again. Pilot rows describe 10 notebooks and are a pilot, not a claim.

**Counts.** 4351 non-E0 cells; by kind {"introduced": 819, "propagated": 3053, "harness": 73, "cascade": 376, "nondet": 30}.

**How causes were assigned.** Ordered rules over the comparator's first failing check per level, the exception type and message, and the cell code (plus the bodies of user functions the cell calls); 18 hand-inspected cells are fixed in `CURATED` with the decoded values as evidence. Every rule is listed in taxonomy.json (`rules`); each example below names the rule that fired. Rules are heuristics: counts are per introduced cell, one cause per cell.

**How documentation was verified (2026-10-04).** Every URL was fetched with WebFetch and the quoted sentence was found on the page. For the long pandas release notes (v2.0.0, v3.0.0) WebFetch returns a truncated page, so the quotes were also checked by a full-text search of the downloaded HTML. `documented: no` means no statement was found in the engine's or pandas' documentation by these searches; it is not proof of absence.

**Limitations.** Engine reproducers were written but not run (they start Ray, MPI or thread pools); they are listed in `probes_todo.json` for a guarded probes campaign. The Bodo part of `approximate_quantile` is a hypothesis from the cell code (quantile/percentile thresholds) until its probe runs. Engine rows come from the 10-notebook pilot; rerun with `--preset conf1x` once conf_1x compare is complete.

## Table 1 (root causes; counts are introduced cells)

| cause | severity | documented | cells | strict-clean | notebooks | engines (cells) | example (engine nb cell) | reproducer |
|---|---|---|---|---|---|---|---|---|
| `str_default_dtype` | representation_only | yes: https://pandas.pydata.org/docs/whatsnew/v3.0.0.html, https://pandas.pydata.org/docs/user_guide/migration-3-strings.html | 157 | 143 | 99 | p3.0 157 | p30 akgauravin/gun-violence-data-exploration-and-plotting c2 | repro/str_default_dtype.py |
| `value_counts_naming` | representation_only | yes: https://pandas.pydata.org/docs/whatsnew/v2.0.0.html | 127 | 91 | 36 | p1.5 127 | p15 akshaypetkar/supermarket-sales-analysis c8 | repro/value_counts_naming.py |
| `float_rounding_within_tolerance` | silent_value_change | partial: https://modin.readthedocs.io/en/latest/supported_apis/dataframe_supported.html | 96 | 93 | 43 | p1.5 79, FD 9, Mo 8 | p15 akgauravin/gun-violence-data-exploration-and-plotting c6 | repro/float_rounding_within_tolerance.py |
| `arrow_backed_dtypes` | representation_only | partial: https://pandas.pydata.org/docs/user_guide/pyarrow.html, https://github.com/dask/dask/pull/10400 | 44 | 36 | 10 | PA 14, Bo 13, BoD 13, Da 4 | bodo corazzon/how-to-use-pandas-filter-in-survey-eda c2 | repro/arrow_backed_dtypes.py |
| `engine_bug_error` | error | partial: https://fireducks-dev.github.io/docs/user-guide/04-compatibility/ | 36 | 5 | 6 | BoD 15, Bo 13, Mo 7, FD 1 | bodo corazzon/how-to-use-pandas-filter-in-survey-eda c56 | repro/engine_bug_error.py |
| `engine_unsupported_api` | error | partial: https://docs.dask.org/en/stable/dataframe-indexing.html | 34 | 1 | 9 | Da 26, Bo 4, BoD 3, FD 1 | bodo kimtaehun/simple-preprocessing-for-time-series-prediction c8 | repro/engine_unsupported_api.py |
| `str_dtype_object_checks` | silent_value_change | yes: https://pandas.pydata.org/docs/user_guide/migration-3-strings.html | 33 | 0 | 7 | p3.0 12, PA 6, Bo 5, BoD 5, Da 5 | p30 arjoonn/scout-script-7 c5 | repro/str_dtype_object_checks.py |
| `nondeterminism` | excluded | no | 30 | 19 | 8 | ref 14, dask#2 6, modin#2 6, bodo#2 3, fireducks#2 1 | ref#2 drainvers/instacart-sandbox-lmf c14 |  |
| `index_not_preserved` | representation_only | no | 30 | 3 | 7 | Bo 12, BoD 11, FD 5, Da 1, Mo 1 | bodo corazzon/how-to-use-pandas-filter-in-survey-eda c13 | repro/index_not_preserved.py |
| `cow_chained_assignment` | silent_value_change | yes: https://pandas.pydata.org/docs/user_guide/copy_on_write.html, https://pandas.pydata.org/docs/whatsnew/v3.0.0.html | 20 | 0 | 15 | p3.0 19, FD 1 | p30 arjoonn/scout-script-7 c9 | repro/cow_chained_assignment.py |
| `int_float_nullable_repr` | representation_only | no | 20 | 20 | 5 | Mo 14, FD 6 | fireducks sabya40/data-cleaning-and-pandas-for-beginners c13 | repro/int_float_nullable_repr.py |
| `row_order_ties` | silent_value_change | partial: https://modin.readthedocs.io/en/latest/supported_apis/dataframe_supported.html, https://fireducks-dev.github.io/docs/user-guide/04-compatibility/ | 18 | 7 | 10 | p3.0 6, Mo 5, FD 3, Bo 2, BoD 2 | p30 carlmcbrideellis/simple-eda-of-kaggle-grandmasters-scheduled c5 | repro/row_order_ties.py |
| `offset_alias_removed` | error | yes: https://pandas.pydata.org/docs/whatsnew/v3.0.0.html | 18 | 2 | 4 | p3.0 18 | p30 grudd0/mass-shooting-analysis c3 | repro/offset_alias_removed.py |
| `numeric_dtype_preservation` | representation_only | yes: https://pandas.pydata.org/docs/whatsnew/v2.0.0.html | 17 | 17 | 12 | p1.5 17 | p15 akshaypetkar/supermarket-sales-analysis c15 | repro/numeric_dtype_preservation.py |
| `lazy_partition_model` | error | yes: https://docs.dask.org/en/stable/dataframe-indexing.html | 17 | 2 | 7 | Da 17 | dask corazzon/how-to-use-pandas-filter-in-survey-eda c2 | repro/lazy_partition_model.py |
| `removed_deprecated_api` | error | yes: https://pandas.pydata.org/docs/whatsnew/v3.0.0.html, https://pandas.pydata.org/docs/whatsnew/v2.1.0.html, https://pandas.pydata.org/docs/whatsnew/v2.0.0.html | 15 | 0 | 8 | p3.0 15 | p30 guyalmog/hr-analytics-predicting-employees-attrition c6 | repro/removed_deprecated_api.py |
| `approximate_quantile` | silent_value_change | partial: https://docs.dask.org/en/stable/generated/dask.dataframe.Series.quantile.html | 15 | 0 | 3 | Bo 5, BoD 5, Da 5 | bodo deffro/eda-is-fun c12 | repro/approximate_quantile.py |
| `engine_bug_silent` | silent_value_change | no | 15 | 3 | 4 | BoD 7, Bo 6, Mo 2 | bodo deffro/eda-is-fun c40 | repro/engine_bug_silent.py |
| `get_dummies_bool` | representation_only | yes: https://pandas.pydata.org/docs/whatsnew/v2.0.0.html | 14 | 12 | 12 | p1.5 14 | p15 dbatao/kernel2f80fc9d78 c48 | repro/get_dummies_bool.py |
| `arrow_dtype_errors` | error | partial: https://pandas.pydata.org/docs/user_guide/missing_data.html | 11 | 1 | 4 | PA 5, Bo 2, BoD 2, FD 2 | bodo deffro/eda-is-fun c6 | repro/arrow_dtype_errors.py |
| `read_csv_none_as_na` | silent_value_change | yes: https://pandas.pydata.org/docs/whatsnew/v2.0.0.html | 10 | 10 | 9 | p1.5 10 | p15 ashukr/first-step-ingestion-to-prediction c1 | repro/read_csv_none_as_na.py |
| `merge_row_order` | silent_value_change | yes: https://pandas.pydata.org/docs/whatsnew/v2.2.0.html | 9 | 8 | 7 | p1.5 9 | p15 blaskowitz100/feature-engineering-based-on-the-suprise-me c2 | repro/merge_row_order.py |
| `missing_sentinel_repr` | representation_only | no | 9 | 9 | 5 | FD 9 | fireducks corazzon/how-to-use-pandas-filter-in-survey-eda c3 | repro/missing_sentinel_repr.py |
| `datetime_resolution_inference` | silent_value_change | yes: https://pandas.pydata.org/docs/whatsnew/v3.0.0.html | 8 | 0 | 4 | p3.0 8 | p30 j0thu777/onlineretailanalysis c20 | repro/datetime_resolution_inference.py |
| `int_key_positional_fallback_removed` | error | yes: https://pandas.pydata.org/docs/whatsnew/v3.0.0.html | 7 | 0 | 4 | p3.0 7 | p30 corazzon/how-to-use-pandas-filter-in-survey-eda c21 | repro/int_key_positional_fallback_removed.py |
| `axis_names_lost` | representation_only | no | 7 | 3 | 2 | Mo 3, Bo 2, BoD 2 | bodo corazzon/how-to-use-pandas-filter-in-survey-eda c11 | repro/axis_names_lost.py |
| `partitioned_type_inference` | error | partial: https://docs.dask.org/en/stable/generated/dask.dataframe.read_csv.html | 5 | 5 | 4 | Da 4, Mo 1 | dask kanncaa1/dataiteam-titanic-eda c1 | repro/partitioned_type_inference.py |
| `describe_datetime_numeric` | silent_value_change | yes: https://pandas.pydata.org/docs/whatsnew/v2.0.0.html | 4 | 4 | 2 | p1.5 4 | p15 xokent/cyber-security-attack-eda c5 | repro/describe_datetime_numeric.py |
| `setitem_incompatible_dtype_raises` | error | yes: https://pandas.pydata.org/docs/whatsnew/v3.0.0.html, https://pandas.pydata.org/docs/whatsnew/v2.1.0.html | 3 | 1 | 3 | p3.0 3 | p30 blaskowitz100/feature-engineering-based-on-the-suprise-me c11 | repro/setitem_incompatible_dtype_raises.py |
| `str_dtype_na_semantics` | silent_value_change | partial: https://pandas.pydata.org/docs/user_guide/migration-3-strings.html | 3 | 0 | 3 | p3.0 3 | p30 grudd0/mass-shooting-analysis c43 | repro/str_dtype_na_semantics.py |
| `str_dtype_errors` | error | yes: https://pandas.pydata.org/docs/user_guide/migration-3-strings.html | 2 | 1 | 2 | p3.0 2 | p30 dbatao/kernel2f80fc9d78 c28 | repro/str_dtype_errors.py |
| `engine_corr_wrong_values` | silent_value_change | no | 2 | 2 | 1 | Mo 2 | modin deffro/eda-is-fun c30 | repro/engine_corr_wrong_values.py |
| `api_added_later` | error | yes: https://pandas.pydata.org/docs/whatsnew/v2.0.0.html | 1 | 1 | 1 | p1.5 1 | p15 balajivenkat96/solar-plants c1 | repro/api_added_later.py |
| `str_replace_regex_default` | silent_value_change | yes: https://pandas.pydata.org/docs/whatsnew/v2.0.0.html | 1 | 1 | 1 | p1.5 1 | p15 brianmendieta/data-cleaning-plus-eda c14 | repro/str_replace_regex_default.py |
| `loc_setitem_inplace` | representation_only | yes: https://pandas.pydata.org/docs/whatsnew/v2.0.0.html | 1 | 1 | 1 | p1.5 1 | p15 charulatashelar/indian-startup-funding-exploratory-data-analysis c9 | repro/loc_setitem_inplace.py |
| `numeric_only_default` | silent_value_change | yes: https://pandas.pydata.org/docs/whatsnew/v2.0.0.html | 1 | 0 | 1 | p1.5 1 | p15 sabya40/data-cleaning-and-pandas-for-beginners c16 | repro/numeric_only_default.py |
| `to_datetime_consistent_format` | silent_value_change | yes: https://pandas.pydata.org/docs/whatsnew/v2.0.0.html | 1 | 1 | 1 | p1.5 1 | p15 ukveteran/sarima-time-series-eda-predict-jma-sao-paulo c4 | repro/to_datetime_consistent_format.py |
| `read_csv_big_int_python_ints` | silent_value_change | partial: https://pandas.pydata.org/docs/whatsnew/v3.0.0.html | 1 | 1 | 1 | p3.0 1 | p30 chinstan/notebook249b4f3f5b c2 | repro/read_csv_big_int_python_ints.py |
| `p3_stricter_validation` | error | no | 1 | 0 | 1 | p3.0 1 | p30 saniaks/melbourne-house-price-eda c26 | repro/p3_stricter_validation.py |

Not root causes (reported separately):

| category | cells | notebooks | engines |
|---|---|---|---|
| `cascade_undefined_name`: NameError/UnboundLocalError after an earlier cell failed (cascade) | 339 | 18 | Da 120, p3.0 103, Bo 27, BoD 27, p1.5 24, PA 20, FD 16, Mo 2 |
| `capture_cap`: output above the capture cap (hash only): UNCOMPARABLE | 73 | 15 | dask#2 29, p1.5 15, p3.0 15, fireducks#2 10, Bo 1, BoD 1, FD 1, PA 1 |
| `resource_memory_cap`: notebook stopped at the 96 GB per-notebook memory cap (MEMORY) and cells after it (NOTRUN) | 37 | 1 | Mo 37 |
| `order_propagated`: DIFF in a cell whose inputs differ only in row order or index (E1/E4): head()/[:n]/lists expose the earlier order difference; attributed to the cell that reordered | 22 | 3 | p1.5 15, FD 3, p3.0 2, Bo 1, BoD 1 |
| `unattributed`: unattributed | 6 | 4 | Mo 4, p1.5 1, PA 1 |
| `propagated`: class not coarser than the input level: divergence inherited from an earlier cell | 3053 | | |

## Per engine (non-E0 cells by kind)

| campaign:engine | introduced | propagated | cascade | harness | nondet | unattributed |
|---|---|---|---|---|---|---|
| drift:p15 | 266 | 537 | 24 | 15 | 0 | 1 |
| drift:p30 | 252 | 1650 | 103 | 15 | 0 | 0 |
| drift:ref#2 | 0 | 0 | 0 | 0 | 14 | 0 |
| pilot:bodo | 64 | 192 | 27 | 1 | 0 | 0 |
| pilot:bodo#2~vs~bodo | 0 | 0 | 0 | 0 | 3 | 0 |
| pilot:bodo_dw | 65 | 191 | 27 | 1 | 0 | 0 |
| pilot:dask | 62 | 156 | 120 | 0 | 0 | 0 |
| pilot:dask#2~vs~dask | 0 | 0 | 0 | 29 | 6 | 0 |
| pilot:fireducks | 37 | 96 | 16 | 1 | 0 | 0 |
| pilot:fireducks#2~vs~fireducks | 0 | 0 | 0 | 10 | 1 | 0 |
| pilot:modin | 47 | 33 | 39 | 0 | 0 | 4 |
| pilot:modin#2~vs~modin | 0 | 0 | 0 | 0 | 6 | 0 |
| pilot:pyarrow_backend | 26 | 198 | 20 | 1 | 0 | 1 |

## Causes in detail

### `str_default_dtype` (representation_only)

pandas 3 default `str` dtype replaces object for text (dtype strings, `.dtypes`/repr output).

- Cells 157 (strict-clean 143), notebooks 99, by class {"E2": 143, "DIFF": 11, "E3": 2, "E4": 1}; observed severity per cell {"equal_at_E1_to_E4": 146, "DIFF_not_equal_at_E4": 11}.
- Engines: {"drift:p30": 157}.
- Documented: <https://pandas.pydata.org/docs/whatsnew/v3.0.0.html> ("Dedicated string data type by default").
- Documented: <https://pandas.pydata.org/docs/user_guide/migration-3-strings.html> ("migration guide for the new string data type").
- Example: p30 `akgauravin/gun-violence-data-exploration-and-plotting` cell 2, E2 (inputs equal at E0), check `labels_dtype:object/str`.
- Example: p30 `akshaypetkar/supermarket-sales-analysis` cell 2, E2 (inputs equal at E0), check `labels_dtype:object/str`.
- Example: p30 `arimishabirin/globalsalary-simple-eda` cell 3, E2 (inputs equal at E0), check `labels_dtype:object/str`.
- Example: p30 `arjoonn/scout-script-7` cell 2, E2 (inputs equal at E0), check `labels_dtype:object/str`.
- Reproducer `results/rootcause/repro/str_default_dtype.py`, run in pandas environments (differs from ref: {"p15": false, "p30": true, "pyarrow_backend": true}):
  - p15: rc 0, 0.27 s, max RSS 93 MB: `env: mode=pandas pandas=1.5.3 ; column dtype: object ; dtypes as values: ['object', 'int64'] ; unique() type: ndarray`
  - p30: rc 0, 0.27 s, max RSS 99 MB: `env: mode=pandas pandas=3.0.6 ; column dtype: str ; dtypes as values: ['str', 'int64'] ; unique() type: ArrowStringArray`
  - pyarrow_backend: rc 0, 0.29 s, max RSS 100 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; column dtype: string[pyarrow] ; dtypes as values: ['string[pyarrow]', 'int64[pyarrow]'] ; unique() type: ArrowExtensionArray`
  - ref: rc 0, 0.28 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; column dtype: object ; dtypes as values: ['object', 'int64'] ; unique() type: ndarray`

### `value_counts_naming` (representation_only)

pandas 2.0: value_counts result is named 'count'/'proportion' and its index carries the column name (renames/reset_index then produce different labels).

- Cells 127 (strict-clean 91), notebooks 36, by class {"E4": 120, "DIFF": 7}; observed severity per cell {"equal_at_E1_to_E4": 120, "DIFF_not_equal_at_E4": 7}.
- Engines: {"drift:p15": 127}.
- Documented: <https://pandas.pydata.org/docs/whatsnew/v2.0.0.html> ("Value counts sets the resulting name to count").
- Example: p15 `akshaypetkar/supermarket-sales-analysis` cell 8, E4 (inputs equal at E0), check `names:series_name`.
- Example: p15 `arjoonn/scout-script-7` cell 4, E4 (inputs equal at E0), check `names:series_name`.
- Example: p15 `atultaur/house-sales-in-king-county` cell 30, E4 (inputs equal at E0), check `names:series_name`.
- Example: p15 `beratozmen/clash-of-clans-exploratory-data-analysis` cell 7, DIFF (inputs equal at E0), check `values:col0:row=1`.
- Reproducer `results/rootcause/repro/value_counts_naming.py`, run in pandas environments (differs from ref: {"p15": true, "p30": false, "pyarrow_backend": false}):
  - p15: rc 0, 0.27 s, max RSS 93 MB: `env: mode=pandas pandas=1.5.3 ; value_counts name / index name: ('col', None) ; to_frame().reset_index() columns: ['index', 'col'] ; normalize=True name: col`
  - p30: rc 0, 0.28 s, max RSS 99 MB: `env: mode=pandas pandas=3.0.6 ; value_counts name / index name: ('count', 'col') ; to_frame().reset_index() columns: ['col', 'count'] ; normalize=True name: proportion`
  - pyarrow_backend: rc 0, 0.28 s, max RSS 98 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; value_counts name / index name: ('count', 'col') ; to_frame().reset_index() columns: ['col', 'count'] ; normalize=True name: proportion`
  - ref: rc 0, 0.28 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; value_counts name / index name: ('count', 'col') ; to_frame().reset_index() columns: ['col', 'count'] ; normalize=True name: proportion`

### `float_rounding_within_tolerance` (silent_value_change)

last-ulp float differences within the 1e-9 tolerance (read_csv float parsing in pandas 1.5, corr/describe/mean summation order in parallel engines).

- Cells 96 (strict-clean 93), notebooks 43, by class {"E2": 93, "DIFF": 3}; observed severity per cell {"equal_at_E1_to_E4": 93, "DIFF_not_equal_at_E4": 3}.
- Engines: {"drift:p15": 79, "pilot:fireducks": 9, "pilot:modin": 8}.
- Documented: <https://modin.readthedocs.io/en/latest/supported_apis/dataframe_supported.html> ("Correlation floating point precision may slightly differ from pandas").
- Note: documented for Modin corr only; pandas 1.5 vs 2.x parsing and FireDucks/Bodo summation not found.
- Example: p15 `akgauravin/gun-violence-data-exploration-and-plotting` cell 6, E2 (inputs equal at E0), check `values:col1:row=2`.
- Example: p15 `ashukr/first-step-ingestion-to-prediction` cell 14, E2 (inputs equal at E0), check `values:col0:row=0`.
- Example: p15 `atultaur/house-sales-in-king-county` cell 4, E2 (inputs equal at E0), check `values:col1:row=16`.
- Example: p15 `balajivenkat96/solar-plants` cell 22, E2 (inputs equal at E0), check `values:col2:row=7`.
- Reproducer `results/rootcause/repro/float_rounding_within_tolerance.py`, run in pandas environments (differs from ref: {"p15": true, "p30": false, "pyarrow_backend": false}):
  - p15: rc 0, 0.28 s, max RSS 104 MB: `env: mode=pandas pandas=1.5.3 ; parsed floats (repr): ['24.87302233333333', '25.005149333333332', '-73.9821548461914'] ; exact round trip vs float(): [False, False, True] ; corr a,b (repr): {'a': {'a'`
  - p30: rc 0, 0.28 s, max RSS 107 MB: `env: mode=pandas pandas=3.0.6 ; parsed floats (repr): ['24.873022333333335', '25.005149333333335', '-73.9821548461914'] ; exact round trip vs float(): [True, True, True] ; corr a,b (repr): {'a': {'a':`
  - pyarrow_backend: rc 0, 0.29 s, max RSS 106 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; parsed floats (repr): ['24.873022333333335', '25.005149333333335', '-73.9821548461914'] ; exact round trip vs float(): [True, True, True] ; corr a,b (repr): {'`
  - ref: rc 0, 0.28 s, max RSS 104 MB: `env: mode=pandas pandas=2.3.3 ; parsed floats (repr): ['24.873022333333335', '25.005149333333335', '-73.9821548461914'] ; exact round trip vs float(): [True, True, True] ; corr a,b (repr): {'a': {'a':`
- Engine reproducer pending for modin, fireducks: listed in `results/rootcause/probes_todo.json` (not run: starts worker pools).

### `arrow_backed_dtypes` (representation_only)

engine returns pyarrow-backed dtypes (string[pyarrow], large_string, int64[pyarrow], double[pyarrow]) with pd.NA where pandas returns numpy/object dtypes.

- Cells 44 (strict-clean 36), notebooks 10, by class {"E3": 24, "E4": 5, "E2": 15}; observed severity per cell {"equal_at_E1_to_E4": 44}.
- Engines: {"pilot:bodo": 13, "pilot:bodo_dw": 13, "pilot:dask": 4, "pilot:pyarrow_backend": 14}.
- Documented: <https://pandas.pydata.org/docs/user_guide/pyarrow.html> ("These readers can return PyArrow-backed data by specifying the parameter dtype_backend="pyarrow"").
- Documented: <https://github.com/dask/dask/pull/10400> ("Convert to pyarrow strings if proper dependencies are installed").
- Note: documented for pandas' dtype_backend and Dask (merged PR); Bodo's arrow dtypes not found in its docs.
- Example: bodo `corazzon/how-to-use-pandas-filter-in-survey-eda` cell 2, E3 (inputs equal at E0), check `sentinel:col4:row=132:2/3`.
- Example: bodo `deffro/eda-is-fun` cell 2, E3 (inputs equal at E0), check `sentinel:col28:row=2744604:2/3`.
- Example: bodo `kanncaa1/dataiteam-titanic-eda` cell 1, E3 (inputs equal at E0), check `sentinel:col4:row=10:2/3`.
- Example: bodo `kimtaehun/simple-preprocessing-for-time-series-prediction` cell 2, E3 (inputs equal at E0), check `sentinel:col3:row=1827:2/3`.
- Reproducer `results/rootcause/repro/arrow_backed_dtypes.py`, run in pandas environments (differs from ref: {"p15": true, "p30": true, "pyarrow_backend": true}):
  - p15: rc 0, 0.28 s, max RSS 94 MB: `env: mode=pandas pandas=1.5.3 ; dtypes: ['object', 'int64', 'float64'] ; missing sentinels: ['nan', 'nan']`
  - p30: rc 0, 0.27 s, max RSS 99 MB: `env: mode=pandas pandas=3.0.6 ; dtypes: ['str', 'int64', 'float64'] ; missing sentinels: ['nan', 'np.float64(nan)']`
  - pyarrow_backend: rc 0, 0.30 s, max RSS 100 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; dtypes: ['string[pyarrow]', 'int64[pyarrow]', 'double[pyarrow]'] ; missing sentinels: ['<NA>', '<NA>']`
  - ref: rc 0, 0.29 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; dtypes: ['object', 'int64', 'float64'] ; missing sentinels: ['nan', 'np.float64(nan)']`
- Engine reproducer pending for bodo, dask: listed in `results/rootcause/probes_todo.json` (not run: starts worker pools).

### `engine_bug_error` (error)

engine raises where pandas succeeds on supported API (Bodo `_plan`, BodoStringMethods subscript, 'an integer is required'; Modin Series.filter, RayTaskError; FireDucks materialisation errors).

- Cells 36 (strict-clean 5), notebooks 6, by class {"ERR": 36}; observed severity per cell {"error": 36}.
- Engines: {"pilot:bodo": 13, "pilot:bodo_dw": 15, "pilot:fireducks": 1, "pilot:modin": 7}.
- Documented: <https://fireducks-dev.github.io/docs/user-guide/04-compatibility/> ("the timing of errors and warnings in FireDucks is different from that in pandas").
- Note: FireDucks documents deferred error timing only; the errors themselves are undocumented.
- Example: bodo `corazzon/how-to-use-pandas-filter-in-survey-eda` cell 56, ERR (inputs equal at E2), check `builtins.KeyError: 0`.
- Example: bodo `kimtaehun/simple-preprocessing-for-time-series-prediction` cell 9, ERR (inputs equal at E2), check `builtins.AttributeError: 'DataFrame' object has no attribute '_plan'`.
- Example: bodo `sabya40/data-cleaning-and-pandas-for-beginners` cell 16, ERR (inputs equal at E2), check `builtins.AttributeError: 'DataFrame' object has no attribute '_plan'`.
- Example: bodo `trinath003/data-manipulation-visualisation-on-kaggle-datasets` cell 10, ERR (inputs equal at E2), check `builtins.AttributeError: 'DataFrame' object has no attribute '_plan'`.
- Engine reproducer pending for bodo, bodo_dw, modin, fireducks: listed in `results/rootcause/probes_todo.json` (not run: starts worker pools).

### `engine_unsupported_api` (error)

pandas API not implemented by the engine (Dask: inplace=, cut, pivot, crosstab, iloc rows, read_excel; Bodo: infer_datetime_format, groupby key types; FireDucks: groupby sum of strings).

- Cells 34 (strict-clean 1), notebooks 9, by class {"ERR": 34}; observed severity per cell {"error": 34}.
- Engines: {"pilot:bodo": 4, "pilot:bodo_dw": 3, "pilot:dask": 26, "pilot:fireducks": 1}.
- Documented: <https://docs.dask.org/en/stable/dataframe-indexing.html> ("DataFrame.iloc() only supports indexers where the row indexer is slice(None)").
- Note: documented for Dask iloc only; the other gaps were not found in the engines' docs.
- Example: bodo `kimtaehun/simple-preprocessing-for-time-series-prediction` cell 8, ERR (inputs equal at E2), check `bodo.pandas.utils.BodoLibNotImplementedException: from_pandas(): Could not convert DataFrame to Bodo: Unsupported datatype encountered in on`.
- Example: bodo `sabya40/data-cleaning-and-pandas-for-beginners` cell 21, ERR (inputs equal at E2), check `bodo.pandas.utils.BodoLibNotImplementedException: DataFrameGroupBy: Invalid key type: <class 'int'>`.
- Example: bodo `shashi772/data-cleaning-challenge-parsing-dates` cell 6, ERR (inputs equal at E3), check `builtins.TypeError: to_datetime() got an unexpected keyword argument 'infer_datetime_format'`.
- Example: bodo_dw `kimtaehun/simple-preprocessing-for-time-series-prediction` cell 8, ERR (inputs equal at E4), check `bodo.pandas.utils.BodoLibNotImplementedException: from_pandas(): Could not convert DataFrame to Bodo: Unsupported datatype encountered in on`.
- Engine reproducer pending for dask, bodo, fireducks: listed in `results/rootcause/probes_todo.json` (not run: starts worker pools).

### `str_dtype_object_checks` (silent_value_change)

code that selects columns by `dtype == 'object'` / `select_dtypes('object')` / `include='O'` selects different columns when strings are not object dtype.

- Cells 33 (strict-clean 0), notebooks 7, by class {"DIFF": 33}; observed severity per cell {"DIFF_not_equal_at_E4": 33}.
- Engines: {"drift:p30": 12, "pilot:bodo": 5, "pilot:bodo_dw": 5, "pilot:dask": 5, "pilot:pyarrow_backend": 6}.
- Documented: <https://pandas.pydata.org/docs/user_guide/migration-3-strings.html> ("Checking the dtype ... will no longer work in pandas 3+").
- Example: p30 `arjoonn/scout-script-7` cell 5, DIFF (inputs equal at E2), check `values:col0:row=2`.
- Example: p30 `dbatao/kernel2f80fc9d78` cell 30, DIFF (inputs equal at E2), check `shape:[0]/[23]`.
- Example: p30 `kimtaehun/simple-preprocessing-for-time-series-prediction` cell 8, DIFF (inputs equal at E2), check `values:col0:row=0`.
- Example: p30 `saniaks/melbourne-house-price-eda` cell 7, DIFF (inputs equal at E2), check `shape:[8]/[0]`.
- Reproducer `results/rootcause/repro/str_dtype_object_checks.py`, run in pandas environments (differs from ref: {"p15": false, "p30": true, "pyarrow_backend": true}):
  - p15: rc 0, 0.26 s, max RSS 94 MB: `env: mode=pandas pandas=1.5.3 ; cat cols via dtypes == 'object': ['city'] ; num cols via dtype != 'object': ['price', 'rooms'] ; select_dtypes(include='object'): ['city']`
  - p30: rc 0, 0.27 s, max RSS 100 MB: `env: mode=pandas pandas=3.0.6 ; cat cols via dtypes == 'object': [] ; num cols via dtype != 'object': ['city', 'price', 'rooms'] ; select_dtypes(include='object'): ['city']`
  - pyarrow_backend: rc 0, 0.28 s, max RSS 100 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; cat cols via dtypes == 'object': [] ; num cols via dtype != 'object': ['city', 'price', 'rooms'] ; select_dtypes(include='object'): []`
  - ref: rc 0, 0.29 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; cat cols via dtypes == 'object': ['city'] ; num cols via dtype != 'object': ['price', 'rooms'] ; select_dtypes(include='object'): ['city']`
- Engine reproducer pending for bodo, dask: listed in `results/rootcause/probes_todo.json` (not run: starts worker pools).

### `nondeterminism` (excluded)

output differs between two runs of the same configuration (ref vs ref#2 -> NONDET for every engine; engine vs its own replicate).

- Cells 30 (strict-clean 19), notebooks 8, by class {"NONDET": 14, "DIFF": 10, "E4": 1, "E1": 3, "E2": 2}; observed severity per cell {"nondet": 14, "DIFF_not_equal_at_E4": 10, "equal_at_E1_to_E4": 6}.
- Engines: {"drift:ref#2": 14, "pilot:bodo#2~vs~bodo": 3, "pilot:dask#2~vs~dask": 6, "pilot:fireducks#2~vs~fireducks": 1, "pilot:modin#2~vs~modin": 6}.
- Documented: no documentation found (searched 2026-10-04).
- Example: ref#2 `drainvers/instacart-sandbox-lmf` cell 14, NONDET (inputs equal at E0), check `scalar_value`.
- Example: ref#2 `tunguz/fathers-day-specials-just-the-features` cell 11, NONDET (inputs equal at E0), check `capped`.
- Example: bodo#2~vs~bodo `deffro/eda-is-fun` cell 12, DIFF (inputs equal at E0), check `shape:[4400164]/[4404121]`.
- Example: dask#2~vs~dask `corazzon/how-to-use-pandas-filter-in-survey-eda` cell 2, DIFF (inputs equal at E0), check `values:col0:row=0`.

### `index_not_preserved` (representation_only)

engine does not preserve the pandas row index (filters/sort/groupby as_index=False/partition-local RangeIndex).

- Cells 30 (strict-clean 3), notebooks 7, by class {"E4": 28, "DIFF": 2}; observed severity per cell {"equal_at_E1_to_E4": 28, "DIFF_not_equal_at_E4": 2}.
- Engines: {"pilot:bodo": 12, "pilot:bodo_dw": 11, "pilot:dask": 1, "pilot:fireducks": 5, "pilot:modin": 1}.
- Documented: no documentation found (searched 2026-10-04).
- Example: bodo `corazzon/how-to-use-pandas-filter-in-survey-eda` cell 13, E4 (inputs equal at E3), check `index:values:index0:row=0`.
- Example: bodo `deffro/eda-is-fun` cell 8, E4 (inputs equal at E3), check `index:values:index0:row=1`.
- Example: bodo `kanncaa1/dataiteam-titanic-eda` cell 13, E4 (inputs equal at E3), check `index:values:index0:row=0`.
- Example: bodo `roopahegde/cryptocurrency-price-correlation` cell 11, E4 (inputs equal at E2), check `index:values:index0:row=0`.
- Engine reproducer pending for bodo, bodo_dw, fireducks, dask: listed in `results/rootcause/probes_todo.json` (not run: starts worker pools).

### `cow_chained_assignment` (silent_value_change)

Copy-on-Write: chained assignment and inplace methods on a column selection no longer modify the parent.

- Cells 20 (strict-clean 0), notebooks 15, by class {"DIFF": 19, "ERR": 1}; observed severity per cell {"DIFF_not_equal_at_E4": 19, "error": 1}.
- Engines: {"drift:p30": 19, "pilot:fireducks": 1}.
- Documented: <https://pandas.pydata.org/docs/user_guide/copy_on_write.html> ("chained assignment will consistently never work").
- Documented: <https://pandas.pydata.org/docs/whatsnew/v3.0.0.html> ("Consistent copy/view behaviour with Copy-on-Write").
- Example: p30 `arjoonn/scout-script-7` cell 9, DIFF (inputs equal at E2), check `dtype_family:int/str:col5`.
- Example: p30 `ayushsingh5941/tweet-disaster-or-not` cell 9, DIFF (inputs equal at E2), check `missing_mask:col1:row=0`.
- Example: p30 `brianmendieta/data-cleaning-plus-eda` cell 27, DIFF (inputs equal at E2), check `kind:scalar/Series`.
- Example: p30 `ersinsen/fraud-3-eda` cell 21, DIFF (inputs equal at E2), check `missing_mask:col8:row=9686`.
- Reproducer `results/rootcause/repro/cow_chained_assignment.py`, run in pandas environments (differs from ref: {"p15": false, "p30": true, "pyarrow_backend": false}):
  - p15: rc 0, 0.27 s, max RSS 93 MB: `env: mode=pandas pandas=1.5.3 ; df['a'].loc[mask] = 10: [1, 10, 10] ; df['b'].fillna(0, inplace=True): [0.0, 2.0, 0.0] ; df['b'].iloc[0] = -1: [-1.0, 2.0, nan]`
  - p30: rc 0, 0.28 s, max RSS 98 MB: `env: mode=pandas pandas=3.0.6 ; df['a'].loc[mask] = 10: [1, 20, 30] ; df['b'].fillna(0, inplace=True): [nan, 2.0, nan] ; df['b'].iloc[0] = -1: [nan, 2.0, nan]`
  - pyarrow_backend: rc 0, 0.28 s, max RSS 98 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; df['a'].loc[mask] = 10: [1, 10, 10] ; df['b'].fillna(0, inplace=True): [0.0, 2.0, 0.0] ; df['b'].iloc[0] = -1: [-1.0, 2.0, nan]`
  - ref: rc 0, 0.28 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; df['a'].loc[mask] = 10: [1, 10, 10] ; df['b'].fillna(0, inplace=True): [0.0, 2.0, 0.0] ; df['b'].iloc[0] = -1: [-1.0, 2.0, nan]`
- Engine reproducer pending for fireducks: listed in `results/rootcause/probes_todo.json` (not run: starts worker pools).

### `int_float_nullable_repr` (representation_only)

integer column with missing values elsewhere: engine returns int64 for a NaN-free slice/aggregate where pandas returns float64.

- Cells 20 (strict-clean 20), notebooks 5, by class {"E2": 20}; observed severity per cell {"equal_at_E1_to_E4": 20}.
- Engines: {"pilot:fireducks": 6, "pilot:modin": 14}.
- Documented: no documentation found (searched 2026-10-04).
- Example: fireducks `sabya40/data-cleaning-and-pandas-for-beginners` cell 13, E2 (inputs equal at E0), check `dtype:col2:float64/int64`.
- Example: fireducks `shashi772/data-cleaning-challenge-parsing-dates` cell 10, E2 (inputs equal at E0), check `dtype:col0:float64/int32`.
- Example: fireducks `xingobar/computer-science-data-visualization` cell 5, E2 (inputs equal at E0), check `dtype:col17:float64/int64`.
- Example: modin `kanncaa1/dataiteam-titanic-eda` cell 19, E2 (inputs equal at E0), check `dtype:col1:float64/int64`.
- Engine reproducer pending for modin, fireducks: listed in `results/rootcause/probes_todo.json` (not run: starts worker pools).

### `row_order_ties` (silent_value_change)

different order of rows (ties in sort_values/value_counts, merge/groupby output order); equal as multisets (E1) or different after head()/[:n] truncation.

- Cells 18 (strict-clean 7), notebooks 10, by class {"E4": 5, "DIFF": 7, "E1": 6}; observed severity per cell {"equal_at_E1_to_E4": 11, "DIFF_not_equal_at_E4": 7}.
- Engines: {"drift:p30": 6, "pilot:bodo": 2, "pilot:bodo_dw": 2, "pilot:fireducks": 3, "pilot:modin": 5}.
- Documented: <https://modin.readthedocs.io/en/latest/supported_apis/dataframe_supported.html> ("Order of indexes that have the same sort key is not guaranteed").
- Documented: <https://fireducks-dev.github.io/docs/user-guide/04-compatibility/> ("The order of rows in merge/join results may not match the order in pandas").
- Note: documented for Modin sort_values and FireDucks merge/join; not for pandas 3 tie order or Bodo group order.
- Example: p30 `carlmcbrideellis/simple-eda-of-kaggle-grandmasters-scheduled` cell 5, E4 (inputs equal at E2), check `index:values:index0:row=0`.
- Example: p30 `grudd0/mass-shooting-analysis` cell 42, E4 (inputs equal at E2), check `index:values:index0:row=7`.
- Example: p30 `mikedelong/python-eda-with-kdes` cell 8, E4 (inputs equal at E2), check `index:values:index0:row=5`.
- Example: p30 `shubhammahalank/eda-hotel-booking-demand` cell 13, E4 (inputs equal at E2), check `index:values:index0:row=48`.
- Reproducer `results/rootcause/repro/row_order_ties.py`, run in pandas environments (differs from ref: {"p15": false, "p30": true, "pyarrow_backend": true}):
  - p15: rc 0, 0.26 s, max RSS 95 MB: `env: mode=pandas pandas=1.5.3 ; value_counts().nlargest(10) labels: ['n161', 'n289', 'n035', 'n041', 'n039', 'n227', 'n120', 'n288', 'n083', 'n086'] dtype=object ; sort_values ties: id order: {1: 1, 3`
  - p30: rc 0, 0.26 s, max RSS 101 MB: `env: mode=pandas pandas=3.0.6 ; value_counts().nlargest(10) labels: ['n161', 'n035', 'n289', 'n041', 'n010', 'n246', 'n114', 'n120', 'n288', 'n083'] dtype=str ; sort_values ties: id order: {1: 1, 3: 3`
  - pyarrow_backend: rc 0, 0.29 s, max RSS 103 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; value_counts().nlargest(10) labels: ['n161', 'n035', 'n289', 'n041', 'n010', 'n246', 'n114', 'n120', 'n288', 'n083'] dtype=string[pyarrow] ; sort_values ties: `
  - ref: rc 0, 0.28 s, max RSS 99 MB: `env: mode=pandas pandas=2.3.3 ; value_counts().nlargest(10) labels: ['n161', 'n289', 'n035', 'n041', 'n039', 'n227', 'n120', 'n288', 'n083', 'n086'] dtype=object ; sort_values ties: id order: {1: 1, 3`
- Engine reproducer pending for modin, fireducks, bodo: listed in `results/rootcause/probes_todo.json` (not run: starts worker pools).

### `offset_alias_removed` (error)

frequency aliases M, H, AS removed in pandas 3 (ME, h, YS).

- Cells 18 (strict-clean 2), notebooks 4, by class {"ERR": 18}; observed severity per cell {"error": 18}.
- Engines: {"drift:p30": 18}.
- Documented: <https://pandas.pydata.org/docs/whatsnew/v3.0.0.html> ("Enforced deprecation of string AS denoting frequency in YearBegin; strings H, BH, and CBH denoting frequencies in Hour; MonthEnd M -> ME").
- Example: p30 `grudd0/mass-shooting-analysis` cell 3, ERR (inputs equal at E0), check `builtins.ValueError: Invalid frequency: AS. Failed to parse with error message: ValueError("Invalid frequency: AS. Failed to parse with erro`.
- Example: p30 `roopahegde/cryptocurrency-price-correlation` cell 27, ERR (inputs equal at E2), check `builtins.ValueError: Invalid frequency: M. Failed to parse with error message: ValueError("'M' is no longer supported for offsets. Please us`.
- Example: p30 `xokent/cyber-security-attack-eda` cell 6, ERR (inputs equal at E2), check `builtins.ValueError: Invalid frequency: M. Failed to parse with error message: ValueError("'M' is no longer supported for offsets. Please us`.
- Example: p30 `yuliagm/talkingdata-eda-plus-time-patterns` cell 26, ERR (inputs equal at E2), check `builtins.ValueError: Invalid frequency: H. Failed to parse with error message: ValueError("Invalid frequency: H. Failed to parse with error `.
- Reproducer `results/rootcause/repro/offset_alias_removed.py`, run in pandas environments (differs from ref: {"p15": true, "p30": true, "pyarrow_backend": false}):
  - p15: rc 0, 0.30 s, max RSS 94 MB: `env: mode=pandas pandas=1.5.3 ; date_range freq=AS: ['2000-01-01 00:00:00', '2001-01-01 00:00:00'] ; date_range freq=M: ['2000-01-31 00:00:00', '2000-02-29 00:00:00'] ; date_range freq=H: ['2000-01-01`
  - p30: rc 0, 0.27 s, max RSS 98 MB: `env: mode=pandas pandas=3.0.6 ; date_range freq=AS: raised ValueError: Invalid frequency: AS. Failed to parse with error message: ValueError("Invalid frequency: AS. Failed to parse with error message:`
  - pyarrow_backend: rc 0, 0.28 s, max RSS 98 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; date_range freq=AS: ['2000-01-01 00:00:00', '2001-01-01 00:00:00'] ; date_range freq=M: ['2000-01-31 00:00:00', '2000-02-29 00:00:00'] ; date_range freq=H: ['2`
  - ref: rc 0, 0.28 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; date_range freq=AS: ['2000-01-01 00:00:00', '2001-01-01 00:00:00'] ; date_range freq=M: ['2000-01-31 00:00:00', '2000-02-29 00:00:00'] ; date_range freq=H: ['2000-01-01`

### `numeric_dtype_preservation` (representation_only)

pandas 2.0 keeps narrow numeric dtypes (int32 datetime fields, Index of int32/uint32/float32) where 1.5 widened.

- Cells 17 (strict-clean 17), notebooks 12, by class {"E2": 16, "DIFF": 1}; observed severity per cell {"equal_at_E1_to_E4": 16, "DIFF_not_equal_at_E4": 1}.
- Engines: {"drift:p15": 17}.
- Documented: <https://pandas.pydata.org/docs/whatsnew/v2.0.0.html> ("Index can now hold numpy numeric dtypes; datetime fields are now int32").
- Example: p15 `akshaypetkar/supermarket-sales-analysis` cell 15, E2 (inputs equal at E0), check `dtype:col11:int32/int64`.
- Example: p15 `blaskowitz100/feature-engineering-based-on-the-suprise-me` cell 5, E2 (inputs equal at E0), check `dtype:col4:int32/int64`.
- Example: p15 `j0thu777/onlineretailanalysis` cell 17, E2 (inputs equal at E0), check `dtype:col7:int32/int64`.
- Example: p15 `loveall/favorita-analytics` cell 16, E2 (inputs equal at E0), check `dtype:col3:int32/int64`.
- Reproducer `results/rootcause/repro/numeric_dtype_preservation.py`, run in pandas environments (differs from ref: {"p15": true, "p30": false, "pyarrow_backend": false}):
  - p15: rc 0, 0.28 s, max RSS 94 MB: `env: mode=pandas pandas=1.5.3 ; dt.year dtype: int64 ; Index(np.uint32 array) dtype: uint64 ; groupby uint32 key -> index dtype: uint64`
  - p30: rc 0, 0.28 s, max RSS 100 MB: `env: mode=pandas pandas=3.0.6 ; dt.year dtype: int32 ; Index(np.uint32 array) dtype: uint32 ; groupby uint32 key -> index dtype: uint32`
  - pyarrow_backend: rc 0, 0.28 s, max RSS 97 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; dt.year dtype: int32 ; Index(np.uint32 array) dtype: uint32 ; groupby uint32 key -> index dtype: uint32`
  - ref: rc 0, 0.28 s, max RSS 99 MB: `env: mode=pandas pandas=2.3.3 ; dt.year dtype: int32 ; Index(np.uint32 array) dtype: uint32 ; groupby uint32 key -> index dtype: uint32`

### `lazy_partition_model` (error)

lazy/partitioned execution model (unknown partition lengths -> shape NaN, unknown divisions, metadata inference, lazy scalars).

- Cells 17 (strict-clean 2), notebooks 7, by class {"DIFF": 5, "ERR": 12}; observed severity per cell {"DIFF_not_equal_at_E4": 5, "error": 12}.
- Engines: {"pilot:dask": 17}.
- Documented: <https://docs.dask.org/en/stable/dataframe-indexing.html> ("Dask DataFrame does not track the length of partitions").
- Example: dask `corazzon/how-to-use-pandas-filter-in-survey-eda` cell 2, DIFF (inputs equal at E0), check `values:col0:row=0`.
- Example: dask `deffro/eda-is-fun` cell 5, ERR (inputs equal at E4), check `builtins.TypeError: unsupported format string passed to Scalar.__format__`.
- Example: dask `kanncaa1/dataiteam-titanic-eda` cell 16, ERR (inputs equal at E3), check `builtins.KeyError: 'Cannot index with list against unknown division. Try setting divisions using ``ddf.set_index``'`.
- Example: dask `roopahegde/cryptocurrency-price-correlation` cell 5, DIFF (inputs equal at E2), check `values:col0:row=0`.
- Engine reproducer pending for dask: listed in `results/rootcause/probes_todo.json` (not run: starts worker pools).

### `removed_deprecated_api` (error)

APIs deprecated in 2.x and removed in 3.0 (fillna(method=/downcast=), to_datetime(infer_datetime_format=), pd.value_counts, DataFrame.applymap, Index.sort).

- Cells 15 (strict-clean 0), notebooks 8, by class {"ERR": 15}; observed severity per cell {"error": 15}.
- Engines: {"drift:p30": 15}.
- Documented: <https://pandas.pydata.org/docs/whatsnew/v3.0.0.html> ("Removed deprecated keyword method on Series.fillna(), DataFrame.fillna(); Removed DataFrame.applymap; Removed pandas.value_counts; Removed Index.sort()").
- Documented: <https://pandas.pydata.org/docs/whatsnew/v2.1.0.html> ("Deprecated the downcast keyword in ... Series.fillna(), DataFrame.fillna()").
- Documented: <https://pandas.pydata.org/docs/whatsnew/v2.0.0.html> ("Deprecated argument infer_datetime_format in to_datetime() and read_csv()").
- Example: p30 `guyalmog/hr-analytics-predicting-employees-attrition` cell 6, ERR (inputs equal at E2), check `builtins.AttributeError: 'DataFrame' object has no attribute 'applymap'`.
- Example: p30 `jirakst/book-recommendation` cell 29, ERR (inputs equal at E2), check `builtins.TypeError: NDFrame.fillna() got an unexpected keyword argument 'downcast'`.
- Example: p30 `luizep/movieslens20m` cell 16, ERR (inputs equal at E2), check `builtins.TypeError: to_datetime() got an unexpected keyword argument 'infer_datetime_format'`.
- Example: p30 `maxiaoyue/data-cleaning-challenge-handling-missing-values` cell 21, ERR (inputs equal at E2), check `builtins.TypeError: NDFrame.fillna() got an unexpected keyword argument 'method'`.
- Reproducer `results/rootcause/repro/removed_deprecated_api.py`, run in pandas environments (differs from ref: {"p15": false, "p30": true, "pyarrow_backend": false}):
  - p15: rc 0, 0.28 s, max RSS 94 MB: `env: mode=pandas pandas=1.5.3 ; fillna(method='bfill'): [1.0, 3.0, 3.0] ; fillna(0, downcast='infer'): int64 ; to_datetime(infer_datetime_format=True): datetime64[ns] ; pd.value_counts: {1: 2, 2: 1} ;`
  - p30: rc 0, 0.27 s, max RSS 98 MB: `env: mode=pandas pandas=3.0.6 ; fillna(method='bfill'): raised TypeError: NDFrame.fillna() got an unexpected keyword argument 'method' ; fillna(0, downcast='infer'): raised TypeError: NDFrame.fillna()`
  - pyarrow_backend: rc 0, 0.29 s, max RSS 98 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; fillna(method='bfill'): [1.0, 3.0, 3.0] ; fillna(0, downcast='infer'): int64 ; to_datetime(infer_datetime_format=True): datetime64[ns] ; pd.value_counts: {1: 2`
  - ref: rc 0, 0.28 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; fillna(method='bfill'): [1.0, 3.0, 3.0] ; fillna(0, downcast='infer'): int64 ; to_datetime(infer_datetime_format=True): datetime64[ns] ; pd.value_counts: {1: 2, 2: 1} ;`

### `approximate_quantile` (silent_value_change)

quantile/percentile computed approximately; threshold filters keep different rows.

- Cells 15 (strict-clean 0), notebooks 3, by class {"DIFF": 15}; observed severity per cell {"DIFF_not_equal_at_E4": 15}.
- Engines: {"pilot:bodo": 5, "pilot:bodo_dw": 5, "pilot:dask": 5}.
- Documented: <https://docs.dask.org/en/stable/generated/dask.dataframe.Series.quantile.html> ("Approximate quantiles of Series").
- Note: documented for Dask; for Bodo the quantile hypothesis is from the cell code and must be confirmed by the probe.
- Example: bodo `deffro/eda-is-fun` cell 12, DIFF (inputs equal at E3), check `shape:[4402460]/[4400164]`.
- Example: bodo `kanncaa1/dataiteam-titanic-eda` cell 16, DIFF (inputs equal at E3), check `shape:[10, 12]/[46, 12]`.
- Example: bodo_dw `deffro/eda-is-fun` cell 12, DIFF (inputs equal at E3), check `shape:[4402460]/[4408707]`.
- Example: bodo_dw `kanncaa1/dataiteam-titanic-eda` cell 16, DIFF (inputs equal at E3), check `shape:[10, 12]/[46, 12]`.
- Engine reproducer pending for bodo, bodo_dw, dask: listed in `results/rootcause/probes_todo.json` (not run: starts worker pools).

### `engine_bug_silent` (silent_value_change)

engine returns a different value without error (Modin pd.value_counts(pd.cut) drops a bin, pivot_table(aggfunc='size') returns a DataFrame; Bodo head() after column changes shows stale columns).

- Cells 15 (strict-clean 3), notebooks 4, by class {"DIFF": 15}; observed severity per cell {"DIFF_not_equal_at_E4": 15}.
- Engines: {"pilot:bodo": 6, "pilot:bodo_dw": 7, "pilot:modin": 2}.
- Documented: no documentation found (searched 2026-10-04).
- Example: bodo `deffro/eda-is-fun` cell 40, DIFF (inputs equal at E3), check `shape:[5, 39]/[5, 29]`.
- Example: bodo `sabya40/data-cleaning-and-pandas-for-beginners` cell 7, DIFF (inputs equal at E2), check `shape:[5, 7]/[5, 6]`.
- Example: bodo_dw `deffro/eda-is-fun` cell 40, DIFF (inputs equal at E3), check `shape:[5, 39]/[5, 29]`.
- Example: bodo_dw `sabya40/data-cleaning-and-pandas-for-beginners` cell 7, DIFF (inputs equal at E2), check `shape:[5, 7]/[5, 6]`.
- Engine reproducer pending for modin, bodo, bodo_dw: listed in `results/rootcause/probes_todo.json` (not run: starts worker pools).

### `get_dummies_bool` (representation_only)

pandas 2.0: get_dummies returns bool instead of uint8.

- Cells 14 (strict-clean 12), notebooks 12, by class {"DIFF": 14}; observed severity per cell {"DIFF_not_equal_at_E4": 14}.
- Engines: {"drift:p15": 14}.
- Documented: <https://pandas.pydata.org/docs/whatsnew/v2.0.0.html> ("Default value of dtype in get_dummies() is changed to bool from uint8").
- Example: p15 `dbatao/kernel2f80fc9d78` cell 48, DIFF (inputs equal at E0), check `dtype_family:bool/int:col43`.
- Example: p15 `galiph/titanic-explorary-data-analysis` cell 20, DIFF (inputs equal at E0), check `dtype_family:bool/int:col0`.
- Example: p15 `guyalmog/hr-analytics-predicting-employees-attrition` cell 76, DIFF (inputs equal at E0), check `dtype_family:bool/int:col16`.
- Example: p15 `kanncaa1/dataiteam-titanic-eda` cell 53, DIFF (inputs equal at E0), check `dtype_family:bool/int:col11`.
- Reproducer `results/rootcause/repro/get_dummies_bool.py`, run in pandas environments (differs from ref: {"p15": true, "p30": false, "pyarrow_backend": false}):
  - p15: rc 0, 0.30 s, max RSS 94 MB: `env: mode=pandas pandas=1.5.3 ; get_dummies dtypes: ['uint8', 'uint8']`
  - p30: rc 0, 0.29 s, max RSS 100 MB: `env: mode=pandas pandas=3.0.6 ; get_dummies dtypes: ['bool', 'bool']`
  - pyarrow_backend: rc 0, 0.30 s, max RSS 98 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; get_dummies dtypes: ['bool', 'bool']`
  - ref: rc 0, 0.29 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; get_dummies dtypes: ['bool', 'bool']`

### `arrow_dtype_errors` (error)

errors caused by arrow-backed data: strict typing on setitem ('8+' into int64), pd.NA in a boolean context, .str accessor / numpy calls on arrow scalars.

- Cells 11 (strict-clean 1), notebooks 4, by class {"ERR": 11}; observed severity per cell {"error": 11}.
- Engines: {"pilot:bodo": 2, "pilot:bodo_dw": 2, "pilot:fireducks": 2, "pilot:pyarrow_backend": 5}.
- Documented: <https://pandas.pydata.org/docs/user_guide/missing_data.html> ("it is ambiguous to convert NA to a boolean value").
- Note: pd.NA boolean semantics documented; strict arrow setitem typing not found.
- Example: bodo `deffro/eda-is-fun` cell 6, ERR (inputs equal at E3), check `pyarrow.lib.ArrowInvalid: Could not convert '8+' with type str: tried to convert to int64`.
- Example: bodo_dw `deffro/eda-is-fun` cell 6, ERR (inputs equal at E3), check `pyarrow.lib.ArrowInvalid: Could not convert '8+' with type str: tried to convert to int64`.
- Example: fireducks `deffro/eda-is-fun` cell 6, ERR (inputs equal at E0), check `materialize_error`.
- Example: fireducks `kimtaehun/simple-preprocessing-for-time-series-prediction` cell 8, ERR (inputs equal at E4), check `materialize_error`.
- Reproducer `results/rootcause/repro/arrow_dtype_errors.py`, run in pandas environments (differs from ref: {"p15": false, "p30": true, "pyarrow_backend": true}):
  - p15: rc 0, 0.27 s, max RSS 93 MB: `env: mode=pandas pandas=1.5.3 ; int column <- '8+': [1, '8+'] ; np.isnan on a missing scalar: True ; if value > 0 on a missing scalar: False`
  - p30: rc 0, 0.27 s, max RSS 98 MB: `env: mode=pandas pandas=3.0.6 ; int column <- '8+': raised TypeError: Invalid value '8+' for dtype 'int64' ; np.isnan on a missing scalar: True ; if value > 0 on a missing scalar: False`
  - pyarrow_backend: rc 0, 0.29 s, max RSS 100 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; int column <- '8+': raised ArrowInvalid: Could not convert '8+' with type str: tried to convert to int64 ; np.isnan on a missing scalar: raised TypeError: bool`
  - ref: rc 0, 0.27 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; int column <- '8+': [1, '8+'] ; np.isnan on a missing scalar: True ; if value > 0 on a missing scalar: False`
- Engine reproducer pending for bodo, fireducks: listed in `results/rootcause/probes_todo.json` (not run: starts worker pools).

### `read_csv_none_as_na` (silent_value_change)

pandas 2.0 read_csv parses the string 'None' as missing.

- Cells 10 (strict-clean 10), notebooks 9, by class {"DIFF": 10}; observed severity per cell {"DIFF_not_equal_at_E4": 10}.
- Engines: {"drift:p15": 10}.
- Documented: <https://pandas.pydata.org/docs/whatsnew/v2.0.0.html> ("Added "None" to default na_values in read_csv()").
- Example: p15 `ashukr/first-step-ingestion-to-prediction` cell 1, DIFF (inputs equal at E0), check `missing_mask:col25:row=1`.
- Example: p15 `carlmcbrideellis/simple-eda-of-kaggle-grandmasters-scheduled` cell 1, DIFF (inputs equal at E0), check `missing_mask:col2:row=14689`.
- Example: p15 `corazzon/how-to-use-pandas-filter-in-survey-eda` cell 2, DIFF (inputs equal at E0), check `missing_mask:col18:row=51`.
- Example: p15 `dbatao/kernel2f80fc9d78` cell 3, DIFF (inputs equal at E0), check `missing_mask:col25:row=0`.
- Reproducer `results/rootcause/repro/read_csv_none_as_na.py`, run in pandas environments (differs from ref: {"p15": true, "p30": false, "pyarrow_backend": false}):
  - p15: rc 0, 0.27 s, max RSS 94 MB: `env: mode=pandas pandas=1.5.3 ; isna per row: [False, False, True]`
  - p30: rc 0, 0.27 s, max RSS 99 MB: `env: mode=pandas pandas=3.0.6 ; isna per row: [False, True, True]`
  - pyarrow_backend: rc 0, 0.30 s, max RSS 100 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; isna per row: [False, True, True]`
  - ref: rc 0, 0.28 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; isna per row: [False, True, True]`

### `merge_row_order` (silent_value_change)

pandas 2.2: merge/join row order follows the documented sort rules (inner keeps left order).

- Cells 9 (strict-clean 8), notebooks 7, by class {"DIFF": 5, "E4": 3, "E1": 1}; observed severity per cell {"DIFF_not_equal_at_E4": 5, "equal_at_E1_to_E4": 4}.
- Engines: {"drift:p15": 9}.
- Documented: <https://pandas.pydata.org/docs/whatsnew/v2.2.0.html> ("merge() and DataFrame.join() now consistently follow documented sort behavior").
- Example: p15 `blaskowitz100/feature-engineering-based-on-the-suprise-me` cell 2, DIFF (inputs equal at E0), check `values:col1:row=3`.
- Example: p15 `loveall/favorita-analytics` cell 4, DIFF (inputs equal at E0), check `values:col0:row=0`.
- Example: p15 `nadare/feature-engenieering-with-pivot-table` cell 17, DIFF (inputs equal at E0), check `values:col37:row=2`.
- Example: p15 `tanulsingh077/twitter-sentiment-extaction-analysis-eda-and-model` cell 15, E4 (inputs equal at E0), check `index:values:index0:row=0`.
- Reproducer `results/rootcause/repro/merge_row_order.py`, run in pandas environments (differs from ref: {"p15": true, "p30": false, "pyarrow_backend": false}):
  - p15: rc 0, 0.27 s, max RSS 94 MB: `env: mode=pandas pandas=1.5.3 ; inner merge order: [[1, 'x', 'p'], [1, 'z', 'p'], [2, 'y', 'q']]`
  - p30: rc 0, 0.28 s, max RSS 99 MB: `env: mode=pandas pandas=3.0.6 ; inner merge order: [[1, 'x', 'p'], [2, 'y', 'q'], [1, 'z', 'p']]`
  - pyarrow_backend: rc 0, 0.29 s, max RSS 99 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; inner merge order: [[1, 'x', 'p'], [2, 'y', 'q'], [1, 'z', 'p']]`
  - ref: rc 0, 0.28 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; inner merge order: [[1, 'x', 'p'], [2, 'y', 'q'], [1, 'z', 'p']]`

### `missing_sentinel_repr` (representation_only)

missing strings come back as None instead of NaN (equal at E3).

- Cells 9 (strict-clean 9), notebooks 5, by class {"E3": 9}; observed severity per cell {"equal_at_E1_to_E4": 9}.
- Engines: {"pilot:fireducks": 9}.
- Documented: no documentation found (searched 2026-10-04).
- Example: fireducks `corazzon/how-to-use-pandas-filter-in-survey-eda` cell 3, E3 (inputs equal at E0), check `sentinel:col7:row=3:2/1`.
- Example: fireducks `kanncaa1/dataiteam-titanic-eda` cell 1, E3 (inputs equal at E0), check `sentinel:col9:row=0:2/1`.
- Example: fireducks `kimtaehun/simple-preprocessing-for-time-series-prediction` cell 2, E3 (inputs equal at E0), check `sentinel:col7:row=0:2/1`.
- Example: fireducks `shashi772/data-cleaning-challenge-parsing-dates` cell 0, E3 (inputs equal at E0), check `sentinel:col9:row=6703:2/1`.
- Engine reproducer pending for fireducks: listed in `results/rootcause/probes_todo.json` (not run: starts worker pools).

### `datetime_resolution_inference` (silent_value_change)

pandas 3 infers microsecond (not nanosecond) resolution when parsing strings.

- Cells 8 (strict-clean 0), notebooks 4, by class {"DIFF": 8}; observed severity per cell {"DIFF_not_equal_at_E4": 8}.
- Engines: {"drift:p30": 8}.
- Documented: <https://pandas.pydata.org/docs/whatsnew/v3.0.0.html> ("The new default resolution when parsing strings is microseconds").
- Example: p30 `j0thu777/onlineretailanalysis` cell 20, DIFF (inputs equal at E2), check `values:col9:row=0`.
- Example: p30 `xokent/cyber-security-attack-eda` cell 5, DIFF (inputs equal at E2), check `values:col1:row=0`.
- Example: p30 `yonelanuba/elo-merchant-by-yonela` cell 138, DIFF (inputs equal at E2), check `values:col23:row=0`.
- Example: p30 `yuliagm/talkingdata-eda-plus-time-patterns` cell 8, DIFF (inputs equal at E2), check `values:col0:row=1`.
- Reproducer `results/rootcause/repro/datetime_resolution_inference.py`, run in pandas environments (differs from ref: {"p15": false, "p30": true, "pyarrow_backend": false}):
  - p15: rc 0, 0.27 s, max RSS 93 MB: `env: mode=pandas pandas=1.5.3 ; dtype after parsing strings: datetime64[ns] ; astype('int64'): [1523404800000000000, 1509840000000000000] ; mean(): 2017-11-06 22:30:07.333333248`
  - p30: rc 0, 0.27 s, max RSS 98 MB: `env: mode=pandas pandas=3.0.6 ; dtype after parsing strings: datetime64[us] ; astype('int64'): [1523404800000000, 1509840000000000] ; mean(): 2017-11-06 22:30:07.333333`
  - pyarrow_backend: rc 0, 0.27 s, max RSS 98 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; dtype after parsing strings: datetime64[ns] ; astype('int64'): [1523404800000000000, 1509840000000000000] ; mean(): 2017-11-06 22:30:07.333333248`
  - ref: rc 0, 0.28 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; dtype after parsing strings: datetime64[ns] ; astype('int64'): [1523404800000000000, 1509840000000000000] ; mean(): 2017-11-06 22:30:07.333333248`

### `int_key_positional_fallback_removed` (error)

Series[int] on a non-integer index no longer falls back to position (KeyError).

- Cells 7 (strict-clean 0), notebooks 4, by class {"ERR": 7}; observed severity per cell {"error": 7}.
- Engines: {"drift:p30": 7}.
- Documented: <https://pandas.pydata.org/docs/whatsnew/v3.0.0.html> ("Changed behavior of Series.__getitem__() and Series.__setitem__() to always treat integer keys as labels, never as positional").
- Example: p30 `corazzon/how-to-use-pandas-filter-in-survey-eda` cell 21, ERR (inputs equal at E2), check `builtins.KeyError: 0`.
- Example: p30 `jirakst/book-recommendation` cell 63, ERR (inputs equal at E2), check `builtins.KeyError: 0`.
- Example: p30 `seriousran/eda-ing` cell 9, ERR (inputs equal at E2), check `builtins.KeyError: 5`.
- Example: p30 `shivavashishtha/zomato-eda-tutorial` cell 85, ERR (inputs equal at E2), check `builtins.KeyError: 1`.
- Reproducer `results/rootcause/repro/int_key_positional_fallback_removed.py`, run in pandas environments (differs from ref: {"p15": false, "p30": true, "pyarrow_backend": false}):
  - p15: rc 0, 0.28 s, max RSS 93 MB: `env: mode=pandas pandas=1.5.3 ; s[0] on a string index: first ; corr()['x'][1]: 1.0`
  - p30: rc 0, 0.28 s, max RSS 99 MB: `env: mode=pandas pandas=3.0.6 ; s[0] on a string index: raised KeyError: 0 ; corr()['x'][1]: raised KeyError: 1`
  - pyarrow_backend: rc 0, 0.29 s, max RSS 98 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; s[0] on a string index: first ; corr()['x'][1]: 1.0`
  - ref: rc 0, 0.30 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; s[0] on a string index: first ; corr()['x'][1]: 1.0`

### `axis_names_lost` (representation_only)

axis or Series names lost (crosstab columns name, iloc row Series name).

- Cells 7 (strict-clean 3), notebooks 2, by class {"E4": 6, "E2": 1}; observed severity per cell {"equal_at_E1_to_E4": 7}.
- Engines: {"pilot:bodo": 2, "pilot:bodo_dw": 2, "pilot:modin": 3}.
- Documented: no documentation found (searched 2026-10-04).
- Example: bodo `corazzon/how-to-use-pandas-filter-in-survey-eda` cell 11, E4 (inputs equal at E3), check `names:columns_names`.
- Example: bodo `trinath003/data-manipulation-visualisation-on-kaggle-datasets` cell 13, E4 (inputs equal at E2), check `names:columns_names`.
- Example: bodo_dw `corazzon/how-to-use-pandas-filter-in-survey-eda` cell 11, E4 (inputs equal at E3), check `names:columns_names`.
- Example: bodo_dw `trinath003/data-manipulation-visualisation-on-kaggle-datasets` cell 13, E4 (inputs equal at E2), check `names:columns_names`.
- Engine reproducer pending for modin, bodo: listed in `results/rootcause/probes_todo.json` (not run: starts worker pools).

### `partitioned_type_inference` (error)

per-partition / sample-based dtype inference in read_csv (Dask: Mismatched dtypes at compute; Modin: mixed int/str object column).

- Cells 5 (strict-clean 5), notebooks 4, by class {"ERR": 4, "DIFF": 1}; observed severity per cell {"error": 4, "DIFF_not_equal_at_E4": 1}.
- Engines: {"pilot:dask": 4, "pilot:modin": 1}.
- Documented: <https://docs.dask.org/en/stable/generated/dask.dataframe.read_csv.html> ("Dask dataframe tries to infer the dtype of each column by reading a sample from the start of the file").
- Note: documented for Dask; Modin's mixed-type column not found in its docs (silent value change there).
- Example: dask `kanncaa1/dataiteam-titanic-eda` cell 1, ERR (inputs equal at E0), check `materialize_error`.
- Example: dask `kimtaehun/simple-preprocessing-for-time-series-prediction` cell 2, ERR (inputs equal at E0), check `materialize_error`.
- Example: dask `shashi772/data-cleaning-challenge-parsing-dates` cell 0, ERR (inputs equal at E0), check `materialize_error`.
- Example: dask `xingobar/computer-science-data-visualization` cell 2, ERR (inputs equal at E0), check `materialize_error`.
- Engine reproducer pending for dask, modin: listed in `results/rootcause/probes_todo.json` (not run: starts worker pools).

### `describe_datetime_numeric` (silent_value_change)

pandas 2.0 describe() always summarises datetime columns as numeric (1.5: object-style summary or excluded).

- Cells 4 (strict-clean 4), notebooks 2, by class {"DIFF": 4}; observed severity per cell {"DIFF_not_equal_at_E4": 4}.
- Engines: {"drift:p15": 4}.
- Documented: <https://pandas.pydata.org/docs/whatsnew/v2.0.0.html> ("Removed argument datetime_is_numeric from DataFrame.describe() ... datetime data will always be summarized as numeric data").
- Example: p15 `xokent/cyber-security-attack-eda` cell 5, DIFF (inputs equal at E0), check `shape:[5, 8]/[4, 8]`.
- Example: p15 `yuliagm/talkingdata-eda-plus-time-patterns` cell 8, DIFF (inputs equal at E0), check `shape:[7, 2]/[6, 8]`.
- Reproducer `results/rootcause/repro/describe_datetime_numeric.py`, run in pandas environments (differs from ref: {"p15": true, "p30": false, "pyarrow_backend": false}):
  - p15: rc 0, 0.28 s, max RSS 93 MB: `env: mode=pandas pandas=1.5.3 ; describe() index and columns: (['count', 'mean', 'std', 'min', '25%', '50%', '75%', 'max'], ['x'])`
  - p30: rc 0, 0.28 s, max RSS 99 MB: `env: mode=pandas pandas=3.0.6 ; describe() index and columns: (['count', 'mean', 'min', '25%', '50%', '75%', 'max', 'std'], ['t', 'x'])`
  - pyarrow_backend: rc 0, 0.28 s, max RSS 98 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; describe() index and columns: (['count', 'mean', 'min', '25%', '50%', '75%', 'max', 'std'], ['t', 'x'])`
  - ref: rc 0, 0.29 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; describe() index and columns: (['count', 'mean', 'min', '25%', '50%', '75%', 'max', 'std'], ['t', 'x'])`

### `setitem_incompatible_dtype_raises` (error)

setting a value of an incompatible dtype raises instead of upcasting (PDEP-6).

- Cells 3 (strict-clean 1), notebooks 3, by class {"ERR": 3}; observed severity per cell {"error": 3}.
- Engines: {"drift:p30": 3}.
- Documented: <https://pandas.pydata.org/docs/whatsnew/v3.0.0.html> ("Enforce banning of upcasting in in-place setitem-like operations; see PDEP6").
- Documented: <https://pandas.pydata.org/docs/whatsnew/v2.1.0.html> ("Deprecated silent upcasting in setitem-like Series operations").
- Example: p30 `blaskowitz100/feature-engineering-based-on-the-suprise-me` cell 11, ERR (inputs equal at E0), check `builtins.TypeError: Invalid value '[3.58351894 2.30258509 0.         ... 1.09861229 1.60943791 1.79175947]' for dtype 'int64'`.
- Example: p30 `charulatashelar/indian-startup-funding-exploratory-data-analysis` cell 9, ERR (inputs equal at E2), check `builtins.TypeError: Invalid value '<DatetimeArray>
['2020-01-09 00:00:00', '2020-01-13 00:00:00', '2020-01-09 00:00:00',
 '2020-01-02 00:00:`.
- Example: p30 `deffro/eda-is-fun` cell 6, ERR (inputs equal at E2), check `builtins.TypeError: Invalid value '8+' for dtype 'int64'`.
- Reproducer `results/rootcause/repro/setitem_incompatible_dtype_raises.py`, run in pandas environments (differs from ref: {"p15": false, "p30": true, "pyarrow_backend": false}):
  - p15: rc 0, 0.26 s, max RSS 94 MB: `env: mode=pandas pandas=1.5.3 ; int column <- '8+': ([1, 2, '8+'], 'object') ; int column <- floats: [1.0, 0.6931471805599453, 1.0986122886681098]`
  - p30: rc 0, 0.28 s, max RSS 99 MB: `env: mode=pandas pandas=3.0.6 ; int column <- '8+': raised TypeError: Invalid value '8+' for dtype 'int64' ; int column <- floats: raised TypeError: Invalid value '[0.69314718 1.09861229]' for dtype '`
  - pyarrow_backend: rc 0, 0.29 s, max RSS 98 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; int column <- '8+': ([1, 2, '8+'], 'object') ; int column <- floats: [1.0, 0.6931471805599453, 1.0986122886681098]`
  - ref: rc 0, 0.29 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; int column <- '8+': ([1, 2, '8+'], 'object') ; int column <- floats: [1.0, 0.6931471805599453, 1.0986122886681098]`

### `str_dtype_na_semantics` (silent_value_change)

missing values under the pandas 3 `str` dtype: astype(str) keeps NaN (2.x wrote 'nan'), str accessor results on missing entries differ.

- Cells 3 (strict-clean 0), notebooks 3, by class {"DIFF": 3}; observed severity per cell {"DIFF_not_equal_at_E4": 3}.
- Engines: {"drift:p30": 3}.
- Documented: <https://pandas.pydata.org/docs/user_guide/migration-3-strings.html> ("astype(str) preserving missing values; The missing value sentinel is now always NaN").
- Note: astype(str) documented; str.split/str.contains on missing entries not described explicitly.
- Example: p30 `grudd0/mass-shooting-analysis` cell 43, DIFF (inputs equal at E2), check `missing_mask:col23:row=15`.
- Example: p30 `luckygemini/notebook5d5fc80c9f` cell 6, DIFF (inputs equal at E2), check `missing_mask:col3:row=385`.
- Example: p30 `luizep/movieslens20m` cell 13, DIFF (inputs equal at E2), check `shape:[20, 1]/[21, 1]`.
- Reproducer `results/rootcause/repro/str_dtype_na_semantics.py`, run in pandas environments (differs from ref: {"p15": false, "p30": true, "pyarrow_backend": false}):
  - p15: rc 0, 0.27 s, max RSS 93 MB: `env: mode=pandas pandas=1.5.3 ; astype(str) of a missing value: ["'1.5'", "'nan'"] ; str.split(...).tolist() -> DataFrame.stack().unique(): raised TypeError: object of type 'NoneType' has no len() ; s`
  - p30: rc 0, 0.27 s, max RSS 99 MB: `env: mode=pandas pandas=3.0.6 ; astype(str) of a missing value: ["'1.5'", 'nan'] ; str.split(...).tolist() -> DataFrame.stack().unique(): raised TypeError: object of type 'float' has no len() ; str.co`
  - pyarrow_backend: rc 0, 0.28 s, max RSS 98 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; astype(str) of a missing value: ["'1.5'", "'nan'"] ; str.split(...).tolist() -> DataFrame.stack().unique(): raised TypeError: object of type 'NoneType' has no `
  - ref: rc 0, 0.29 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; astype(str) of a missing value: ["'1.5'", "'nan'"] ; str.split(...).tolist() -> DataFrame.stack().unique(): raised TypeError: object of type 'NoneType' has no len() ; s`

### `str_dtype_errors` (error)

operations that raise on the pandas 3 `str` dtype (mixed-dtype sort of `.dtypes`, numeric reductions, categorical dtype mismatch, non-string setitem).

- Cells 2 (strict-clean 1), notebooks 2, by class {"ERR": 2}; observed severity per cell {"error": 2}.
- Engines: {"drift:p30": 2}.
- Documented: <https://pandas.pydata.org/docs/user_guide/migration-3-strings.html> ("setitem operations will now raise an error for non-string data; prod() raising for string data").
- Example: p30 `dbatao/kernel2f80fc9d78` cell 28, ERR (inputs equal at E2), check `builtins.TypeError: '<' not supported between instances of 'numpy.dtypes.Float64DType' and 'StringDtype'`.
- Example: p30 `roydatascience/malware-detection-stacking-2-0` cell 5, ERR (inputs equal at E0), check `builtins.TypeError: dtype of categories must be the same`.
- Reproducer `results/rootcause/repro/str_dtype_errors.py`, run in pandas environments (differs from ref: {"p15": false, "p30": true, "pyarrow_backend": false}):
  - p15: rc 0, 0.27 s, max RSS 94 MB: `env: mode=pandas pandas=1.5.3 ; dtypes.sort_values() with float64 and str: ['float64', 'object'] ; setitem float into string Series: (['a', 2.5], 'object') ; categorical with object vs str categories `
  - p30: rc 0, 0.27 s, max RSS 100 MB: `env: mode=pandas pandas=3.0.6 ; dtypes.sort_values() with float64 and str: raised TypeError: '<' not supported between instances of 'StringDtype' and 'numpy.dtypes.Float64DType' ; setitem float into s`
  - pyarrow_backend: rc 0, 0.27 s, max RSS 98 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; dtypes.sort_values() with float64 and str: ['float64', 'object'] ; setitem float into string Series: (['a', 2.5], 'object') ; categorical with object vs str ca`
  - ref: rc 0, 0.30 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; dtypes.sort_values() with float64 and str: ['float64', 'object'] ; setitem float into string Series: (['a', 2.5], 'object') ; categorical with object vs str categories `

### `engine_corr_wrong_values` (silent_value_change)

Modin DataFrame.corr(numeric_only=True) returns out-of-range correlations (diagonal 5.38, 8.41) on a 4.4M-row frame.

- Cells 2 (strict-clean 2), notebooks 1, by class {"DIFF": 2}; observed severity per cell {"DIFF_not_equal_at_E4": 2}.
- Engines: {"pilot:modin": 2}.
- Documented: no documentation found (searched 2026-10-04).
- Example: modin `deffro/eda-is-fun` cell 30, DIFF (inputs equal at E0), check `values:col0:row=0`.
- Engine reproducer pending for modin: listed in `results/rootcause/probes_todo.json` (not run: starts worker pools).

### `api_added_later` (error)

pandas 1.5 lacks an API that notebooks written for 2.x use (read_csv(date_format=)).

- Cells 1 (strict-clean 1), notebooks 1, by class {"ERR": 1}; observed severity per cell {"error": 1}.
- Engines: {"drift:p15": 1}.
- Documented: <https://pandas.pydata.org/docs/whatsnew/v2.0.0.html> ("read_csv(), read_table(), read_fwf() and read_excel() now accept date_format").
- Example: p15 `balajivenkat96/solar-plants` cell 1, ERR (inputs equal at E0), check `builtins.TypeError: read_csv() got an unexpected keyword argument 'date_format'`.
- Reproducer `results/rootcause/repro/api_added_later.py`, run in pandas environments (differs from ref: {"p15": true, "p30": true, "pyarrow_backend": false}):
  - p15: rc 0, 0.94 s, max RSS 92 MB: `env: mode=pandas pandas=1.5.3 ; read_csv(date_format=...): raised TypeError: read_csv() got an unexpected keyword argument 'date_format'`
  - p30: rc 0, 0.84 s, max RSS 98 MB: `env: mode=pandas pandas=3.0.6 ; read_csv(date_format=...): datetime64[us]`
  - pyarrow_backend: rc 0, 0.29 s, max RSS 100 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; read_csv(date_format=...): datetime64[ns]`
  - ref: rc 0, 0.84 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; read_csv(date_format=...): datetime64[ns]`

### `str_replace_regex_default` (silent_value_change)

pandas 2.0: Series.str.replace default regex=False (1.5: regex=True).

- Cells 1 (strict-clean 1), notebooks 1, by class {"DIFF": 1}; observed severity per cell {"DIFF_not_equal_at_E4": 1}.
- Engines: {"drift:p15": 1}.
- Documented: <https://pandas.pydata.org/docs/whatsnew/v2.0.0.html> ("Change the default argument of regex for Series.str.replace() from True to False").
- Example: p15 `brianmendieta/data-cleaning-plus-eda` cell 14, DIFF (inputs equal at E0), check `values:col0:row=0`.
- Reproducer `results/rootcause/repro/str_replace_regex_default.py`, run in pandas environments (differs from ref: {"p15": true, "p30": false, "pyarrow_backend": false}):
  - p15: rc 0, 0.25 s, max RSS 93 MB: `env: mode=pandas pandas=1.5.3 ; str.replace('(Sr.)', 'sr.'): ['sr. Data Scientist', '(sr.) Analyst']`
  - p30: rc 0, 0.27 s, max RSS 98 MB: `env: mode=pandas pandas=3.0.6 ; str.replace('(Sr.)', 'sr.'): ['Sr. Data Scientist', 'sr. Analyst']`
  - pyarrow_backend: rc 0, 0.28 s, max RSS 98 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; str.replace('(Sr.)', 'sr.'): ['Sr. Data Scientist', 'sr. Analyst']`
  - ref: rc 0, 0.28 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; str.replace('(Sr.)', 'sr.'): ['Sr. Data Scientist', 'sr. Analyst']`

### `loc_setitem_inplace` (representation_only)

pandas 2.0: df.loc[:, col] = values sets in place (keeps the old dtype) instead of replacing the column.

- Cells 1 (strict-clean 1), notebooks 1, by class {"DIFF": 1}; observed severity per cell {"DIFF_not_equal_at_E4": 1}.
- Engines: {"drift:p15": 1}.
- Documented: <https://pandas.pydata.org/docs/whatsnew/v2.0.0.html> ("Changed behavior in setting values with df.loc[:, foo] = bar ... now always attempt to set values inplace").
- Example: p15 `charulatashelar/indian-startup-funding-exploratory-data-analysis` cell 9, DIFF (inputs equal at E0), check `dtype_family:obj/dt:col1`.
- Reproducer `results/rootcause/repro/loc_setitem_inplace.py`, run in pandas environments (differs from ref: {"p15": true, "p30": true, "pyarrow_backend": false}):
  - p15: rc 0, 0.29 s, max RSS 93 MB: `env: mode=pandas pandas=1.5.3 ; dtype after df.loc[:, col] = to_datetime(...): ('datetime64[ns]', ['Timestamp', 'Timestamp'])`
  - p30: rc 0, 0.29 s, max RSS 99 MB: `env: mode=pandas pandas=3.0.6 ; dtype after df.loc[:, col] = to_datetime(...): raised TypeError: Invalid value '<DatetimeArray>`
  - pyarrow_backend: rc 0, 0.27 s, max RSS 98 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; dtype after df.loc[:, col] = to_datetime(...): ('object', ['Timestamp', 'Timestamp'])`
  - ref: rc 0, 0.36 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; dtype after df.loc[:, col] = to_datetime(...): ('object', ['Timestamp', 'Timestamp'])`

### `numeric_only_default` (silent_value_change)

pandas 2.0: numeric_only defaults to False (1.5 silently dropped nuisance columns in groupby/DataFrame reductions).

- Cells 1 (strict-clean 0), notebooks 1, by class {"DIFF": 1}; observed severity per cell {"DIFF_not_equal_at_E4": 1}.
- Engines: {"drift:p15": 1}.
- Documented: <https://pandas.pydata.org/docs/whatsnew/v2.0.0.html> ("Changed default of numeric_only in various DataFrameGroupBy methods; all methods now default to numeric_only=False").
- Example: p15 `sabya40/data-cleaning-and-pandas-for-beginners` cell 16, DIFF (inputs equal at E2), check `shape:[6, 6]/[6, 2]`.
- Reproducer `results/rootcause/repro/numeric_only_default.py`, run in pandas environments (differs from ref: {"p15": true, "p30": false, "pyarrow_backend": false}):
  - p15: rc 0, 0.28 s, max RSS 94 MB: `env: mode=pandas pandas=1.5.3 ; groupby('Month').sum() columns: ['Price']`
  - p30: rc 0, 0.27 s, max RSS 100 MB: `env: mode=pandas pandas=3.0.6 ; groupby('Month').sum() columns: ['Product', 'Price']`
  - pyarrow_backend: rc 0, 0.28 s, max RSS 98 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; groupby('Month').sum() columns: ['Product', 'Price']`
  - ref: rc 0, 0.28 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; groupby('Month').sum() columns: ['Product', 'Price']`

### `to_datetime_consistent_format` (silent_value_change)

pandas 2.0 to_datetime infers ONE format from the first value (1.5 guessed per element); errors='coerce' yields more NaT.

- Cells 1 (strict-clean 1), notebooks 1, by class {"DIFF": 1}; observed severity per cell {"DIFF_not_equal_at_E4": 1}.
- Engines: {"drift:p15": 1}.
- Documented: <https://pandas.pydata.org/docs/whatsnew/v2.0.0.html> ("Datetimes are now parsed with a consistent format").
- Example: p15 `ukveteran/sarima-time-series-eda-predict-jma-sao-paulo` cell 4, DIFF (inputs equal at E0), check `shape:[13, 4]/[36, 4]`.
- Reproducer `results/rootcause/repro/to_datetime_consistent_format.py`, run in pandas environments (differs from ref: {"p15": true, "p30": false, "pyarrow_backend": false}):
  - p15: rc 0, 0.25 s, max RSS 92 MB: `env: mode=pandas pandas=1.5.3 ; to_datetime(errors='coerce'): ['2001-01-13 00:00:00', '2001-02-01 00:00:00', '2001-02-13 00:00:00', '2001-03-01 00:00:00']`
  - p30: rc 0, 0.27 s, max RSS 98 MB: `env: mode=pandas pandas=3.0.6 ; to_datetime(errors='coerce'): ['2001-01-13 00:00:00', 'NaT', 'NaT', 'NaT']`
  - pyarrow_backend: rc 0, 0.28 s, max RSS 98 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; to_datetime(errors='coerce'): ['2001-01-13 00:00:00', 'NaT', 'NaT', 'NaT']`
  - ref: rc 0, 0.27 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; to_datetime(errors='coerce'): ['2001-01-13 00:00:00', 'NaT', 'NaT', 'NaT']`

### `read_csv_big_int_python_ints` (silent_value_change)

pandas 3 read_csv parses integers beyond int64 as Python ints; a chunk holding one such value turns zero-padded code strings ('0078700802378') into ints (2.3.3 kept the chunk as strings).

- Cells 1 (strict-clean 1), notebooks 1, by class {"DIFF": 1}; observed severity per cell {"DIFF_not_equal_at_E4": 1}.
- Engines: {"drift:p30": 1}.
- Documented: <https://pandas.pydata.org/docs/whatsnew/v3.0.0.html> ("Bug in read_csv() with c and python engines reading big integers as strings. Now reads them as python integers. (GH 51295)").
- Note: the change is documented as a bug fix; its effect on leading-zero codes is not.
- Example: p30 `chinstan/notebook249b4f3f5b` cell 2, DIFF (inputs equal at E0), check `values:col0:row=4096`.
- Reproducer `results/rootcause/repro/read_csv_big_int_python_ints.py`, run in pandas environments (differs from ref: {"p15": false, "p30": true, "pyarrow_backend": true}):
  - p15: rc 0, 0.25 s, max RSS 94 MB: `env: mode=pandas pandas=1.5.3 ; dtype: object ; values (repr): ["'0078700802378'", "'99999999999999999999999'"]`
  - p30: rc 0, 0.27 s, max RSS 98 MB: `env: mode=pandas pandas=3.0.6 ; dtype: object ; values (repr): ['78700802378', '99999999999999999999999']`
  - pyarrow_backend: rc 0, 0.29 s, max RSS 99 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; dtype: string[pyarrow] ; values (repr): ["'0078700802378'", "'99999999999999999999999'"]`
  - ref: rc 0, 0.27 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; dtype: object ; values (repr): ["'0078700802378'", "'99999999999999999999999'"]`

### `p3_stricter_validation` (error)

pandas 3 raises on argument combinations 2.3.3 accepted (drop(index=..., axis=1)).

- Cells 1 (strict-clean 0), notebooks 1, by class {"ERR": 1}; observed severity per cell {"error": 1}.
- Engines: {"drift:p30": 1}.
- Documented: no documentation found (searched 2026-10-04).
- Example: p30 `saniaks/melbourne-house-price-eda` cell 26, ERR (inputs equal at E2), check `builtins.ValueError: Cannot specify both 'axis' and 'index'/'columns'`.
- Reproducer `results/rootcause/repro/p3_stricter_validation.py`, run in pandas environments (differs from ref: {"p15": false, "p30": true, "pyarrow_backend": false}):
  - p15: rc 0, 0.27 s, max RSS 93 MB: `env: mode=pandas pandas=1.5.3 ; drop(index=..., axis=1, errors='ignore'): (2, 1)`
  - p30: rc 0, 0.27 s, max RSS 98 MB: `env: mode=pandas pandas=3.0.6 ; drop(index=..., axis=1, errors='ignore'): raised ValueError: Cannot specify both 'axis' and 'index'/'columns'`
  - pyarrow_backend: rc 0, 0.28 s, max RSS 98 MB: `env: mode=pyarrow_backend pandas=2.3.3 ; drop(index=..., axis=1, errors='ignore'): (2, 1)`
  - ref: rc 0, 0.28 s, max RSS 98 MB: `env: mode=pandas pandas=2.3.3 ; drop(index=..., axis=1, errors='ignore'): (2, 1)`

## LaTeX rows for Table 1

Columns: cause & severity & documented & cells & notebooks & engines (cells). Pilot engine counts are from 10 notebooks.

```latex
str default dtype & repr. & yes & 157 & 99 & p3.0 157 \\
value counts naming & repr. & yes & 127 & 36 & p1.5 127 \\
float rounding within tolerance & silent & partial & 96 & 43 & p1.5 79, FD 9, Mo 8 \\
arrow backed dtypes & repr. & partial & 44 & 10 & PA 14, Bo 13, BoD 13, Da 4 \\
engine bug error & error & partial & 36 & 6 & BoD 15, Bo 13, Mo 7, FD 1 \\
engine unsupported api & error & partial & 34 & 9 & Da 26, Bo 4, BoD 3, FD 1 \\
str dtype object checks & silent & yes & 33 & 7 & p3.0 12, PA 6, Bo 5, BoD 5, Da 5 \\
nondeterminism & excl. & no & 30 & 8 & ref 14, dask\#2 6, modin\#2 6, bodo\#2 3, fireducks\#2 1 \\
index not preserved & repr. & no & 30 & 7 & Bo 12, BoD 11, FD 5, Da 1, Mo 1 \\
cow chained assignment & silent & yes & 20 & 15 & p3.0 19, FD 1 \\
int float nullable repr & repr. & no & 20 & 5 & Mo 14, FD 6 \\
row order ties & silent & partial & 18 & 10 & p3.0 6, Mo 5, FD 3, Bo 2, BoD 2 \\
offset alias removed & error & yes & 18 & 4 & p3.0 18 \\
numeric dtype preservation & repr. & yes & 17 & 12 & p1.5 17 \\
lazy partition model & error & yes & 17 & 7 & Da 17 \\
removed deprecated api & error & yes & 15 & 8 & p3.0 15 \\
approximate quantile & silent & partial & 15 & 3 & Bo 5, BoD 5, Da 5 \\
engine bug silent & silent & no & 15 & 4 & BoD 7, Bo 6, Mo 2 \\
get dummies bool & repr. & yes & 14 & 12 & p1.5 14 \\
arrow dtype errors & error & partial & 11 & 4 & PA 5, Bo 2, BoD 2, FD 2 \\
read csv none as na & silent & yes & 10 & 9 & p1.5 10 \\
merge row order & silent & yes & 9 & 7 & p1.5 9 \\
missing sentinel repr & repr. & no & 9 & 5 & FD 9 \\
datetime resolution inference & silent & yes & 8 & 4 & p3.0 8 \\
int key positional fallback removed & error & yes & 7 & 4 & p3.0 7 \\
axis names lost & repr. & no & 7 & 2 & Mo 3, Bo 2, BoD 2 \\
partitioned type inference & error & partial & 5 & 4 & Da 4, Mo 1 \\
describe datetime numeric & silent & yes & 4 & 2 & p1.5 4 \\
setitem incompatible dtype raises & error & yes & 3 & 3 & p3.0 3 \\
str dtype na semantics & silent & partial & 3 & 3 & p3.0 3 \\
str dtype errors & error & yes & 2 & 2 & p3.0 2 \\
engine corr wrong values & silent & no & 2 & 1 & Mo 2 \\
api added later & error & yes & 1 & 1 & p1.5 1 \\
str replace regex default & silent & yes & 1 & 1 & p1.5 1 \\
loc setitem inplace & repr. & yes & 1 & 1 & p1.5 1 \\
numeric only default & silent & yes & 1 & 1 & p1.5 1 \\
to datetime consistent format & silent & yes & 1 & 1 & p1.5 1 \\
read csv big int python ints & silent & partial & 1 & 1 & p3.0 1 \\
p3 stricter validation & error & no & 1 & 1 & p3.0 1 \\
```


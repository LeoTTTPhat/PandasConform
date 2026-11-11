"""D2 cases (pre-declared 2026-11-10, before any D2 run): the disputed engine outcomes replayed WITHOUT the capture
harness. Each case names the configuration of the captured run, the notebook (PandasBench slug at commit ae70611), the
0-based code-cell index, and per value an observation expression evaluated on that value only (`v`), which is applied
identically to the engine object in the uncaptured replay and to the decoded captured values of the original runs.

group: "named"   claims the paper reports as unconfirmed by probes or the reviewers call out (R3 W3);
       "silent"  headline silent behaviours of Section VII (probe-confirmed on synthetic inputs, not on the notebook);
       "rater"   single-rater behaviours named in the lessons (probe-confirmed on synthetic inputs only).
"""

DIAG = ("{'diag': [None if x != x else round(float(x), 6) for x in [v.iloc[i, i] for i in range(v.shape[0])]], "
        "'n_outside': int((v.abs() > 1 + 1e-9).sum().sum())}")

CASES = [
    {"id": "corr_diag_deffro", "group": "named", "configs": ["modin"], "nb": "deffro/eda-is-fun", "cell": 30,
     "values": {"_": DIAG}, "claim": "Modin corr(numeric_only=True) has diagonal entries 5.38 and 8.41 (out of range)"},
    {"id": "corr_diag_ev", "group": "named", "configs": ["modin"],
     "nb": "qnqfbqfqo/electric-vehicle-landscape-in-washington-state", "cell": 8, "values": {"__last__": DIAG},
     "claim": "Modin corr() returns entries outside [-1, 1] (second notebook of the same cause)"},
    {"id": "read_rows_bodo_dw", "group": "named", "configs": ["bodo_dw", "bodo"],
     "nb": "shashi772/data-cleaning-challenge-parsing-dates", "cell": 0,
     "values": {"landslides": "len(v)", "volcanos": "len(v)", "earthquakes": "len(v)"},
     "claim": "Bodo at its default worker count reads 1,692 of 1,693 (and 1,507 of 1,508) rows; one worker reads all"},
    {"id": "approx_quantile_deffro", "group": "silent", "configs": ["bodo"], "nb": "deffro/eda-is-fun", "cell": 12,
     "values": {"_": "len(v)"}, "claim": "Bodo's approximate 0.99 quantile changes which rows a threshold filter keeps"},
    {"id": "approx_quantile_gmanish", "group": "silent", "configs": ["bodo"], "nb": "gmanish/help-ngo-country-clustering",
     "cell": 16, "values": {"Q1": "round(float(v), 6)", "Q3": "round(float(v), 6)", "__last__": "len(v)"},
     "claim": "Bodo's approximate 0.05/0.95 quantiles differ and the outlier filter keeps another row count"},
    {"id": "chained_assignment_tweet", "group": "silent", "configs": ["fireducks"],
     "nb": "ayushsingh5941/tweet-disaster-or-not", "cell": 9,
     "values": {"tweet_train_df": "{str(c): int(v[c].isna().sum()) for c in v.columns}"},
     "claim": "FireDucks' chained fillna(inplace=True) does not write through, without pandas' warning"},
    {"id": "chained_assignment_scout", "group": "silent", "configs": ["fireducks"], "nb": "arjoonn/scout-script-7",
     "cell": 9,
     "values": {"df": "{'ncol': int(v.shape[1]), 'state_cols': [str(c) for c in v.columns if str(c).startswith('state_')][:6], "
                      "'self_employed_na': int(v['self_employed'].isna().sum()) if 'self_employed' in v.columns else None}",
                "st": "str(v)"},
     "claim": "FireDucks chained assignment (cell attributed to cow_chained_assignment)"},
    {"id": "value_counts_cut_modin", "group": "silent", "configs": ["modin"],
     "nb": "trinath003/data-manipulation-visualisation-on-kaggle-datasets", "cell": 11,
     "values": {"__last__": "{'len': int(len(v)), 'zeros': int((v == 0).sum())}"},
     "claim": "Modin's value_counts of a cut result drops the empty bin"},
    {"id": "pivot_table_size_modin", "group": "silent", "configs": ["modin"],
     "nb": "sabya40/data-cleaning-and-pandas-for-beginners", "cell": 22,
     "values": {"dups_category": "{'type': type(v).__name__, 'ndim': int(v.ndim), 'shape': [int(s) for s in v.shape]}"},
     "claim": "Modin's pivot_table(aggfunc='size') returns a DataFrame instead of a Series"},
    {"id": "index_name_modin", "group": "silent", "configs": ["modin"], "nb": "grudd0/mass-shooting-analysis", "cell": 2,
     "values": {"df": "{'index_name': None if v.index.name is None else str(v.index.name)}"},
     "claim": "Modin loses an axis name (index name after df.index = df.Date)"},
    {"id": "apply_side_effects_modin", "group": "rater", "configs": ["modin"], "nb": "shivavashishtha/zomato-eda-tutorial",
     "cell": 33, "values": {"cuisines": "int(len(v))"},
     "claim": "Modin loses the side effects of a function passed to apply (a list extended inside apply)"},
    {"id": "stale_head_bodo", "group": "rater", "configs": ["bodo"], "nb": "kwullum/when-do-traffic-related-deaths-occur",
     "cell": 4, "values": {"__last__": "[str(x) for x in v['Time'].tolist()]"},
     "claim": "Bodo's head() shows data from before a column update"},
    {"id": "stale_groupby_fireducks", "group": "rater", "configs": ["fireducks"],
     "nb": "danielresende/game-of-thrones-battles", "cell": 5,
     "values": {"__last__": "{'shape': [int(s) for s in v.shape], 'index': [str(x) for x in v.index]}"},
     "claim": "FireDucks' group-by after .at assignments uses the data from before them"},
    {"id": "positions_labels_bodo", "group": "rater", "configs": ["bodo"],
     "nb": "snanilim/video-games-sales-analysis-and-visualization", "cell": 2,
     "values": {"data": "{'rows': int(len(v)), 'index_head': [int(x) for x in list(v.index[:3])]}",
                "drop_row_index": "[int(x) for x in list(v)[:3]]"},
     "claim": "Bodo's filtered index holds positions, so drop() removes other rows"},
    {"id": "nunique_fireducks", "group": "rater", "configs": ["fireducks"],
     "nb": "jyotsananegi/melbourne-housing-snapshot-eda", "cell": 4,
     "values": {"__last__": "[int(x) for x in v.iloc[:, 0].tolist()]"},
     "claim": "FireDucks' nunique() counts missing values"},
    {"id": "int_float_slice_fireducks", "group": "named", "configs": ["fireducks"],
     "nb": "kwullum/when-do-traffic-related-deaths-occur", "cell": 2,
     "values": {"__last__": "[str(t) for t in list(v.dtypes)][:3]",
                "df": "{'dtype1': str(v.dtypes.iloc[1]), 'col0_98304': str(v.iloc[98304, 0])}"},
     "claim": "FireDucks returns int64 where pandas has float64 (unconfirmed by probes)"},
]

# configurations: environment, harness engine name (setup code and env vars from src/pconf/engines.py, read only)
CONFIGS = {"pandas": "ref", "modin": "modin", "fireducks": "fireducks", "bodo": "bodo", "bodo_dw": "bodo_dw"}
REPS = 2

# PandasConform: project-level analysis

Generated 2026-10-28T09:31:26Z by `analyze.py` (schema 1). Accepted tags: harness `hd1c421ecb5ee`, compare `d92c8db54d45b`. Every number below is read from `results/summary.json`, which is computed from the per-cell compare outputs and run records of those tags. Shares are pooled over cells; brackets are 95% percentile bootstrap intervals over notebooks (10000 resamples, seed 20261004 combined with a per-series key).

## Campaign status

| campaign | status | records found / expected | compare outputs found / expected | check n_problems |
|---|---|---|---|---|
| pilot (PILOT, 10 notebooks) | complete | 140 / 140 | 170 / 170 | 0 |
| drift | complete | 408 / 408 | 306 / 306 | 0 |
| conf_1x | complete | 816 / 816 | 714 / 714 | 0 |
| timing | complete | 480 / 480 | 0 / 0 | None |
| conf_5x | complete | 145 / 145 | 116 / 116 | 5 |


## Analysis rules applied here (aggregation layer, classify.py unchanged)

- REF_ERR, NONDET (ref vs ref#2) and NOOUT cells are excluded from every view; SETUP_ERR cells are excluded and counted per engine.
- Cells after the first engine TIMEOUT cell of a notebook are post-timeout cascades: counted separately and excluded from the strict and clean-at-E2 views (the all-comparable view keeps them, so that it equals the per-campaign analysis).
- nb_timeout records with summed cell wall_s below 3,600 s are capture-inflated and never engine slowness results.
- CRASH/KILLED, MEMORY, TIMEOUT, NOTRUN and ERR cells and nb_crash/nb_memory/nb_timeout records are counted per engine; FALLBACK flags are counted per view.
- Operation families are the per-cell `families` recorded by classify (attribute names in the cell's AST); 'finest level reached' = finest L with at least half of the cells conformant at <= L.

## RQ3: pandas version drift (drift campaign, 102 notebooks)

**All comparable cells.** Share of cells (%) per class.

| config | notebooks | cells | E0 | <=E2 | <=E4 | DIFF | ERR | TIMEOUT | CRASH | MEMORY | NOTRUN | UNCOMP. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ref#2 | 102 | 2809 | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| p15 | 102 | 2809 | 70.0 [64.7, 75.7] | 80.1 [75.5, 85.1] | 87.3 [83.0, 91.6] | 11.1 [7.1, 15.2] | 1.0 [0.0, 3.2] | 0.0 | 0.0 | 0.0 | 0.0 | 0.5 |
| p30 | 102 | 2811 | 28.1 [24.5, 31.9] | 82.5 [76.6, 87.9] | 83.1 [77.3, 88.3] | 10.3 [6.5, 14.6] | 6.1 [2.7, 10.7] | 0.0 | 0.0 | 0.0 | 0.0 | 0.5 |

**Strict clean-input cells.** Share of cells (%) per class.

| config | notebooks | cells | E0 | <=E2 | <=E4 | DIFF | ERR | TIMEOUT | CRASH | MEMORY | NOTRUN | UNCOMP. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ref#2 | 102 | 2796 | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| p15 | 102 | 1771 | 87.2 [85.0, 89.3] | 92.5 [90.4, 94.3] | 97.6 [96.7, 98.3] | 2.2 [1.4, 3.0] | 0.1 [0.0, 0.2] | 0.0 | 0.0 | 0.0 | 0.0 | 0.2 |
| p30 | 102 | 299 | 49.2 [43.3, 54.7] | 97.0 [94.9, 98.8] | 97.0 [94.9, 98.8] | 0.3 [0.0, 1.1] | 1.3 [0.0, 3.0] | 0.0 | 0.0 | 0.0 | 0.0 | 1.3 |

**Cells clean at E2.** Share of cells (%) per class.

| config | notebooks | cells | E0 | <=E2 | <=E4 | DIFF | ERR | TIMEOUT | CRASH | MEMORY | NOTRUN | UNCOMP. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ref#2 | 102 | 2796 | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| p15 | 102 | 2129 | 79.4 [73.7, 84.1] | 91.7 [89.4, 93.8] | 97.5 [96.6, 98.2] | 2.3 [1.6, 3.1] | 0.0 [0.0, 0.2] | 0.0 | 0.0 | 0.0 | 0.0 | 0.2 |
| p30 | 102 | 2215 | 31.3 [27.5, 35.2] | 94.7 [92.6, 96.3] | 95.0 [93.1, 96.6] | 2.5 [1.6, 3.6] | 2.1 [1.0, 3.7] | 0.0 | 0.0 | 0.0 | 0.0 | 0.3 |

**Failures, fallbacks, exclusions and cascades.**

| config | records by status | ERR / TIMEOUT / CRASH / MEMORY / NOTRUN cells | FALLBACK cells (all / strict / @E2) | excluded REF_ERR / NONDET / NOOUT / SETUP_ERR | post-timeout cascade cells (removed strict / @E2) |
|---|---|---|---|---|---|
| ref#2 | completed 102 | 0 / 0 / 0 / 0 / 0 | 0 / 0 / 0 | 2 / 14 / 783 / 0 | 0 (0 / 0) |
| p15 | completed 102 | 29 / 0 / 0 / 0 / 0 | 0 / 0 / 0 | 2 / 14 / 783 / 0 | 0 (0 / 0) |
| p30 | completed 102 | 172 / 0 / 0 / 0 / 0 | 0 / 0 / 0 | 2 / 14 / 781 / 0 | 0 (0 / 0) |

**First divergence per notebook** (share of notebooks with a divergent cell; median relative position).

| config | at E0 | at E2 | at E4 | median rel. position at E0 / E2 / E4 |
|---|---|---|---|---|
| ref#2 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | - / - / - |
| p15 | 79.4 [71.6, 87.3] | 64.7 [54.9, 73.5] | 42.2 [32.4, 52.0] | 0.22 / 0.31 / 0.41 |
| p30 | 100.0 [100.0, 100.0] | 55.9 [46.1, 65.7] | 52.0 [42.2, 61.8] | 0.08 / 0.34 / 0.30 |

**Operation family x configuration** (clean at E2, post-timeout cascades removed): finest level reached by at least half of the cells, with the number of cells.

| family | ref#2 | p15 | p30 |
|---|---|---|---|
| read | E0 (137) | E0 (136) | E2 (137) |
| merge_join | E0 (125) | E0 (93) | E2 (104) |
| groupby_agg | E0 (295) | E0 (255) | E2 (237) |
| sort | E0 (197) | E0 (167) | E2 (159) |
| string | E0 (48) | E0 (33) | E2 (34) |
| datetime | E0 (66) | E0 (55) | E2 (59) |
| apply_map | E0 (202) | E0 (150) | E2 (147) |
| pivot_reshape | E0 (110) | E0 (78) | E2 (72) |
| describe_stats | E0 (770) | E0 (617) | E2 (592) |
| missing | E0 (227) | E0 (175) | E2 (184) |
| dedup_unique | E0 (80) | E0 (61) | E2 (59) |
| indexing | E0 (816) | E0 (641) | E2 (618) |
| dtype_conv | E0 (97) | E0 (71) | E2 (78) |
| other | E0 (854) | E0 (602) | E0 (721) |

Cross-check against `results/drift/analysis__hd1c421ecb5ee__d92c8db54d45b.json`: 197 checks, 0 mismatches.

## PILOT (10 notebooks; pilot observations, not claims)

**All comparable cells.** Share of cells (%) per class.

| config | notebooks | cells | E0 | <=E2 | <=E4 | DIFF | ERR | TIMEOUT | CRASH | MEMORY | NOTRUN | UNCOMP. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ref#2 | 10 | 404 | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| pyarrow_backend | 10 | 404 | 39.4 [25.6, 58.2] | 63.6 [49.0, 85.6] | 80.2 [64.3, 99.0] | 10.6 [0.5, 17.9] | 8.9 [0.0, 18.4] | 0.0 | 0.0 | 0.0 | 0.0 | 0.2 |
| p15 | 10 | 404 | 74.3 [65.7, 87.7] | 79.2 [70.8, 94.4] | 85.6 [80.2, 98.5] | 14.4 [1.5, 19.8] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| p30 | 10 | 404 | 34.9 [19.9, 50.3] | 88.6 [81.0, 95.3] | 88.9 [81.2, 95.7] | 8.2 [0.0, 16.3] | 2.7 [0.7, 7.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.2 |
| fireducks | 10 | 404 | 62.9 [48.6, 81.2] | 70.8 [57.5, 91.2] | 81.9 [69.9, 97.8] | 9.2 [0.0, 17.2] | 8.7 [1.0, 16.7] | 0.0 | 0.0 | 0.0 | 0.0 | 0.2 |
| bodo | 10 | 404 | 29.7 [15.9, 50.7] | 48.0 [30.7, 73.0] | 62.6 [44.1, 88.9] | 19.3 [2.7, 35.7] | 17.8 [5.2, 30.1] | 0.0 | 0.0 | 0.0 | 0.0 | 0.2 |
| bodo_dw | 10 | 404 | 29.7 [16.0, 51.1] | 47.0 [29.8, 71.8] | 60.9 [43.0, 86.5] | 20.5 [4.7, 36.4] | 18.3 [6.3, 30.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.2 |
| modin | 10 | 419 | 71.6 [57.7, 88.2] | 79.2 [63.1, 96.0] | 80.4 [63.8, 97.4] | 6.9 [1.0, 12.1] | 3.8 [0.0, 6.1] | 0.0 | 0.0 | 0.2 | 8.6 | 0.0 |
| dask | 10 | 404 | 16.3 [6.9, 24.4] | 25.0 [12.1, 36.0] | 29.0 [14.8, 40.7] | 12.1 [3.3, 19.8] | 58.9 [41.5, 80.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| modin#2 | 10 | 419 | 71.6 [57.4, 88.3] | 79.5 [62.7, 96.4] | 80.7 [63.3, 97.8] | 6.7 [0.9, 12.0] | 3.8 [0.0, 6.2] | 0.0 | 0.0 | 0.2 | 8.6 | 0.0 |
| fireducks#2 | 10 | 404 | 62.9 [48.7, 80.9] | 70.8 [57.3, 90.8] | 81.9 [70.2, 97.9] | 9.2 [0.0, 17.2] | 8.7 [1.0, 16.5] | 0.0 | 0.0 | 0.0 | 0.0 | 0.2 |
| bodo#2 | 10 | 404 | 29.7 [15.9, 51.2] | 48.0 [30.7, 72.9] | 62.6 [44.1, 88.9] | 19.3 [2.6, 34.5] | 17.8 [5.1, 30.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.2 |
| dask#2 | 10 | 404 | 16.3 [7.1, 24.6] | 25.0 [12.4, 36.4] | 29.0 [15.3, 40.9] | 12.1 [3.3, 19.8] | 58.9 [41.0, 79.6] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| modin#2~vs~modin | 10 | 366 | 98.4 [96.4, 100.0] | 99.7 [99.0, 100.0] | 99.7 [99.0, 100.0] | 0.3 [0.0, 1.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| fireducks#2~vs~fireducks | 10 | 379 | 97.1 [95.1, 99.1] | 97.1 [95.1, 99.1] | 97.4 [95.6, 99.2] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 2.6 |
| bodo#2~vs~bodo | 10 | 331 | 99.1 [96.6, 100.0] | 99.1 [96.6, 100.0] | 99.1 [96.6, 100.0] | 0.9 [0.0, 3.4] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| dask#2~vs~dask | 10 | 194 | 82.0 [60.6, 93.3] | 82.0 [60.6, 93.3] | 82.0 [60.6, 93.3] | 3.1 [0.9, 7.4] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 14.9 |

**Strict clean-input cells.** Share of cells (%) per class.

| config | notebooks | cells | E0 | <=E2 | <=E4 | DIFF | ERR | TIMEOUT | CRASH | MEMORY | NOTRUN | UNCOMP. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ref#2 | 10 | 404 | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| pyarrow_backend | 10 | 24 | 50.0 [30.0, 63.3] | 66.7 [52.0, 80.0] | 95.8 [87.0, 100.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 4.2 |
| p15 | 10 | 244 | 91.0 [88.3, 94.0] | 96.7 [94.1, 98.7] | 99.2 [97.9, 100.0] | 0.8 [0.0, 2.1] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| p30 | 10 | 30 | 60.0 [33.3, 72.9] | 96.7 [93.5, 100.0] | 96.7 [93.5, 100.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 3.3 |
| fireducks | 10 | 170 | 82.4 [72.7, 87.8] | 92.4 [84.0, 97.4] | 98.2 [96.9, 100.0] | 0.0 [0.0, 0.0] | 1.2 [0.0, 2.8] | 0.0 | 0.0 | 0.0 | 0.0 | 0.6 |
| bodo | 10 | 20 | 40.0 [15.4, 57.7] | 60.0 [37.5, 77.8] | 95.0 [83.3, 100.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 5.0 |
| bodo_dw | 10 | 20 | 40.0 [16.7, 57.7] | 60.0 [35.7, 77.8] | 90.0 [72.2, 100.0] | 5.0 [0.0, 18.8] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 5.0 |
| modin | 10 | 281 | 84.3 [78.3, 90.1] | 94.3 [90.8, 97.9] | 95.4 [91.8, 99.0] | 3.2 [0.9, 5.8] | 1.4 [0.0, 3.6] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| dask | 10 | 20 | 40.0 [20.0, 54.5] | 55.0 [36.8, 70.6] | 65.0 [52.4, 78.9] | 5.0 [0.0, 14.3] | 30.0 [14.3, 47.4] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| modin#2 | 10 | 281 | 84.3 [78.3, 90.1] | 94.7 [91.1, 98.0] | 95.7 [92.1, 99.1] | 2.8 [0.9, 5.0] | 1.4 [0.0, 3.6] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| fireducks#2 | 10 | 170 | 82.4 [72.5, 87.9] | 92.4 [83.6, 97.5] | 98.2 [96.9, 100.0] | 0.0 [0.0, 0.0] | 1.2 [0.0, 2.8] | 0.0 | 0.0 | 0.0 | 0.0 | 0.6 |
| bodo#2 | 10 | 20 | 40.0 [16.7, 57.7] | 60.0 [36.8, 78.3] | 95.0 [83.3, 100.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 5.0 |
| dask#2 | 10 | 20 | 40.0 [21.0, 54.5] | 55.0 [36.8, 71.4] | 65.0 [50.0, 78.9] | 5.0 [0.0, 14.3] | 30.0 [14.3, 47.1] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| modin#2~vs~modin | 10 | 366 | 98.4 [96.5, 100.0] | 99.7 [99.0, 100.0] | 99.7 [99.0, 100.0] | 0.3 [0.0, 1.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| fireducks#2~vs~fireducks | 10 | 370 | 98.9 [97.6, 99.7] | 98.9 [97.6, 99.7] | 99.2 [98.2, 100.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.8 |
| bodo#2~vs~bodo | 10 | 329 | 99.1 [96.6, 100.0] | 99.1 [96.6, 100.0] | 99.1 [96.6, 100.0] | 0.9 [0.0, 3.4] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| dask#2~vs~dask | 10 | 161 | 93.2 [83.1, 96.2] | 93.2 [83.1, 96.2] | 93.2 [83.1, 96.2] | 3.7 [1.2, 9.8] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 3.1 |

**Cells clean at E2.** Share of cells (%) per class.

| config | notebooks | cells | E0 | <=E2 | <=E4 | DIFF | ERR | TIMEOUT | CRASH | MEMORY | NOTRUN | UNCOMP. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ref#2 | 10 | 404 | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| pyarrow_backend | 10 | 134 | 38.8 [22.8, 54.2] | 89.6 [77.4, 96.2] | 97.0 [92.2, 100.0] | 2.2 [0.0, 5.7] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.7 |
| p15 | 10 | 252 | 88.9 [84.4, 92.9] | 96.4 [93.9, 98.3] | 98.8 [97.3, 100.0] | 1.2 [0.0, 2.7] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| p30 | 10 | 353 | 36.8 [23.7, 52.0] | 94.1 [92.1, 96.5] | 94.3 [92.2, 96.7] | 2.8 [0.0, 5.5] | 2.5 [0.8, 5.3] | 0.0 | 0.0 | 0.0 | 0.0 | 0.3 |
| fireducks | 10 | 183 | 78.7 [67.9, 85.6] | 92.3 [84.7, 97.0] | 97.8 [96.5, 99.3] | 0.0 [0.0, 0.0] | 1.6 [0.0, 3.3] | 0.0 | 0.0 | 0.0 | 0.0 | 0.5 |
| bodo | 10 | 113 | 28.3 [14.5, 45.9] | 76.1 [62.3, 85.4] | 86.7 [74.0, 96.7] | 6.2 [0.0, 14.9] | 6.2 [1.4, 14.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.9 |
| bodo_dw | 10 | 110 | 29.1 [15.4, 47.3] | 76.4 [64.6, 85.4] | 88.2 [75.7, 97.5] | 7.3 [0.0, 16.9] | 3.6 [0.0, 6.8] | 0.0 | 0.0 | 0.0 | 0.0 | 0.9 |
| modin | 10 | 338 | 84.9 [79.2, 90.4] | 94.1 [90.8, 97.3] | 95.0 [91.6, 98.2] | 2.7 [0.8, 5.4] | 2.1 [0.0, 3.8] | 0.0 | 0.0 | 0.3 | 0.0 | 0.0 |
| dask | 10 | 77 | 35.1 [19.7, 50.0] | 62.3 [56.4, 66.7] | 64.9 [59.1, 69.1] | 11.7 [0.0, 21.4] | 23.4 [13.4, 37.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| modin#2 | 10 | 338 | 84.9 [79.1, 90.3] | 94.4 [91.1, 97.6] | 95.3 [91.9, 98.4] | 2.4 [0.7, 4.6] | 2.1 [0.0, 3.8] | 0.0 | 0.0 | 0.3 | 0.0 | 0.0 |
| fireducks#2 | 10 | 183 | 78.7 [67.4, 85.7] | 92.3 [84.6, 97.1] | 97.8 [96.4, 99.3] | 0.0 [0.0, 0.0] | 1.6 [0.0, 3.3] | 0.0 | 0.0 | 0.0 | 0.0 | 0.5 |
| bodo#2 | 10 | 113 | 28.3 [14.8, 46.2] | 76.1 [62.7, 85.4] | 86.7 [73.8, 96.6] | 6.2 [0.0, 15.0] | 6.2 [1.4, 14.3] | 0.0 | 0.0 | 0.0 | 0.0 | 0.9 |
| dask#2 | 10 | 77 | 35.1 [19.5, 50.0] | 62.3 [56.5, 66.7] | 64.9 [59.1, 69.0] | 11.7 [0.0, 21.5] | 23.4 [13.2, 37.2] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| modin#2~vs~modin | 10 | 366 | 98.4 [96.4, 100.0] | 99.7 [99.0, 100.0] | 99.7 [99.0, 100.0] | 0.3 [0.0, 1.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| fireducks#2~vs~fireducks | 10 | 370 | 98.9 [97.6, 99.7] | 98.9 [97.6, 99.7] | 99.2 [98.2, 100.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.8 |
| bodo#2~vs~bodo | 10 | 329 | 99.1 [96.5, 100.0] | 99.1 [96.5, 100.0] | 99.1 [96.5, 100.0] | 0.9 [0.0, 3.5] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| dask#2~vs~dask | 10 | 161 | 93.2 [83.3, 96.2] | 93.2 [83.3, 96.2] | 93.2 [83.3, 96.2] | 3.7 [1.2, 9.5] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 3.1 |

**Failures, fallbacks, exclusions and cascades.**

| config | records by status | ERR / TIMEOUT / CRASH / MEMORY / NOTRUN cells | FALLBACK cells (all / strict / @E2) | excluded REF_ERR / NONDET / NOOUT / SETUP_ERR | post-timeout cascade cells (removed strict / @E2) |
|---|---|---|---|---|---|
| ref#2 | completed 10 | 0 / 0 / 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 82 / 0 | 0 (0 / 0) |
| pyarrow_backend | completed 10 | 36 / 0 / 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 82 / 0 | 0 (0 / 0) |
| p15 | completed 10 | 0 / 0 / 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 82 / 0 | 0 (0 / 0) |
| p30 | completed 10 | 11 / 0 / 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 82 / 0 | 0 (0 / 0) |
| fireducks | completed 10 | 35 / 0 / 0 / 0 / 0 | 158 / 56 / 61 | 0 / 0 / 82 / 0 | 0 (0 / 0) |
| bodo | completed 10 | 72 / 0 / 0 / 0 / 0 | 210 / 2 / 54 | 0 / 0 / 82 / 0 | 0 (0 / 0) |
| bodo_dw | completed 10 | 74 / 0 / 0 / 0 / 0 | 210 / 2 / 54 | 0 / 0 / 82 / 0 | 0 (0 / 0) |
| modin | completed 9, nb_memory 1 | 16 / 0 / 0 / 1 / 36 | 13 / 13 / 13 | 0 / 0 / 67 / 0 | 0 (0 / 0) |
| dask | completed 10 | 238 / 0 / 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 82 / 0 | 0 (0 / 0) |
| modin#2 | completed 9, nb_memory 1 | 16 / 0 / 0 / 1 / 36 | 13 / 13 / 13 | 0 / 0 / 67 / 0 | 0 (0 / 0) |
| fireducks#2 | completed 10 | 35 / 0 / 0 / 0 / 0 | 158 / 56 / 61 | 0 / 0 / 82 / 0 | 0 (0 / 0) |
| bodo#2 | completed 10 | 72 / 0 / 0 / 0 / 0 | 210 / 2 / 54 | 0 / 0 / 82 / 0 | 0 (0 / 0) |
| dask#2 | completed 10 | 238 / 0 / 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 82 / 0 | 0 (0 / 0) |
| modin#2~vs~modin | - | 0 / 0 / 0 / 0 / 0 | 13 / 13 / 13 | 16 / 0 / 67 / 0 | 0 (0 / 0) |
| fireducks#2~vs~fireducks | - | 0 / 0 / 0 / 0 / 0 | 156 / 155 / 155 | 25 / 0 / 82 / 0 | 0 (0 / 0) |
| bodo#2~vs~bodo | - | 0 / 0 / 0 / 0 / 0 | 179 / 179 / 179 | 72 / 0 / 83 / 0 | 0 (0 / 0) |
| dask#2~vs~dask | - | 0 / 0 / 0 / 0 / 0 | 0 / 0 / 0 | 209 / 0 / 83 / 0 | 0 (0 / 0) |

**First divergence per notebook** (share of notebooks with a divergent cell; median relative position).

| config | at E0 | at E2 | at E4 | median rel. position at E0 / E2 / E4 |
|---|---|---|---|---|
| ref#2 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | - / - / - |
| pyarrow_backend | 100.0 [100.0, 100.0] | 70.0 [40.0, 100.0] | 50.0 [20.0, 80.0] | 0.07 / 0.05 / 0.42 |
| p15 | 80.0 [50.0, 100.0] | 60.0 [30.0, 90.0] | 40.0 [10.0, 70.0] | 0.41 / 0.46 / 0.52 |
| p30 | 100.0 [100.0, 100.0] | 80.0 [50.0, 100.0] | 80.0 [50.0, 100.0] | 0.07 / 0.45 / 0.45 |
| fireducks | 100.0 [100.0, 100.0] | 70.0 [40.0, 100.0] | 60.0 [30.0, 90.0] | 0.13 / 0.08 / 0.45 |
| bodo | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 90.0 [70.0, 100.0] | 0.07 / 0.09 / 0.40 |
| bodo_dw | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 90.0 [70.0, 100.0] | 0.07 / 0.09 / 0.19 |
| modin | 90.0 [70.0, 100.0] | 70.0 [40.0, 100.0] | 60.0 [30.0, 90.0] | 0.23 / 0.50 / 0.38 |
| dask | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 0.07 / 0.09 / 0.12 |
| modin#2 | 90.0 [70.0, 100.0] | 70.0 [40.0, 100.0] | 60.0 [30.0, 90.0] | 0.23 / 0.50 / 0.38 |
| fireducks#2 | 100.0 [100.0, 100.0] | 70.0 [40.0, 100.0] | 60.0 [30.0, 90.0] | 0.13 / 0.08 / 0.45 |
| bodo#2 | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 90.0 [70.0, 100.0] | 0.07 / 0.09 / 0.40 |
| dask#2 | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 0.07 / 0.09 / 0.12 |
| modin#2~vs~modin | 30.0 [0.0, 60.0] | 10.0 [0.0, 30.0] | 10.0 [0.0, 30.0] | 0.15 / 0.95 / 0.95 |
| fireducks#2~vs~fireducks | 50.0 [20.0, 80.0] | 50.0 [20.0, 80.0] | 50.0 [20.0, 80.0] | 0.67 / 0.67 / 0.67 |
| bodo#2~vs~bodo | 10.0 [0.0, 30.0] | 10.0 [0.0, 30.0] | 10.0 [0.0, 30.0] | 0.30 / 0.30 / 0.30 |
| dask#2~vs~dask | 90.0 [70.0, 100.0] | 90.0 [70.0, 100.0] | 90.0 [70.0, 100.0] | 0.14 / 0.14 / 0.14 |

**Operation family x configuration** (clean at E2, post-timeout cascades removed): finest level reached by at least half of the cells, with the number of cells.

| family | ref#2 | pyarrow_backend | p15 | p30 | fireducks | bodo | bodo_dw | modin | dask | modin#2 | fireducks#2 | bodo#2 | dask#2 | modin#2~vs~modin | fireducks#2~vs~fireducks | bodo#2~vs~bodo | dask#2~vs~dask |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| read | E0 (12) | E3 (12) | E0 (12) | E2 (12) | E0 (12) | E3 (12) | E3 (12) | E0 (12) | >E4 (12) | E0 (12) | E0 (12) | E3 (12) | >E4 (12) | E0 (11) | E0 (12) | E0 (12) | E0 (10) |
| merge_join | E0 (8) | E2 (3) | E0 (7) | E2 (7) | E0 (3) | E2 (3) | E2 (3) | E0 (8) | E2 (1) | E0 (8) | E0 (3) | E2 (3) | E2 (1) | E0 (8) | E0 (8) | E0 (8) | E0 (3) |
| groupby_agg | E0 (15) | E2 (6) | E0 (14) | E2 (15) | E0 (8) | >E4 (5) | >E4 (3) | E0 (12) | E2 (4) | E0 (12) | E0 (8) | >E4 (5) | E2 (4) | E0 (15) | E0 (13) | E0 (6) | E0 (5) |
| sort | E0 (17) | E2 (7) | E0 (12) | E2 (17) | E1 (10) | E2 (5) | E2 (5) | E0 (13) | >E4 (1) | E0 (13) | E1 (10) | E2 (5) | >E4 (1) | E0 (15) | E0 (17) | E0 (14) | - |
| string | E0 (8) | E3 (1) | E0 (2) | E2 (8) | E2 (2) | >E4 (1) | >E4 (1) | E0 (6) | - | E0 (6) | E2 (2) | >E4 (1) | - | E0 (8) | E0 (6) | - | E0 (2) |
| datetime | E0 (14) | E2 (6) | E0 (12) | E2 (12) | E0 (6) | E2 (6) | E2 (6) | E0 (12) | E2 (1) | E0 (12) | E0 (6) | E2 (6) | E2 (1) | E0 (14) | E0 (14) | E0 (10) | E0 (6) |
| apply_map | E0 (12) | E2 (4) | E0 (5) | E2 (10) | E0 (4) | E2 (4) | E2 (4) | E0 (9) | E0 (1) | E0 (9) | E0 (4) | E2 (4) | E0 (1) | E0 (12) | E0 (9) | E0 (4) | E0 (1) |
| pivot_reshape | E0 (21) | E2 (10) | E0 (14) | E2 (15) | E0 (12) | E2 (8) | E2 (8) | E2 (20) | >E4 (5) | E2 (20) | E0 (12) | E2 (8) | >E4 (5) | E0 (19) | E0 (20) | E0 (16) | - |
| describe_stats | E0 (79) | E2 (30) | E0 (64) | E2 (70) | E0 (45) | E2 (27) | E2 (25) | E0 (70) | E2 (14) | E0 (70) | E0 (45) | E2 (27) | E2 (14) | E0 (79) | E0 (75) | E0 (67) | E0 (39) |
| missing | E0 (23) | E0 (6) | E0 (19) | E2 (21) | E0 (9) | E2 (4) | E2 (4) | E0 (18) | E0 (4) | E0 (18) | E0 (9) | E2 (4) | E0 (4) | E0 (23) | E0 (23) | E0 (20) | E0 (7) |
| dedup_unique | E0 (1) | E2 (1) | E0 (1) | E2 (1) | E0 (1) | E2 (1) | E4 (1) | E0 (1) | E2 (1) | E0 (1) | E0 (1) | E2 (1) | E2 (1) | E0 (1) | E0 (1) | E0 (1) | E0 (1) |
| indexing | E0 (96) | E2 (34) | E0 (66) | E2 (72) | E0 (47) | E2 (30) | E2 (28) | E0 (84) | E2 (16) | E0 (84) | E0 (47) | E2 (30) | E2 (16) | E0 (89) | E0 (89) | E0 (77) | E0 (22) |
| dtype_conv | E0 (22) | E2 (6) | E0 (14) | >E4 (19) | E0 (10) | >E4 (5) | >E4 (5) | E0 (15) | >E4 (5) | E0 (15) | E0 (10) | >E4 (5) | >E4 (5) | E0 (20) | E0 (20) | E0 (12) | E0 (11) |
| other | E0 (163) | E0 (44) | E0 (72) | E0 (151) | E0 (57) | E0 (34) | E0 (33) | E0 (130) | E0 (26) | E0 (130) | E0 (57) | E0 (34) | E0 (26) | E0 (138) | E0 (144) | E0 (133) | E0 (67) |

Cross-check against `results/pilot/analysis__hd1c421ecb5ee__d92c8db54d45b.json`: 1107 checks, 0 mismatches.

## RQ1: engine conformance (conf_1x)

**All comparable cells.** Share of cells (%) per class.

| config | notebooks | cells | E0 | <=E2 | <=E4 | DIFF | ERR | TIMEOUT | CRASH | MEMORY | NOTRUN | UNCOMP. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ref#2 | 102 | 2809 | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| pyarrow_backend | 102 | 2809 | 27.7 [23.9, 32.0] | 62.7 [56.8, 69.0] | 77.8 [71.2, 84.8] | 15.1 [9.8, 20.5] | 6.6 [2.7, 11.3] | 0.0 | 0.0 | 0.0 | 0.0 | 0.6 |
| fireducks | 102 | 2811 | 52.3 [46.3, 58.3] | 63.1 [56.1, 70.1] | 72.3 [64.5, 79.9] | 12.0 [8.1, 16.3] | 14.3 [6.9, 23.0] | 0.2 | 0.0 | 0.0 | 0.4 | 0.7 |
| bodo | 102 | 2837 | 14.4 [10.9, 19.0] | 34.3 [27.8, 41.2] | 44.9 [36.9, 53.5] | 14.4 [9.8, 19.1] | 34.5 [25.4, 44.2] | 0.1 | 0.2 | 0.0 | 5.5 | 0.3 |
| modin | 102 | 2840 | 74.8 [69.7, 79.5] | 83.0 [77.7, 87.9] | 84.6 [79.3, 89.4] | 6.9 [4.5, 9.4] | 4.5 [2.5, 6.8] | 0.1 | 0.0 | 0.2 | 3.6 | 0.1 |
| dask | 102 | 2819 | 11.7 [9.1, 14.6] | 18.0 [13.8, 22.7] | 20.2 [15.7, 25.2] | 8.2 [5.6, 11.0] | 71.6 [64.8, 77.7] | 0.0 | 0.0 | 0.0 | 0.0 | 0.1 |
| bodo_dw | 102 | 2861 | 12.8 [9.3, 17.6] | 29.0 [22.7, 36.3] | 39.0 [30.9, 47.9] | 11.8 [8.0, 16.1] | 40.6 [30.3, 51.0] | 0.3 | 0.2 | 0.0 | 7.8 | 0.3 |

**Strict clean-input cells.** Share of cells (%) per class.

| config | notebooks | cells | E0 | <=E2 | <=E4 | DIFF | ERR | TIMEOUT | CRASH | MEMORY | NOTRUN | UNCOMP. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ref#2 | 102 | 2796 | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| pyarrow_backend | 102 | 291 | 54.3 [47.3, 60.3] | 69.8 [63.9, 74.8] | 94.8 [90.6, 98.0] | 1.7 [0.3, 3.8] | 1.7 [0.0, 5.0] | 0.0 | 0.0 | 0.0 | 0.0 | 1.7 |
| fireducks | 102 | 1078 | 78.7 [75.0, 81.6] | 88.3 [84.5, 91.4] | 95.1 [93.2, 96.6] | 2.7 [1.6, 4.0] | 0.8 [0.3, 1.5] | 0.2 | 0.1 | 0.0 | 0.0 | 1.1 |
| bodo | 102 | 247 | 41.7 [35.2, 47.5] | 63.6 [56.3, 70.2] | 85.0 [79.9, 89.9] | 4.0 [1.7, 6.8] | 8.9 [5.1, 13.0] | 0.0 | 0.4 | 0.0 | 0.0 | 1.6 |
| modin | 102 | 2209 | 86.5 [84.1, 88.6] | 94.7 [92.9, 96.1] | 96.2 [94.7, 97.3] | 1.9 [1.3, 2.7] | 1.7 [0.8, 2.8] | 0.0 | 0.0 | 0.1 | 0.0 | 0.0 |
| dask | 102 | 260 | 39.2 [34.8, 43.6] | 53.5 [46.6, 60.0] | 60.4 [54.0, 66.5] | 1.9 [0.4, 3.7] | 37.7 [31.3, 44.2] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| bodo_dw | 102 | 239 | 41.0 [34.8, 46.9] | 61.9 [54.7, 68.8] | 81.6 [76.1, 86.7] | 5.9 [3.0, 9.1] | 8.4 [5.0, 12.0] | 2.5 | 0.0 | 0.0 | 0.0 | 1.7 |

**Cells clean at E2.** Share of cells (%) per class.

| config | notebooks | cells | E0 | <=E2 | <=E4 | DIFF | ERR | TIMEOUT | CRASH | MEMORY | NOTRUN | UNCOMP. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ref#2 | 102 | 2796 | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| pyarrow_backend | 102 | 1091 | 36.3 [31.3, 41.4] | 88.3 [85.1, 90.7] | 96.0 [94.2, 97.4] | 2.6 [1.5, 3.8] | 0.9 [0.3, 1.9] | 0.0 | 0.0 | 0.0 | 0.0 | 0.5 |
| fireducks | 102 | 1248 | 72.0 [67.6, 76.1] | 88.6 [85.2, 91.4] | 94.9 [93.2, 96.3] | 2.7 [1.7, 3.9] | 1.0 [0.4, 1.6] | 0.2 | 0.1 | 0.0 | 0.0 | 1.1 |
| bodo | 102 | 753 | 28.2 [23.5, 33.6] | 72.0 [66.9, 76.3] | 82.2 [77.3, 86.6] | 6.0 [3.8, 8.5] | 10.8 [7.1, 15.3] | 0.1 | 0.3 | 0.0 | 0.0 | 0.7 |
| modin | 102 | 2332 | 85.0 [82.3, 87.4] | 94.5 [92.8, 95.8] | 95.9 [94.5, 97.0] | 2.0 [1.4, 2.8] | 1.8 [1.0, 2.9] | 0.0 | 0.0 | 0.2 | 0.0 | 0.0 |
| dask | 102 | 545 | 36.0 [30.6, 41.4] | 61.7 [54.5, 67.7] | 65.5 [59.1, 71.0] | 6.2 [3.8, 8.9] | 28.3 [22.4, 35.3] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| bodo_dw | 102 | 682 | 28.3 [23.3, 34.1] | 70.8 [65.4, 75.5] | 81.1 [75.8, 85.9] | 6.5 [4.1, 9.4] | 10.6 [6.6, 15.4] | 1.0 | 0.1 | 0.0 | 0.0 | 0.7 |

**Failures, fallbacks, exclusions and cascades.**

| config | records by status | ERR / TIMEOUT / CRASH / MEMORY / NOTRUN cells | FALLBACK cells (all / strict / @E2) | excluded REF_ERR / NONDET / NOOUT / SETUP_ERR | post-timeout cascade cells (removed strict / @E2) |
|---|---|---|---|---|---|
| ref#2 | completed 102 | 0 / 0 / 0 / 0 / 0 | 0 / 0 / 0 | 2 / 14 / 783 / 0 | 0 (0 / 0) |
| pyarrow_backend | completed 102 | 184 / 0 / 0 / 0 / 0 | 0 / 0 / 0 | 2 / 14 / 783 / 0 | 0 (0 / 0) |
| fireducks | completed 101, nb_crash 1 | 402 / 7 / 1 / 0 / 10 | 856 / 336 / 394 | 2 / 14 / 781 / 0 | 40 (5 / 6) |
| bodo | completed 94, nb_crash 6, nb_memory 1, nb_timeout 1 | 979 / 3 / 6 / 1 / 156 | 1010 / 62 / 301 | 2 / 14 / 755 / 0 | 15 (0 / 2) |
| modin | completed 94, nb_memory 8 | 127 / 4 / 0 / 7 / 102 | 138 / 114 / 120 | 2 / 14 / 752 / 0 | 12 (3 / 3) |
| dask | completed 102 | 2018 / 0 / 0 / 0 / 0 | 0 / 0 / 0 | 2 / 14 / 773 / 0 | 0 (0 / 0) |
| bodo_dw | completed 93, nb_crash 6, nb_memory 1, nb_timeout 2 | 1161 / 9 / 6 / 1 / 222 | 824 / 61 / 268 | 2 / 14 / 731 / 0 | 331 (3 / 4) |

**First divergence per notebook** (share of notebooks with a divergent cell; median relative position).

| config | at E0 | at E2 | at E4 | median rel. position at E0 / E2 / E4 |
|---|---|---|---|---|
| ref#2 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | - / - / - |
| pyarrow_backend | 100.0 [100.0, 100.0] | 84.3 [77.5, 91.2] | 58.8 [49.0, 68.6] | 0.08 / 0.10 / 0.36 |
| fireducks | 99.0 [97.1, 100.0] | 78.4 [70.6, 86.3] | 65.7 [55.9, 74.5] | 0.12 / 0.11 / 0.24 |
| bodo | 100.0 [100.0, 100.0] | 97.1 [93.1, 100.0] | 92.2 [86.3, 97.1] | 0.08 / 0.11 / 0.19 |
| modin | 88.2 [81.4, 94.1] | 63.7 [54.9, 72.5] | 55.9 [46.1, 65.7] | 0.21 / 0.38 / 0.36 |
| dask | 100.0 [100.0, 100.0] | 98.0 [95.1, 100.0] | 98.0 [95.1, 100.0] | 0.08 / 0.09 / 0.11 |
| bodo_dw | 100.0 [100.0, 100.0] | 97.1 [93.1, 100.0] | 92.2 [86.3, 97.1] | 0.08 / 0.11 / 0.15 |

**Operation family x configuration** (clean at E2, post-timeout cascades removed): finest level reached by at least half of the cells, with the number of cells.

| family | ref#2 | pyarrow_backend | fireducks | bodo | modin | dask | bodo_dw |
|---|---|---|---|---|---|---|---|
| read | E0 (137) | E3 (135) | E2 (135) | E3 (133) | E0 (132) | >E4 (134) | E3 (130) |
| merge_join | E0 (125) | E2 (47) | E2 (55) | >E4 (24) | E0 (94) | >E4 (19) | E4 (21) |
| groupby_agg | E0 (295) | E2 (82) | E0 (126) | >E4 (69) | E0 (218) | E2 (45) | >E4 (64) |
| sort | E0 (197) | E2 (72) | E1 (89) | E4 (40) | E1 (143) | >E4 (21) | E4 (38) |
| string | E0 (48) | E3 (11) | E0 (17) | >E4 (10) | E0 (36) | >E4 (6) | >E4 (8) |
| datetime | E0 (66) | E2 (26) | E0 (35) | E2 (24) | E0 (55) | E4 (12) | E2 (24) |
| apply_map | E0 (202) | E2 (52) | E2 (81) | E2 (39) | E0 (155) | >E4 (20) | E2 (35) |
| pivot_reshape | E0 (110) | E2 (41) | E0 (45) | E2 (25) | E0 (76) | >E4 (17) | E2 (22) |
| describe_stats | E0 (770) | E2 (252) | E0 (319) | E2 (185) | E0 (632) | E2 (119) | E2 (162) |
| missing | E0 (227) | E0 (31) | E0 (63) | E2 (21) | E0 (179) | E0 (15) | E2 (19) |
| dedup_unique | E0 (80) | E2 (17) | E0 (27) | E2 (18) | E0 (70) | >E4 (7) | E2 (15) |
| indexing | E0 (816) | E2 (304) | E0 (371) | E2 (211) | E0 (682) | E2 (137) | E2 (189) |
| dtype_conv | E0 (97) | E2 (29) | E2 (43) | >E4 (20) | E0 (69) | >E4 (16) | >E4 (20) |
| other | E0 (854) | E0 (384) | E0 (396) | E0 (236) | E0 (733) | E0 (184) | E0 (211) |

Cross-check against `results/conf_1x/analysis__hd1c421ecb5ee__d92c8db54d45b.json`: 457 checks, 0 mismatches.

## conf_5x (5x scale, 29 of the 30 conf5x notebooks; not run: jirakst/book-recommendation (not prepared at 5x: its PandasBench scaling cell calls read_csv(error_bad_lines=...), which pandas 2.0 removed))

**All comparable cells.** Share of cells (%) per class.

| config | notebooks | cells | E0 | <=E2 | <=E4 | DIFF | ERR | TIMEOUT | CRASH | MEMORY | NOTRUN | UNCOMP. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ref#2 | 29 | 818 | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| modin | 29 | 824 | 77.4 [69.1, 85.8] | 85.2 [77.9, 92.0] | 86.5 [79.2, 93.2] | 6.7 [2.7, 10.6] | 3.0 [1.1, 5.6] | 0.5 | 0.0 | 0.1 | 3.2 | 0.0 |
| fireducks | 29 | 821 | 62.9 [55.5, 69.9] | 70.2 [63.1, 76.5] | 79.8 [71.8, 87.0] | 10.1 [5.0, 15.5] | 5.7 [1.9, 11.3] | 0.4 | 0.2 | 0.0 | 1.8 | 1.9 |
| bodo | 29 | 827 | 16.2 [7.6, 29.1] | 34.5 [21.6, 49.0] | 45.5 [30.2, 62.4] | 8.9 [4.5, 14.8] | 41.1 [23.8, 57.6] | 0.1 | 0.4 | 0.0 | 2.1 | 1.9 |

**Strict clean-input cells.** Share of cells (%) per class.

| config | notebooks | cells | E0 | <=E2 | <=E4 | DIFF | ERR | TIMEOUT | CRASH | MEMORY | NOTRUN | UNCOMP. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ref#2 | 29 | 818 | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| modin | 29 | 549 | 90.2 [86.9, 92.9] | 95.3 [92.7, 97.3] | 96.2 [93.6, 98.2] | 1.6 [0.8, 2.7] | 1.8 [0.3, 4.1] | 0.2 | 0.0 | 0.2 | 0.0 | 0.0 |
| fireducks | 29 | 343 | 81.6 [76.6, 85.8] | 87.2 [81.9, 91.4] | 93.9 [91.0, 96.5] | 3.5 [1.6, 5.8] | 0.9 [0.0, 1.9] | 0.0 | 0.6 | 0.0 | 0.0 | 1.2 |
| bodo | 29 | 60 | 36.7 [26.0, 46.8] | 61.7 [48.9, 74.5] | 88.3 [78.1, 97.7] | 1.7 [0.0, 5.9] | 10.0 [1.7, 20.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

**Cells clean at E2.** Share of cells (%) per class.

| config | notebooks | cells | E0 | <=E2 | <=E4 | DIFF | ERR | TIMEOUT | CRASH | MEMORY | NOTRUN | UNCOMP. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ref#2 | 29 | 818 | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| modin | 29 | 629 | 87.3 [81.6, 91.5] | 95.1 [92.8, 97.0] | 95.9 [93.6, 97.7] | 1.4 [0.7, 2.4] | 2.4 [0.8, 4.4] | 0.2 | 0.0 | 0.2 | 0.0 | 0.0 |
| fireducks | 29 | 371 | 76.5 [68.0, 82.9] | 87.1 [82.2, 91.2] | 93.8 [91.2, 96.2] | 3.8 [1.9, 5.9] | 0.8 [0.0, 1.8] | 0.0 | 0.5 | 0.0 | 0.0 | 1.1 |
| bodo | 29 | 205 | 28.8 [20.5, 38.3] | 73.2 [62.2, 80.3] | 87.3 [79.1, 93.2] | 4.4 [1.4, 8.4] | 7.3 [3.0, 13.1] | 0.5 | 0.5 | 0.0 | 0.0 | 0.0 |

**Failures, fallbacks, exclusions and cascades.**

| config | records by status | ERR / TIMEOUT / CRASH / MEMORY / NOTRUN cells | FALLBACK cells (all / strict / @E2) | excluded REF_ERR / NONDET / NOOUT / SETUP_ERR | post-timeout cascade cells (removed strict / @E2) |
|---|---|---|---|---|---|
| ref#2 | completed 29 | 0 / 0 / 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 178 / 0 | 0 (0 / 0) |
| modin | completed 28, nb_memory 1 | 25 / 4 / 0 / 1 / 26 | 41 / 36 / 40 | 0 / 0 / 172 / 0 | 12 (3 / 3) |
| fireducks | completed 27, nb_crash 2 | 47 / 3 / 2 / 0 / 15 | 270 / 103 / 113 | 0 / 0 / 175 / 0 | 20 (2 / 2) |
| bodo | completed 26, nb_crash 3 | 340 / 1 / 3 / 0 / 17 | 265 / 14 / 83 | 0 / 0 / 169 / 0 | 13 (0 / 1) |

**First divergence per notebook** (share of notebooks with a divergent cell; median relative position).

| config | at E0 | at E2 | at E4 | median rel. position at E0 / E2 / E4 |
|---|---|---|---|---|
| ref#2 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | - / - / - |
| modin | 82.8 [69.0, 96.6] | 58.6 [41.4, 75.9] | 51.7 [34.5, 69.0] | 0.39 / 0.50 / 0.50 |
| fireducks | 96.6 [89.7, 100.0] | 82.8 [69.0, 96.6] | 65.5 [48.3, 82.8] | 0.12 / 0.11 / 0.22 |
| bodo | 100.0 [100.0, 100.0] | 96.6 [89.7, 100.0] | 89.7 [79.3, 100.0] | 0.07 / 0.10 / 0.22 |

**Operation family x configuration** (clean at E2, post-timeout cascades removed): finest level reached by at least half of the cells, with the number of cells.

| family | ref#2 | modin | fireducks | bodo |
|---|---|---|---|---|
| read | E0 (36) | E0 (36) | E2 (36) | E3 (36) |
| merge_join | E0 (30) | E0 (26) | E2 (22) | >E4 (11) |
| groupby_agg | E0 (90) | E0 (53) | E0 (33) | >E4 (12) |
| sort | E0 (60) | E0 (39) | E0 (29) | E2 (17) |
| string | E0 (6) | E0 (6) | E2 (6) | >E4 (3) |
| datetime | E0 (21) | E0 (21) | E0 (14) | E2 (8) |
| apply_map | E0 (45) | E0 (35) | E0 (21) | E2 (10) |
| pivot_reshape | E0 (22) | E0 (20) | E0 (13) | >E4 (11) |
| describe_stats | E0 (183) | E0 (150) | E0 (96) | E2 (57) |
| missing | E0 (57) | E0 (48) | E0 (18) | E2 (5) |
| dedup_unique | E0 (27) | E0 (6) | E2 (3) | E2 (2) |
| indexing | E0 (248) | E0 (209) | E0 (124) | E2 (64) |
| dtype_conv | E0 (16) | E0 (16) | E2 (9) | E2 (5) |
| other | E0 (278) | E0 (217) | E0 (124) | E0 (69) |

Cross-check against `results/conf_5x/analysis__hd1c421ecb5ee__d92c8db54d45b.json`: 262 checks, 0 mismatches.

## A11: paired common-cell view (clean at E2 under all five core engines and both pandas versions)

Population: cells (notebook, cell index) in the clean_E2 view (post-timeout cascades removed) of every label: conf_1x:pyarrow_backend, conf_1x:modin, conf_1x:fireducks, conf_1x:bodo, conf_1x:dask, drift:p15, drift:p30. Notebooks compared 102, with at least one common cell 102; excluded none. Common cells: 461 (median 2.0 per notebook, at most 32; the 5 largest notebooks hold 26.9%). Each label's own clean-at-E2 cells in the compared notebooks: pyarrow_backend 1091, modin 2332, fireducks 1248, bodo 753, dask 545, p15 2129, p30 2215.

Reading rule: about as often: paired 95% interval of the DIFF-share difference contains 0; more often: interval above 0; less often: interval below 0 (fixed 2026-10-05 before the first run). Intervals of the differences use one shared set of 10000 notebook resamples (paired by cell and notebook).

| label | cells | DIFF cells | DIFF %% [95%% CI] | ERR %% | <=E2 %% | DIFF diff vs p30 (pp) [paired 95%% CI] | reading | DIFF diff vs p15 (pp) [paired 95%% CI] | reading |
|---|---|---|---|---|---|---|---|---|---|
| pyarrow_backend | 461 | 14 | 3.0 [1.3, 5.0] | 1.3 | 78.7 | +1.1 [-0.4, +2.7] | about as often | -0.7 [-3.8, +2.3] | about as often |
| modin | 461 | 13 | 2.8 [1.4, 4.7] | 2.6 | 92.8 | +0.9 [-0.9, +2.8] | about as often | -0.9 [-3.5, +1.6] | about as often |
| fireducks | 461 | 17 | 3.7 [1.7, 6.3] | 0.9 | 84.8 | +1.7 [-0.5, +4.5] | about as often | +0.0 [-1.5, +1.5] | about as often |
| bodo | 461 | 23 | 5.0 [3.0, 7.3] | 8.9 | 70.9 | +3.0 [+1.5, +4.9] | more often | +1.3 [-1.6, +4.2] | about as often |
| dask | 461 | 23 | 5.0 [3.0, 7.0] | 29.3 | 61.6 | +3.0 [+0.8, +5.2] | more often | +1.3 [-2.0, +4.2] | about as often |
| p15 | 461 | 17 | 3.7 [1.8, 6.0] | 0.2 | 90.0 | +1.7 [-0.6, +4.4] | about as often | (baseline) | - |
| p30 | 461 | 9 | 2.0 [0.8, 3.3] | 1.7 | 95.4 | (baseline) | - | -1.7 [-4.4, +0.6] | about as often |

## nb_timeout records (all campaigns)

Rule (ledger 2026-10-03): summed cell `wall_s` below 3,600 s means capture-inflated, never engine slowness. The last two columns split the remaining time between capture and time outside the recorded cells (e.g. an in-flight cell blocked in native code that the record does not contain).

| campaign | engine | notebook | cells in record | cell wall_s | capture s | outside recorded cells s | capture-inflated (rule) | larger share |
|---|---|---|---|---|---|---|---|---|
| conf_1x | bodo | penny8/my-sub1 | 24 | 652.9 | 9.4 | 2937.8 | yes | time_outside_recorded_cells |
| conf_1x | bodo_dw | jagangupta/stop-the-s-toxic-comments-eda | 3 | 0.0 | 0.0 | 3600.5 | yes | time_outside_recorded_cells |
| conf_1x | bodo_dw | jirakst/book-recommendation | 3 | 0.8 | 1.7 | 3597.8 | yes | time_outside_recorded_cells |
| timing | bodo | j0thu777/onlineretailanalysis | 24 | 27.7 | 0.0 | 3572.4 | yes | time_outside_recorded_cells |
| timing | bodo | jagangupta/stop-the-s-toxic-comments-eda | 3 | 0.0 | 0.0 | 3600.4 | yes | time_outside_recorded_cells |
| timing | modin | penny8/my-sub1 | 22 | 2422.3 | 0.0 | 1177.9 | yes | time_outside_recorded_cells |
| timing | modin | penny8/my-sub1 | 22 | 2422.5 | 0.0 | 1178.0 | yes | time_outside_recorded_cells |
| timing | modin | penny8/my-sub1 | 22 | 2410.2 | 0.0 | 1190.3 | yes | time_outside_recorded_cells |
| timing | modin | penny8/my-sub1 | 22 | 2409.6 | 0.0 | 1190.4 | yes | time_outside_recorded_cells |

## Run records per configuration (all campaigns, incl. partial ones)

| campaign | config | records | by status | pandas | peak tree RSS GB | fallback-flagged cells |
|---|---|---|---|---|---|---|
| pilot | bodo | 10 | completed 10 | 2.3.3 | 0.0 | 210 |
| pilot | bodo#2 | 10 | completed 10 | 2.3.3 | 43.6 | 210 |
| pilot | bodo_dw | 10 | completed 10 | 2.3.3 | 0.0 | 210 |
| pilot | dask | 10 | completed 10 | 2.3.3 | 19.0 | 0 |
| pilot | dask#2 | 10 | completed 10 | 2.3.3 | 19.3 | 0 |
| pilot | fireducks | 10 | completed 10 | 2.3.3 | 0.0 | 158 |
| pilot | fireducks#2 | 10 | completed 10 | 2.3.3 | 28.6 | 158 |
| pilot | modin | 10 | completed 9, nb_memory 1 | 2.3.3 | 103.3 | 13 |
| pilot | modin#2 | 10 | completed 9, nb_memory 1 | 2.3.3 | 107.2 | 13 |
| pilot | p15 | 10 | completed 10 | 1.5.3 | 0.0 | 0 |
| pilot | p30 | 10 | completed 10 | 3.0.6 | 0.0 | 0 |
| pilot | pyarrow_backend | 10 | completed 10 | 2.3.3 | 0.0 | 0 |
| pilot | ref | 10 | completed 10 | 2.3.3 | 0.0 | 0 |
| pilot | ref#2 | 10 | completed 10 | 2.3.3 | 0.0 | 0 |
| drift | p15 | 102 | completed 102 | 1.5.3 | 28.3 | 0 |
| drift | p30 | 102 | completed 102 | 3.0.6 | 18.3 | 0 |
| drift | ref | 102 | completed 102 | 2.3.3 | 28.8 | 0 |
| drift | ref#2 | 102 | completed 102 | 2.3.3 | 28.7 | 0 |
| conf_1x | bodo | 102 | completed 94, nb_crash 6, nb_memory 1, nb_timeout 1 | 2.3.3 | 96.7 | 1020 |
| conf_1x | bodo_dw | 102 | completed 93, nb_crash 6, nb_memory 1, nb_timeout 2 | 2.3.3 | 97.2 | 832 |
| conf_1x | dask | 102 | completed 102 | 2.3.3 | 66.7 | 0 |
| conf_1x | fireducks | 102 | completed 101, nb_crash 1 | 2.3.3 | 52.2 | 862 |
| conf_1x | modin | 102 | completed 94, nb_memory 8 | 2.3.3 | 103.3 | 139 |
| conf_1x | pyarrow_backend | 102 | completed 102 | 2.3.3 | 21.5 | 0 |
| conf_1x | ref | 102 | completed 102 | 2.3.3 | 28.8 | 0 |
| conf_1x | ref#2 | 102 | completed 102 | 2.3.3 | 28.7 | 0 |
| timing | bodo | 120 | completed 26, nb_crash 92, nb_timeout 2 | 2.3.3 | 25.3 | 288 |
| timing | fireducks | 120 | completed 120 | 2.3.3 | 11.9 | 0 |
| timing | modin | 120 | completed 116, nb_timeout 4 | 2.3.3 | 29.4 | 196 |
| timing | ref | 120 | completed 120 | 2.3.3 | 7.7 | 0 |
| conf_5x | bodo | 29 | completed 26, nb_crash 3 | 2.3.3 | 38.0 | 268 |
| conf_5x | fireducks | 29 | completed 27, nb_crash 2 | 2.3.3 | 58.3 | 272 |
| conf_5x | modin | 29 | completed 28, nb_memory 1 | 2.3.3 | 110.0 | 41 |
| conf_5x | ref | 29 | completed 29 | 2.3.3 | 39.8 | 0 |
| conf_5x | ref#2 | 29 | completed 29 | 2.3.3 | 40.8 | 0 |

## RQ4: speed versus conformance

Source: raw timing records (same rule as pconf.timing report) (status complete).

| cpus | engine | notebooks both ok | geomean speed-up vs ref [95%] | not ok (crash / timeout / error cells / other) | pairs with host load on both runs |
|---|---|---|---|---|---|
| 8 | bodo | 0 | - | 30 (30 / 0 / 0 / 0) | 0 |
| 8 | fireducks | 17 | 0.66 [0.35, 1.21] | 13 (0 / 3 / 10 / 0) | 0 |
| 8 | modin | 19 | 0.36 [0.24, 0.54] | 11 (0 / 1 / 10 / 0) | 0 |
| default | bodo | 4 | 0.17 [0.08, 0.35] | 26 (2 / 5 / 19 / 0) | 4 |
| default | fireducks | 17 | 0.93 [0.52, 1.67] | 13 (0 / 3 / 10 / 0) | 17 |
| default | modin | 19 | 0.19 [0.12, 0.30] | 11 (0 / 1 / 10 / 0) | 19 |

Reference drift (ref at cpus=default over ref at cpus=8, same single-threaded configuration measured in two periods): median ratio 1.168026, IQR [1.099965, 1.260226], min/max [0.994992, 1.501249] over 30 notebooks (1.125264 for the 23 notebooks with a reference time of at least 1 s).

- censored slowdown (8 CPUs, fireducks, jirakst/book-recommendation): engine observed for at least 1205.595653 s, reference median 8.906157 s, so speed-up at most 0.007387.
- censored slowdown (8 CPUs, fireducks, penny8/my-sub1): engine observed for at least 2433.235414 s, reference median 68.59558 s, so speed-up at most 0.028191.
- censored slowdown (8 CPUs, fireducks, shivavashishtha/zomato-eda-tutorial): engine observed for at least 2404.989091 s, reference median 18.418192 s, so speed-up at most 0.007658.
- censored slowdown (8 CPUs, modin, penny8/my-sub1): engine observed for at least 3600.181 s, reference median 68.59558 s, so speed-up at most 0.019053.
- censored slowdown (default CPUs, bodo, akgauravin/gun-violence-data-exploration-and-plotting): engine observed for at least 1200.010541 s, reference median 2.341412 s, so speed-up at most 0.001951.
- censored slowdown (default CPUs, bodo, j0thu777/onlineretailanalysis): engine observed for at least 3600.088 s, reference median 27.000925 s, so speed-up at most 0.0075.
- censored slowdown (default CPUs, bodo, jagangupta/stop-the-s-toxic-comments-eda): engine observed for at least 3600.371 s, reference median 12.541625 s, so speed-up at most 0.003483.
- censored slowdown (default CPUs, bodo, nadare/feature-engenieering-with-pivot-table): engine observed for at least 1236.221776 s, reference median 34.653277 s, so speed-up at most 0.028032.
- censored slowdown (default CPUs, bodo, penny8/my-sub1): engine observed for at least 1251.656937 s, reference median 80.866081 s, so speed-up at most 0.064607.
- censored slowdown (default CPUs, fireducks, jirakst/book-recommendation): engine observed for at least 1205.681651 s, reference median 9.975902 s, so speed-up at most 0.008274.
- censored slowdown (default CPUs, fireducks, penny8/my-sub1): engine observed for at least 2435.910302 s, reference median 80.866081 s, so speed-up at most 0.033197.
- censored slowdown (default CPUs, fireducks, shivavashishtha/zomato-eda-tutorial): engine observed for at least 2405.723963 s, reference median 19.660639 s, so speed-up at most 0.008172.
- censored slowdown (default CPUs, modin, penny8/my-sub1): engine observed for at least 3600.558 s, reference median 80.866081 s, so speed-up at most 0.022459.

**Timing failures** (records by status; non-ok cells by status; notebooks affected).

| cpus / engine | records by status | non-ok cells | notebooks with error / timeout cells / crash or notebook timeout |
|---|---|---|---|
| 8|bodo | nb_crash 90 | - | 0 / 0 / 30 |
| 8|fireducks | completed 90 | error 297, timeout 15 | 12 / 3 / 0 |
| 8|modin | completed 87, nb_timeout 3 | error 78, timeout 6 | 11 / 1 / 1 |
| 8|ref | completed 90 | - | 0 / 0 / 0 |
| default|bodo | completed 26, nb_crash 2, nb_timeout 2 | error 331, timeout 4 | 24 / 4 / 4 |
| default|fireducks | completed 30 | error 99, timeout 5 | 12 / 3 / 0 |
| default|modin | completed 29, nb_timeout 1 | error 26, timeout 2 | 11 / 1 / 1 |
| default|ref | completed 30 | - | 0 / 0 / 0 |

**Host load** (`runs/host_load.jsonl`, 5233 samples, 2026-10-05T02:32:05Z to 2026-10-28T03:47:55Z; 1-minute load averages sampled in [start, end + 75 s]; covered = a sample within 90 s before the start and within 90 s after the end, no gap above 150 s). Records covered: 137 of 480.

| cpus / engine | records | covered | runs from (UTC) | to (UTC) | load1 median [p25, p75] | load1 max |
|---|---|---|---|---|---|---|
| 8|bodo | 90 | 17 | 2026-10-04T17:07:55Z | 2026-10-05T04:30:59Z | 185.4 [150.3, 217.7] | 283.2 |
| 8|fireducks | 90 | 0 | 2026-10-04T05:31:53Z | 2026-10-04T17:07:55Z | - | - |
| 8|modin | 90 | 0 | 2026-10-04T01:10:11Z | 2026-10-04T05:31:53Z | - | - |
| 8|ref | 90 | 0 | 2026-10-04T00:53:39Z | 2026-10-04T01:10:11Z | - | - |
| default|bodo | 30 | 30 | 2026-10-06T20:05:54Z | 2026-10-27T04:08:54Z | 26.1 [19.6, 35.2] | 204.4 |
| default|fireducks | 30 | 30 | 2026-10-05T10:58:57Z | 2026-10-06T20:05:54Z | 42.3 [30.3, 53.1] | 198.4 |
| default|modin | 30 | 30 | 2026-10-05T04:36:50Z | 2026-10-05T10:58:57Z | 52.5 [38.8, 70.4] | 121.4 |
| default|ref | 30 | 30 | 2026-10-05T04:31:00Z | 2026-10-05T04:36:50Z | 50.3 [35.3, 56.7] | 166.1 |

Conformance coordinate of Figure 4 (clean_E2 view, timing30 notebooks; engine-specific cell sets, A11): ref#2 100.0 [100.0, 100.0] of 891 cells; pyarrow_backend 89.6 [84.1, 93.2] of 357 cells; fireducks 87.5 [82.8, 91.4] of 393 cells; bodo 72.2 [60.8, 79.8] of 212 cells; modin 95.3 [93.4, 96.8] of 740 cells; dask 62.9 [48.5, 75.1] of 170 cells; bodo_dw 72.6 [60.3, 80.5] of 186 cells.

## Scale effect (conf_5x notebooks at 1x vs 5x, all comparable cells)

| engine | 1x E0 | 5x E0 | 1x <=E2 | 5x <=E2 | 1x DIFF | 5x DIFF |
|---|---|---|---|---|---|---|
| modin | 83.6 | 77.4 | 89.9 | 85.2 | 5.7 | 6.7 |
| fireducks | 58.3 | 62.9 | 70.9 | 70.2 | 9.3 | 10.1 |
| bodo | 16.2 | 16.2 | 34.7 | 34.5 | 8.9 | 8.9 |

## Ledger cross-check

106 numbers stated in plan.md's Ledger (drift and pilot) were recomputed from the compare outputs at the ledger's precision (percent with one decimal, round half up; counts exact): 2 mismatches.
- MISMATCH plan.md line 391: pilot fireducks clean_strict E0: ledger 82.3, recomputed 82.4
- MISMATCH plan.md line 400: pilot modin all E1: ledger 0.9, recomputed 1.0

## Figures

- `fig3_drift.pdf`: written
- `fig1_conformance_by_engine_pilot.pdf`: written
- `fig2_opfamily_heatmap_pilot.pdf`: written
- `fig5_first_divergence_pilot.pdf`: written
- `fig1_conformance_by_engine.pdf`: written
- `fig2_opfamily_heatmap.pdf`: written
- `fig5_first_divergence.pdf`: written
- `fig4_speed_vs_conformance.pdf`: written

## Caveats

- The pilot covers 10 notebooks and is a pilot, not a claim.
- Operation families come from attribute names only (e.g. any `.str`/`.dt` access, `.size`, `.agg`); a cell can count in several families, and function calls such as pd.merge(...) count only through their attribute name.
- The capture-inflated rule uses recorded cell time only; a notebook can reach the 3,600 s limit through an in-flight cell the record does not contain (native hang), which the rule also labels capture-inflated. The nb_timeout table splits that time for this reason.
- Shares pool cells across notebooks, so notebooks with many cells weigh more; the bootstrap resamples notebooks to reflect that clustering.
- Engines are converted to pandas with their own conversion before comparison (plan Section 2 confound); capture forces materialisation of lazy engines.

## Excluded inputs

- `results/drift/raw/compare__hd1c421ecb5ee__da915cb28b4c6`: tag not accepted
- `results/pilot/analysis__hd1c421ecb5ee__da915cb28b4c6.json`: tag not accepted
- `results/pilot/check__pilot_hd1c421ecb5ee__da915cb28b4c6.json`: tag not accepted
- `results/pilot/raw/compare__hd1c421ecb5ee__d0f54f30a0628`: tag not accepted
- `results/pilot/raw/compare__hd1c421ecb5ee__d39d5176190a8`: tag not accepted
- `results/pilot/raw/compare__hd1c421ecb5ee__d617d450c8406`: tag not accepted
- `results/pilot/raw/compare__hd1c421ecb5ee__d7fb610ea2bfa`: tag not accepted
- `results/pilot/raw/compare__hd1c421ecb5ee__da56b2460d09f`: tag not accepted
- `results/pilot/raw/compare__hd1c421ecb5ee__da915cb28b4c6`: tag not accepted
- `results/pilot/raw/compare__hd1c421ecb5ee__df7c30850a49c`: tag not accepted
- `results/pilot/summary__hd1c421ecb5ee__da915cb28b4c6.json`: tag not accepted
- `results/pilot/superseded_input_capture_20261002`: superseded folder
- `results/pilot/superseded_prep_bug_20261002`: superseded folder
- `results/pilot/superseded_replicate_with_ref2_20261003`: superseded folder
- `results/previous_2026-10-05`: copy of earlier project-level outputs (summary.json, analysis.md), kept for the record
- `results/rootcause`: campaign not analysed (not in plan matrix of the main batch)
- `results/smoke`: campaign not analysed (not in plan matrix of the main batch)
- `results/smoke_timing`: campaign not analysed (not in plan matrix of the main batch)
- `results/timing_bodo_r2`: campaign not analysed (not in plan matrix of the main batch)

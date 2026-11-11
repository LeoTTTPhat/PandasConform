# R5 replay and audit experiments (round REV-06-R5B2-2026-11-10, agent B2)

Paper: PandasConform, "Some pandas Are More Equal Than Others" (`icde27/main.tex`, read only here). Items: D1 targeted
second execution, D2 uncaptured replay of disputed cases, D3 stratified mechanical attribution audit. Everything in this
folder and in `work/r5_replay/` is new; no released file, harness file or stored blob was changed. Paths are relative to
`06_pandas_conformance-ICDE/` unless absolute. Each section starts with the design written BEFORE its first run
(timestamps in ICT); anything decided after seeing results is labelled exploratory.

## Summary for the paper owner (details, designs, `% src:` lines and limitations in each section)

* **D1 (second execution; FINAL):** every notebook with an engine's introduced DIFF (run time up to 900 s) was executed
  a second time with identical run fingerprints (184 notebooks, plus 15 controls). 331 of the 332 compared disputed
  cells are again introduced DIFF (285 bit-identical); the one exception is outside the published counts; all 277
  compared cells of the paper's own counts reproduce; no replay produced a new introduced DIFF; no notebook count
  (24-43), DIFF share or paired contrast changes. Values do change between runs in 2.7-4.2% of scored Modin, FireDucks
  and Dask cells (0.5% Bodo), without moving any cell across the DIFF boundary. (7 cells in 4 long notebooks not
  replayed, 2 replayed cells not compared within the cap.)
* **D2 (uncaptured replay; FINAL, 16 cases):** without the capture harness, on the notebooks themselves, Modin's
  out-of-range `corr` diagonal (5.38, 8.41; and 1.71 in a second notebook) and the `bodo_dw` `read_csv` row loss
  (1,692 of 1,693; all rows with one worker) reproduce exactly, as do FireDucks' chained assignments without a warning,
  its int64 slices, Modin's `value_counts`/`pivot_table`/axis-name behaviours, Bodo's approximate quantiles (row count
  varies by run) and the single-rater behaviours. No case is a capture or conversion artifact.
* **D3 (mechanical attribution audit, not a human one; FINAL):** 358 attributions in six strata, tested by
  counterfactual re-execution with parallel and partitioned execution switched off (N2), injection of the claimed
  mechanism alone (N3), single-relaxation sufficiency (N1), an encoding census (N6) and the D2 replays (N7); 196 have
  a mechanism check. Agreement with the label: rules 63%, single rater 61%, curated 2 of 4 (decided cells); 67
  disagreements, listed in `d3_disagreements.md`. With parallelism off, the difference disappears in 14 of Modin's 18
  parallel-or-lazy cells but in only 2 of FireDucks' 14, 3 of Bodo's 12 and 0 of the pyarrow backend's 4; Dask 4-23 of
  46. Over all of Modin's 49 introduced DIFF cells, one-partition execution removes at least 20 (41-45%; exploratory).
  So "few differences are due to parallel execution" holds for FireDucks, Bodo and the pyarrow backend (at most 4% on
  the notebooks tested), but not for Modin, and Section IX's numerators 14, 12 and 4 are not supported mechanically.

---------------------------------------------------------------------------------------------------------------------

## D1. Targeted second execution of disputed engine outcomes

Reviews: metareview P1 "Repeat disputed engine outcomes ... deterministic and nondeterministic outcomes separated",
R2 W4 ("a targeted second execution of disputed notebooks and representative stable controls"), SUMMARY Section 6
path item 5.

### Pre-declared design (written 2026-11-10 21:42 ICT, before any replay run)

* **Question.** Are the engine cells that the paper counts as introduced DIFF reproducible when the same notebook is
  executed a second time with the same inputs and settings, or do some of them come from run-to-run nondeterminism of
  the engine? How do the principal counts change when the nondeterministic ones are separated?
* **Sampling frame (disputed cells).** Every conf_1x engine cell that is an introduced DIFF under the pure criterion
  (class DIFF, coarser than its clean level; `r4_cell_flags.csv` `kind_exception_off == introduced`): 341 cells
  (pyarrow backend 63, Modin 57, FireDucks 73, Bodo 99, Dask 49). The paper's published counts (inheritance exception
  on) are the subset of 300 (58, 51, 60, 85, 46), of which 284 are not printed-form artifacts (51, 49, 58, 80, 46, the
  numbers the paper cites). Both views are reported.
* **Notebooks replayed.** All notebooks that contain a disputed cell and whose original conf_1x engine run took at most
  900 s: 184 notebook runs (pyarrow 38, Modin 35, FireDucks 42, Bodo 45, Dask 24) holding 334 of the 341 cells. Not
  replayed (cost): Modin `luizep/movieslens20m` (2 cells; its original run hit the 96 GB cap after 2,022 s),
  FireDucks `shivavashishtha/zomato-eda-tutorial` (2), Bodo `nadare/feature-engenieering-with-pivot-table` (2) and
  `artgor/eda-and-models` (1). They keep their original status and are reported as not replayed.
* **Stable controls.** Per engine, 3 notebooks without any disputed cell for that engine, whose original run completed
  in at most 300 s, drawn with `random.Random("20261110|<engine>")` from that pool (15 runs). They measure how often a
  second execution creates a new introduced DIFF where the first had none.
* **Configurations, inputs, seeds.** The unchanged harness (`src/pconf`, harness tag d1c421ecb5ee), the conf_1x run
  configuration (cell timeout 600 s, notebook timeout 3,600 s, seed 0 for Python and NumPy, `PYTHONHASHSEED=0`, input
  capture with the 1 GB rule, no CPU override: Modin 8 Ray CPUs and 16 GB object store, Bodo 1 MPI worker, FireDucks
  and Dask at defaults), the same environments and the same prepared inputs. The driver checks before running that the
  replay fingerprint of every one of the 199 runs equals the original record's fingerprint (engine, frozen package
  list, notebook hash, input content hash, harness hash, run configuration): 199 of 199 equal (dry run 21:41).
  Records and blobs go to `work/r5_replay/` (own content-addressed store). Declared deviation: several notebooks run
  at once (lanes: Bodo 3, Dask 2, Modin 2, FireDucks 2, pyarrow 3), whereas conf_1x ran the parallel engines one
  notebook at a time; this changes CPU contention (recorded: load averages, machine memory, free disk every 30 s),
  not settings. Bodo jobs run with `OMPI_MCA_btl_tcp_if_include=lo0` (changes no computation).
* **Comparisons (unchanged comparator, compare tag d92c8db54d45b).** (a) replay vs the original reference: the same
  `ref` and `ref#2` records the paper used (`classify.classify_run`, NONDET from ref vs ref#2 as in the paper);
  (b) replay vs the original engine run (self-comparison; class E0 means every output of the cell is bit-identical).
  Comparisons read blobs from the replay store first and else from the released store (read only).
* **Per disputed cell (categories).**
  * R-id: in the replay the cell is again an introduced DIFF (pure criterion) and its outputs are bit-identical to the
    original run (self class E0).
  * R-var: again an introduced DIFF, but its outputs differ from the original run (the divergence reproduces, its value
    varies).
  * M: the cell is DIFF in the replay but inherited (its inputs already differ at every level): the divergence now
    appears earlier in the notebook.
  * N: the replay cell agrees with the reference at some level E0-E4 (not reproduced).
  * F: the replay cell failed or did not run (ERR, CRASH, TIMEOUT, MEMORY, NOTRUN, UNCOMPARABLE, notebook not run).
  Reproducible = R-id + R-var. Nondeterministic outcome = M + N (the cell's status as an introduced DIFF changed between
  the two executions). R-var cells are reported as reproducible divergences with nondeterministic values.
* **Metrics.** Per engine and overall: counts of the five categories (pure and exception-on views, with and without the
  16 printed-form artifacts); self-disagreement over all scored cells of the replayed notebooks (comparable to the
  pilot's Bodo 0.9% and Dask 3.1%); cells that are introduced DIFF in the replay but not in the original run
  (disputed-notebook and control notebooks separately).
* **The comparison that answers the question, and recomputed principal counts.** With M and N cells separated (removed
  from the counts; not-replayed and F cells keep their original status and are listed): (1) introduced DIFF cells per
  engine as cited in the paper (exception on, without printed-form artifacts: 49, 58, 80, 51, 46); (2) notebooks with
  an introduced DIFF (Table IV NB corrected 31, 34, 38, 43, 24 and raw 36, 36, 40, 45, 24; abstract range 24-43);
  (3) clean@E2 DIFF counts and unpaired shares (M and N cells removed from numerator and denominator, as NONDET is),
  and, if time allows, the paired contrasts with pandas 3.0.6 recomputed by the paper's own bootstrap code.
* **Stop rule.** One replay per notebook. One guarded job (launch deadline 38 min, hard budget 44 min); notebooks not
  finished are replayed in a second job of at most 45 minutes if the 2-hour cap allows, otherwise reported as not
  replayed. No further repetitions, no re-selection after seeing results.
* **What would count against the paper.** Any engine with more than 10% of its disputed cells in M or N, or a change in
  a notebook count of Table IV or in the sign or detectability of a paired contrast once they are separated, means that
  the published counts mix behaviour and run-to-run noise and must be narrowed. In particular, if Bodo's or Dask's
  clean@E2 DIFF excess over pandas 3.0.6 disappears without the nondeterministic cells, the claim that they differ more
  often than 3.0.6 weakens.

### What ran

* `d1_plan.py` -> `d1_plan.json` (21:39:44, before any run). Dry run of `d1_run.py --dry-run`: 199 of 199 replay
  fingerprints equal the original records' fingerprints.
* Guarded job 1, `runs/06_pandas_conformance_r5_replay_d1.json`: 21:42:23-21:51:29 ICT (9 min 6 s), stopped by me
  with SIGTERM (state `failed`, rc 130) after 12 notebooks because a global limit of two large-input notebooks at a
  time serialized the lanes (a deviation from the stop rule, decided on throughput alone, before any comparison
  result existed); its 12 records were kept (`d1_run_d1.json`). Peak tree RSS 91.8 GB, peak host use
  217.5 GB (guard measure).
* Guarded job 2, `runs/06_pandas_conformance_r5_replay_d1b.json`: 21:51:48-22:09:15 ICT (17 min 27 s), rc 0, the same
  driver with up to five large-input notebooks at a time (`d1_run_d1b.json`): 12 records adopted from job 1, 182
  completed, 2 memory stops and 3 crashes, each with the same status as in the original run (Modin
  `artgor/eda-and-models` and `yonelanuba/elo-merchant-by-yonela` stop at the 96 GB cap as before; Bodo
  `beratozmen/...` and `shunjiangxu/...` crash with the same import error in `bodo.libs` as in the original runs, and
  `luizep/movieslens20m` with the same ValueError on duplicate internal column names). Peak
  tree RSS 165.2 GB, peak host use 234.7 GB. Host load (`work/r5_replay/logs/host_d1*.jsonl`, every 30 s): 1-minute
  load average 28-65 on 32 cores (other projects' campaigns and CI runners were also running), machine memory below
  235 GB, free disk at least 142 GiB.
* `dedupe_store.py`: 153,494 of the 154,853 blobs the D1 replays wrote had the same content-hash name and size as a
  blob already in the released store (identical column content) and were removed from the replay store; 1,359 new
  blobs (1.3 GB) remain.
* `d1_hashcheck.py` -> `d1_hashcheck.json` (no decoding): 157 of the 199 replays are identical to their original run
  in every cell (status, exception type, every captured output and input hash); for them the comparator's result is
  the published one. The other 42 notebooks (Dask 17, Modin 14, FireDucks 8, Bodo 2, pyarrow 1) were compared again
  with the unchanged comparator (`d1_compare.py`; vs the original `ref`/`ref#2`, and vs the original engine run):
  notebooks with at most 0.3 GB of input directly (72 s; note: one comparison worker peaked at 17.4 GB RSS for about a
  minute, above the 4 GB guideline for unguarded work, with more than 300 GB of the machine free), the 10 larger ones
  under the guard: `runs/06_pandas_conformance_r5_replay_d1cmp.json` (22:24:01-22:30:34 ICT, three attempts with four
  workers, each stopped at its 100 GB limit; outputs of finished notebooks kept) and `..._d1cmp2.json` (01:57:26-
  02:23:55 ICT on 11 November, one worker, peak 74.9 GB; stopped by me after 26.5 minutes to keep the 2-hour cap for D3;
  the vs-reference comparisons of Modin `maxiaoyue/...` and `yuliagm/talkingdata-...` and 9 self-comparisons were not
  reached). `d1_shortcut.py` classified pending cells whose comparator inputs were unchanged (37 cells provably
  unchanged; validated against the comparator, see Results).
* `paired.py` re-implements the paired clean@E2 contrasts and unpaired shares of `r3_sensitivity.py` (base variant,
  same seeds and resamples) with an optional exclusion set; with no exclusion it reproduces all 10 contrasts of
  `r4_audit.json` exactly (0 mismatches). `d1_analyze.py` -> `d1_results.json`.

### Results (`d1_results.json`; per-cell rows with category, replay class and self-comparison failure in `cells`)

**Disputed cells.** R-id: again an introduced DIFF with bit-identical outputs; R-var: again an introduced DIFF, other
values; M: DIFF but now inherited; N: not reproduced; F: failed. "not replayed" = the 7 cells of the 4 long notebooks
plus 2 cells whose comparison did not finish within the 2-hour cap (Modin `maxiaoyue/...` 28 and
`yuliagm/talkingdata-eda-plus-time-patterns` 15; see What ran and Status).

| Configuration | disputed cells (pure; exception-on, no printed) | replayed | R-id | R-var | M | N | F | not replayed |
|---|---|---|---|---|---|---|---|---|
| pyarrow backend | 63; 51 | 63 | 63 | 0 | 0 | 0 | 0 | 0 |
| Modin | 57; 49 | 53 | 39 | 13 | 0 | 1 | 0 | 4 |
| FireDucks | 73; 58 | 71 | 62 | 9 | 0 | 0 | 0 | 2 |
| Bodo (1 worker) | 99; 80 | 96 | 92 | 4 | 0 | 0 | 0 | 3 |
| Dask | 49; 46 | 49 | 29 | 20 | 0 | 0 | 0 | 0 |
| all | 341; 284 | 332 | 285 | 46 | 0 | 1 | 0 | 9 |

* Of the 332 replayed and compared disputed cells, **331 are again introduced DIFF cells** (285 with bit-identical
  outputs, 46 with other values); **1 is not reproduced** (N: Modin `shivavashishtha/zomato-eda-tutorial` cell 56,
  one of the 59 exception cells, which the paper's counts do not include; in the replay its inputs agree at E2 and its
  output at E0, so the difference came from a run-dependent row order or index of its input). M = F = 0.
* In the paper's own view (exception on, no printed-form artifacts; 284 cells), **all 277 compared cells reproduce**
  (241 bit-identical, 36 with other values); 5 are in the long notebooks and 2 were not compared.
* R-var cells keep their DIFF status while their values change: Dask's lazy objects (15 `lazy_partition_model` cells,
  for example `df.shape` returning an unevaluated expression whose printed name carries a run-specific token), Bodo's
  approximate-quantile filters in `deffro/eda-is-fun` (3; the kept row count changes from run to run, as in D2), Modin
  cells whose values, row order or index change between runs (13, six of them `corr` cells of one notebook whose input
  frame's index changes), FireDucks cells of five notebooks whose frames change between runs (9), and one Bodo cell of
  the date-dependent notebook below.
* Run statuses reproduce: the 2 memory stops and 3 crashes of the replays are the original ones; every introduced
  failure cell of the replayed notebooks (ERR, CRASH, TIMEOUT, MEMORY, NOTRUN; 183 cells) recurs with the same class
  (exploratory check, `exploratory_failure_cells`).
* **No replay produced a new introduced DIFF**, neither in the 15 control notebooks nor elsewhere in the 184 disputed
  notebooks.
* Check of the decode-free shortcut (`d1_shortcut.py`, which classifies a cell without decoding when every input of the
  comparator for that cell is unchanged): all 37 cells it marked unchanged were later compared by the comparator, and
  all 37 got exactly the published class and clean level; in the final counts every category comes from a comparator
  output (a new one, or the published one for the 157 hash-identical notebooks).

**How often do two executions differ, and in what?** Self-comparison of every scored cell of the replayed notebooks
(cells NONDET between `ref` and `ref#2` excluded, as in the paper; the self comparisons of 9 large notebooks did not
finish within the cap and are missing from these denominators). "Identical failures": both runs failed to convert
the same output with the same error, which the comparator can only call UNCOMPARABLE; "token-only": printed forms that
differ only in hexadecimal tokens (Dask expression names). The split (`d1_selfdiff.py`) was added after the first
results were seen (exploratory refinement of the pre-declared self-disagreement metric, which is the "differing"
column).

| Configuration | notebooks replayed (+controls) | hash-identical | scored cells | differing between runs | of which identical failures / token-only / value changes | new introduced DIFF (controls / disputed nbs) |
|---|---|---|---|---|---|---|
| pyarrow backend | 38 (+3) | 40 | 1205 | 2 (0.17%) | 0 / 0 / 2 (0.17%) | 0 / 0 |
| Modin | 33 (+3) | 24 | 977 | 41 (4.20%) | 0 / 0 / 41 (4.20%) | 0 / 0 |
| FireDucks | 42 (+3) | 37 | 1321 | 103 (7.80%) | 56 / 0 / 47 (3.56%) | 0 / 0 |
| Bodo (1 worker) | 45 (+3) | 46 | 1062 | 10 (0.94%) | 5 / 0 / 5 (0.47%) | 0 / 0 |
| Dask | 24 (+3) | 10 | 438 | 67 (15.30%) | 27 / 28 / 12 (2.74%) | 0 / 0 |

The pyarrow backend (plain pandas 2.3.3) differs in 2 cells and Bodo in 1 for a reason outside the engines:
`tunguz/fathers-day-specials-just-the-features` computes with `datetime.datetime.today()`, so a replay on a later day
changes those values for every configuration. Bodo's other value changes are its approximate quantiles (3 cells) and one
output whose conversion failed differently in the two runs.

**Principal counts with the nondeterministic cells (M, N) separated** (the M/N set is the single Modin cell above):

| Configuration | introduced DIFF, no printed (paper -> without M, N) | NB corrected (paper -> without) | NB raw (paper -> without) |
|---|---|---|---|
| pyarrow backend | 51 -> 51 | 31 -> 31 | 36 -> 36 |
| Modin | 49 -> 49 | 34 -> 34 | 36 -> 36 |
| FireDucks | 58 -> 58 | 38 -> 38 | 40 -> 40 |
| Bodo (1 worker) | 80 -> 80 | 43 -> 43 | 45 -> 45 |
| Dask | 46 -> 46 | 24 -> 24 | 24 -> 24 |

The abstract's range stays 24-43 notebooks; the clean@E2 DIFF shares and all ten paired contrasts of Table IV and the
Sensitivity paragraph are unchanged (recomputed with `paired.py`, which reproduces `r4_audit.json` exactly; e.g. Bodo
-pandas 3.0.6 +4.14 [2.18, 6.44] and Dask-pandas 3.0.6 +3.90 [1.64, 6.14] points, both "more often"; Modin, FireDucks and
the pyarrow backend within -0.30 to +0.59 points, "not distinguishable"), because the one cell that did not reproduce
is outside the clean@E2 population and outside the exception-on counts. The 2 uncompared cells (both Modin, each the
only disputed cell of its notebook) could lower Modin's count by at most 2 cells and 2 notebooks (34 -> 32).

**What it means for the paper.**
* R2 W4's concern (engine nondeterminism pooled into the conformance deficit) does not change any reported number: the
  disputed engine outcomes are reproducible as outcomes. The paper's caveat "so its DIFF share against pandas may
  include run-to-run differences" (Section VI) and "some engine DIFF may be run-to-run noise" (Threats) can be replaced
  by the measured result. It weakens nothing; it strengthens "Bodo and Dask differ more often than 3.0.6".
* Engines are not deterministic in values: Modin, FireDucks and Dask change values in 2.7-4.2% of scored cells between
  two executions (Modin mostly row order and index, E1/E4; FireDucks mostly the index, E4), Bodo in 0.5% (its
  approximate quantiles, one cell of the date-dependent notebook, one conversion failure). These changes do not move
  cells across the DIFF boundary. Dask's raw rate (15%) is dominated by identical failures and by run-specific names of
  its lazy objects; without them it is 2.7%, similar to the pilot's 3.1%.
* The replays also show that the measurement pipeline is deterministic: 157 of 199 notebooks reproduce bit for bit in
  every captured input and output (99% of the 154,853 blobs written already existed in the store under the same
  content hash).

**Proposed paper text** (Section VI, after the pilot replicate sentence, or in place of its last clause; Threats as
noted):

> A second execution of the 184 notebooks that hold an engine's introduced \cls{DIFF} cells (identical run
> fingerprints; four longer notebooks with 7 cells excluded) and of 15 control notebooks reproduced 331 of the 332
> compared cells as introduced \cls{DIFF}, 285 with bit-identical outputs; the exception lies outside the published
> counts, no replay added an introduced \cls{DIFF}, and no count, share or paired contrast changes. Values did change
> between the two executions in 2.7--4.2\% of scored Modin, FireDucks and Dask cells (mostly row order and index) and
> in 0.5\% of Bodo's, without moving any cell across the \cls{DIFF} boundary.

    % src: icde27/analysis/r5_replay/d1_results.json engines.*.categories_pure {R-id 285, R-var 46, N 1 of 332 compared}; icde27/analysis/r5_replay/d1_plan.json engines.*.{notebooks (184), controls (15), not_replayed_long (4 nbs, 7 cells)}
    % src: icde27/analysis/r5_replay/d1_results.json principal_counts.*, paired.{base,without_nondet}, engines.*.{new_in_controls 0, new_in_disputed_notebooks 0}
    % src: icde27/analysis/r5_replay/d1_results.json engines.{modin,fireducks,dask,bodo}.self_differing_value_share (0.04197, 0.03558, 0.0274, 0.00471)

Threats (Internal validity), replacing "engine replicates exist only for the 10 pilot notebooks, where Dask differed
from itself on 3.1\% of cells, so some engine \cls{DIFF} may be run-to-run noise":

> a second execution of every notebook with an engine's introduced \cls{DIFF} reproduced all but one of these cells
> (Section~\ref{sec:conformance}), although 2.7--4.2\% of Modin's, FireDucks' and Dask's values changed between runs.

    % src: icde27/analysis/r5_replay/d1_results.json (as above)

**Limitations.** One second execution per notebook (two runs in all), not a distribution of runs; the replays ran
several notebooks at once on a loaded host (conf_1x ran parallel engines one at a time), which may have increased
run-to-run variation, not reduced it. Four long notebooks (7 cells) were not replayed and 2 replayed cells were not
compared within the cap. Notebooks without an engine's introduced DIFF were sampled only as 15 controls, so the
self-difference rates describe the replayed notebooks. A cell that varies in value is counted as reproduced when it
stays DIFF; its exact value is not reproducible.

Status: FINAL (332 of the 334 replayed disputed cells compared; the remaining 2 are reported as not compared, with
the bound above). Outputs: `d1_plan.json` 4e2c471460329b06ae239e7129a5f91fad03d418871f48106ad9622509764444,
`d1_run_d1.json` 1e1b311d830b641dd881216ae34703a7f47d435d73a9d41c9be5c5205659e290, `d1_run_d1b.json`
94a45900e24d3d695ac5fdb5909a851b94f935a197d0b5957fe45c65ef5a898f, `d1_hashcheck.json`
30bfe1e16c65293b06b403da1342aa0e0cd2b23ae90205e6928e2d7222b2e958, `d1_shortcut.json`
dba0aabe32da1f0a73a5f2971062bf25c1fd0fc40934da2d66fb75f4ebb1bc69, `d1_selfdiff.json`
af18ea95d6ba727d171478c98dcc2ce859817b8e8bc445ff50e990f90c60ec8e, `d1_results.json`
617c0cc370cdf174dda220cfd7d441365e813c94daf2d6634aa6be5106583d97; raw records and comparisons under
`work/r5_replay/` (hashes in `manifest.json`).

---------------------------------------------------------------------------------------------------------------------

## D2. Uncaptured replay of the most consequential disputed cases

Reviews: metareview P1 (replay without capture, matched inputs), R3 W3 ("the out-of-range correlation diagonal and the
worker-dependent read-row loss ... should remain candidate symptoms until an exact notebook replay ... establishes
their source"), R4 W2 (end-to-end validation of the capture path), SUMMARY Section 6 path item 5.

### Pre-declared design (written 2026-11-10 21:54 ICT, before any D2 run)

* **Question.** Does each disputed engine outcome appear when the notebook runs WITHOUT the capture harness, with the
  same inputs, seeds and engine settings, observing only the value in question? Or is it an artifact of capture or of
  the engine-to-pandas conversion, or not reproducible?
* **Cases (16, in `d2_cases.py`; one representative cell per behaviour, chosen from the paper's text before any run).**
  Named or unconfirmed: Modin's out-of-range `corr` diagonal (`deffro/eda-is-fun` cell 30, the 5.38/8.41 notebook, and
  `qnqfbqfqo/electric-vehicle-...` cell 8, a second notebook of the same cause whose captured diagonal also leaves
  [-1, 1]); the `bodo_dw` `read_csv` row loss (`shashi772/data-cleaning-challenge-parsing-dates` cell 0, observed in
  both the pilot and the conf_1x `bodo_dw` captured runs; replayed at the default worker count AND with one worker);
  FireDucks' int64-for-float64 result (`kwullum/...` cell 2). Headline silent behaviours of Section VII: Bodo's
  approximate quantiles (`deffro` cell 12, `gmanish/help-ngo-country-clustering` cell 16), FireDucks' chained
  assignment (`ayushsingh5941/tweet-disaster-or-not` cell 9, `arjoonn/scout-script-7` cell 9), Modin's
  `value_counts` of a `cut` result (`trinath003/...` cell 11), Modin's `pivot_table(aggfunc='size')`
  (`sabya40/...` cell 22), a lost axis name (Modin, `grudd0/mass-shooting-analysis` cell 2). Single-rater behaviours
  of the lessons: Modin's lost `apply` side effects (`shivavashishtha/zomato-eda-tutorial` cell 33), Bodo's stale
  `head()` (`kwullum/...` cell 4), FireDucks' stale group-by after `.at` (`danielresende/game-of-thrones-battles`
  cell 5), Bodo's positions instead of labels (`snanilim/...` cell 2), FireDucks' `nunique()`
  (`jyotsananegi/...` cell 4).
* **Uncaptured replay (`d2_child.py`).** A fresh process in the engine's environment executes the notebook's code
  cells in order up to the target cell with plain `exec`/`eval`: no AST-driven input or output capture, no hashing, no
  conversion to pandas, no materialisation of bound values. Kept from the harness (so inputs and settings match): the
  pandas-import rewrite to the engine module (`nbsource.prepare_cell`, which only strips magics and rewrites imports),
  PandasBench's `evaluate_lazy` hook, `random.seed(0)`, `numpy.random.seed(0)`, `PYTHONHASHSEED=0`, the setup-cell
  rule, Agg plotting with `plt.show` disabled, a no-op `display()`, the 600 s cell alarm, the prepared inputs, and the
  engine setup code and environment variables of `src/pconf/engines.py` (Modin 8 Ray CPUs and 16 GB object store;
  FireDucks `-Wfallback`; Bodo `BODO_NUM_WORKERS=1`; `bodo_dw` without it). After the target cell, and only then, each
  named value is observed with a small expression (for example the diagonal and the number of entries outside [-1, 1]
  for `corr`, `len()` for a read, the missing count per column for the chained-assignment frame); this observation is
  the only extra computation. Warnings raised in the target cell are recorded.
* **Repetitions and baselines.** Each engine case twice (fresh processes); pandas 2.3.3 (`envs/ref`) once per notebook
  as the uncaptured baseline. The same observation expressions are applied (`d2_captured.py`, in `envs/ref`, read
  only) to the decoded captured values of the original engine run, the original reference run and, where available,
  the D1 captured replay, so the uncaptured value can be compared with what the harness recorded.
* **Classification per case (decided before running).**
  * confirmed engine behaviour: in both uncaptured engine runs the observed value differs from the uncaptured pandas
    value in the described way (reported with whether it equals the captured engine value exactly);
  * capture or conversion artifact: both uncaptured engine runs equal the pandas value while the captured engine value
    differed from the captured reference (and the D1 captured replay, if available, still differs);
  * not reproduced (nondeterministic): the two uncaptured runs disagree with each other about whether they differ
    from pandas, or neither differs and the D1 captured replay does not differ either;
  * inconclusive: a run or an observation failed (error, timeout), or the uncaptured pandas value differs from the
    captured reference value (the observation would then not measure the same thing).
* **Stop rule.** One guarded job (all cases, 2 repetitions); no reruns except of runs that failed for infrastructure
  reasons (reported).
* **What would count against the paper.** Any case classified as a capture or conversion artifact means the
  corresponding claim must be withdrawn or labelled as harness-dependent; a case that is not reproduced must be
  described as run-dependent. A confirmed case upgrades the claim from "unconfirmed by probes" to "reproduced on the
  notebook without the harness", but only for that cell (not for every cell of the cause).

### What ran

* `d2_cases.py` (16 cases), `d2_child.py` (the uncaptured runner), `d2_run.py` (driver), written before the run; one
  code test of the child with pandas on `gmanish/...` (output discarded) before the guarded job.
* Guarded job `runs/06_pandas_conformance_r5_replay_d2.json`: 22:13:41-22:16:28 ICT (2 min 47 s), rc 0, peak tree RSS
  47.9 GB, peak host use 157.1 GB; 48 runs (pandas once per notebook, each engine case twice), all exited normally
  (`d2_raw.json`, children's output in `work/r5_replay/logs/d2_children.log`). Host 1-minute load average 24-36 at
  the ends of the runs (other projects running).
* `d2_captured.py` (envs/ref, 3 s, 0.6 GB) applied the same observation expressions to the decoded captured values of
  the original conf_1x runs, the pilot `bodo_dw` run and the D1 captured replays (`d2_captured.json`);
  `d2_analyze.py` -> `d2_results.json`.
* **Infrastructure fault and rerun:** in the four FireDucks cases other than the group-by case, the observation
  itself raised `KeyError: '__name__'` in all runs: FireDucks inspects the caller's frame globals, and the observation
  expression was evaluated with globals that lacked `__name__` (the notebook cells themselves ran in a namespace with
  `__name__ = "__main__"`, as in the harness). Fixed in `d2_child.py` (observation globals now carry
  `__name__ = "__main__"`; nothing else changed); the four cases (FireDucks only, two runs each) were rerun in guarded
  job `runs/06_pandas_conformance_r5_replay_d2b.json` (00:04:42-00:04:46 ICT, 11 November; rc 0; 8 runs, all exited
  normally) -> `d2_raw_rerun.json`, which `d2_analyze.py` uses in place of the failed runs. This is the only rerun, and
  the stop rule allows it (infrastructure failure).

### Results (`d2_results.json`)

In every case the uncaptured pandas value equals the captured reference value, so each observation measures what the
harness recorded.

| Case (configuration, notebook, cell) | Uncaptured pandas | Uncaptured engine, run 1 / run 2 | Captured engine (conf_1x; D1 replay) | Verdict |
|---|---|---|---|---|
| Modin `corr` diagonal, `deffro/eda-is-fun` 30 | all 1.0; 0 entries outside [-1, 1] | 0.029, 5.378, 8.411, -0.479, ..., 3.859, ..., 8.401, -0.543; 108 entries outside [-1, 1] (both runs identical) | identical (both) | confirmed engine behaviour |
| Modin `corr` diagonal, `qnqfbqfqo/electric-vehicle-...` 8 | all 1.0; 0 outside | NaN, 0.029, NaN, 1.707, 1.0, 0.9998, 1.0; 6 outside (both) | identical (both) | confirmed |
| Bodo default workers (`bodo_dw`) `read_csv`, `shashi772/...` 0 | 1,693 / 1,508 / 23,412 rows | 1,692 / 1,507 / 23,412 (both) | 1,692 / 1,507 (conf_1x and pilot) | confirmed |
| same notebook, Bodo with 1 worker | 1,693 / 1,508 / 23,412 | 1,693 / 1,508 / 23,412 (both) | 1,693 / 1,508 | no difference: the row loss depends on the worker count |
| Bodo approximate 0.99 quantile filter, `deffro` 12 | 4,402,460 rows | 4,396,024 / 4,389,719 | 4,400,164; D1 replay 4,415,729 | confirmed; the kept row count changes from run to run |
| Bodo approximate quantiles, `gmanish/...` 16 | Q1 465.9, Q3 48,610, 9 rows | Q1 459.0, Q3 48,700, 8 rows (both) | identical (both) | confirmed |
| Modin `value_counts` of a `cut`, `trinath003/...` 11 | 8 bins, 1 empty | 7 bins, none empty (both) | identical | confirmed |
| Modin `pivot_table(aggfunc='size')`, `sabya40/...` 22 | Series (261) | DataFrame (261 x 5) (both) | identical | confirmed |
| Modin index name after `df.index = df.Date`, `grudd0/...` 2 | `Date` | none (both) | identical | confirmed |
| Modin `apply` side effects (single rater), `shivavashishtha/...` 33 | 124,234 list elements | 5 (both) | identical | confirmed |
| Bodo stale `head()` (single rater), `kwullum/...` 4 | `18`, `07`, ... (updated column) | `18:45`, `07:50`, ... (data from before the update) (both) | identical | confirmed |
| FireDucks stale group-by after `.at` (single rater), `danielresende/...` 5 | 5 groups | 4 groups (`Mance Rayder` missing) (both) | identical | confirmed |
| Bodo positions instead of labels (single rater), `snanilim/...` 2 | dropped index 221, 271, 351, ...; kept index starts 0, 1, 2 | dropped 0, 1, 2, ...; kept index starts 348, 349, 350 (both) | identical | confirmed |
| FireDucks chained `fillna(inplace=True)`, `ayushsingh5941/...` 9 | 0 missing `keyword` / `location`; pandas 2.3.3 warns (FutureWarning: chained assignment with an inplace method) | 61 / 2,533 missing, no warning of any kind in the cell (both; rerun) | identical | confirmed |
| FireDucks chained assignment, `arjoonn/scout-script-7` 9 | `self_employed` 0 missing; pandas warns (FutureWarning) | 18 missing; only FallbackWarnings, no chained-assignment warning (both; rerun) | identical | confirmed; the cell also differs in column labels (`unique()` yields `None` where pandas yields `nan`, so `state_None` instead of `state_nan`) |
| FireDucks `nunique()` (single rater), `jyotsananegi/...` 4 | ..., 11, ..., 602, 144, 33, ... | ..., 12, ..., 603, 145, 34, ... (missing values counted; both; rerun) | identical | confirmed |
| FireDucks int64 for float64 slice, `kwullum/...` 2 | `head()` dtypes object, float64, float64 (the full frame's column is float64 in both) | object, int64, int64 (both; rerun) | identical | confirmed (FireDucks re-infers the slice's dtype) |

**What it means for the paper.**
* The two claims R3 W3 names as "unconfirmed by the reported probes" are confirmed on the notebooks themselves without
  the capture harness: Modin's `corr` returns diagonal entries far outside [-1, 1] (5.38, 8.41 and more; 108 entries
  outside [-1, 1] in a 25 x 25 matrix) in `deffro/eda-is-fun`, and also in a second notebook (diagonal 1.71, 6 entries
  outside), identically in four executions (two uncaptured, two captured); and Bodo at its default worker count reads
  1,692 of 1,693 and 1,507 of 1,508 rows, while one worker reads all, so the row loss is worker-dependent engine
  behaviour, not a capture or conversion artifact. The paper's sentence "Unconfirmed by probes are ... the pilot's
  bodo_dw read_csv ... and an out-of-range corr diagonal ..." should be replaced (proposed text below); the synthetic
  4.4M-row probe simply did not trigger the Modin defect.
* The headline silent behaviours of Section VII that this test covers (Modin's `value_counts` of a `cut`, Modin's
  `pivot_table(aggfunc='size')`, a lost axis name, Bodo's approximate quantiles) and four single-rater behaviours of the
  lessons (Modin's lost `apply` side effects, Bodo's stale `head()`, FireDucks' stale group-by, Bodo's positions
  instead of labels) reproduce on the notebook without the harness. This extends the R4 probes (synthetic inputs) to
  the notebook cells themselves, for one representative cell per behaviour (not for every cell of each cause).
* Bodo's approximate quantiles are not just approximate but run-dependent: the filter keeps 4,389,719, 4,396,024,
  4,400,164 or 4,415,729 rows in four executions (pandas: 4,402,460); every run differs from pandas.
* FireDucks' chained assignments do not write through on the notebook either (61 and 2,533 values stay missing in one
  notebook, 18 in another), and FireDucks emits no chained-assignment warning where pandas 2.3.3 does, which is the
  paper's headline example; FireDucks' `nunique()` counting missing values and its int64 dtype for a `head()` slice of a
  float64 column (listed as unconfirmed by probes in the paper) also reproduce on the notebook.
* No case turned out to be a capture or conversion artifact: all 16 cases (17 case-configuration verdicts, counting Bodo with one
  worker as the expected no-difference control) are engine behaviour that appears without the harness.

**Proposed paper text** (Section VII, replacing the sentence "Unconfirmed by probes are ..."):

> Replayed on the notebooks without the capture harness (same inputs, seeds and settings; only the value in question
> observed; two runs each), Modin's out-of-range \texttt{corr} diagonal (5.38 and 8.41, and 1.71 in a second notebook)
> and the \eng{bodo\_dw} \texttt{read\_csv} that returns 1,692 of 1,693 rows (all of them with one worker) reproduce
> exactly, as do FireDucks' int64 slices of float64 columns, the silent behaviours above (FireDucks' chained
> assignments again without any warning) and, for one cell each, the four single-rater behaviours of the lessons and
> FireDucks' \texttt{nunique()}; Bodo's approximate quantile filter keeps a different number of rows in every run
> (4,389,719 to 4,415,729 against 4,402,460).

    % src: icde27/analysis/r5_replay/d2_results.json cases.{corr_diag_deffro,corr_diag_ev,read_rows_bodo_dw}.configs.*.{uncaptured,verdict}
    % src: icde27/analysis/r5_replay/d2_results.json cases.{value_counts_cut_modin,pivot_table_size_modin,index_name_modin,apply_side_effects_modin,stale_head_bodo,stale_groupby_fireducks,positions_labels_bodo}.configs.*.verdict (confirmed, 2 of 2 runs)
    % src: icde27/analysis/r5_replay/d2_results.json cases.approx_quantile_deffro.{pandas_uncaptured._ 4402460, configs.bodo.{uncaptured 4396024/4389719, captured_conf_1x 4400164, captured_d1_replay 4415729}}
    % src: icde27/analysis/r5_replay/d2_results.json cases.{chained_assignment_tweet,chained_assignment_scout,nunique_fireducks,int_float_slice_fireducks}.configs.fireducks.{verdict confirmed, uncaptured.*.warnings (no chained-assignment warning), rerun true}

**Limitations.** One representative cell per behaviour (the claim is about the behaviour on a real notebook, not about
every cell attributed to the cause). The uncaptured runner shares the harness's import rewrite, seeds and setup-cell
rule, so a fault in those would affect both; it shares no capture, hashing or conversion code. The observation itself
is a small computation on the target value (for example `len()` or a scalar diagonal access); for lazy engines this
forces that value, as any display of it in a notebook would. Two runs per case.

Status: FINAL (all 16 cases; the four FireDucks cases from the infrastructure rerun, guarded job
`runs/06_pandas_conformance_r5_replay_d2b.json`, 00:04:42-00:04:46 ICT on 11 November, rc 0). Outputs: `d2_raw.json`
9b8c168dbeda064ce72321ecb7e2c0ecc1f6de4483cba8d241e2e1f17f8f93e9, `d2_raw_rerun.json`
23e090436eeecf441338917d953d2043791c9eee8f2739e034d7d157da73fa40, `d2_captured.json`
c01da25f9b4b69a98e1d327592e75f1a3c73882768dabe495acdfcdeaf100f5a, `d2_results.json`
419cb9f26331fda7f2f8bfb01e71d696f4749f8575f7fcb4dae8e6980874d8ad. (`d2_raw.json` came from the child before its
one-line fix, which only added `__name__` to the observation globals.)

---------------------------------------------------------------------------------------------------------------------

## D3. Stratified mechanical attribution audit

Reviews: metareview P1 "Audit a stratified sample of all attribution sources" and decisive issue 3, R1 W3, R4 W3 and Q4
("an audit with a different failure mode"; "not merely agreement between two language-model outputs"), SUMMARY
Section 6 path item 4.

**This is a mechanical audit, not a human one.** No language model labels anything: each check is a deterministic
counterfactual or encoding test written as code before it ran; its failure modes (a neutralization that also changes
something else, a counterfactual that cannot be applied) differ from those of the ordered rules (which read the
comparator's first failing check, the error and the code) and of the single AI rater (which read evidence sheets).

### Pre-declared design (written 2026-11-10 22:00 ICT, before any D3 check; strata and samples fixed in `d3_plan.json`)

* **Question.** When the mechanism that an attribution names is neutralized (or injected alone), does the difference
  disappear (or appear)? Per attribution source, how often does the mechanical check agree with the label, and what
  does that do to the aggregates, in particular the parallel-or-lazy share ("at most 37%")?
* **Sampling frame.** The paper's introduced cells (exception-on view, 2,147; `r4_cell_flags.csv`), with their source
  (rule, curated table, single rater) and cause. Strata (`d3_plan.py`; overlapping strata are reported per stratum):
  * P, census (75): every conf_1x engine introduced DIFF cell outside the printed-form artifacts that the paper counts
    as parallel or lazy execution (Modin 18, FireDucks 14, Bodo 12, pyarrow backend 4, Dask 27; 48 by rules or the
    curated table, 27 by the single rater).
  * Q, cluster sample (31): the other introduced DIFF cells of the same engine in the notebooks of P (the denominator
    side: differences attributed to something else that serial execution might nevertheless remove).
  * C, census (21): the curated cells. S, census (117): the cells the rules leave unattributed (single-rater labels).
  * R, stratified random sample (51): rule-assigned engine cells of non-parallel causes, up to 3 per cause, drawn with
    `random.Random("20261110|<cause>")`.
  * H, census (150): conf_1x cells of the high-impact causes the abstract, findings and lessons name (FireDucks chained
    assignment, silent engine errors of Modin and Bodo, Modin `corr` values, lost axis names and Arrow-backed dtypes
    (DIFF cells), dtype-name checks, approximate quantiles).
* **Checks.**
  * N2, serial-execution counterfactual (new captured runs of the 56 notebooks of P with the unchanged harness and
    comparator; only the engine's execution mode changes, registered at run time without editing `engines.py`):
    Modin on its in-process Python engine with 1 partition; Dask with the synchronous scheduler and one partition per
    CSV read (`blocksize=None`); FireDucks with 1 thread; the pyarrow backend with 1 Arrow thread; Bodo (already 1
    worker) with exact quantiles (its Series `quantile` and DataFrame `quantile`/`describe` computed by pandas on the
    collected data). A cell is *confirmed* if, under the serial variant, it is no longer DIFF against the reference
    (class E0-E4), *not confirmed* if it is still an introduced DIFF, and *inconclusive* if it fails, does not run or
    becomes an inherited DIFF. For Bodo's row-order cells, worker pinning is already in place (1 worker): the original
    runs are the counterfactual, so they are *not confirmed as a parallel effect* by construction.
  * N3, cross-configuration injection (existing records, comparator): the engine's output is compared with a
    configuration that differs from the reference only by the claimed mechanism: the pyarrow backend (pandas with
    Arrow-backed dtypes) for the Arrow causes and dtype-name checks of Bodo and Dask; pandas 3.0.6 (Copy-on-Write on)
    for FireDucks' chained assignment. *Confirmed* if the engine's cell agrees with that partner at E4 or finer while it
    is DIFF/coarser against the reference.
  * N1, single-mechanism sufficiency (stored values; cells of class E1-E4 whose cause maps to one relaxation):
    only that relaxation (sort rows; float tolerance; canonical dtype; unified missing values; dropped index; dropped
    names) is applied to both decoded values; *confirmed* if that alone makes them equal (otherwise the cell needs more
    than its one primary cause).
  * N6, printed-form census, for cells the rater calls harness artefacts: confirmed if `r4_printed_forms.json` lists
    the cell among those whose differing printed forms made it DIFF. N7, the D2 verdict for cells that are D2 cases.
    N8, by construction: pyarrow-backend cells with an Arrow-family cause. N9, localization only: bit-identical inputs
    (clean level E0) show that the cell itself introduces the difference, whatever its cause (not a mechanism test).
* **Metrics.** Per stratum and per check: tested, confirmed, not confirmed, inconclusive, untestable (no check
  applies); every disagreement listed with its cell ID; agreement = confirmed / (confirmed + not confirmed).
* **Corrected aggregates.** Parallel-or-lazy share per engine as an interval over the paper's denominator (introduced
  DIFF cells without printed-form artifacts): lower = P cells confirmed by N2; upper = P cells not refuted (confirmed or
  inconclusive or untested) plus Q cells that N2 confirms (differences that vanish without parallelism although
  attributed elsewhere). The same for the paper's "at most 37%" statement.
* **Stop rule.** N2: one guarded job (launch deadline 35 min, hard budget 42 min), longest notebooks first; notebooks
  not finished are untested. N1/N3: one pass. No re-selection after seeing results.
  *Amendment (22:13 ICT, before any N2 run; it changes only time budgets, not samples or checks):* to keep every
  guarded job under 45 minutes with
  the comparator work inside the guard, the N2 job uses a launch deadline of 24 min and a hard budget of 29 min, then
  runs the serial-record comparisons (`d1_compare.py --d3`) and N3/N1/N6 (`d3_checks.py`) in the same guarded job.
  `d3_checks.py` was code-tested once on the notebooks with at most 0.02 GB of input (output kept in the scratch
  folder, not used).
  *Amendment 2 (22:38 ICT, before any N2 result exists):* serial execution removes parallelism and partitioning but
  not laziness, so for cells attributed to Dask's lazy partition model (`lazy_partition_model`, 19 P cells) an N2
  outcome "persists" is recorded as *inconclusive (laziness not neutralized)*, not as a disagreement; "vanishes" still
  counts as agreement. Bodo's row-order cells stay as declared (worker pinning already in place).
* **Exploratory extension (decided at 23:50 ICT, AFTER the N2 results were seen; labelled exploratory throughout).**
  Four of Modin's five Q cells vanished under serial execution, so the pre-declared upper bound (which only tests the
  notebooks of P) may understate Modin's partitioned-execution share. The same `modin_serial` variant is therefore run
  on the 16 other notebooks that hold 24 of Modin's remaining 26 introduced DIFF cells (exception on, no printed forms;
  `luizep/movieslens20m` and `artgor/eda-and-models`, 1 cell each, excluded because their original Modin runs stopped
  at the memory cap) (`d3_ext_plan.json`), in guarded job `runs/06_pandas_conformance_r5_replay_d3post.json`
  (`d3_post.py`), which also reruns the comparisons and `d3_checks.py` (parallel and resumable; its first attempt timed
  out after 6 minutes inside the N2 job, before writing any output). To keep all guarded jobs within the 2-hour cap,
  `d3_post.py` computes the remaining budget from the guard state files when it starts: with at least 17.5 minutes
  left it runs the extension (launch deadline 200 s, hard budget 290 s), the comparisons (at most 4 min) and the checks
  (at most 8 min); with 6-17.5 minutes left only the checks; otherwise nothing.
* **What would count against the paper.** Many P cells not confirmed means the parallel-or-lazy label is wrong for them
  (the share is overstated, and those differences come from the engines' algorithms); Q cells confirmed mean the share
  is understated and "at most 37%" may be false. In other strata, low agreement means the cause counts of Table II
  carry more labelling error than the paper states.

### What ran

* `d3_plan.py` -> `d3_plan.json` (22:00:48, before any check): 358 audited cells (P 75, Q 31, C 21, S 117, R 51, H 150;
  overlapping), tests assigned per cell (N2 114 cells, N3 55, N1 26, N6 16, N7 15, N8 49, N9 121; 117 cells have no
  mechanism check at all).
* `d3_checks.py` code-tested twice on notebooks with at most 0.02 GB of input (scratch output, not used; the second
  test cached its tiny N3 jobs in `work/r5_replay/d3checks/`, which the guarded run reuses).
* Guarded job `runs/06_pandas_conformance_r5_replay_d3n2b.json` (`d3_run.py`): 23:10:16-23:47:19 ICT (37 min 3 s),
  rc 0, peak tree RSS 145.0 GB, peak host use 378.5 GB (other projects' load; 1-minute load average about 45-63). 56
  serial-variant runs in 26.7 min (54 completed; Modin-serial `yonelanuba/elo-merchant-by-yonela` stopped at the 96 GB
  cap after 279 s, as the original Modin run did; FireDucks-1-thread `guyalmog/...` crashed after 9 s); the Bodo
  exact-quantile patch was applied (child log: "patched BodoSeries BodoDataFrame"). The serial-record comparisons
  (`d1_compare.py --d3`, 56 outputs in 257 s) succeeded; `d3_checks.py` (N3/N1/N6) timed out after its 6 minutes
  without output and was rerun, parallel and resumable, in `runs/06_pandas_conformance_r5_replay_d3post.json` (see
  What ran, follow-up). An earlier queued copy (`..._d3n2.json`) was withdrawn before it started so that a D1
  comparison could go first.
* Code fix after the first analysis (no rerun needed): the N2 outcome rule "vanishes = no longer DIFF" had also been
  applied to cells that were never DIFF (E1-E4 cells of strata R, S, C, H), which made every such cell "vanish". For
  those cells `d3_analyze.py` now uses: vanishes = a finer class under the serial variant, persists = the same or a
  coarser class (failure cells: vanishes = a value class). The rule for DIFF cells, and so P, Q and the interval, is
  unchanged.

### Results (`d3_results.json`; every disagreement with its cell, checks and outcomes in `d3_disagreements.md`)

**Coverage.** Of the 358 audited cells, 196 have at least one mechanism check (N1, N2, N3, N6 or N7), 45 are only
consistent by construction (N8), and 117 have no mechanical check (mostly symptom-level groups such as "engine returns
other value" and engine-specific single-rater causes; 24 Modin cells among them are tested by the exploratory extension
below). "Decided" = agree + disagree + mixed (mixed: one check agrees, another disagrees; counted against agreement).

**Agreement per stratum.**

| Stratum | cells | agree | disagree | mixed | inconclusive | untested | agreement (decided) | outcomes by check |
|---|---|---|---|---|---|---|---|---|
| P | 75 | 23 | 31 | 2 | 19 | 0 | 0.411 (56) | N2 persists 28, persists (1 worker) 5, persists (laziness not neutralized) 19, vanishes 23; N7 confirmed engine behaviour 2, confirmed engine behaviour (uncaptured value differs from the captured one in 2 of 2 runs) 1 |
| Q | 31 | 24 | 3 | 4 | 0 | 0 | 0.774 (31) | N2 persists 27, vanishes 4; N3 confirmed 12, not confirmed 3; N7 confirmed engine behaviour 1; N8 consistent by construction 2 |
| C | 21 | 2 | 2 | 0 | 0 | 17 | 0.5 (4) | N1 not confirmed 1; N2 persists 1, persists (1 worker) 1; N7 confirmed engine behaviour 1 |
| S | 117 | 34 | 21 | 1 | 4 | 57 | 0.607 (56) | N1 not confirmed 4; N2 persists 24, persists (1 worker) 1, persists (laziness not neutralized) 4, vanishes 7; N6 confirmed 16; N7 confirmed engine behaviour 5; N8 consistent by construction 8 |
| R | 51 | 22 | 6 | 2 | 0 | 21 | 0.733 (30) | N1 confirmed 15, not confirmed 6; N2 persists 7, vanishes 3; N3 confirmed 6, not confirmed 1; N7 confirmed engine behaviour 3; N8 consistent by construction 6 |
| H | 150 | 45 | 20 | 6 | 1 | 78 | 0.634 (71) | N2 persists 21, vanishes 9; N3 confirmed 32, inconclusive 1, not confirmed 19; N7 confirmed engine behaviour 8, confirmed engine behaviour (uncaptured value differs from the captured one in 2 of 2 runs) 1; N8 consistent by construction 37 |

**Agreement per attribution source** (decided cells): rules 73 of 116 (0.63; 36 disagree, 7 mixed), single rater 34
of 56 (0.61; 21 disagree, 1 mixed), curated table 2 of 4 (0.50). **Per check:** N2 56 agree / 39 disagree (of which
parallel-or-lazy labels 23 / 33, other labels 33 / 6); N3 35 / 19; N1 15 / 11; N6 16 / 0; N7 15 / 0.

**N2, serial execution, and the parallel-or-lazy share** (pre-declared interval; denominators as in the paper):

| Configuration | paper | P vanish / persist / other | Q vanish (of) | interval (cells) | interval (share) |
|---|---|---|---|---|---|
| pyarrow backend | 4/51 = 7.8% | 0 / 4 / 0 | 0 (2) | [0, 0] | [0.0%, 0.0%] |
| Modin | 18/49 = 36.7% | 14 / 4 / 0 | 4 (5) | [14, 18] | [28.6%, 36.7%] |
| FireDucks | 14/58 = 24.1% | 2 / 12 / 0 | 0 (5) | [2, 2] | [3.4%, 3.4%] |
| Bodo (1 worker) | 12/80 = 15.0% | 3 / 9 / 0 | 0 (12) | [3, 3] | [3.8%, 3.8%] |
| Dask | 27/46 = 58.7% | 4 / 4 / 19 | 0 (7) | [4, 23] | [8.7%, 50.0%] |

By cause (P cells; vanish / tested): Modin row order of ties 4/5, partitioned dtype inference 7/7, lost `apply` side
effects 2/4, amplified float rounding 1/2; FireDucks row order of ties 1/12, amplified float rounding 1/2; Bodo
approximate quantiles 3/7 (exact quantiles), row order of ties 0/5 (already one worker); pyarrow backend row order of
ties 0/4 (one Arrow thread); Dask approximate quantiles 4/5 (one partition), `value_counts` order 0/3, lazy partition
model 19 not neutralized by serial execution. Q cells: 4 of 31 vanish, all Modin (two `corr` cells, one int64-for-
float64 cell, one undetermined); the other 27 persist, as their non-parallel attributions predict.

**Exploratory extension (decided after the N2 results):** on the 16 other notebooks with Modin introduced DIFF cells,
the serial variant removes the difference in 2 of 24 cells (CR-only line endings, which Modin's partitioned CSV reader
mishandles, and one lost axis name) and leaves 22 (all 9 silent-engine-error cells such as `value_counts` of a `cut`
and `pivot_table(aggfunc='size')`, all 10 `corr` cells, 1 axis name, 2 unattributed), as their non-parallel
attributions predict. Over all of Modin's 49 introduced DIFF cells, serial one-partition execution therefore removes
**20 (41%)**, at most 22 (45%) counting the 2 untested cells (`d3_results.json` `exploratory_modin_extension`).

**N3, injection of the claimed mechanism alone** (the engine's cell compared with pandas carrying only that
mechanism): dtype-name checks confirmed in 21 of 22 decided Bodo and Dask cells (pandas with Arrow-backed dtypes gives
the same output at E4 or finer); FireDucks chained assignment confirmed in 9 of 13 (pandas 3.0.6 with Copy-on-Write
agrees with FireDucks at E4 or finer; in the other 4, FireDucks or pandas 3.0.6 differs in something else as well, for example `unique()` labels in
`arjoonn/scout-script-7`); Arrow-backed result dtypes confirmed in only 3 of 11 Bodo cells and 0 of 6 Dask cells: these
engines' outputs differ from pandas-with-Arrow-dtypes beyond the dtype (index, values or shape), so "Arrow-backed
dtypes" names a visible part of a larger difference there.

**N1, single-mechanism sufficiency** (E1-E4 cells): confirmed 15 of 26 (missing-value sentinels 3/3, lost names 3/3,
int64-for-float64 3/3, NumPy scalar types 3/3, Arrow dtypes 2/3, dropped index 1/3); not confirmed 11, where one
relaxation does not suffice: "float rounding within tolerance" 0/4 (these E2 cells also need a dtype widening), Modin
"other inferred dtype" 0/3 (values typed differently, not just stored differently), a curated pandas 3.0.6 `str` cell
(also an index difference), 2 dropped-index cells (also other values) and one pyarrow-backend Arrow-dtype cell.

**N6 and N7:** the 16 single-rater "harness artefact" cells are all confirmed as printed-form DIFF cells by the
encoding census; all 15 audited cells that are D2 cases are confirmed engine behaviour without the harness.

**What it means for the paper.**
* About 6 in 10 decided attributions agree with the mechanical checks (rules 63%, single rater 61%), and the failure
  pattern is informative rather than random. Where a cause names a representation (sentinels, names, int64 slices, dtype-name
  checks, printed forms) or a probe-confirmed behaviour, the mechanical checks agree almost always (N1 for those
  sentinel, name, int64-slice, scalar-type and Arrow-dtype causes 14/15, N3 dtype-name checks 21/22, N6 16/16, N7
  15/15). Disagreement concentrates in two places: (1) the
  parallel-or-lazy label for row order of ties and rounding in FireDucks, Bodo and the pyarrow backend (the difference
  persists without parallelism: 33 of the 39 N2 disagreements), and (2) cells whose label names one of several
  mechanisms (Arrow dtypes in Bodo and Dask, float rounding in E2 cells, Bodo's approximate-quantile rule matching
  `np.percentile` or `describe()` in cells whose difference has another cause).
* Section IX and the Findings bullet should change: parallel execution explains few differences for FireDucks, Bodo
  and the pyarrow backend (at most 2, 3 and 0 cells, 3.4%, 3.8% and 0%, on the notebooks tested, which hold all their
  parallel-labelled cells and whose other DIFF cells all persisted), but for Modin, partitioned execution explains
  more than its labels say: 41-45% of its introduced DIFF cells vanish on one in-process partition (exploratory; the
  pre-declared interval on the notebooks of P is 29-37%). "At most 37%" is therefore not supported for Modin as a
  statement about mechanisms; it remains true only of the labels. For Dask the evidence gives 4-23 of 46.
* The paper's statement that the taxonomy supports diagnostic hypotheses, not precise causal prevalence (R1 W3), is
  supported by this audit; Table II's counts for "Arrow-backed result dtypes" (Bodo, Dask) and "row order of ties"
  (FireDucks, pyarrow backend) carry the largest labelling error found.

**Proposed paper text** (Section IX, replacing the sentence "Few introduced DIFF cells are assigned to parallel or
lazy execution itself ...", and the Findings bullet; Threats or Section VII for the audit sentence):

> A mechanical counterfactual audit, which re-ran these notebooks with parallel and partitioned execution switched off
> (Modin on one in-process partition, FireDucks and Arrow on one thread, Dask synchronously on one partition per file,
> Bodo with exact quantiles), removes the difference in 14 of Modin's 18 cells but in only 2 of FireDucks' 14, 3 of
> Bodo's 12 and none of the pyarrow backend's 4, whose tie orders and roundings differ from pandas even serially; in a
> follow-up on all Modin notebooks it removes at least 20 of Modin's 49 introduced \cls{DIFF} cells (41\%), so
> partitioned execution matters for Modin, while for FireDucks, Bodo and the pyarrow backend it explains at most 4\%
> on the notebooks tested.

    % src: icde27/analysis/r5_replay/d3_results.json parallel_or_lazy.{modin {P_vanish 14}, fireducks {P_vanish 2}, bodo {P_vanish 3}, pyarrow_backend {P_vanish 0}}; exploratory_modin_extension.modin_partitioned_share_cells [20, 22] (of 49)

> A mechanical audit of 358 attributions (counterfactual re-execution, injection of the claimed mechanism alone,
> single-relaxation checks; no human or language-model rater) agrees with 63\% of the decided rule assignments and 61\%
> of the single-rater ones; the disagreements concentrate in parallel-execution labels and in cells whose label names
> one of several mechanisms (artifact: every disagreement).

    % src: icde27/analysis/r5_replay/d3_results.json cells (assigned_by x overall: rule 73 of 116 decided, none 34 of 56); d3_disagreements.md (67 cells)

**Limitations.** A mechanical audit, not a human one: it tests whether a named mechanism is necessary or sufficient for
the observed difference, not whether the label is the best description. 117 of the 358 cells have no mechanical check
(symptom-level groups and engine-specific semantics), so the agreement rates describe the checkable attributions.
The serial variants change more than concurrency (Modin's one-partition engine skips partition-specific code paths;
Bodo's exact-quantile patch does not cover `np.percentile`), and the DIFF boundary is binary, so a cell with two
mechanisms persists when one is neutralized (two inspected cases: Modin's `apply` list regains its elements but gets 5
duplicate calls; Bodo's exact quantiles fix Q1/Q3 and the row count while stale values remain). The partner
configurations of N3 differ from the reference in more than the injected mechanism (pandas 3.0.6 has other changes;
the pyarrow backend is pandas, not the engine), which biases N3 towards "not confirmed". One run per variant. The Modin
extension is exploratory (decided after seeing N2).

**Inspection notes** (by the AI agent that ran the audit, on decoded values; not part of the mechanical verdicts):
Bodo `kanncaa1/dataiteam-titanic-eda` 16-17 use `np.percentile` (exact); their 46 instead of 10 rows come from the
positional index after a Boolean filter (the single rater's "positions instead of labels"), so the rule's
"approximate quantiles" label is wrong there; Bodo `mahtieu/...` 3: `describe()` includes a column that Bodo parsed as a
datetime, an inferred-dtype difference; Bodo `gmanish/...` 16: exact quantiles reproduce pandas' Q1/Q3 and its 9 rows,
but stale column values and the positional index keep the cell DIFF; Modin `shivavashishtha/...` 33: on the serial
engine the list extended inside `apply` holds 124,239 elements (pandas 124,234, Modin on Ray 5), so the lost side
effects are an out-of-process effect and the remaining difference is 5 duplicate calls.

### What ran (follow-up)

* Guarded job `runs/06_pandas_conformance_r5_replay_d3post.json` (`d3_post.py`): 02:35:39-02:44:36 ICT on 11 November
  (8 min 57 s), rc 0, peak tree RSS 40.4 GB, peak host use 295.0 GB; remaining budget at start 20.5 min, so all three
  steps ran: the Modin serial extension (16 of 16 notebooks completed, 274 s), the comparisons (16 new outputs, 1 s) and
  `d3_checks.py` (N3 37 jobs, N1 26 cells, N6 16 cells; 261 s).
* `d3_analyze.py` -> `d3_results.json`; `report_tables.py d3dis` -> `d3_disagreements.md` (67 cells: 59 disagree, 8
  mixed).

Status: FINAL. Outputs: `d3_plan.json` a2f3bed8bbafca1437fbda28629bf6f3d6f82dc2cc1ea914cccd32ba18e5fee0,
`d3_ext_plan.json` b01836a69a5352ed6613888dfff91f3e6224b0679f068a49fb36c71ff2155efd, `d3_run_d3n2.json`
ad3b8fe7c5a32ccac1f361107ff9570feda8e5dc9097b600b8717762f9419a4f, `d3_run_ext.json`
97e96738984624275d4251f22e438da22e01b6afb59000d84881d25ed5743759, `d3_checks.json`
3f4dfc32ecdde83d405bf62ee2f05ef7d13753236fee546190ed9a68d921e296, `d3_results.json`
7051304190bed7307a90ee4f6b56e8b164acc45f983bbefb98ada9dd3e51e05e, `d3_disagreements.md`
e2415885380c66415942dd5d0b225a8962befb02849b8b89b736b7da26bd42a4; serial comparisons under
`work/r5_replay/compare/serial/` and check caches under `work/r5_replay/d3checks/` (hashes in `manifest.json`).

---------------------------------------------------------------------------------------------------------------------

## Guarded jobs, budget and deviations

| State file (`runs/`) | Item | Start-end (ICT) | Wall | rc / status | Peak tree RSS |
|---|---|---|---|---|---|
| `06_pandas_conformance_r5_replay_d1.json` | D1 replays (stopped by me, throughput) | 21:42:23-21:51:29 | 9.1 min | 130 / failed | 91.8 GB |
| `06_pandas_conformance_r5_replay_d1b.json` | D1 replays | 21:51:48-22:09:15 | 17.5 min | 0 / completed | 165.2 GB |
| `06_pandas_conformance_r5_replay_d2.json` | D2 uncaptured replays | 22:13:41-22:16:28 | 2.8 min | 0 / completed | 47.9 GB |
| `06_pandas_conformance_r5_replay_d1cmp.json` | D1 comparisons, 4 workers | 22:24:01-22:30:34 | 6.6 min | -15 x3 / stopped at 100 GB | 100.4 GB |
| `06_pandas_conformance_r5_replay_d3n2b.json` | D3 serial runs + comparisons | 23:10:16-23:47:19 | 37.1 min | 0 / completed | 145.0 GB |
| `06_pandas_conformance_r5_replay_d2b.json` | D2 FireDucks rerun | 00:04:42-00:04:46 | 0.1 min | 0 / completed | 0.4 GB |
| `06_pandas_conformance_r5_replay_d1cmp2.json` | D1 comparisons, 1 worker (stopped by me, budget) | 01:57:26-02:23:55 | 26.5 min | -15 / failed | 74.9 GB |
| `06_pandas_conformance_r5_replay_d3post.json` | D3 extension, comparisons, checks | 02:35:39-02:44:36 | 8.9 min | 0 / completed | 40.4 GB |

Total guarded wall time 108.5 minutes of the 2-hour cap; every job was launched before 06:00 and finished before
09:00 ICT. Two guard states have no `finished_utc` because the jobs were stopped; their end times come from my watch
loops. The withdrawn queue entry `..._d3n2` never started and wrote no state.

Deviations and faults, all reported in the sections above: D1 job 1 stopped and relaunched with more concurrency
(throughput, before any comparison); D1 small-notebook comparisons run unguarded peaked at 17.4 GB in one worker for
about a minute (above the 4 GB guideline; the machine had more than 300 GB free); the D1 large-notebook comparison was
stopped at 26.5 minutes to keep the cap, leaving 2 disputed cells uncompared; the D2 observation fault in four FireDucks
cases (rerun allowed by the stop rule); the D3 N2 rule for non-DIFF cells (code fix, no rerun); the D3 checks timeout
inside the N2 job (rerun in the follow-up job); two time-budget amendments and one analysis amendment to D3 written
before the results they concern; one exploratory extension (Modin) decided after the N2 results. While a background
monitor was being set up, an empty helper file was briefly written to `/tmp` and deleted at once; nothing else was
written outside the write set.

Not done within the cap: the vs-reference comparison of 2 replayed Modin notebooks (`maxiaoyue/...`,
`yuliagm/talkingdata-...`) and 9 self-comparisons of large notebooks; replays of the 4 long notebooks (7 cells); the
2 Modin notebooks with memory stops in the exploratory extension.

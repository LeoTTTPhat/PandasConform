# R5 capture experiments (agent B1, round REV-06-R5B1-2026-11-10)

Paper: PandasConform (ICDE 2027 EAB), project `06_pandas_conformance-ICDE`. Items: C1 exact recapture of printed-form
comparisons (metareview P0 and decisive issue 1, R1 W2 and minor 2, R2 W2, R4 Q3, SUMMARY section 6 path item 2);
C2 adversarial end-to-end capture suite (R4 W2 and Q3). Everything here was written by B1; the paper, checker,
response file and release belong to agent A. All paths are relative to the project folder unless stated.

Shared code for both items: a copy of the harness in `icde27/analysis/r5_capture/harness/pconf/`
(`harness_source_sha256_original.txt` lists the SHA-256 of the original `src/pconf` modules).

* `capture_orig.py`, `classify.py`, `dfeq.py`, `compare_worker.py`, `nbsource.py`, `engines.py`: byte-identical to
  `src/pconf` (the comparator is the existing one).
* `capture.py`: the original encoder plus an exact recursive encoding of nested values. An element of an object column
  that the original encoder prints (tag `T_CONTAINER`: a nested list, tuple, dict or set, printed element by element;
  tag `T_OTHER`: a frame, Series, array or any other object, printed with `repr`) is instead captured as an object
  record of its own (engine objects first converted with the engine's own conversion, as top-level values are) and
  tagged `T_NESTED` with payload `<kind>#<object hash>`; equal payloads therefore mean E0-equal nested values. A
  nested container whose elements are (recursively) exactly tagged scalars is encoded inline instead, as canonical
  JSON of (tag, payload, type) triples (`<kind>j#...`, hashed as `<kind>h#<sha256>` above 2,048 characters), which is
  unambiguous where the printed form was not. Lazy engine scalars become their computed exact scalar tag; NumPy and
  pandas dtype objects, ranges, slices and bound methods get exact pseudo-records. An element without an exact
  encoding even then (an arbitrary object, nesting deeper than 8, more than 5e7 nested cells or 2,000 nested records
  per value, an engine value whose conversion raises) keeps `T_OTHER` with its `repr` and is listed as inexact in the
  object record (`info.nested_inexact`). Encodings of everything else and `ENCODING_VERSION` are unchanged, so a
  value without such elements has the same hash under both encoders (checked).
* `runner_child.py`: captures every value with the exact encoder and, when the value holds a nested element, also
  with the original encoder (`capture_orig.py`) from the same object in the same run (`inputs_orig`,
  `outputs_orig`); records nested records; optional `stop_after` cell. `orchestrate.py`: per (engine, notebook) stop
  cell from `--stop-plan` (part of the run fingerprint), nested records in salvaged progress. `util.py`/`datasets.py`:
  read environments, PandasBench data and the prepared inputs of the original campaigns from the project (never
  prepare inputs), write runs, captures and scratch only under `work/r5_capture/`.
* `c1_compare.py`: classifies a reference/engine pair of new runs three times with the unchanged
  `classify.classify_run`: `orig` (every entry replaced by the original encoder's entry for the same value), `exact`
  (nested values compared through their exact payloads) and `graded` (nested values graded by the same comparator;
  see the C1 design).

Because both encodings come from one execution, `exact` against `orig` of the same new runs isolates the encoding
effect (no run-to-run variation by construction), and `orig` of the new runs against the original campaign
isolates run-to-run (and run-condition) variation.

---------------------------------------------------------------------------------------------------------------------

## C1. Exact recapture of the printed-form comparisons

### Pre-declared design (written 2026-11-10 21:50 ICT, before any C1 run)

**Question.** For the scored cells compared through printed forms (r4_printed_forms.json: 688 cells, 317 matching,
343 DIFF, 28 other classes, over the seven configurations), are the matching printed forms exact matches, exact
mismatches, or not exactly encodable, and the same for the non-matching ones; how do the classes and clean-input
levels of these cells and of the cells that read printed-form values change, and what does that do to the paper's
principal comparisons (clean@E2 DIFF shares, the paired engine-minus-pandas DIFF differences on cells clean@E2
under both, the notebooks with an introduced DIFF)?

**Census and selection (no new runs).** `c1_triage.py` (elements of each printed-form output: containers of exactly
tagged scalars, pandas/NumPy objects, other objects) and `c1_plan.py` (printed forms in cell outputs, `pf_out`, and
in cell inputs, `pf_in`, per configuration; recorded time to each cell). A cell whose class or clean level can change
under an exact encoding is pf_out or pf_in; all other cells keep class and clean level if the run repeats exactly.
`c1_select.py` (rule in its docstring): tier 1 = pf cells in clean@E2 or able to enter it (they read a printed-form
value and all their other inputs agree at E2 or finer); tier 2 = the other scored pf cells. Each (configuration,
notebook) stops at its last pf cell unless that costs more than 120 s beyond the last tier-1 cell (then at the last
tier-1 cell); notebooks with only tier-2 cells run if they cost at most 120 s. Selection: 1,128 of 1,130 tier-1 cells
(2 dropped for the budget, below), 210 tier-2 cells covered, 23 tier-2 cells not covered (`c1_selection.json`).

**Configurations and runs.** New reference (pandas 2.3.3, `ref`) on all 54 selected notebooks up to the largest stop
cell; p15, p30, pyarrow_backend, modin, fireducks, bodo (`BODO_NUM_WORKERS=1`, `OMPI_MCA_btl_tcp_if_include=lo0`),
dask on their selected notebooks; scale 1, seed 0, the original run configuration (600 s cell timeout, 3,600 s
notebook timeout, input capture off above 1 GB of input, 96 GB per-notebook memory cap). Streams (one orchestrator
per stream, own campaign name `r5c1_<stream>`, one capture store `work/r5_capture/captures`; layout in
`c1_selection.json`, files in `c1_streams/`): guarded job 1 (`runs/06_pandas_conformance_r5_capture_c1a.json`;
it finally ran as `..._c1a2.json`, and job 2 as `..._c1b2.json`, see Part B;
`c1_job.sh job1 2100 2580`, guard limit 190 GB): ref (3 notebooks at a time; revised at 22:28, before the run, since
every configuration needs it), p15, p30, pyarrow_backend (2 at a time each), and
dask, fireducks, bodo, modin (one notebook at a time each) on every run costing at most 1,000 s of recorded time
(longest first; the modin stream starts and the other engine streams end with runs whose original peak exceeded
50 GB, so that they do not overlap); guarded job 2 (`..._c1b.json`, `c1_job.sh job2 600 1980`, limit 120 GB): the
heavy runs, of which the guarded-time budget allows one per stream: modin
`tanulsingh077/twitter-sentiment-extaction-analysis-eda-and-model` (18 tier-1 cells) and bodo
`artgor/eda-and-models` (2); modin `pmr3508f20977e697/...` and bodo `nadare/...` (one tier-1 cell each) are not run.
`--deadline`/`--hard-budget` bound each job (about 45 and 35 minutes). Each job ends by classifying every new pair
(`c1_compare_all.py`, 6 workers, at most 15 minutes; pairs left over are classified by the next job, or by a
separate guarded compare job). (This paragraph was revised at 22:00 ICT, before job 1 started, to fit the 2-hour
guarded budget.) Engines of different configurations run concurrently (the original campaign ran them one after
another); this can change timing, not values, except through the 600 s cell timeout: a cell that times out here
but not originally is a run-condition difference and is reported as such.

**Comparisons (existing comparator).** For each configuration and notebook, `c1_compare.py` on (new ref, new
configuration run), both truncated at the configuration's stop cell, in three variants: `orig` (the original
encoder's entries), `exact` (exact entries; the unchanged comparator compares a nested value through its exact
payload, so nested values must be E0-equal), and `graded` (exact entries; a comparison that the unchanged comparator
finds DIFF and that involves nested values is graded: each differing aligned nested pair is compared by the same
comparator on its own exact records, recursively, and if all reach a level the pair is compared again with the
engine's nested payloads replaced by the reference's; the level is the coarser of the two). Original NONDET cells
(ref vs ref#2 of the original campaign) stay excluded.
*Amendment (code in place before job 1 started at 22:09 ICT; text written at 22:10, before any C1 result existed):*
the `graded` variant was added and made primary after a smoke test
showed that pandas 3.0.6 gives column labels the `str` dtype, so every frame differs from pandas 2.3.3 at E2; under
`exact` every nested frame of pandas 3.0.6 would therefore become DIFF, an artifact of comparing nested values more
strictly than top-level values. `graded` applies the contract's levels to nested values; `exact` is kept as the
strict reading. Tested on synthetic pairs (labels dtype, float tolerance: E2; one changed value: DIFF; equal: E0;
in lists, dicts and object columns).

**Metrics.**
1. Per printed-form output and cell of the census (by original outcome: matching = E0-E4, non-matching = DIFF, other):
   exact match (the new `graded` comparison gives the class of the new `orig` comparison), exact match at a finer
   level, exact mismatch (for originally matching cells, now DIFF or another non-level class: false agreement; for
   DIFF cells, still DIFF: a confirmed difference, or now a level: a difference that came from the printed form),
   still not exactly encodable (an element left inexact on either side), not recaptured (run not selected, cut, cell
   missing, or the new `orig` run disagrees with the original run in this cell's class: run-to-run). The same on
   `exact` (nested values E0-equal) as the strict reading.
2. Run-to-run: per configuration, cells (up to the stop cells) whose `orig` class or clean level in the new runs
   differs from the original campaign, and outputs whose original-encoder object hash differs between the new and
   the original run (new reference against original reference, and per engine). Encoding effects are counted only
   on cells whose new `orig` outcome equals the original outcome.
3. Propagation: clean levels of the readers (`pf_in` cells) under `graded`; cells entering or leaving clean@E2.
4. Principal comparisons recomputed by `c1_analyze.py` (same population, bootstrap seed and keys as r1_cells.py;
   the `published` variant must reproduce r1_cells.json and r4_audit.json, 51 checks): clean@E2 DIFF share per
   configuration, the ten paired differences (engine minus p15/p30 on cells clean@E2 under both, 90%/95% intervals,
   readings), notebooks with an introduced DIFF (pure rule-independent definition and the published heuristic), in
   the variants `published`; `exact_graded` (primary: printed-form cells with an encoding effect and no run-to-run
   change take their `graded` class, clean level, outputs and input levels; all other cells keep the original);
   `exact_nested_e0` (the same with `exact`); `exact_graded_strict` (as `exact_graded`, and printed-form cells that
   were not recaptured, remain inexact, or have both a run-to-run change and an encoding effect leave every view);
   `exclude_all_pf` (every printed-form cell, outputs and readers, leaves every view: the bound that certifies
   nothing). Cell-level changes are delivered as `c1_cell_changes.csv` (keys label, notebook, cell; original, new
   `orig`, `graded` and `exact` class and clean level; flags) for A's scripts, and the recomputed comparisons as
   `c1_results.json` (`principal`).

**Stop rule.** Each job runs until its streams finish or reach their deadline/hard budget; nothing is rerun after
looking at results, except a run that failed for a harness reason (reported).

**What counts against the paper.** Matching printed forms that are exact mismatches (false agreement) in clean@E2
cells, especially if they change a paired reading (for example a drop-in engine becoming distinguishable from a
pandas version, or Bodo/Dask no longer differing more often than pandas 3.0.6); readers whose clean status was
wrong; any change of the headline notebook range. Conversely DIFF cells that become exact matches (false
differences, for example lazy Dask values inside containers printed instead of computed) weaken "Bodo and Dask
differ more often" if they are frequent in clean@E2.

### Part A: census of printed forms in outputs and inputs, and the exclusion bound (stored data only)

Run directly (analysis on stored records, `nice`, < 6 GB, 20-35 s each): `c1_triage.py` -> `c1_triage.json`,
`c1_plan.py` -> `c1_plan.json`, `c1_analyze.py --bound-only` -> `c1_bound.json` (its `published` variant reproduces
r1_cells.json and r4_audit.json in all 51 checks).

* Printed forms reach more cells than the 688 of the R4 census, because a cell also depends on printed-form values
  through its inputs: 1,363 scored cells are printed-form cells, 688 with a printed-form output and 675 more that only
  read a printed-form value (pre-cell input record, or last captured value in the 10 notebooks without input
  capture); 493 of them are in the clean@E2 view (330 + 163).
* What the 817 printed-form outputs hold (an output can hold several kinds): 459 hold nested containers of exactly
  tagged scalars (for example lists of strings from `str.split`; their printed form is exact up to delimiter
  collisions, which C2 shows can happen); 363 hold pandas or NumPy objects, most often the dtype objects of a
  `df.dtypes` Series (numpy Int64/Float64/Object dtypes: 90, 87 and 74 outputs), then Series (78), frames (73),
  arrays (58) and engine objects (Dask lazy scalars 40, Modin/FireDucks/Bodo frames and Series); 44 hold other
  objects (bound methods 17, ranges 6, ...).
* Per cell (`c1_triage_cells.py` -> `c1_triage_cells.json`): of the 317 cells whose printed forms matched, 170 hold
  only nested containers of exactly tagged scalars (their match is exact up to delimiter collisions without new
  runs), 42 hold NumPy or pandas dtype objects (a `df.dtypes` Series; their reprs identify the dtype), 83 involve a
  printed frame, Series or array (rows can be cut, floats are printed with 6 decimals, dtypes are not printed: the
  real uncertainty) and 22 another object. Of the 343 printed-form DIFF cells: 153, 39, 138 and 13.
* Exclusion bound (`exclude_all_pf`): every printed-form cell, outputs and readers, leaves every view (nothing
  certified). Same population, bootstrap seeds and keys as the paper.

| configuration | clean@E2 cells, published -> bound | DIFF share %, published -> bound | notebooks with an introduced DIFF (pure rule), published -> bound |
|---|---:|---:|---:|
| p15 | 2129 -> 2033 | 2.3 -> 2.2 | 36 -> 34 |
| p30 | 2215 -> 2070 | 2.5 -> 1.9 | 33 -> 23 |
| pyarrow_backend | 1091 -> 1035 | 2.6 -> 1.4 | 38 -> 27 |
| modin | 2332 -> 2227 | 2.0 -> 1.8 | 36 -> 31 |
| fireducks | 1248 -> 1201 | 2.7 -> 2.3 | 43 -> 37 |
| bodo | 753 -> 734 | 6.0 -> 4.8 | 47 -> 41 |
| dask | 545 -> 520 | 6.2 -> 2.9 | 24 -> 12 |

| pair | published: diff [95%] (cells) | bound: diff [95%] [90%] (cells) | reading, published -> bound |
|---|---|---|---|
| pyarrow_backend-p15 | -0.3 [-2.0, +1.4] (997) | -1.7 [-3.1, -0.2] [-2.9, -0.4] (961) | n.d. -> less often |
| pyarrow_backend-p30 | +0.6 [-0.7, +1.9] (1010) | -0.2 [-1.5, +0.9] [-1.2, +0.7] (956) | n.d. -> n.d. |
| modin-p15 | -0.1 [-1.2, +1.0] (1833) | -0.2 [-1.3, +0.8] [-1.1, +0.7] (1758) | n.d. -> n.d. |
| modin-p30 | -0.3 [-1.3, +0.7] (1938) | -0.1 [-1.1, +1.0] [-0.9, +0.8] (1840) | n.d. -> n.d. |
| fireducks-p15 | -0.2 [-1.4, +1.1] (1137) | -0.5 [-1.6, +0.8] [-1.4, +0.6] (1105) | n.d. -> n.d. |
| fireducks-p30 | +0.6 [-0.8, +2.0] (1206) | +0.8 [-0.6, +2.1] [-0.3, +1.9] (1166) | n.d. -> n.d. |
| bodo-p15 | +2.8 [+0.4, +5.5] (715) | +1.7 [-0.6, +4.3] [-0.3, +3.8] (695) | more often -> n.d. |
| bodo-p30 | +4.1 [+2.2, +6.4] (749) | +3.7 [+1.9, +6.0] [+2.1, +5.6] (728) | more often -> more often |
| dask-p15 | +2.8 [-0.6, +5.9] (541) | -0.4 [-3.2, +2.4] [-2.7, +1.9] (509) | n.d. -> n.d. |
| dask-p30 | +3.9 [+1.6, +6.1] (539) | +1.4 [-0.2, +3.1] [+0.0, +2.8] (509) | more often -> n.d. |

Meaning: if no printed-form cell or reader is trusted, Modin and FireDucks keep their readings, but the pyarrow
backend becomes distinguishable from pandas 1.5.3 (it differs LESS often), Bodo is no longer distinguishable from
1.5.3 (already so in the paper's 16-cell sensitivity) and Dask no longer from 3.0.6; the notebooks with an
introduced DIFF would range over 12 to 41 (pure rule; 24 to 47 published) or 12 to 39 (published heuristic; 24 to 45
with the 16 known artifact cells, 24 to 43 without them, the abstract's range). The bound is conservative: it drops 1,363 cells most of which may be
exact, which is what Part B measures. Proposed use: report this bound only together with Part B's exact result.

Status (Part A): FINAL (2026-11-10 22:27 ICT; per-cell kinds added 23:11). Output SHA-256: `c1_bound.json`
d976fee7bb8b4dc9331be76e3bf1ab26ba03a06ee95548a5f3cdbc251a6cf11e; `c1_triage_cells.json` bbaede638ea6dae9a188041072164bcda843b7c788b12379768c012d873b29b3; `c1_plan.json`
24d03415fd46f396bf8ccff0fe88db08b8e87671146c9fddc23634ae8bf3606d; `c1_triage.json`
6c3c37bd33e10d55ee7666a160acb2a61834ee20ba58cb1a86607a6498b589e4.

### Part B: exact recapture (new runs)

What has run so far: a first attempt of guarded job 1 (`runs/06_pandas_conformance_r5_capture_c1a.json`, started
22:09:15 ICT, stopped by B1 at about 22:13:40 after about 4.5 minutes, status stopped) wrote 295,000 capture blobs
in 4 minutes, because the first version of the exact encoder gave every nested list of a list-valued column its own
record and blob; with 158 GiB of free disk this was unsafe, so B1 stopped it, deleted its outputs, and changed the
encoder so that nested containers of scalars are encoded inline (canonical JSON, hashed above 2,048 characters) and
nested records are capped at 2,000 per value (inexact beyond). A first attempt of job 2 (`..._c1b.json`) started
22:17:08 on the changed but still untested encoder while the store was being cleaned; B1 stopped it after about 2
minutes (status stopped) and deleted its outputs. The changed encoder was then unit-tested (inline lists, depth 6,
the delimiter collision, a 20,000-row list column: 0.22 s, no extra blobs) and C2 ran on it. Jobs 1 and 2 are
queued again (`runs/06_pandas_conformance_r5_capture_c1a2.json`, `..._c1b2.json`, same streams and budgets).
No result of the stopped attempts is used.

Job 1 (second attempt, `runs/06_pandas_conformance_r5_capture_c1a2.json`): started 00:44:32 ICT after 8,370 s in
the lock queue; run phase 00:44:32-01:18:19 (2,027 s), every stream finished before its deadline: ref 54, p15 35,
p30 35, pyarrow_backend 35, dask 48, fireducks 31 notebooks completed; modin 30 completed and 1 crashed
(`balajivenkat96/solar-plants`); bodo 22 completed and 4 crashed (`j0thu777/onlineretailanalysis`,
`gravix/gradient-in-a-box`, `jirakst/book-recommendation`, `shunjiangxu/blood-is-thicker-than-water-friendship-forever`).
Peak process-tree RSS 126.6 GB (limit 190), peak host use 321 GB; host load averages 36-78 during the run (other
projects and CI runners were active). Compare phase from 01:18:19: 208 of the 241 pairs in the 15-minute budget;
two workers held the heavy pairs. At 01:43 B1 stopped the last worker (still on p15 `yonelanuba/elo-merchant-by-yonela`,
whose `orig` comparison was written) to keep within the 2-hour budget. Because B1 had edited `c1_job.sh` for job 2
while job 1's bash was still reading that file, bash then executed a misaligned line ("line 35: 0: command not
found"), repeated the "runs end" message and ran the compare phase a second time (31 pending pairs, 6 workers; it
classified the small ones within 21 s) before the script returned 241 (guard status failed, finished 01:43:37; 59 minutes of guarded wall time). The
comparator code did not change and every output is written atomically, so no result is affected; 240 of 241 job-1
pairs are classified, and the last one (p15 elo-merchant, `exact` and `graded`) is classified in job 2.
Job 2 (`runs/06_pandas_conformance_r5_capture_c1b2.json`), decided at 01:39 before any C1 result had been read: the
bodo `artgor/eda-and-models` run (2 tier-1 cells, 1,536 s of recorded time) is dropped to fit the budget; job 2 runs
modin `tanulsingh077/...` (18 tier-1 cells) and, in parallel, the remaining job-1 comparison (3 workers), then
classifies the modin pair.

Job 2: started 01:43:37 ICT (lock wait 11,906 s), completed 01:57:23, return code 0 (13.8 minutes; peak tree RSS
33.1 GB, peak host 260.5 GB): the modin run completed (cells to 67), the last job-1 pair and the modin pair were
classified. All 242 pairs of the selection are classified (the dropped bodo `artgor` run has none). Guarded wall time
of all B1 jobs: about 79.5 minutes (stopped attempts 4.5 and 1.7, C2 0.4, job 1 59.1, job 2 13.8).

### Part B results (`c1_results.json`, `c1_cell_changes.csv`, `c1_runlog.json`)

Coverage. Of the 1,363 printed-form cells, 1,335 were recaptured (1,330 with the same original-encoder outcome as the
original campaign, 5 with a run-to-run change); 28 were not (12 tier-2 cells excluded by the cost rule, 11 tier-2
cells after the stop cell, 3 cells of the dropped bodo `artgor` run, 2 cells of the two runs over the budget). No cell
outside the printed-form set changed with the encoding.

Run to run (new run under the original encoder against the original campaign). Object hashes of the outputs up to the
stop cells: reference 2,124 of 2,124 identical, pandas 1.5.3 1,824/1,824, pandas 3.0.6 1,753/1,753, pyarrow backend
1,739/1,739, Bodo 771/771; Dask 574/639, FireDucks 1,334/1,394, Modin 1,384/1,406 identical (engine-side
nondeterminism). Cell classes changed in 5 printed-form cells (Dask 1, FireDucks 3 row-order flips, Modin 1) and 3
other Modin cells; these are not counted as encoding effects. Bodo's 4 crashes are the original ones (same notebooks,
same cell); one Modin run (`balajivenkat96/solar-plants`) ended with a crash after its stop cell (the runner record
was salvaged with all cells up to the stop cell; originally it completed).

The census (688 cells; graded nested levels, the primary reading):

| original outcome | exact match | finer level | coarser level | now DIFF | DIFF came from the printed form (now E0 / E2 / E3 / E4) | still DIFF | not exactly encodable | not recaptured |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| matching printed form (317) | 276 | 28 | 4 | 0 | - | - | 5 | 4 |
| printed-form DIFF (343) | - | - | - | - | 71 (17 / 35 / 10 / 9) | 223 | 39 | 10 |
| other classes (28: 14 ERR, 10 UNCOMPARABLE, 4) | 24 unchanged | | | | | | 4 | 0 |

In the clean@E2 view: of 243 matching cells, 207 exact, 28 finer, 4 coarser, 2 inexact, 2 not recaptured; of 76 DIFF
cells, 43 came from the printed form (13 / 20 / 7 / 3), 29 stay DIFF, 4 inexact. The 4 coarser cells are pandas
3.0.6 cells whose nested frames carry `str` column labels that the printed form hides (E0 becomes E2). The 28 finer
cells are Modin (16) and FireDucks (12) cells whose nested engine frames the original encoder recorded with the engine
type name (E2 becomes E0). The 71 false DIFF cells: Dask 19 (16 of them lazy scalars printed uncomputed), pyarrow
backend 18 (nested frames and arrays with Arrow dtypes print differently), Bodo 13, p15 7 (`Int64Index` reprs), Modin
5, FireDucks 5, p30 4 (nested `ArrowStringArray` reprs). 15 of the paper's 16 known printed-form artifact cells are
among them (10 now E2, 5 now E3); the 16th (Modin `j0thu777/onlineretailanalysis` cell 20, bound methods stored as
values) is not exactly encodable. The not exactly encodable
cells are mostly Dask lazy values whose computation raises (25 DIFF cells) and FireDucks nested arrays beyond the
2,000-record cap (10). Strict reading (nested values E0-equal): 17 of the matching cells become DIFF (under graded
nested levels 16 of them are E2 and 1 is E1: dtype or label differences), and only 18 DIFF cells reach a level.

Readers (`pf_in` cells, graded): of the 965 recaptured readers, 29 enter clean@E2 (pyarrow backend 13, Bodo 8, Dask
3, p15 2, p30 2, Modin 1) and none leaves it; the clean level changes for 80 of them (the 29 included).

Principal comparisons (same population, bootstrap seeds and keys as the paper; `published` reproduces
r1_cells.json and r4_audit.json in all 51 checks):

| configuration | clean@E2 DIFF %, published [95%] (cells) | exact, graded nested levels (primary) | exact, nested E0 (strict) | exact graded, uncertain cells removed |
|---|---|---|---|---|
| pandas 1.5.3 | 2.3 [1.6, 3.1] (2,129) | 2.2 [1.5, 3.0] (2,131) | 2.4 (2,131) | 2.2 (2,126) |
| pandas 3.0.6 | 2.5 [1.6, 3.5] (2,215) | 2.4 [1.5, 3.4] (2,217) | 2.8 (2,200) | 2.3 (2,216) |
| pyarrow backend | 2.6 [1.5, 3.8] (1,091) | 1.7 [0.9, 2.7] (1,104) | 2.7 (1,091) | 1.7 (1,102) |
| Modin | 2.0 [1.4, 2.8] (2,332) | 1.8 [1.2, 2.5] (2,333) | 2.1 (2,332) | 1.8 (2,331) |
| FireDucks | 2.7 [1.7, 4.0] (1,248) | 2.5 [1.4, 3.7] (1,248) | 2.8 (1,247) | 2.4 (1,246) |
| Bodo | 6.0 [3.9, 8.6] (753) | 5.1 [3.1, 7.6] (761) | 6.0 (753) | 5.2 (756) |
| Dask | 6.2 [3.8, 9.0] (545) | 3.5 [1.6, 5.8] (548) | 3.7 (545) | 3.3 (546) |

| pair (engine minus pandas, points) | published: diff [95%] [90%] reading | exact, graded (primary) | exact, nested E0 | graded, uncertain removed |
|---|---|---|---|---|
| pyarrow - 1.5.3 | -0.3 [-2.0, +1.4] [-1.7, +1.1] n.d. | -1.2 [-2.8, +0.4] [-2.5, +0.2] n.d., 90% leaves +-2 | -0.3 [-2.1, +1.5] n.d. | -1.2 [-2.8, +0.4] n.d. |
| pyarrow - 3.0.6 | +0.6 [-0.7, +1.9] [-0.5, +1.7] n.d. | -0.1 [-1.3, +1.0] [-1.1, +0.8] n.d. | +0.3 [-0.9, +1.5] n.d. | -0.1 n.d. |
| Modin - 1.5.3 | -0.1 [-1.2, +1.0] n.d. | -0.2 [-1.2, +0.8] [-1.1, +0.6] n.d. | -0.1 n.d. | -0.3 n.d. |
| Modin - 3.0.6 | -0.3 [-1.3, +0.7] n.d. | -0.4 [-1.3, +0.6] [-1.2, +0.4] n.d. | -0.6 n.d. | -0.4 n.d. |
| FireDucks - 1.5.3 | -0.2 [-1.4, +1.1] n.d. | -0.4 [-1.5, +0.8] [-1.3, +0.7] n.d. | -0.2 n.d. | -0.4 n.d. |
| FireDucks - 3.0.6 | +0.6 [-0.8, +2.0] n.d. | +0.5 [-0.8, +1.8] [-0.6, +1.6] n.d. | +0.1 n.d. | +0.5 n.d. |
| Bodo - 1.5.3 | +2.8 [+0.4, +5.5] more often | +2.1 [-0.2, +4.6] [+0.1, +4.2] n.d. | +2.8 [+0.4, +5.5] more often | +2.1 n.d. |
| Bodo - 3.0.6 | +4.1 [+2.2, +6.4] more often | +3.6 [+1.8, +5.8] [+2.0, +5.4] more often | +3.6 more often | +3.6 more often |
| Dask - 1.5.3 | +2.8 [-0.6, +5.9] n.d. | +0.0 [-3.0, +2.7] [-2.4, +2.3] n.d. | +0.2 n.d. | -0.2 n.d. |
| Dask - 3.0.6 | +3.9 [+1.6, +6.1] more often | +1.3 [-0.2, +3.0] [+0.0, +2.7] n.d. | +0.7 [-1.1, +2.6] n.d. | +1.1 n.d. |

Notebooks with an introduced DIFF (pure rule / published heuristic): published p15 36/34, p30 33/33, pyarrow
38/36, Modin 36/36, FireDucks 43/40, Bodo 47/45, Dask 24/24 (ranges 24-47 / 24-45); exact graded 35/33, 31/31,
31/29, 32/32, 39/36, 44/42, 15/15 (ranges 15-44 / 15-42); strict 36/34, 38/38, 39/37, 37/37, 44/41, 47/45, 16/16.

### What Part B means for the paper's claims

* The reviewers' main worry, false agreement, is not borne out where it was measured: none of the 308 recaptured,
  exactly encodable matching printed forms hides a value difference; 4 (pandas 3.0.6) hide a dtype-only label change
  that makes them E2 instead of E0, and 28 were in fact finer (E0, not E2). The readers of printed-form values do not
  leave clean@E2; 29 enter it.
* The reverse error is larger than the paper says: 71 of the 343 printed-form DIFF cells (43 of 76 in clean@E2) are
  representation artifacts, not 16. They concentrate in Dask (lazy values inside containers printed uncomputed), the
  pyarrow backend and Bodo, so they inflate exactly the comparisons that make Bodo and Dask look worse.
* Modin and FireDucks keep their readings (paired differences -0.4 to +0.5 points, 90% intervals inside +-2). The
  pyarrow backend becomes less error-prone than reported (clean@E2 DIFF 1.7%, paired -1.2 against 1.5.3; not
  distinguishable, but its 90% interval leaves the +-2 margin). Bodo still differs more often than pandas 3.0.6
  (+3.6 [+1.8, +5.8]) but no longer distinguishably from 1.5.3 (as in the paper's 16-cell sensitivity). Dask is no
  longer distinguishable from either version (+1.3 [-0.2, +3.0] against 3.0.6): the paper's statements that "Bodo and
  Dask differ more often than 3.0.6" and its abstract phrase that Bodo and Dask "exceed 3.0.6's" DIFF share do not
  survive an exact encoding for Dask. The notebook range of the abstract, 24 to 43, becomes 15 to 42 (heuristic;
  15 to 44 under the pure rule); its lower end moves because Dask's lazy-value artifacts disappear.
* The strict reading (nested values must be E0-equal) gives the same conclusions for the drop-in engines and Dask,
  and keeps Bodo more often than both versions; it is stricter than the contract applies to top-level values.

### Proposed paper text

Sensitivity paragraph (replaces the sentences on the 16 printed-form cells; numbers from the primary reading):

> Printed forms enter 1,363 scored cells (688 outputs and 675 cells that read such values). Re-executing the 54
> affected notebooks with a recursive exact encoding of nested values recaptured 1,335 of them (the reference
> reproduced all 2,124 of its earlier outputs bit for bit): none of the 308 recaptured matching printed forms hid a
> value difference (4 hid a pandas 3 label-dtype change), but 71 of the 343 printed-form DIFF cells, 15 of the 16
> known artifacts among them, were
> representation artifacts, most of them uncomputed Dask values. With the exact classes, the paired differences of
> Modin, FireDucks and the pyarrow backend lie between -1.2 and +0.5 points, none distinguishable from 0 (the pyarrow
> backend's 90% interval against 1.5.3 leaves the +-2 margin); Bodo still differs more often than 3.0.6 (+3.6
> [+1.8, +5.8]) but not distinguishably from 1.5.3, and Dask no longer distinguishably from either (+1.3 [-0.2,
> +3.0] against 3.0.6); 15 (Dask) to 42 (Bodo) notebooks contain an introduced DIFF.
% src: icde27/analysis/r5_capture/c1_bound.json pf_cells {pf_cells 1363, pf_out_cells 688, pf_in_only_cells 675}; c1_results.json pf_cells_recaptured 1335; object_hash_determinism.ref {identical 2124, outputs 2124}; census_categories.matching (exact match 276, finer 28, coarser 4 = 308 recaptured and exactly encoded; no "exact mismatch"); census_categories.DIFF ("DIFF came from the printed form" 17+35+10+9 = 71 of 343); principal.exact_graded.pairs.{modin,fireducks,pyarrow_backend}-{p15,p30}.diff_pp (-1.198 .. +0.497), pyarrow_backend-p15.ci90_pp [-2.524, 0.186], bodo-p30 {diff_pp 3.567, ci95_pp [1.771, 5.766]}, bodo-p15.reading, dask-p30 {diff_pp 1.287, ci95_pp [-0.214, 3.0]}; principal.exact_graded.by_label.*.notebooks_introduced_DIFF_heuristic.num (dask 15, bodo 42); 15 of 16: c1_cell_changes.csv rows of r1_hand_attribution.json printed_form_comparison cells

Threats sentence (replaces "... compared by their printed form, in 688 of the 19,736 scored cells (330 of the 10,313
clean@E2 cells): a matching printed form (317 cells) can hide what it does not print, ... (both removed in Section
VI)"):

> and nested containers and objects without an exact encoding were compared by their printed form, which an exact
> recapture shows erred mostly toward false differences (Section VI); 48 of the 688 printed-form cells (5 of them
> matching) remain without an exact encoding, mostly Dask values whose computation raises.
% src: icde27/analysis/r5_capture/c1_results.json census_categories.{matching,DIFF,other}."not exactly encodable" (5 + 39 + 4 = 48)

If A adopts the exact recapture as the primary result, the abstract's "24 to 43" becomes "15 to 42" and the clause
that Dask exceeds pandas 3.0.6's DIFF share must go (Bodo still exceeds it). A cheaper alternative that keeps the
published numbers as primary: report this table as a sensitivity and narrow the Dask claim to "not robust to an exact
encoding of nested values".

### Limitations

* 28 printed-form cells were not recaptured (listed in `c1_cell_changes.csv`, `why_not`); 48 census cells remain
  without an exact encoding (inexact elements are listed per object in the new run records).
* The graded reading aligns nested elements by position and compares inline nested containers of scalars exactly
  (as the original printed form did), so a nested list of floats that differs within the tolerance stays DIFF.
* New runs used the original run configuration, but engines of different configurations ran concurrently on a shared
  host (load averages 36-78). Run-to-run changes (8 cells) are excluded from the encoding effects; they are engine
  nondeterminism, not a capture effect.
* Notebooks with more than 1 GB of input still run without pre-cell input capture, as in the paper.
* The exact encoder is a copy of the harness in this folder, not the paper's harness; its original-encoder entries
  reproduce the paper's harness (C2 check 71/71; reference outputs 2,124/2,124 identical).

How A can consume the cell-level changes (both ways are delivered): `c1_results.json` (`principal`) already holds
the recomputed principal comparisons for every variant; `c1_overrides.json` (`c1_overrides.py`) holds, keyed
"label|notebook|cell", the complete new compare-cell fields of the 152 cells that `exact_graded` changes (and of the
101 that `exact_nested_e0` changes), plus the 130 cells that `exact_graded_strict` removes, so that a script built on
the original compare outputs (r1_cells.py, r3_sensitivity.py, r4_audit.py with rootcause_taxonomy) can substitute
them; `c1_cell_changes.csv` lists every printed-form cell with its original, new `orig`, `graded` and `exact` class
and clean level and the flags.

Status (Part B): FINAL (2026-11-11 02:03 ICT; overrides file added 02:05). Output SHA-256: `c1_results.json`
beb0327217835be339c379b4e7d4bc391a8252dc71339bdbff142e76fb571726; `c1_cell_changes.csv`
9be43026d1715aa4d6ed6eee7f54f214ee6c7f3a03bfdf14a40027c925806ae2; `c1_overrides.json`
5f7b52a178364fc9489dcfeda9b877fbc37d62ec27ba0d304097234e96537c5c; `c1_runlog.json`
2315db373ac5073c3b1095bea8129168c32f04950ecb2785826a7ae43288bdce; `c1_selection.json`
10a11bf16b41818adbb5b00b9bab086b092d63c1e782413ceaded9327c3965a9; raw runs and comparisons
`work/r5_capture/MANIFEST_c1_raw_sha256.txt` 4ebbf55d8bc0cef58f81b1617650669a67ac1c5db2a59488602c910fd0dfeb49 (296
run records, 726 comparison outputs; capture store `work/r5_capture/captures`, 9.3 GB, not hashed per blob).
Scripts: `c1_analyze.py` ba7289420456edb386ac13577a7debb5aa4fd6eff097b9eb567f55ae1c67e4b7, `c1_compare.py`
3e7e51d4db465b54ff671ee0c2ff130a9fbfad0264bae18903c0330ed00a6528, `c1_compare_all.py`
b9f8b84dd04afbf8b967cb7b33f3fd64ae88acd1f8af68d5a01842107fcb7959, `c1_job.sh`
ad807a4fdff261c345131bcdd8fc9c29a1c6c775967148c1c20c141abe8e4128, `c1_select.py`
6925b33f1506b71289e199eebf8c12f8f15dd70859cef82f846fa32d288b6a02; harness copy `harness_source_sha256_r5copy.txt`
84b620cea556411e95b8434849603e72d43a48f3ea1d23f5379b1a70291a12c0.

Status: FINAL (C1, both parts; 2026-11-11 02:03 ICT). Outputs as listed in the two part status lines above.

---------------------------------------------------------------------------------------------------------------------

## C2. Adversarial end-to-end capture suite

### Pre-declared design (written 2026-11-10 21:50 ICT, before any C2 run)

**Question.** Which capture paths of the harness (as used for the paper, and the C1 exact-encoding copy) record a
known difference exactly, flag it as uncertain, or miss it, end to end (AST analysis, input and output capture,
encoding, comparison, clean-input classification)?

**Corpus.** Six small synthetic notebooks, 33 cases (`work/r5_capture/c2/work/probes/nb/<nb>/old.ipynb`, written by
`c2_build.py`, with a 100-row all-numeric CSV input). A difference is planted only under the alternative
configurations through a hidden helper (`_alt()`, a function, so it is never captured itself: true when `pd` is not
pandas 2.3.x), so the truth is known by construction; one case relies on a natural pandas 3.0.6 change (str dtype).
Cases, by category (cell lists and truths in `c2_cases.json`):
* nested containers: a frame inside a list with one changed row outside the printed rows; a dict holding a frame
  whose values differ at relative 1e-7 (beyond the 1e-9 tolerance, hidden by 6 printed decimals); a list holding an
  Int64 instead of an int64 frame (dtype only, E2); a list nested 6 deep with a change at the innermost level; a
  nested list whose printed form collides by delimiters (`["a,0:str:b"]` vs `["a", "b"]`); an equal control; a
  string frame inside a list (natural pandas 3 dtype change); `object()` inside a list (repr with an address);
* mutable aliases: mutation through a second name (visible to the AST), through a called function (invisible), the
  same without any later reader;
* in-place side effects: a function passed to `apply` that changes an attribute of a user-class object; a lambda
  passed to `apply` that appends to a list (the AST ignores mutating calls inside lambdas: prediction revised before
  the run after a static check, and a reader cell added); an in-place sort on another key (E1);
* hidden globals and dynamic accesses: a global read by a called function (traced), the same global read by a
  closure returned by a factory (untraced), a counter changed through a `global` statement in a called function, a
  value bound through `globals()[...]`, through `exec`, and read through `globals()[...]`;
* lazy values: an assigned, never displayed reduction and Series; a GroupBy object (not serializable) grouping by
  another key, with a later aggregation; Dask-compatible notebook: an assigned lazy reduction, lazy reductions inside
  a dict and a list, a lazy Series inside a list, a planted lazy reduction inside a dict;
* printed-form-only objects: an object whose `repr` hides its state, a bound method, dtype objects (`df.dtypes`), a
  range inside a list, a lambda inside a list.
`c2_cases.json` (written before the run) gives per case the truth and the predicted result per harness and engine.

**Configurations.** ref (pandas 2.3.3) and its replicate ref#2, p30 (pandas 3.0.6) and fireducks (FireDucks 1.4.4)
on all six notebooks; dask on the Dask-compatible notebook. Two harnesses on the same corpus, in one guarded job
(`runs/06_pandas_conformance_r5_capture_c2.json`, script `c2_job.sh`): the unmodified harness of the paper
(`src/pconf`, run as is with `PCONF_WORK/RESULTS/CAPTURES` pointing to `work/r5_capture/c2/`; its harness and
comparator fingerprints are those of the paper's campaigns) with its own `compare` (ref#2 for NONDET), and the C1
harness copy (exact encoder; its own `compare` with ref#2, plus `c1_compare.py` for the original-encoder entries of
the same runs).

**Result per case, configuration and harness.** The verdict at the cell where the difference arises (or, for reader
cases, at the reader): correct (the class the contract gives, or E0 for a control; for reader cases, the reader is
not clean, so its difference counts as inherited), coarser (right direction, coarser class), wrong (a difference
reported as a match or the reverse, or a reader counted clean with an introduced difference), late (the cell where
it arises shows nothing; a later reader shows it as an input difference), unscored (nothing shows it). The flag:
printed (an element compared by its printed form, the R4 census definition), inexact (an element the exact encoder
could not encode), uncapturable_input (the reader is unclean because an input cannot be serialized), NONDET (the two
reference runs disagree, so the cell is excluded), or none. Categories reported: captured exactly = correct with no
flag; flagged uncertain = any flag; missed = wrong or unscored with no flag; late and coarser separately.

**Stop rule.** One run per configuration; a case whose notebook fails for a reason unrelated to the case is fixed
once and rerun, and the fix is reported.

**What counts against the paper.** Any silent miss of a difference in a path the paper does not already disclose.
The paper already discloses: printed forms of nested containers, mutations through aliases or called functions and
dynamic reads caught only by a later reader, the 10 notebooks without input capture.

Changes to the design before or at the run, all recorded in `c2_cases.json`: (1) before the run, a static check of
the AST analyzer showed that it ignores mutating calls inside a lambda, so the prediction for the `apply` + `append`
case was changed to "late" and a reader cell was added; (2) before the run, a smoke test showed that pandas 3.0.6
gives column labels the `str` dtype, so every frame differs from 2.3.3 at E2; the truths of four pandas 3.0.6 cases
(equal control, in-place sort, bound method, dtype objects) were corrected to E2 (or E0|E2); (3) after the run, from
the record: FireDucks binds pandas' own `NDFrame.head` (method pseudo-record `pandas.core.generic.NDFrame.head`), so
the truth of its bound-method case is E0, not DIFF; (4) after the run, the verdict labels were made more specific
without changing any reported class or category: "wrong" is reported as understated (a finer class than the truth),
misattributed (a reader counted clean with an introduced difference) or overstated (a coarser class than the truth,
including a DIFF for a pair equal at some level; the design's "coarser"), and UNCOMPARABLE counts as a flag.

### What ran

* Corpus: `python3 c2_build.py` (6 notebooks, 33 cases, 100-row input; files under `work/r5_capture/c2/work/probes/nb/`).
* Guarded job `runs/06_pandas_conformance_r5_capture_c2.json` (`c2_job.sh`, limit 60 GB): status completed, return
  code 0, started 22:16:28 ICT, finished 22:16:54 (26 s of guarded wall time; lock wait 1,065 s), peak process-tree
  RSS 0.45 GB, host load averages 28.6 / 25.7 (1 min) at start / end (other projects were running). Both harnesses ran
  ref, ref#2, p30 and fireducks on the five pandas notebooks and additionally dask on `c2_dask` (65 runs, all
  completed), then their own `compare` with ref#2 (NONDET). Original harness: `src/pconf` as is (harness
  `hd1c421ecb5ee`, comparator `d92c8db54d45b`, the paper's fingerprints); exact harness: the copy (harness
  `hd676cb11c1e1`, comparator `d902a75c969b3`; its `classify.py`/`dfeq.py` are byte-identical to the original).
* Analysis (unguarded, seconds): `c1_compare.py` on the exact-harness runs (variants `orig`, `exact`, `graded`;
  outputs `work/r5_capture/c2/compare_c1/`), then `c2_analyze.py` -> `c2_results.json`.

### Results (`c2_results.json`)

Per engine, 33 cases for pandas 3.0.6 and FireDucks (28 in the pandas notebooks, 5 in `c2_dask`), 5 for Dask:

| harness | engine | captured exactly | flagged uncertain | late (at a reader) | missed | overstated |
|---|---|---:|---:|---:|---:|---:|
| original (paper) | pandas 3.0.6 | 9 | 16 | 5 | 3 | 0 |
| original (paper) | FireDucks | 9 | 16 | 5 | 3 | 0 |
| original (paper) | Dask | 1 | 4 | 0 | 0 | 0 |
| exact encoder, graded nested levels | pandas 3.0.6 | 19 | 5 | 5 | 3 | 1 |
| exact encoder, graded nested levels | FireDucks | 19 | 6 | 5 | 3 | 0 |
| exact encoder, graded nested levels | Dask | 5 | 0 | 0 | 0 | 0 |
| exact encoder, nested values E0-equal | pandas 3.0.6 | 16 | 5 | 5 | 3 | 4 |
| exact encoder, nested values E0-equal | FireDucks | 18 | 6 | 5 | 3 | 1 |

Dual-capture check: the original encoder's entries recorded in the exact-harness runs (`exact_origenc`) give the
original harness's result in all 71 case x engine rows (so the `orig` variant of C1 reproduces the paper's harness).
Pre-run predictions held in 137 of 142 rows (mispredicted: the float case was detected by the original harness
because one of the ten printed values crossed a 6th-decimal rounding boundary; FireDucks `df.dtypes` is
UNCOMPARABLE, below).

Per case (reported class at the cell where the difference arises; reader class/clean level; outcome, flags):

| case | truth | original: pandas 3.0.6 | original: FireDucks | exact (graded): pandas 3.0.6 | exact (graded): FireDucks |
|---|---|---|---|---|---|
| nested_hidden_row | DIFF | E0 (flagged, printed) | E2 (flagged, printed) | DIFF (exact) | DIFF (exact) |
| nested_float_digits | DIFF | DIFF (flagged, printed) | DIFF (flagged, printed) | DIFF (exact) | DIFF (exact) |
| nested_dtype_only | E2 | E0 (flagged, printed) | E2 (flagged, printed) | E2 (exact) | E2 (exact) |
| nested_depth_cut | DIFF | E0 (flagged, printed) | E0 (flagged, printed) | DIFF (exact) | DIFF (exact) |
| nested_delimiter_collision | DIFF | E0 (flagged, printed) | E0 (flagged, printed) | DIFF (exact) | DIFF (exact) |
| nested_control_equal | p30 E2; FD E0 | E0 (flagged, printed) | E2 (flagged, printed) | E2 (exact) | E0 (exact) |
| nested_natural_str_dtype | p30 E2; FD E0 | E0 (flagged, printed) | E2 (flagged, printed) | E2 (exact) | E0 (exact) |
| nested_object_address | no value | DIFF (flagged, NONDET, printed) | DIFF (flagged, NONDET, printed) | DIFF (flagged, NONDET, inexact) | DIFF (flagged, NONDET, inexact) |
| alias_visible | DIFF | DIFF (exact) | DIFF (exact) | DIFF (exact) | DIFF (exact) |
| alias_function | reader | E0; reader DIFF/unclean (late) | same | same | same |
| alias_function_no_reader | unscored | E0 (MISSED) | E0 (MISSED) | E0 (MISSED) | E0 (MISSED) |
| attribute_side_effect | reader | E0; reader DIFF/unclean (flagged, uncapturable input) | same | same | same |
| apply_append | reader | E0; reader DIFF/unclean (late) | same | same | same |
| hidden_global_traced | origin + reader | DIFF; reader DIFF/unclean (exact) | same | same | same |
| hidden_global_closure | origin + reader | DIFF; reader DIFF/E2 (MISSED: counted introduced) | DIFF; reader DIFF/E0 (MISSED) | as original | as original |
| global_statement | reader | E0; reader DIFF/unclean (late) | same | same | same |
| dynamic_globals_store | reader | NOOUT; reader DIFF/unclean (late) | same | same | same |
| dynamic_exec_store | reader | E0; reader DIFF/unclean (late) | same | same | same |
| dynamic_globals_read | origin + reader | NOOUT; reader DIFF/E2 (MISSED: counted introduced) | NOOUT; reader DIFF/E0 (MISSED) | as original | as original |
| lazy_assigned_scalar | DIFF | DIFF (exact) | DIFF (exact) | DIFF (exact) | DIFF (exact) |
| lazy_assigned_series | DIFF | DIFF (exact) | DIFF (exact) | DIFF (exact) | DIFF (exact) |
| inplace_sort | p30 E2; FD E1 | E2 (exact) | E1 (exact) | E2 (exact) | E1 (exact) |
| groupby_object | reader | no output; reader DIFF/unclean (flagged, uncapturable input) | same | same | same |
| repr_hides_state | DIFF | E0 (flagged, printed) | E0 (flagged, printed) | E0 (flagged, inexact) | E0 (flagged, inexact) |
| bound_method | p30 E2; FD E0 | E0 (flagged, printed) | E0 (flagged, printed) | DIFF (overstated) | E0 (exact) |
| dtype_objects | p30 E0 or E2; FD E0 | E2 (flagged, printed) | UNCOMPARABLE (flagged) | E2 (exact) | UNCOMPARABLE (flagged) |
| range_in_list | DIFF | DIFF (flagged, printed) | DIFF (flagged, printed) | DIFF (exact) | DIFF (exact) |
| lambda_in_list | no value | DIFF (flagged, NONDET, printed) | same | DIFF (flagged, NONDET, inexact) | same |
| dask_* (5 cases) | E0/E2, planted DIFF | p30 and FireDucks: 4 exact, 1 flagged (printed Series) | Dask: 1 exact, 4 flagged; 3 of them DIFF for equal values (uncomputed lazy scalars printed) | Dask: 5 exact | p30, FireDucks: 5 exact |

### What this means for the paper's claims

* The printed-form problem is real and goes both ways. With the paper's harness, matching printed forms claimed
  agreement for 8 of the 14 printed-form cases under pandas 3.0.6 where values or dtypes differ: 4 value differences
  hidden (a changed row outside the printed head and tail, a change below the depth-4 cut, a delimiter collision,
  an object whose repr hides its state) and 4 dtype or label differences hidden (E0 reported where the contract
  gives E2, e.g. pandas 3's `str` column labels inside a list). FireDucks hid the same 4 value differences, while
  its equal nested frames reached only E2 because the original encoder records the engine type name. Under Dask,
  lazy reductions inside a dict or list are printed uncomputed, so equal values are reported as DIFF. These are
  exactly the risks R1 W2, R2 W2 and the metareview name; the 688-cell census marks such cells, and C1 measures
  their effect on the real corpus.
* With the recursive exact encoding, every nested-container, dtype, range and Dask case is captured exactly (19 of
  33 per engine; graded nested levels give the contract's class, e.g. E2 for a dtype-only nested difference). What
  remains is the capture boundary that an encoding cannot fix: objects without an exact encoding (a user class whose
  repr hides state: still compared by repr, now listed as inexact), memory addresses in reprs (excluded as NONDET by
  the two reference runs in both harnesses), and uncapturable inputs (a GroupBy, a user-class object), which make
  their readers unclean (conservative: the difference is not counted as introduced).
* AST and dynamic-access boundary (identical in both harnesses): 5 cases surface only at a later reader, as an input
  difference with a correct "inherited" attribution: a mutation through a called function, a lambda passed to
  `apply` that appends to a list (the AST ignores mutating calls inside lambdas), a `global` statement in a called
  function, and bindings through `globals()[...]` and `exec`. 3 cases are missed: a mutation through a called
  function that no later cell reads is never seen, and reads through `globals()[...]` or through a closure returned
  by a factory are not inputs, so the reading cell counts as clean and its inherited difference as introduced. The
  paper's sentence "a mutation through an alias or a called function, or a dynamic read (globals(), getattr, exec),
  is caught only when a later cell reads the value" is right for mutations and dynamic bindings but wrong for dynamic
  reads: a dynamic read (or a global read through a closure) is not caught later; it can make an inherited
  difference count as introduced. The paper should say so.
* A new, small conversion gap: FireDucks' `df.dtypes` returns a `fireducks.PandasWrapper` that the engine conversion
  does not convert, so that output is UNCOMPARABLE (flagged, never counted as agreement or difference).

### Proposed paper text (Threats, construct validity; replaces the clause on aliases and dynamic reads)

> An adversarial suite of 33 planted cases in six small notebooks (pandas 3.0.6 and FireDucks against 2.3.3, five
> cases also on Dask) checks the capture boundary end to end: the harness reports 9 cases exactly per engine, marks
> 16 as uncertain (in 8 of them under pandas 3.0.6 a matching printed form hides a value or dtype difference), finds
> 5 only at a later cell that reads the value (mutations through called functions or lambdas, `global`, `exec` and
> `globals()` bindings), and misses 3: a mutation that no later cell reads, and reads through `globals()` or a
> closure, which leave the reading cell clean so that its inherited difference counts as introduced.
% src: icde27/analysis/r5_capture/c2_results.json summary.{orig:p30,orig:fireducks} {captured exactly 9, flagged 16, late 5, missed 3}; by_case[harness=orig, engine=p30] verdict=understated with flag printed: nested_hidden_row, nested_dtype_only, nested_depth_cut, nested_delimiter_collision, nested_control_equal, nested_natural_str_dtype, repr_hides_state, bound_method (8); c2_cases.json cases (33)

> With a recursive exact encoding of nested values, all nested-container, dtype and Dask cases are captured exactly
> (19 of 33 per engine); objects without an exact encoding, uncapturable inputs and the cases above remain.
% src: icde27/analysis/r5_capture/c2_results.json summary.{exact_graded:p30 {captured exactly 19}, exact_graded:fireducks {captured exactly 19}, exact_graded:dask {captured exactly 5}}

Correction of the existing Threats clause (`main.tex`, "so a mutation through an alias or a called function, or a
dynamic read (\texttt{globals()}, \texttt{getattr}, \texttt{exec}), is caught only when a later cell reads the
value (not at all in the 10 notebooks without input capture)"), which C2 shows is right for mutations and dynamic
bindings but not for dynamic reads:

> so a mutation through an alias, a called function or a lambda, or a binding through \texttt{exec} or
> \texttt{globals()}, is caught only when a later cell reads the value (never if no cell does, and not at all in the
> 10 notebooks without input capture), and a value read through \texttt{globals()} or a closure is not an input, so
> the reading cell can count as clean and its inherited difference as introduced
% src: icde27/analysis/r5_capture/c2_results.json by_case[harness=orig]: alias_function, apply_append, global_statement, dynamic_globals_store, dynamic_exec_store (verdict late); alias_function_no_reader (unscored); hidden_global_closure, dynamic_globals_read (verdict misattributed)

### Limitations

Synthetic cases with planted differences: they show which paths can fail, not how often they fail in the corpus
(C1 measures that for printed forms). One run per configuration; Modin, Bodo and the pyarrow backend were not run
on the suite (FireDucks and pandas 3.0.6 cover a drop-in engine and a pandas version; Dask covers lazy values).
`getattr` reads were not tested separately (`getattr(df, "b")` reads a captured name); the 10 notebooks without
pre-cell input capture would turn every "late" case into a miss. Truth corrections are listed above; one of them
(FireDucks bound method) was made after the run, from the record.

Status: FINAL (2026-11-10 22:25 ICT). Output SHA-256: `c2_results.json` 1efbd0b74de007209fd7f411db415c81c532b399314fde606e7df76911ed4293;
`c2_cases.json` 8626c8ed39b8eb3684d43944ce1eb1f8304fcdb90078648c9678571141201084; scripts `c2_build.py`
3bef4a5d4007f21322aeb44e9eb3a6c4c4d8840b6c34f8ff36f571e1df3fd6f0, `c2_analyze.py`
56dd06ad4e8108ece0862b48e52191bc4701df51942d0c60730a8a65a5ea2d1f, `c2_job.sh`
4cd8fed8efb85b8aa124cf50a116b363b8771ccfc02629ba1e1bb09808d2708a, `c1_compare.py`
3e7e51d4db465b54ff671ee0c2ff130a9fbfad0264bae18903c0330ed00a6528 (the C2 comparisons were made with revision
438d4a59...; revision 5eace840... only stops resetting the comparator cache between variants, and re-running it on
the C2 runs gave byte-identical outputs apart from timings, 39 of 39; the final revision 3e7e51d4... only adds a
deadline option); harness copy hashes in `harness_source_sha256_r5copy.txt`
(84b620cea556411e95b8434849603e72d43a48f3ea1d23f5379b1a70291a12c0).

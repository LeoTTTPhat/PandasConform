#!/usr/bin/env python3
"""Recheck the numbers printed in icde27/main.tex against their sources (ICDE 2027 copy; written 2026-10-27).

The ICDE counterpart of scripts/check_paper_a3_a9_a11.py (which checks the frozen SIGMOD copy and still passes).
Every check recomputes a printed fragment from a result file and asserts that the fragment occurs verbatim in
main.tex (comments removed, whitespace collapsed), or compares a printed value with its source. Sources, all
read-only: results/summary.json, results/rootcause/{taxonomy_conf1x,taxonomy,paper_provenance,conf1x_paper_counts,
engine_probe_outcomes}.json and icde27/analysis/{r1_cells,r1_sort_ties,r1_tolerance,r1_hand_attribution,
rq4_timing,r3_sensitivity,r4_audit,r4_probes,r4_printed_forms,r5_uncertainty,r5_reliability,r5_evidence,r5_corpus,
r5_exact}.json, icde27/analysis/r5_capture/{c1_results,c2_results,c2_cases}.json and c1_cell_changes.csv, and
icde27/analysis/r5_replay/{d1_plan,d1_results,d2_results,d3_results}.json (the r3, r4 and r5 files added on
2026-11-10; r5_exact, c1 and d3 on 2026-11-11). Percentages: one decimal, round half up; intervals as printed. Numbers inside \\pending{} are not
checked (they do not exist yet). Prints one line per failed check and a summary; exits 1 on any failure.

    cd ..
    .venv/bin/python 06_pandas_conformance/icde27/analysis/check_icde_numbers.py [--verbose]
"""
import decimal
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ICDE = os.path.dirname(HERE)
PROJ = os.path.dirname(ICDE)


def load(*p):
    with open(os.path.join(PROJ, *p)) as f:
        return json.load(f)


def load_r5_tables():
    """Rows of Tables II and V as icde27/analysis/r5_tables.py computes them now."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("r5_tables", os.path.join(HERE, "r5_tables.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.rows()


def tex_text():
    out = []
    with open(os.path.join(ICDE, "main.tex")) as f:
        for line in f:
            out.append(re.sub(r"(?<!\\)%.*$", "", line.rstrip("\n")))
    return re.sub(r"\s+", " ", " ".join(out))


def q(x, nd=1):
    """x rounded half up to nd decimals, as a string."""
    d = decimal.Decimal(repr(float(x))).quantize(decimal.Decimal(1).scaleb(-nd), rounding=decimal.ROUND_HALF_UP)
    return str(d)


def p1(share):
    return q(100.0 * share)


def ci(c):
    return "[%s, %s]" % (p1(c[0]), p1(c[1]))


def n(x):
    return "{:,}".format(int(x))


def sg(x):
    """signed one-decimal number in math mode, as printed: $+0.6$ or $-0.3$."""
    s = q(x)
    if s in ("0.0", "-0.0"):
        s = "0.0"
    return "$%s$" % (s if s.startswith("-") else "+" + s)


class Checker:
    def __init__(self, tex, verbose):
        self.tex, self.verbose, self.n, self.fail = tex, verbose, 0, []

    def frag(self, label, fragment):
        self.n += 1
        ok = fragment in self.tex
        if not ok:
            self.fail.append((label, "fragment not in main.tex: %r" % fragment))
        elif self.verbose:
            print("ok   %-60s %s" % (label, fragment[:90]))

    def eq(self, label, expected, got):
        self.n += 1
        if expected != got:
            self.fail.append((label, "printed %r, source %r" % (expected, got)))
        elif self.verbose:
            print("ok   %-60s %r" % (label, got))


def main(argv):
    verbose = "--verbose" in argv
    T = tex_text()
    pend = re.findall(r"\\pending\{", T)
    C = Checker(T, verbose)
    S = load("results", "summary.json")
    c1, dr = S["campaigns"]["conf_1x"]["engines"], S["campaigns"]["drift"]["engines"]
    fam = S["campaigns"]["conf_1x"]["families"]
    famd = S["campaigns"]["drift"]["families"]
    R1 = load("icde27", "analysis", "r1_cells.json")
    B = R1["by_label"]
    PW = R1["pairwise_vs_pandas_clean_E2"]
    ST = load("icde27", "analysis", "r1_sort_ties.json")
    TOL = load("icde27", "analysis", "r1_tolerance.json")["by_label"]
    HA = load("icde27", "analysis", "r1_hand_attribution.json")
    RQ = load("icde27", "analysis", "rq4_timing.json")
    TX = load("results", "rootcause", "taxonomy_conf1x.json")
    TXD = load("results", "rootcause", "taxonomy.json")
    PP = load("results", "rootcause", "paper_provenance.json")
    CPC = load("results", "rootcause", "conf1x_paper_counts.json")
    EPO = load("results", "rootcause", "engine_probe_outcomes.json")
    R3 = load("icde27", "analysis", "r3_sensitivity.json")
    R3V = R3["variants"]
    R4 = load("icde27", "analysis", "r4_audit.json")
    EXC = R4["exception"]
    PRB = load("icde27", "analysis", "r4_probes.json")
    PFM = load("icde27", "analysis", "r4_printed_forms.json")
    # 2026-11-10 (third update): pure introduced definition primary, printed-form uncertainty, notebook reliability
    RL = load("icde27", "analysis", "r5_reliability.json")
    UN = load("icde27", "analysis", "r5_uncertainty.json")
    EV = load("icde27", "analysis", "r5_evidence.json")
    CO = load("icde27", "analysis", "r5_corpus.json")
    # 2026-11-11 (review round R5, pass 2): exact recapture of printed forms (icde27/analysis/r5_capture, C1 part B) applied
    # by r5_exact.py; final replay and audit results (icde27/analysis/r5_replay, D1-D3)
    EX = load("icde27", "analysis", "r5_exact.json")
    XX = EX["exact"]
    C1R = load("icde27", "analysis", "r5_capture", "c1_results.json")
    D3 = load("icde27", "analysis", "r5_replay", "d3_results.json")
    ENG = ("pyarrow_backend", "modin", "fireducks", "bodo", "dask")
    LAB7 = ENG + ("p15", "p30")

    def view(lab, v):
        return (dr if lab in ("p15", "p30") else c1)[lab]["views"][v]

    # ---------------------------------------------------------------- abstract and introduction
    C.frag("p30 all E0 and <=E2 (abstract)", "pandas 3.0.6 is bit-exact on only %s\\%% of scored cells, yet %s\\%% agree"
           % (p1(view("p30", "all")["share"]["E0"]), p1(view("p30", "all")["cum_share"]["<=E2"])))
    C.frag("p30 all E0 and <=E2 (findings)", "bit-exact with 2.3.3 on %s\\%% of scored cells but agrees at \\lv{E2} or finer on %s\\%%"
           % (p1(view("p30", "all")["share"]["E0"]), p1(view("p30", "all")["cum_share"]["<=E2"])))
    C.frag("findings: pyarrow/Bodo bit-exact", "bit-exact on only %s\\%% and %s\\%%." % (p1(view("pyarrow_backend", "all")["share"]["E0"]),
                                                                              p1(view("bodo", "all")["share"]["E0"])))
    for e in ("modin", "fireducks", "pyarrow_backend"):
        for v in ("p15", "p30"):
            C.eq("equivalent within 2 pp: %s-%s" % (e, v), True, PW["%s-%s" % (e, v)]["equivalent_within_2pp"])
            C.eq("not equivalent within 1 pp: %s-%s" % (e, v), False, PW["%s-%s" % (e, v)]["equivalent_within_1pp"])
    for k, r in (("bodo-p15", "more often"), ("bodo-p30", "more often"), ("dask-p30", "more often"),
                 ("dask-p15", "not distinguishable")):
        C.eq("pairwise reading %s" % k, r, PW[k]["reading"])
    # 2026-11-10: the abstract and Findings state the drop-in closeness that holds in every variant of
    # r3_sensitivity.json (base, without the 16 printed-form cells, with their readers counted as clean, without the
    # 10 notebooks lacking input capture, without both) and drop the post hoc +-2-point margin
    allv = list(R3V)
    C.eq("r3: base variant reproduces r1_cells.json (consistency checks, no mismatch)", [], R3["consistency_checks"]["mismatches"])
    C.eq("r3: base pairs = r1_cells.json pairs", True, all(R3V["base"]["pairs"][k]["diff_pp"] == PW[k]["diff_pp"] and
                                                          R3V["base"]["pairs"][k]["ci90_pp"] == PW[k]["ci90_pp"] for k in PW))
    mx = max(R3V[v]["readings"]["drop_in_max_abs_diff_pp"] for v in allv)
    C.eq("drop-in paired differences within 1.2 points in every variant", True, mx <= 1.2)
    C.eq("drop-in paired differences: 1.2 is the rounded maximum", "1.2", q(mx))
    C.eq("drop-in paired differences never distinguishable (every variant)", True,
         all(R3V[v]["readings"]["drop_in_all_not_distinguishable"] for v in allv))
    C.eq("Bodo and Dask more often than 3.0.6 in every variant", True,
         all(R3V[v]["pairs"]["%s-p30" % e]["reading"] == "more often" for v in allv for e in ("bodo", "dask")))
    # the drop-in claim is "not detectably higher" on cells clean@E2 (pooled, equal notebook weights, without the
    # cells touching printed forms, and the r3 variants); strictly clean inputs against 3.0.6 are the stated exception
    DROP = ("modin", "fireducks", "pyarrow_backend")
    CT = RL["contrasts"]
    C.eq("reliability and uncertainty consistency checks (no mismatch)", (0, 0, True, True),
         (RL["consistency_checks"]["mismatches"], UN["consistency_checks"]["mismatches"], RL["consistency_checks"]["n"] >= 40,
          UN["consistency_checks"]["n"] >= 60))
    C.eq("no drop-in pair more often in the clean@E2 variants", True,
         all(CT["%s-%s" % (e, v)][x]["reading"] != "more often" for e in DROP for v in ("p15", "p30")
             for x in ("pooled_E2", "notebook_weighted_E2", "pooled_E2_certain")))
    C.eq("strictly clean inputs: only Modin and FireDucks against 3.0.6 more often", ["fireducks-p30", "modin-p30"],
         sorted(k for k, c_ in CT.items() if k.split("-")[0] in DROP and c_["pooled_E0"]["reading"] == "more often"))
    C.eq("Bodo more often than 3.0.6 in every variant", True,
         all(CT["bodo-p30"][x]["reading"] == "more often" for x in ("pooled_E2", "notebook_weighted_E2", "pooled_E0", "pooled_E2_certain")))
    NBK = RL["notebooks"]
    ef = {l: NBK[l]["error_free"]["num"] for l in LAB7}
    agr = {l: NBK[l]["agreeing"]["num"] for l in LAB7}
    C.eq("error-free notebooks = r1 no_engine_failure", {l: B[l]["notebooks"]["no_engine_failure"]["num"] for l in LAB7}, ef)
    # R6 (2026-11-11, writing): the abstract no longer prints 1.5.3's 100 or Dask's 2 error-free notebooks (checked by
    # "notebooks: unconditional reliability" and "conclusion: drop-in and notebook reliability")
    C.frag("abstract: drop-in closeness and notebook reliability", "Modin, FireDucks and the pyarrow backend have \\cls{DIFF} shares (unequal even at \\lv{E4}) not detectably higher than pandas 1.5.3's or 3.0.6's on the same cells, yet run %d to %d notebooks without error, against %d for 3.0.6"
           % (min(ef[l] for l in DROP), max(ef[l] for l in DROP), ef["p30"]))
    FD_ = RL["failure_decomposition"]
    err_cats = {"unsupported API or execution model", "error on supported API", "error after an earlier difference"}
    C.eq("Dask's failing notebooks all first fail with a raised error", (100, True),
         (sum(FD_["dask"]["not_error_free"].values()), set(FD_["dask"]["not_error_free"]) <= err_cats))
    C.frag("findings: drop-in closeness and notebook reliability", "are not detectably higher than either pandas version's in every variant of Section~\\ref{sec:conformance} but strictly clean inputs against 3.0.6, while they run %d to %d notebooks without error (%d under 3.0.6); Bodo (one worker) differs more often than 3.0.6 in every variant, and Dask raises an error in %d of the 102 notebooks"
           % (min(ef[l] for l in DROP), max(ef[l] for l in DROP), ef["p30"], sum(FD_["dask"]["not_error_free"].values())))
    nbs = {l: B[l]["notebooks"]["introduced_DIFF"]["num"] for l in LAB7}
    # 2026-11-10: the range without the 16 printed-form cells is primary; the raw range and the range without the
    # inheritance exception (r4_audit.json) are given beside it
    nbs_np = {l: R3V["no_printed"]["by_label"][l]["notebooks"]["introduced_DIFF"]["num"] for l in LAB7}
    off_raw, off_np = EXC["by_variant"]["base"]["notebooks_range_off"], EXC["by_variant"]["no_printed"]["notebooks_range_off"]
    on_raw, on_np = EXC["by_variant"]["base"]["notebooks_range_on"], EXC["by_variant"]["no_printed"]["notebooks_range_on"]
    C.eq("r4: exception-on ranges = r1/r3 ranges", ([min(nbs.values()), max(nbs.values())], [min(nbs_np.values()), max(nbs_np.values())]), (on_raw, on_np))
    C.eq("r4: 24 is the lower end in all four views (raw/no printed x exception on/off)", {24}, {on_raw[0], on_np[0], off_raw[0], off_np[0]})
    C.eq("r4: 47 is the largest upper end over the four views", 47, max(on_raw[1], on_np[1], off_raw[1], off_np[1]))
    C.eq("r4: the exception covers 59 cells", 59, EXC["totals"]["exception_cells"])
    C.eq("r4: audit consistency checks (no mismatch, at least 200)", (0, True), (R4["consistency_checks"]["mismatches"], R4["consistency_checks"]["n"] >= 200))
    # the pure definition (exception off) is primary; without the 16 printed-form cells first
    # pass 2: with nested values recaptured exactly (r5_exact.json = c1_results.json principal.exact_graded) primary,
    # the original capture (all cells, r4_audit.json base) second
    xr_ = EX["readings"]["exact_introduced_DIFF_range"]
    egl = C1R["principal"]["exact_graded"]["by_label"]
    C.eq("exact range: without known artifacts = all cells = c1_results.json pure counts (min, max)", (xr_, xr_),
         (EX["readings"]["exact_introduced_DIFF_range_all"],
          [min(egl[l]["notebooks_introduced_DIFF_pure"]["num"] for l in LAB7), max(egl[l]["notebooks_introduced_DIFF_pure"]["num"] for l in LAB7)]))
    C.eq("original-capture range (all cells) = r4 base pure range", off_raw, EX["readings"]["base_introduced_DIFF_range_all"])
    C.eq("r5_exact.json: consistency checks without mismatch (base = r5_reliability/r4_audit; exact = c1_results)", (0, True),
         (EX["consistency_checks"]["mismatches"], EX["consistency_checks"]["n"] >= 80))
    # R6 (pass 2): the abstract gives the exact-recapture range with the original-capture range
    C.frag("abstract: exact range primary", "Every configuration, pandas versions included, introduces such a difference without an error in %d to %d of the 102 notebooks (%d to %d before nested values are recaptured exactly)"
           % (xr_[0], xr_[1], off_raw[0], off_raw[1]))
    cr_ = UN["readings"]["certain_notebooks_introduced_DIFF_range"]
    C.frag("findings: exact range primary", "the pandas versions included, %d to %d of the 102 notebooks contain a cell that introduces a \\cls{DIFF} without raising, once nested values are recaptured exactly (%d to %d with the original capture)"
           % (xr_[0], xr_[1], off_raw[0], off_raw[1]))
    intro = TX["counts"]["by_kind"]["introduced"]
    und = HA["by_confidence"]["undetermined"]
    C.eq("hand attribution covers the unattributed cells", TX["causes"]["unattributed"]["n_cells"], HA["cells"] if isinstance(HA["cells"], int) else len(HA["rows"]))
    nroot = len([c for c in TX["causes"].values() if c.get("family") not in ("not_a_root_cause", "nondeterminism") and c["cause"] != "unattributed"])
    rule_n = intro - TX["causes"]["unattributed"]["n_cells"]
    intro_off = EXC["totals"]["introduced"]["off"]
    C.eq("pure introduced = 2,147 + 59 exception cells", intro + EXC["totals"]["exception_cells"], intro_off)
    C.eq("rule and curated assignments unchanged by the definition", rule_n, EXC["totals"]["assigned_by_rules_or_curated"])
    C.frag("rules and curated table: 2,030 of 2,206 (abstract)", "Rules and a small curated table assign %s of the %s introduced divergences to %d cause or symptom groups"
           % (n(rule_n), n(intro_off), nroot))
    C.frag("rules and curated table: 2,030 of 2,206 (findings)", "Rules and a small curated table assign %s of the %s introduced divergences to cause or symptom groups, as diagnostic hypotheses"
           % (n(rule_n), n(intro_off)))
    hcells = HA["cells"] if isinstance(HA["cells"], int) else len(HA["rows"])
    C.frag("findings: single-rater attribution", "a single AI rater attributed %d of the %d cells that match no rule (%d to a harness artifact)"
           % (hcells - und, hcells, HA["by_cause"]["printed_form_comparison"]))
    C.eq("undetermined cells = 2", 2, und)
    RATER = {"apply_side_effects_lost": "apply_side_effects_lost", "stale_after_inplace_update_bodo": "stale_after_inplace_update",
             "stale_after_inplace_update_fireducks": "stale_after_inplace_update", "positions_instead_of_labels": "index_not_preserved",
             "unique_nunique_missing": "unique_nunique_missing"}
    rep_b = {RATER[k] for k in PRB["summary"]["reproduced"]}
    C.eq("probes: four behaviours of the rater reproduced", 4, len(rep_b))
    C.eq("probes: every reproduced behaviour is a cause of the hand attribution on that engine", True,
         all(PRB["verdicts"][k]["engine"] in HA["causes"][RATER[k]]["labels"] for k in PRB["summary"]["reproduced"]))
    # pass 2: the mechanical attribution audit (d3_results.json)
    d3c = D3["cells"]
    d3dec = {}
    for src_ in ("rule", "none", "curated"):
        o_ = [x_["overall"] for x_ in d3c if x_["assigned_by"] == src_]
        d3dec[src_] = (o_.count("agree"), o_.count("agree") + o_.count("disagree") + o_.count("mixed"))
    C.eq("D3: decided agreements by source (rule, single rater, curated)", {"rule": (73, 116), "none": (34, 56), "curated": (2, 4)}, d3dec)
    nocheck = sum(1 for x_ in d3c if not set(x_.get("tests") or {}) & {"N1", "N2", "N3", "N6", "N7", "N8"})
    C.eq("D3: 358 audited cells, 117 without a mechanical check, 67 disagreements listed", (358, 117, 67), (len(d3c), nocheck, len(D3["disagreements"])))
    # 2026-11-12 (R8 scoring fix): the paper now splits all 358 cells: 162 without a deciding (agreement) test
    # (N1-N3, N6, N7; N8 and N9 do not decide), 20 inconclusive, 176 decided
    nodecide = sum(1 for x_ in d3c if not set(x_.get("tests") or {}) & {"N1", "N2", "N3", "N6", "N7"})
    inconc = sum(1 for x_ in d3c if x_["overall"] == "inconclusive")
    C.eq("D3: 162 without a deciding check + 20 inconclusive + 176 decided = 358", (162, 20, 176, 358),
         (nodecide, inconc, sum(v_[1] for v_ in d3dec.values()), nodecide + inconc + sum(v_[1] for v_ in d3dec.values())))
    pr_ = round(100 * d3dec["rule"][0] / d3dec["rule"][1])
    ps_ = round(100 * d3dec["none"][0] / d3dec["none"][1])
    C.frag("findings: mechanical audit", "a mechanical audit of %d attributions confirms %d\\%% of the decided rule assignments and %d\\%% of the rater's" % (len(d3c), pr_, ps_))
    C.frag("abstract: mechanical audit", "(a mechanical audit confirms %d\\%% of the rule assignments it could decide)" % pr_)
    C.eq("about six in ten (rule and single-rater agreement between 0.55 and 0.65)", True,
         all(0.55 <= a_ / b_ <= 0.65 for a_, b_ in (d3dec["rule"], d3dec["none"])))
    C.frag("threats: mechanical audit", "a mechanical audit confirms about six in ten of the attributions it could decide and no human has checked any")
    C.frag("conclusion: probes, replays and the audit", "reproduce in probes and on the notebooks without the harness, and a mechanical audit confirms about six in ten of the attributions it could decide")
    C.eq("probes: Modin apply behaviour reproduced", "reproduced", PRB["verdicts"]["apply_side_effects_lost"]["verdict"])
    C.frag("findings: parallel-execution bullet (pass 2)", "that parallel execution explains few differences, except Modin's (Section~\\ref{sec:rootcause})")
    t8 = S["timing"]["by_cpus"]["8"]
    b8 = RQ["bodo_r2"]["by_cpus"]["8"]["bodo"]
    # R6: the timing sentence left the abstract; the answer to RQ4 states it without the values, which are checked by
    # "geomeans 8 CPUs" and "Bodo 8 CPUs" (Section IX)
    C.frag("geomeans at 8 CPUs (answer to RQ4)", "The data show only that on the 30 timed notebooks at 1x no engine's geometric-mean speed-up exceeded one, as PandasBench~\\cite{pandasbench} also found for Modin on most notebooks; FireDucks' interval includes one, and Bodo ran without error on only %d notebooks"
           % b8["notebooks_both_ok"])
    C.eq("abstract: the three 8-CPU geometric means are below one", True,
         all(g["geomean_speedup_vs_ref"] < 1 for g in (t8["modin"], t8["fireducks"], b8)))
    C.eq("FireDucks' 8-CPU and default intervals include one", True,
         all(g["fireducks"]["ci95"][0] < 1 < g["fireducks"]["ci95"][1] for g in (t8, S["timing"]["by_cpus"]["default"])))
    ratios = {l: view(l, "all")["share"]["DIFF"] / view(l, "clean_E2")["share"]["DIFF"]
              for l in ("modin", "fireducks", "pyarrow_backend", "p15", "p30")}
    C.eq("DIFF all/clean@E2 ratio at least 3 for 5 labels", True, all(r >= 3.0 for r in ratios.values()))
    C.eq("DIFF all/clean@E2 ratio at least 3 in every r3 variant", True, all(R3V[v]["readings"]["ratio_range_drop_in_and_pandas"][0] >= 3.0 for v in allv))
    C.frag("findings: ratio wording", "We also find that most differing cells inherit an earlier difference (Section~\\ref{sec:conformance})")
    C.frag("lessons: ratio wording", "is at least three times that among cells whose inputs agree")
    ed = B["dask"]["err_decomposition_all"]
    C.frag("Dask error cells (findings)", "of Dask's %s error cells, %d raise on their own" % (n(ed["err_cells"]), ed["introduced"]))
    mech = {l: B[l]["introduced_DIFF_by_mechanism_with_hand"] for l in ENG}
    PL = R3["parallel_or_lazy"]
    for l in ENG:
        C.eq("r3 parallel/lazy with hand = r1_cells.json (%s)" % l, mech[l].get("parallel or lazy execution", 0), PL[l]["with_hand"])
        C.eq("r3 introduced DIFF = r1_cells.json (%s)" % l, sum(mech[l].values()), PL[l]["introduced_DIFF"])
    # denominators under the pure definition (r4_audit.json exception.parallel_or_lazy.*.denominator_off)
    EPL = EXC["parallel_or_lazy"]
    pl = {l: (PL[l]["with_hand"], EPL[l]["denominator_off"]) for l in ENG}
    hand_pl = {l: PL[l]["with_hand"] - PL[l]["rules_only"] for l in ENG}
    C.eq("parallel/lazy numerators and single-rater parts agree (r3, r4)", True,
         all(EPL[l]["parallel_or_lazy"] == PL[l]["with_hand"] and EPL[l]["single_rater"] == hand_pl[l] for l in ENG))
    # pass 2: labels on the pure basis, the counterfactual audit (d3_results.json parallel_or_lazy; its P cells are these labels)
    PLD = D3["parallel_or_lazy"]
    C.eq("D3: P cells = the paper's parallel-or-lazy numerators", {l: pl[l][0] for l in ENG},
         {l: PLD[l]["P_vanish"] + PLD[l]["P_persist"] + PLD[l]["P_inconclusive_or_untested"] for l in ENG})
    C.eq("D3: the audit's denominators are the heuristic basis (r4 denominator_on)", {l: EPL[l]["denominator_on"] for l in ENG},
         {l: PLD[l]["paper"][1] for l in ENG})
    XM = D3["exploratory_modin_extension"]
    C.eq("D3: exploratory Modin follow-up removes 20 to 22 of the 49 cells, labelled exploratory", ([20, 22], True),
         (XM["modin_partitioned_share_cells"], XM["label"].startswith("exploratory")))
    # R6: the Findings no longer repeat these label and audit counts; each is checked by "Section VII: parallel/lazy shares"
    # and "Section VII: the counterfactual audit". The check now guards the narrowed reading of Section VII.
    C.frag("parallel labels overstated (Section VII; was the Findings' label counts)", "still, the labels overstate this mechanism for FireDucks, Bodo and the pyarrow backend and understate it for Modin")
    C.frag("Section VII: parallel/lazy shares", "of those that are not harness artifacts, %d of %d for Modin, %d of %d for FireDucks, "
           "%d of %d for Bodo, %d of %d for the pyarrow backend and %d of %d for Dask."
           % (pl["modin"] + pl["fireducks"] + pl["bodo"] + pl["pyarrow_backend"] + pl["dask"]))
    C.eq("D3: Dask interval = vanish to vanish + inconclusive (laziness not neutralized)", [PLD["dask"]["P_vanish"], PLD["dask"]["P_vanish"] + PLD["dask"]["P_inconclusive_or_untested"]],
         PLD["dask"]["interval_cells"])
    C.frag("Section VII: the counterfactual audit", "the difference disappears in %d of Modin's %d such cells but in only %d of FireDucks' %d, %d of Bodo's %d, none of the pyarrow backend's %d and %d to %d of Dask's %d (laziness remains); an exploratory follow-up removes at least %d of the %d Modin cells of the audit's basis, which omits the %d order-or-index cells"
           % (PLD["modin"]["P_vanish"], pl["modin"][0], PLD["fireducks"]["P_vanish"], pl["fireducks"][0], PLD["bodo"]["P_vanish"], pl["bodo"][0],
              pl["pyarrow_backend"][0], PLD["dask"]["interval_cells"][0], PLD["dask"]["interval_cells"][1], pl["dask"][0],
              XM["modin_partitioned_share_cells"][0], EPL["modin"]["denominator_on"], EXC["totals"]["exception_cells"]))
    C.eq("D3: none of the pyarrow backend's cells vanish", 0, PLD["pyarrow_backend"]["P_vanish"])
    C.frag("Section VII: audit agreement", "Of %d sampled attributions (%d without a deciding check and %d inconclusive; no human or language-model rater), the audit confirms %d of %d decided rule assignments (%d\\%%), %d of %d single-rater ones (%d\\%%) and %d of %d curated ones; its %d disagreements (artifact)"
           % (len(d3c), nodecide, inconc, d3dec["rule"][0], d3dec["rule"][1], pr_, d3dec["none"][0], d3dec["none"][1], ps_,
              d3dec["curated"][0], d3dec["curated"][1], len(D3["disagreements"])))
    for l in ENG:
        C.eq("introduced DIFF with hand = taxonomy introduced DIFF (%s)" % l, sum(mech[l].values()),
             sum(B[l]["introduced_DIFF_by_mechanism"].values()))
    C.frag("PandasBench Modin 72", "Modin ran 72")

    # ---------------------------------------------------------------- Sections III-V
    rt_ = PP["comparator_constants"]["float_rtol"]

    def close(x, y):
        return abs(x - y) <= rt_ * max(abs(x), abs(y))
    C.eq("Section III: intransitivity example under the relative tolerance", (True, True, False),
         (close(1.0, 1 + 0.75e-9), close(1 + 0.75e-9, 1 + 1.5e-9), close(1.0, 1 + 1.5e-9)))
    C.frag("Section III: intransitivity example", "$1+0.75\\cdot 10^{-9}$ matches both $1$ and $1+1.5\\cdot 10^{-9}$, which do not match")
    LT = R3["localization"]["totals"]["engines"]
    LB = R3["localization"]["by_label"]
    LOF = EXC["localization_engines"]["off"]
    EBL = EXC["by_variant"]["base"]["by_label"]
    C.eq("the exception cells have no bit-identical inputs (strict count unchanged)", LT["introduced_DIFF_strict_clean"], LOF["strict_clean"])
    C.frag("Section IV: introduced DIFF with bit-identical inputs (pure)", "Only %d of the engines' %d introduced \\cls{DIFF} cells have bit-identical inputs (Modin %d of %d, the pyarrow backend %d of %d)"
           % (LOF["strict_clean"], LOF["introduced_DIFF"], LB["modin"]["introduced_DIFF_by_clean"].get("E0", 0),
              EBL["modin"]["off"]["introduced_DIFF"], LB["pyarrow_backend"]["introduced_DIFF_by_clean"].get("E0", 0),
              EBL["pyarrow_backend"]["off"]["introduced_DIFF"]))
    C.eq("Section IV: engines' introduced DIFF = sum over the five engines (r1_cells.json)", sum(sum(B[l]["introduced_DIFF_by_mechanism"].values()) for l in ENG), LT["introduced_DIFF"])
    C.frag("Section IV: the heuristic is a diagnostic alternative", "a heuristic that counts as inherited %d \\cls{DIFF} cells that no cause rule explains and whose inputs agree only modulo row order or the index is reported only as a diagnostic alternative" % EXC["totals"]["exception_cells"])
    C.frag("Section IV: the pure definition", "is \\emph{introduced} if its class is coarser than its clean level (its grade worsens) and \\emph{inherited} otherwise")
    # the example of a source and a manifestation (pyarrow backend, one notebook) and the matching-budget cell
    _xs = RL["examples"]["source_manifestation"]["cells"]
    C.eq("example: source E2, manifestation DIFF with E2-clean inputs, two later inherited DIFF cells",
         ("E2", "DIFF", "E2", "DIFF", None, "DIFF", None), (_xs["0"]["cls"], _xs["2"]["cls"], _xs["2"]["clean_level"], _xs["3"]["cls"],
                                                         _xs["3"]["clean_level"], _xs["4"]["cls"], _xs["4"]["clean_level"]))
    C.eq("example: the reference selects 116 columns, the pyarrow backend none", "shape:[188318, 116]/[188318, 0]",
         RL["examples"]["source_manifestation"]["manifestation_fail_E4"])
    C.frag("example text", "\\texttt{select\\_dtypes(include=[\"object\"])} then keeps none of 116 columns (\\cls{DIFF}, introduced: the manifestation)")
    _mb = RL["examples"]["match_budget"]
    C.eq("matching budget: the one cell is an inherited DIFF (inputs differ)", ("DIFF", None, True),
         (_mb["cls"], _mb["clean_level"], len(_mb["match_limit_levels"]) > 0))
    C.frag("matching budget text", "its inputs already differed, so it enters no clean-cell share or introduced count")
    C.frag("corpus: dataset groups", "Notebooks that read a byte-identical input file form %d dataset groups (%d single notebooks; the largest holds %d Titanic notebooks)"
           % (CO["dataset_groups"], CO["singleton_groups"], CO["group_sizes"][0]))
    no = dr["p15"]["excluded_cells"]["NOOUT"]
    ex = PP["corpus"]["cells_per_config_p15"]["executed"]
    C.frag("NOOUT p15", "%d of the %s executed cells, %s\\%%" % (no, n(ex), q(100.0 * no / ex)))
    nd = dr["p15"]["excluded_cells"]["NONDET"]
    sc = dr["ref#2"]["views"]["all"]["cells"]
    C.frag("reference replicate disagreement", "disagree on %d of the %s cells either could score (%s\\%%)"
           % (nd, n(sc + nd), q(100.0 * nd / (sc + nd))))
    C.frag("hidden globals", "(%d cells in the corpus read such hidden globals)" % PP["checks"]["drift"]["hidden_global_cells"])
    rt = PP["corpus"]["drift_ref_time_s"]
    C.eq("capture dominates the reference run time (capture above cell time)", True, rt["capture_in_s"] + rt["capture_out_s"] > rt["cell_s"])
    C.frag("capture cost wording", "Capture dominates run time, so timing runs never capture.")
    C.frag("comparator validation trials", "on all %s trials of a final validation (%s under pandas 2.3.3"
           % (n(PP["comparator_validation"]["trials_total"]), n(PP["comparator_validation"]["by_pandas"]["2.3.3"])))
    C.eq("comparator validation mismatches", 0, PP["comparator_validation"]["mismatches_total"])
    C.frag("reclassification", "Re-classifying %s real cells" % n(PP["reclassification_vs_da915cb28b4c6"]["total_cells"]))
    C.frag("store checks", "0 missing among %s (pandas-version runs) and %s (engine runs) referenced blobs"
           % (n(PP["checks"]["drift"]["store"]["referenced_blobs"]), n(PP["checks"]["conf_1x"]["store"]["referenced_blobs"])))
    cp = PP["corpus"]["cells_per_config_p15"]
    C.frag("cells per configuration", "%s executed code cells per configuration (excluding %d empty cells and %d setup cells)"
           % (n(cp["executed"]), cp["empty"], cp["setup"]))
    c5 = PP["corpus"]["conf5x"]
    C.frag("conf5x selection", "(%s--%s\\,MB, %s\\,GB in total)" % (c5["min_mb"], c5["max_mb"], c5["total_gb"]))
    C.frag("scale cell repair", "in %d notebooks the input-scaling cell" % PP["corpus"]["scale_cell_origin"]["old:0"])
    g = S["campaigns"]["conf_1x"]["groups"]["conf1x_bodo_dw"]
    C.eq("bodo_dw complete (filled 2026-10-28)", ("complete", 102, 102), (g["status"], g["records_found"], g["compare_outputs_found"]))
    C.eq("no sentence still calls bodo_dw incomplete", False, "not completed: " in T or "incomplete \\eng{bodo" in T)

    # ---------------------------------------------------------------- Section VI: coverage
    rdw = S["campaigns"]["conf_1x"]["run_records"]["bodo_dw"]["by_status"]
    C.frag("bodo_dw outcomes", "It completed %d of 102 notebooks (%d crashes, %d timeouts, %d memory stop)"
           % (rdw["completed"], rdw["nb_crash"], rdw["nb_timeout"], rdw["nb_memory"]))
    ewa, ewc = S["campaigns"]["conf_1x"]["engines"]["bodo_dw"]["views"]["all"], S["campaigns"]["conf_1x"]["engines"]["bodo_dw"]["views"]["clean_E2"]
    eba, ebc = S["campaigns"]["conf_1x"]["engines"]["bodo"]["views"]["all"], S["campaigns"]["conf_1x"]["engines"]["bodo"]["views"]["clean_E2"]
    C.frag("bodo_dw shares", "1 memory stop), and on its %d clean@\\lv{E2} cells it "
           "agrees at \\lv{E2} or finer on %s\\%% with a \\cls{DIFF} share of %s\\%% %s, against %s\\%% %s for Bodo with one worker"
           % (ewc["cells"], p1(ewc["cum_share"]["<=E2"]),
              p1(ewc["share"]["DIFF"]), ci(ewc["ci95"]["DIFF"]), p1(ebc["share"]["DIFF"]), ci(ebc["ci95"]["DIFF"])))
    C.eq("bodo_dw against bodo: DIFF and ERR intervals overlap (no difference claimed)", True,
         ewc["ci95"]["DIFF"][0] <= ebc["ci95"]["DIFF"][1] and ebc["ci95"]["DIFF"][0] <= ewc["ci95"]["DIFF"][1]
         and ewa["ci95"]["ERR"][0] <= eba["ci95"]["ERR"][1] and eba["ci95"]["ERR"][0] <= ewa["ci95"]["ERR"][1])
    rr = S["campaigns"]["conf_1x"]["run_records"]
    C.eq("FireDucks completed", 101, rr["fireducks"]["by_status"]["completed"])
    C.eq("Modin completed", 94, rr["modin"]["by_status"]["completed"])
    C.eq("Modin memory stops", 8, rr["modin"]["by_status"].get("nb_memory"))
    C.eq("Bodo completed/crash/memory/timeout", (94, 6, 1, 1), tuple(rr["bodo"]["by_status"].get(k) for k in ("completed", "nb_crash", "nb_memory", "nb_timeout")))
    C.eq("ref/ref#2/pyarrow/dask completed", (102, 102, 102, 102), tuple(rr[l]["by_status"].get("completed") for l in ("ref", "ref#2", "pyarrow_backend", "dask")))
    mm = PP["engine_stops"]["modin_nb_memory"]
    C.frag("Modin memory stops: peaks", "summed process-tree peaks of %s--%s\\,GB while the notebook's own process peaked at %s--%s\\,GB"
           % (q(min(x["peak_tree_rss_gb"] for x in mm)), q(max(x["peak_tree_rss_gb"] for x in mm)),
              q(min(x["runner_max_rss_after_gb"] for x in mm)), q(max(x["runner_max_rss_after_gb"] for x in mm))))
    to = {l: (c1[l]["failure_cells"]["TIMEOUT"], c1[l]["post_timeout_cascade"]["cells"],
              c1[l]["post_timeout_cascade"]["notebooks_with_engine_timeout"]) for l in ("fireducks", "modin", "bodo")}
    C.frag("cell timeouts", "hit %d FireDucks cells in five notebooks, %d Modin and %d Bodo cells, whose later cells (%d, %d and %d)"
           % (to["fireducks"][0], to["modin"][0], to["bodo"][0], to["fireducks"][1], to["modin"][1], to["bodo"][1]))
    C.eq("FireDucks timeout notebooks", 5, to["fireducks"][2])
    bt = [x for x in S["campaigns"]["conf_1x"]["nb_timeouts"] if x["engine"] == "bodo"][0]
    C.eq("Bodo notebook timeout dominated by the hung cell", True, bt["not_in_recorded_cells_s"] > bt["cell_wall_s"] + bt["capture_s"])
    C.eq("notebook timeouts: 1 bodo + 2 bodo_dw", ["bodo", "bodo_dw", "bodo_dw"],
         sorted(x["engine"] for x in S["campaigns"]["conf_1x"]["nb_timeouts"]))

    # ---------------------------------------------------------------- Section VI: headline
    a = {l: view(l, "all") for l in LAB7}
    C.frag("Modin/FireDucks bit-exact", "Modin is bit-exact on %s\\%% %s of %s cells and FireDucks on %s\\%% %s of %s"
           % (p1(a["modin"]["share"]["E0"]), ci(a["modin"]["ci95"]["E0"]), n(a["modin"]["cells"]),
              p1(a["fireducks"]["share"]["E0"]), ci(a["fireducks"]["ci95"]["E0"]), n(a["fireducks"]["cells"])))
    C.frag("pyarrow backend all", "the pyarrow backend (%s\\%% bit-exact, a further %s\\%% at \\lv{E2} and %s\\%% at \\lv{E3})"
           % (p1(a["pyarrow_backend"]["share"]["E0"]), p1(a["pyarrow_backend"]["share"]["E2"]), p1(a["pyarrow_backend"]["share"]["E3"])))
    C.frag("Bodo all", "Bodo (%s\\%%; %s\\%% at \\lv{E2} or finer)" % (p1(a["bodo"]["share"]["E0"]), p1(a["bodo"]["cum_share"]["<=E2"])))
    C.frag("Dask/Bodo errors", "errors dominate Dask (%s\\%% %s) and are frequent for Bodo (%s\\%% %s)"
           % (p1(a["dask"]["share"]["ERR"]), ci(a["dask"]["ci95"]["ERR"]), p1(a["bodo"]["share"]["ERR"]), ci(a["bodo"]["ci95"]["ERR"])))
    eds = {l: B[l]["err_decomposition_all"] for l in ("dask", "bodo", "fireducks")}
    for l, d in eds.items():
        C.eq("error decomposition adds up (%s)" % l, d["err_cells"], d["introduced"] + d["name_error_cascade"] + d["on_inputs_that_differed"] + d["other"])
    C.frag("error decomposition", "of Dask's %s error cells, %d raise on their own, %d are name errors after an earlier failure and %s run on inputs that already differed (Bodo: %d, %d and %d of %d; FireDucks: %d, %d and %d of %d)"
           % (n(eds["dask"]["err_cells"]), eds["dask"]["introduced"], eds["dask"]["name_error_cascade"], n(eds["dask"]["on_inputs_that_differed"]),
              eds["bodo"]["introduced"], eds["bodo"]["name_error_cascade"], eds["bodo"]["on_inputs_that_differed"], eds["bodo"]["err_cells"],
              eds["fireducks"]["introduced"], eds["fireducks"]["name_error_cascade"], eds["fireducks"]["on_inputs_that_differed"], eds["fireducks"]["err_cells"]))
    C.frag("lessons: most error cells follow an earlier failure", "and most error cells follow an earlier failure or difference (Section~\\ref{sec:conformance})")
    C.eq("lessons: most Dask, Bodo and FireDucks error cells are not introduced", True, all(d["introduced"] < d["err_cells"] / 2 for d in eds.values()))
    e2 = {l: view(l, "clean_E2") for l in LAB7}
    C.frag("clean@E2 <=E2", "agreement at \\lv{E2} or finer is %s\\%% for Modin (%s cells), %s\\%% for FireDucks (%s), %s\\%% for the pyarrow backend (%s), %s\\%% for Bodo (%s) and %s\\%% for Dask (%s)"
           % tuple(x for l in ("modin", "fireducks", "pyarrow_backend", "bodo", "dask") for x in (p1(e2[l]["cum_share"]["<=E2"]), n(e2[l]["cells"]))))
    C.frag("clean@E2 DIFF", "\\cls{DIFF} shares are %s\\%% %s, %s\\%% %s, %s\\%% %s, %s\\%% %s and %s\\%% %s, against %s\\%% and %s\\%% for pandas 1.5.3 and 3.0.6"
           % (tuple(x for l in ("modin", "fireducks", "pyarrow_backend", "bodo", "dask") for x in (p1(e2[l]["share"]["DIFF"]), ci(e2[l]["ci95"]["DIFF"])))
              + (p1(e2["p15"]["share"]["DIFF"]), p1(e2["p30"]["share"]["DIFF"]))))
    for l in LAB7:
        C.eq("r1 clean@E2 DIFF = summary (%s)" % l, p1(e2[l]["share"]["DIFF"]), p1(B[l]["views"]["clean_E2"]["DIFF"]["share"]))
    C.frag("reading cells", "reading cells are %d of Dask's %d but %d of Modin's %s"
           % (fam["dask"]["read"]["cells"], e2["dask"]["cells"], fam["modin"]["read"]["cells"], n(e2["modin"]["cells"])))
    cells = [PW[k]["cells"] for k in PW]
    C.frag("pairwise cells", "(%d to %s cells, Table~\\ref{tab:variants}; every pair covers all 102 notebooks)" % (min(cells), n(max(cells))))
    C.eq("pairwise notebooks all 102", True, all(PW[k]["notebooks"] == 102 for k in PW))
    C.frag("pairwise Modin/FireDucks/pyarrow", "Modin (%s and %s percentage points against 1.5.3 and 3.0.6), FireDucks (%s, %s) and the pyarrow backend (%s, %s)"
           % tuple(sg(PW["%s-%s" % (e, v)]["diff_pp"]) for e in ("modin", "fireducks", "pyarrow_backend") for v in ("p15", "p30")))
    C.frag("pairwise: exploratory margin", "their 90\\% intervals lie inside $\\pm 2$ points, an exploratory margin chosen after seeing the unpaired shares")
    C.frag("pairwise Bodo", "Bodo differs more often than both (%s [%s, %s] and %s [%s, %s], 95\\%% intervals)"
           % tuple(x for v in ("p15", "p30") for x in (sg(PW["bodo-" + v]["diff_pp"]), sg(PW["bodo-" + v]["ci95_pp"][0]), sg(PW["bodo-" + v]["ci95_pp"][1]))))
    C.frag("pairwise Dask", "Dask more often than 3.0.6 (%s [%s, %s]) but not distinguishably from 1.5.3 (%s [%s, %s])"
           % tuple(x for v in ("p30", "p15") for x in (sg(PW["dask-" + v]["diff_pp"]), sg(PW["dask-" + v]["ci95_pp"][0]), sg(PW["dask-" + v]["ci95_pp"][1]))))
    cc = S["common_clean_E2"]
    C.frag("seven-way common cells", "On the %d cells clean under all seven configurations" % cc["cells"])
    C.eq("seven-way: Bodo vs 1.5.3 not distinguishable", "about as often", cc["paired_DIFF_vs_p15"]["bodo"]["reading"])
    C.eq("seven-way: other readings agree with pairwise", True,
         all((cc["paired_DIFF_vs_" + v][e]["reading"] == "more often") == (PW["%s-%s" % (e, v)]["reading"] == "more often")
             for e in ENG for v in ("p15", "p30") if not (e == "bodo" and v == "p15")))

    # ---------------------------------------------------------------- Section VI: sensitivity (r3_sensitivity.json)
    sv = ("no_printed", "no_reduced", "no_both")
    C.eq("sensitivity: 16 printed-form cells and 10 notebooks removed", (16, 16, 10, PP["corpus"]["input_over_capture_cap"]["n"]),
         (len(R3["removed"]["printed_form_cells"]), HA["by_cause"]["printed_form_comparison"], len(R3["removed"]["reduced_capture_notebooks"]), 10))
    lo_ = min(R3V[v]["readings"]["drop_in_diff_pp_range"][0] for v in sv)
    hi_ = max(R3V[v]["readings"]["drop_in_diff_pp_range"][1] for v in sv)
    C.eq("sensitivity: none distinguishable in the three variants", True, all(R3V[v]["readings"]["drop_in_all_not_distinguishable"] for v in sv))
    C.eq("sensitivity: readers bracket within the same range", True,
         lo_ <= R3V["no_printed_readers"]["readings"]["drop_in_diff_pp_range"][0] and R3V["no_printed_readers"]["readings"]["drop_in_diff_pp_range"][1] <= hi_)
    out2 = sorted({k for v in sv for k in R3V[v]["readings"]["drop_in_outside_2pp"]})
    C.eq("sensitivity: the two intervals that leave the margin", ["fireducks-p30", "pyarrow_backend-p15"], out2)
    pa_lo = min(R3V[v]["pairs"]["pyarrow_backend-p15"]["ci90_pp"][0] for v in sv)
    fd_hi = max(R3V[v]["pairs"]["fireducks-p30"]["ci90_pp"][1] for v in sv)
    C.eq("sensitivity: the two intervals leave the margin (pyarrow-p15 below -2, FireDucks-p30 above +2)", True, pa_lo < -2 and fd_hi > 2)
    C.eq("sensitivity: Bodo and Dask more often than 3.0.6, Bodo not distinguishable from 1.5.3", True,
         all(R3V[v]["pairs"]["bodo-p30"]["reading"] == "more often" and R3V[v]["pairs"]["dask-p30"]["reading"] == "more often"
             and R3V[v]["pairs"]["bodo-p15"]["reading"] == "not distinguishable" for v in sv))
    rng_ = R3V["no_printed"]["readings"]["introduced_DIFF_notebooks_range"]
    C.eq("sensitivity: readers variant gives the same notebook range", rng_, R3V["no_printed_readers"]["readings"]["introduced_DIFF_notebooks_range"])
    shr = {l: (R3V["no_printed"]["by_label"][l]["clean_E2"]["DIFF"]["share"], R3V["no_printed_readers"]["by_label"][l]["clean_E2"]["DIFF"]["share"])
           for l in ("pyarrow_backend", "bodo")}
    rd_ = {(x["label"], x["nb"], x["cell"]) for x in R3["downstream_of_printed"]["list"]
           if x["other_inputs_le_E2"] and x["cls"] not in ("REF_ERR", "NONDET", "NOOUT", "SETUP_ERR")}
    MB = R4["membership"]
    C.eq("r4 membership: 16 printed-form cells, 31 readers counted clean, 10 notebooks, 59 exception cells",
         (16, len(rd_), 10, 59), (len(MB["printed_form_cells"]), MB["printed_form_readers"]["counted_clean_E2_in_no_printed_readers"],
                                  len(MB["reduced_capture_notebooks"]), len(MB["exception_cells"])))
    C.eq("r4 sensitivity table: 5 variants x 10 contrasts with counts", 50,
         sum(1 for v in R4["sensitivity"].values() for p_ in v["pairs"].values() if "engine_DIFF" in p_ and "pandas_DIFF" in p_))
    C.frag("sensitivity: artifact table", "The artifact lists every contrast with its counts and the removed and recaptured cells by ID.")
    # Table V and the printed-form exclusion and bounds (r5_uncertainty.json, r5_reliability.json)
    T5 = load_r5_tables()
    for row_ in T5[0] + T5[1]:
        C.frag("Table V/II row %s" % row_.split(" & ")[0], row_)
    e0c = [CT[k_]["pooled_E0"]["cells"] for k_ in CT]
    cec = [CT[k_]["pooled_E2_certain"]["cells"] for k_ in CT]
    xc_ = [XX["pairs"][k_]["cells"] for k_ in XX["pairs"]]
    C.frag("Table II (variants) caption: cell ranges", "strictly clean inputs (%d--%s cells), without cells touching printed forms (No PF; %d--%s), nested values recaptured exactly (Exact; %d--%s)"
           % (min(e0c), n(max(e0c)), min(cec), n(max(cec)), min(xc_), n(max(xc_))))
    C.eq("Table II Exact column = c1_results.json principal.exact_graded.pairs", True,
         all(XX["pairs"][k_]["diff_pp"] == C1R["principal"]["exact_graded"]["pairs"][k_]["diff_pp"]
             and XX["pairs"][k_]["reading"] == C1R["principal"]["exact_graded"]["pairs"][k_]["reading"] for k_ in XX["pairs"]))
    C.eq("Table II (variants): every pair covers 101 or 102 notebooks in every variant", True,
         all(CT[k_][x]["notebooks"] in (101, 102) for k_ in CT for x in ("pooled_E2", "notebook_weighted_E2", "pooled_E0", "pooled_E2_certain")))
    C.eq("Sensitivity: equal notebook weights keep every drop-in difference within 1.6 points", True,
         all(abs(CT["%s-%s" % (e, v)]["notebook_weighted_E2"]["diff_pp"]) < 1.65 for e in DROP for v in ("p15", "p30")))
    C.frag("Sensitivity: strict clean exception", "whose few strictly clean cells (Section~\\ref{sec:drift}) almost never differ (%s\\%%)" % p1(view("p30", "clean_strict")["share"]["DIFF"]))
    UT = UN["totals"]
    C.eq("printed forms: output cells = r4 census", PFM["totals"]["printed_form_cells"], UT["printed_form_output_cells"])
    C.frag("printed forms: census with readers", "touch %s of the %s scored cells: %d compare an output by its printed form (%d of them equal) and %d only read such an object"
           % (n(UT["uncertain_scored_cells"]), n(UT["scored_cells"]), UT["printed_form_output_cells"], PFM["totals"]["printed_form_cells_equal"], UT["readers_only"]))
    UP = UN["pairs"]
    C.eq("printed forms removed: pyarrow less often than 1.5.3, no drop-in more often, Bodo above 3.0.6", True,
         UP["pyarrow_backend-p15"]["certain"]["reading"] == "less often" and UP["bodo-p30"]["certain"]["reading"] == "more often"
         and all(UP["%s-%s" % (e, v)]["certain"]["reading"] != "more often" for e in DROP for v in ("p15", "p30")))
    # pass 2: the exact recapture (c1_results.json census, by configuration; c1_cell_changes.csv per cell)
    cm_, cd_ = C1R["census_categories"]["matching"], C1R["census_categories"]["DIFF"]
    nrec = lambda d_: sum(v_ for k_, v_ in d_.items() if k_.startswith("not recaptured"))
    art = sum(v_ for k_, v_ in cd_.items() if k_.startswith("exact match (DIFF came from the printed form"))
    mrec = cm_["exact match"] + cm_["exact match, finer level"] + cm_["exact match, coarser level"]
    C.eq("C1: census outputs = the paper's printed-form outputs", UT["printed_form_output_cells"], C1R["census_cells"])
    C.eq("C1: no recaptured matching form hides a value difference (no 'now DIFF' category)", False,
         any("mismatch" in k_ or "now DIFF" in k_ for k_ in cm_))
    import csv as csv_
    p16 = {(r_["label"], r_["nb"], int(r_["cell"])) for r_ in HA["rows"] if r_["cause"] == "printed_form_comparison"}
    with open(os.path.join(HERE, "r5_capture", "c1_cell_changes.csv")) as f_:
        artc = {(r_["label"], r_["nb"], int(r_["cell"])) for r_ in csv_.DictReader(f_)
                if r_["census_category"].startswith("exact match (DIFF came from the printed form")}
    C.eq("C1: artifacts per cell = census count; 15 of the 16 known artifacts among them", (art, 15), (len(artc), len(p16 & artc)))
    dkl = C1R["census_categories_by_label"]["dask"]["DIFF"]
    C.frag("printed forms: exact recapture", "recaptured %d of the %d outputs (the reference reproduced all %s earlier outputs bit for bit): none of the %d recaptured matching forms with an exact encoding hid a value difference (%d hid a pandas~3 label dtype), but %d of the %d recaptured differing ones were representation artifacts (%d stay \\cls{DIFF}; %d cannot be encoded exactly), %d of the 16 known ones among them and %d Dask lazy scalars inside containers"
           % (C1R["census_cells"] - nrec(cm_) - nrec(cd_), C1R["census_cells"], n(C1R["object_hash_determinism"]["ref"]["identical"]), mrec,
              cm_["exact match, coarser level"], art, sum(cd_.values()) - nrec(cd_), cd_["exact mismatch (confirmed DIFF)"], cd_["not exactly encodable"], len(p16 & artc),
              dkl["exact match (DIFF came from the printed form; now E0)"]))
    C.eq("C1: the reference reproduced every earlier output", C1R["object_hash_determinism"]["ref"]["outputs"], C1R["object_hash_determinism"]["ref"]["identical"])
    C.eq("C1: the 4 coarser cells are pandas 3.0.6 cells", 4, C1R["census_categories_by_label"]["p30"]["matching"].get("exact match, coarser level", 0))
    XP = XX["pairs"]
    xd_ = [XP["%s-%s" % (e, v)]["diff_pp"] for e in DROP for v in ("p15", "p30")]
    C.eq("exact: no drop-in reading other than not distinguishable; Bodo-3.0.6 the only 'more often'", (True, ["bodo-p30"]),
         (all(XP["%s-%s" % (e, v)]["reading"] == "not distinguishable" for e in DROP for v in ("p15", "p30")),
          sorted(k_ for k_ in XP if XP[k_]["reading"] == "more often")))
    pa90 = XP["pyarrow_backend-p15"]["ci90_pp"]
    C.eq("exact: the pyarrow backend's 90% interval against 1.5.3 leaves -2, stays below +2", True, pa90[0] < -2 < pa90[1] < 2)
    C.frag("printed forms: exact contrasts", "the drop-in differences lie between %s and %s points (the pyarrow backend's 90\\%% interval against 1.5.3 leaves the $\\pm 2$ margin, on the favorable side), Bodo still differs more often than 3.0.6 (%s [%s, %s]) but not distinguishably from 1.5.3 (%s [%s, %s]), and Dask from neither (%s [%s, %s] against 3.0.6)"
           % (sg(min(xd_)), sg(max(xd_)), sg(XP["bodo-p30"]["diff_pp"]), sg(XP["bodo-p30"]["ci95_pp"][0]), sg(XP["bodo-p30"]["ci95_pp"][1]),
              sg(XP["bodo-p15"]["diff_pp"]), sg(XP["bodo-p15"]["ci95_pp"][0]), sg(XP["bodo-p15"]["ci95_pp"][1]),
              sg(XP["dask-p30"]["diff_pp"]), sg(XP["dask-p30"]["ci95_pp"][0]), sg(XP["dask-p30"]["ci95_pp"][1])))
    C.eq("exact: Dask not distinguishable from either version", True, all(XP["dask-%s" % v]["reading"] == "not distinguishable" for v in ("p15", "p30")))
    C.eq("No PF agrees with Exact except the pyarrow backend against 1.5.3", ["pyarrow_backend-p15"],
         sorted(k_ for k_ in XP if UP[k_]["certain"]["reading"] != XP[k_]["reading"]))
    C.frag("printed forms: No PF agrees", "removing all %s cells (No PF) agrees, except that the pyarrow backend becomes less often different than 1.5.3" % n(UT["uncertain_scored_cells"]))
    C.frag("paired comparison: exact qualifier", "with nested values recaptured exactly, only Bodo's excess over 3.0.6 remains (below)")
    C.frag("contract: nested lazy values", "such as a lazy Dask scalar, is printed by \\texttt{repr}, which can omit rows or leave the value uncomputed")
    C.frag("printed forms: Dask capture limitation", "that the capture printed uncomputed, a capture limitation, as the harness computes top-level Dask values (a user who displays such a container sees an unevaluated object)")

    # ---------------------------------------------------------------- Section VI: notebooks
    off_l = {l: EXC["by_variant"]["no_printed"]["by_label"][l]["off"]["notebooks_introduced_DIFF"]["num"] for l in LAB7}
    off_r = {l: EXC["by_variant"]["base"]["by_label"][l]["off"]["notebooks_introduced_DIFF"]["num"] for l in LAB7}
    C.eq("Dask min and Bodo max of the engines (pure, without and with the printed-form cells)",
         ((off_l["dask"], off_l["bodo"]), (off_r["dask"], off_r["bodo"])),
         ((min(off_l[l] for l in ENG), max(off_l[l] for l in ENG)), (min(off_r[l] for l in ENG), max(off_r[l] for l in ENG))))
    cert_nb = {l: UN["by_label"][l]["certain"]["notebooks_introduced_DIFF_pure"]["num"] for l in LAB7}
    C.eq("certain-view notebook range ends are Dask and Bodo", (cert_nb["dask"], cert_nb["bodo"]), tuple(cr_))
    xn = {l: XX["notebooks"][l]["introduced_DIFF"] for l in LAB7}
    C.eq("exact: Dask min and Bodo max of the engines", (xn["dask"], xn["bodo"]), (min(xn[l] for l in ENG), max(xn[l] for l in ENG)))
    C.frag("notebooks with introduced DIFF (exact, then original)", "Per notebook (Table~\\ref{tab:profile}, nested values recaptured exactly), %d (Dask) to %d (Bodo) of the 102 notebooks contain a cell that introduces a \\cls{DIFF}, against %d and %d under pandas 1.5.3 and 3.0.6; with the original capture, %d (Dask) to %d."
           % (xn["dask"], xn["bodo"], xn["p15"], xn["p30"], off_r["dask"], off_raw[1]))
    NP_ = RL["notebook_pairs"]
    C.eq("exact basis: error-free notebooks unchanged", {l: ef[l] for l in LAB7}, {l: XX["notebooks"][l]["error_free"] for l in LAB7})
    agx = {l: XX["notebooks"][l]["agreeing"] for l in LAB7}
    efd = [NP_["%s-p30" % e]["error_free"] for e in DROP]
    C.eq("drop-in error-free contrasts against 3.0.6 not distinguishable", True, all(x["reading"] == "not distinguishable" for x in efd))
    fa_ = XX["notebook_pairs"]["fireducks-p30"]["agreeing"]
    C.frag("notebooks: unconditional reliability", "the drop-in configurations run %d to %d notebooks without error (no cell raises, stops or times out) against %d under 3.0.6 (paired differences %s to %s points, none distinguishable) and %d under 1.5.3; error-free with every scored cell equal at \\lv{E4} or finer, they run %d to %d against %d under 3.0.6 and %d under 1.5.3 (FireDucks fewer than 3.0.6: %s [%s, %s])"
           % (min(ef[l] for l in DROP), max(ef[l] for l in DROP), ef["p30"], sg(min(x["diff_pp"] for x in efd)), sg(max(x["diff_pp"] for x in efd)),
              ef["p15"], min(agx[l] for l in DROP), max(agx[l] for l in DROP), agx["p30"], agx["p15"],
              sg(fa_["diff_pp"]), sg(fa_["ci95_pp"][0]), sg(fa_["ci95_pp"][1])))
    C.eq("FireDucks agreeing notebooks fewer than 3.0.6", "less often", fa_["reading"])
    ffm, ffb = XX["failure_decomposition"]["modin"], XX["failure_decomposition"]["bodo"]
    XC_ = XX["error_free_confirmed"]
    C.eq("exact basis: confirmed causes do not rest on overridden cells", 0, sum(XC_[l]["confirmed_evidence_from_overridden_cells"] for l in ENG))
    rpc = {l: (XC_[l]["error_free_introduced_DIFF_reproduced_cause"], XC_[l]["error_free_introduced_DIFF"]) for l in ENG}
    C.frag("notebooks: first failures", "resource limits stop %d Modin notebooks first, whereas Bodo raises on supported API in %d; among error-free notebooks with an introduced \\cls{DIFF}, a reproducer or probe confirms an assigned cause in %d of %d (pyarrow backend), %d of %d (Modin), %d of %d (FireDucks) and %d of %d (Bodo)"
           % ((ffm.get("memory cap", 0) + ffm.get("time limit", 0), ffb["error on supported API"]) + rpc["pyarrow_backend"] + rpc["modin"] + rpc["fireducks"] + rpc["bodo"]))
    C.eq("Bodo's six dependency crashes are never a first failure", 0, FD_["bodo"]["not_error_free"].get("dependency crash", 0))
    C.frag("coverage: Bodo crashes after an earlier error", "each after an earlier Bodo error, and one timed out and one hit the memory cap")
    C.eq("Dask min and Bodo max of engines (with and without the printed-form cells)", ((min(nbs[l] for l in ENG), max(nbs[l] for l in ENG)), (min(nbs_np[l] for l in ENG), max(nbs_np[l] for l in ENG))),
         ((nbs["dask"], nbs["bodo"]), (nbs_np["dask"], nbs_np["bodo"])))
    C.eq("pandas versions have no printed-form cell", (nbs["p15"], nbs["p30"]), (nbs_np["p15"], nbs_np["p30"]))
    fd4 = {l: (dr if l in ("p15", "p30") else c1)[l]["first_divergence"]["E4"] for l in LAB7}
    nf = {l: B[l]["notebooks"]["no_engine_failure"]["num"] for l in LAB7}
    C.eq("every engine fewer failure-free notebooks than pandas 3.0.6", True, all(nf[l] < nf["p30"] for l in ENG))

    # ---------------------------------------------------------------- Section VI: what the coarse levels accept
    v = ST["by_label_verdict"]
    tied = sum(x for k, x in v.items() if "only tied keys reordered" in k)
    other = sum(x for k, x in v.items() if "not a sort reordering" in k)
    C.frag("E1 sort ties", "of the %d \\lv{E1} outputs of sorting cells, %d reorder only rows whose sort keys tie" % (tied + other, tied))
    C.frag("E1 sort others", "and %d do not come from the sort" % other)
    es = {l: dict({"index_values": 0, "names": 0}, **B[l]["e4_split"]["all"]) for l in LAB7}
    C.frag("E4 split", "(FireDucks %d of %d, Bodo %d of %d, Dask %d of %d, pyarrow backend %d of %d, Modin %d of %d)"
           % tuple(x for l in ("fireducks", "bodo", "dask", "pyarrow_backend", "modin") for x in (es[l]["index_values"], es[l]["index_values"] + es[l]["names"])))
    C.frag("E4 split pandas 1.5.3", "%d of pandas 1.5.3's %d \\lv{E4} cells differ only in names" % (es["p15"]["names"], es["p15"]["index_values"] + es["p15"]["names"]))
    C.eq("p15 E4 cells = summary", a["p15"]["counts"]["E4"], es["p15"]["index_values"] + es["p15"]["names"])
    dsp = {l: B[l]["diff_split"]["clean_E2"] for l in LAB7}

    def val(l):
        return dsp[l].get("value", 0) + dsp[l].get("other:missing_mask", 0)
    C.frag("DIFF split engines", "(Modin %d of %d, FireDucks %d of %d, pyarrow backend %d of %d, Bodo %d of %d, Dask %d of %d)"
           % tuple(x for l in ("modin", "fireducks", "pyarrow_backend", "bodo", "dask") for x in (val(l), sum(dsp[l].values()))))
    C.frag("DIFF split p15", "for pandas 1.5.3, %d of %d are dtype-family or structural changes"
           % (sum(dsp["p15"].values()) - val("p15"), sum(dsp["p15"].values())))
    for l in ENG + ("p15",):
        C.eq("DIFF split total = clean@E2 DIFF (%s)" % l, e2[l]["counts"]["DIFF"], sum(dsp[l].values()))
    vw = {l: B[l]["views"] for l in LAB7}
    C.frag("clean@E3 FireDucks/pyarrow", "raises the \\cls{DIFF} share of FireDucks to %s\\%% %s and of the pyarrow backend to %s\\%% %s, with %s\\%% and %s\\%% among the %d and %d cells clean only at \\lv{E3}"
           % (p1(vw["fireducks"]["clean_E3"]["DIFF"]["share"]), ci(vw["fireducks"]["clean_E3"]["DIFF"]["ci95"]),
              p1(vw["pyarrow_backend"]["clean_E3"]["DIFF"]["share"]), ci(vw["pyarrow_backend"]["clean_E3"]["DIFF"]["ci95"]),
              p1(vw["fireducks"]["clean_E3_only"]["DIFF"]["share"]), p1(vw["pyarrow_backend"]["clean_E3_only"]["DIFF"]["share"]),
              vw["fireducks"]["clean_E3_only"]["DIFF"]["den"], vw["pyarrow_backend"]["clean_E3_only"]["DIFF"]["den"]))
    C.eq("Modin and pandas: at most one cell clean only at E3", True,
         all(((vw[l].get("clean_E3_only") or {}).get("DIFF") or {"den": 0})["den"] <= 1 for l in ("modin", "p15", "p30")))
    changed = {l: sum(1 for s in ("rtol_1e-6", "assert_frame_equal_default")
                      if TOL[l]["by_setting"][s]["counts"] != TOL[l]["by_setting"]["rtol_1e-9_paper"]["counts"]) for l in TOL}
    diffcls = {l: {s: sum(abs(TOL[l]["by_setting"][s]["counts"].get(k, 0) - TOL[l]["by_setting"]["rtol_1e-9_paper"]["counts"].get(k, 0))
                          for k in set(TOL[l]["by_setting"][s]["counts"]) | set(TOL[l]["by_setting"]["rtol_1e-9_paper"]["counts"])) // 2
                   for s in ("rtol_1e-6", "assert_frame_equal_default")} for l in TOL}
    C.eq("looser tolerance changes one clean@E2 class, pandas 1.5.3 only", {"p15": {"rtol_1e-6": 1, "assert_frame_equal_default": 1}},
         {l: d for l, d in diffcls.items() if any(d.values())})
    C.frag("exact float comparison", "raise the \\cls{DIFF} share to %s\\%% for Modin, %s\\%% for FireDucks and %s\\%% for pandas 1.5.3"
           % (q(TOL["modin"]["by_setting"]["exact"]["DIFF_pct"]), q(TOL["fireducks"]["by_setting"]["exact"]["DIFF_pct"]),
              q(TOL["p15"]["by_setting"]["exact"]["DIFF_pct"])))
    C.eq("tolerance baseline = paper (FireDucks clean@E2 DIFF)", p1(e2["fireducks"]["share"]["DIFF"]), q(TOL["fireducks"]["by_setting"]["rtol_1e-9_paper"]["DIFF_pct"]))
    ratio = TOL["fireducks"]["by_setting"]["exact"]["DIFF_pct"] / TOL["fireducks"]["by_setting"]["rtol_1e-9_paper"]["DIFF_pct"]
    C.eq("exact comparison quadruples FireDucks' DIFF share", True, 3.5 <= ratio <= 4.5)
    TOLALL = load("icde27", "analysis", "r1_tolerance.json")
    C.frag("exact float comparison: skipped cells", "lower bounds, as %d, %d and %d cells were too large to re-compare"
           % (TOLALL["skipped_cells"]["modin"], TOLALL["skipped_cells"]["fireducks"], TOLALL["skipped_cells"]["p15"]))
    C.frag("lessons: 71.9", "would call %s\\%% of pandas 3.0.6's scored cells different" % q(100.0 - float(p1(a["p30"]["share"]["E0"]))))

    # ---------------------------------------------------------------- Section VI: replicates, families, cascades, fallbacks
    pe = S["campaigns"]["pilot"]["engines"]
    rb, rm, rd = (pe[k]["views"]["all"] for k in ("bodo#2~vs~bodo", "modin#2~vs~modin", "dask#2~vs~dask"))

    def nonE0(vv):
        return sum(x for k, x in vv["counts"].items() if k != "E0")
    C.eq("Bodo replicate all DIFF", rb["counts"]["DIFF"], nonE0(rb))
    C.eq("Modin replicate classes", (3, 2, 1), (rm["counts"]["E1"], rm["counts"]["E2"], rm["counts"]["DIFF"]))
    # pass 2: the pilot replicate sentence was cut (the D1 second execution of Section VI replaces it); its data checks stay
    C.eq("Dask replicate: only DIFF besides lost outputs", rd["counts"]["DIFF"], nonE0(rd) - rd["counts"]["UNCOMPARABLE"])
    rf = pe["fireducks#2~vs~fireducks"]["views"]["all"]
    C.eq("FireDucks replicate: one E4 cell, rest uncapturable", (1, nonE0(rf) - 1), (rf["counts"]["E4"], rf["counts"]["UNCOMPARABLE"]))
    RS = R4["replicate_stability"]
    aqd = RS["by_cause"]["approximate_quantile"]["differ_between_replicate_runs"]
    C.eq("replicates: Bodo's differing cells are its three approximate-quantile cells", (3, 3, True),
         (rb["counts"]["DIFF"], len(aqd), all(x.startswith("bodo|") for x in aqd)))
    C.eq("replicates: the only unstable cells of the named silent causes are those three", 3, RS["unstable"])

    def fl(l, f):
        return famd[l][f] if l in ("p15", "p30") else fam[l][f]
    fams = list(fam["modin"].keys())
    # 2026-11-10: the sentence with the seven largest-family counts was cut (Figure 2 shows the rates)
    dt = {l: "%d of %d" % (fl(l, "dtype_conv")["counts"].get("DIFF", 0), fl(l, "dtype_conv")["cells"])
          for l in ("p30", "pyarrow_backend", "bodo", "dask", "modin", "fireducks")}
    C.frag("dtype conversion DIFF hotspot", "pandas 3.0.6 (%s cells), the pyarrow backend (%s), Bodo (%s) and Dask (%s)"
           % (dt["p30"], dt["pyarrow_backend"], dt["bodo"], dt["dask"]))
    C.frag("dtype conversion DIFF elsewhere", "against %s cells under Modin and %s under FireDucks" % (dt["modin"], dt["fireducks"]))

    def dshare(l, f):
        return fl(l, f)["counts"].get("DIFF", 0) / fl(l, f)["cells"] if fl(l, f)["cells"] else 0.0
    C.eq("dtype conversion has the highest DIFF share for pandas 3.0.6, pyarrow backend, Bodo and Dask", ["dtype_conv"] * 4,
         [max(fams, key=lambda f: dshare(l, f)) for l in ("p30", "pyarrow_backend", "bodo", "dask")])
    fd0 = {l: c1[l]["first_divergence"]["E0"]["notebooks_diverged"] for l in ENG}
    C.eq("E0 divergence notebooks", {"bodo": 102, "dask": 102, "pyarrow_backend": 102, "fireducks": 101, "modin": 90}, fd0)
    med = {l: q(fd4[l]["rel_position_quantiles"]["p50"], 2) for l in ENG}
    C.frag("E4 medians", "median relative position of %s (Modin and pyarrow backend), %s (FireDucks), %s (Bodo) and %s (Dask)"
           % (med["modin"], med["fireducks"], med["bodo"], med["dask"]))
    C.eq("Modin = pyarrow E4 median", med["modin"], med["pyarrow_backend"])
    ish = EXC["introduced_share_non_e0"]
    C.frag("introduced shares (pure)", "in %s\\%% of them for Modin, %s\\%% for FireDucks, %s\\%% for Bodo, %s\\%% for Dask and %s\\%% for the pyarrow backend"
           % tuple(p1((CPC["attribution_kinds"][l]["introduced"] + ish[l]["exception_cells"]) / ish[l]["non_e0"])
                   for l in ("modin", "fireducks", "bodo", "dask", "pyarrow_backend")))
    fb = {l: c1[l]["fallback"] for l in ("fireducks", "bodo", "modin")}
    C.frag("fallback shares", "flag %s\\%% of scored FireDucks cells (%d, in %d notebooks), %s\\%% of Bodo cells (%s, in %d) and %s\\%% of Modin cells (%d, in %d)"
           % (p1(fb["fireducks"]["share"]["all"]), fb["fireducks"]["cells"]["all"], fb["fireducks"]["notebooks_with_fallback"],
              p1(fb["bodo"]["share"]["all"]), n(fb["bodo"]["cells"]["all"]), fb["bodo"]["notebooks_with_fallback"],
              p1(fb["modin"]["share"]["all"]), fb["modin"]["cells"]["all"], fb["modin"]["notebooks_with_fallback"]))
    fs = CPC["fallback_split_clean_E2"]
    C.frag("fallback split clean@E2", "(FireDucks %s\\%% against %s\\%%, Bodo %s\\%% against %s\\%%, Modin %s\\%% against %s\\%%)"
           % tuple(x for l in ("fireducks", "bodo", "modin") for x in (p1(fs[l]["fallback_share"]["DIFF"]), p1(fs[l]["other_share"]["DIFF"]))))
    C.frag("fallback split Bodo ERR", "flagged Bodo cells raise less often (%s\\%% against %s\\%%)"
           % (p1(fs["bodo"]["fallback_share"]["ERR"]), p1(fs["bodo"]["other_share"]["ERR"])))

    # ---------------------------------------------------------------- Section VII
    pt = PP["taxonomy"]
    C.frag("pilot contribution", "they contribute %d of the introduced and %d of the non-\\lv{E0} cells" % (pt["pilot_label_cells"]["introduced"], pt["pilot_label_cells"]["non_e0"]))
    C.frag("curated and appended rules", "%d cells were inspected individually and fixed in a curated table, and eight rules appended" % pt["curated_cells"])
    C.eq("appended rules = 8, prefix unchanged", (8, True), (pt["rules"]["appended"], pt["rules"]["prefix_unchanged"]))
    k = TX["counts"]["by_kind"]
    cz = TX["causes"]
    st = PP["engine_stops"]["by_run_status"]
    TP = EV["taxonomy_pure"]
    C.eq("pure decomposition = taxonomy kinds with the 59 cells moved", (TP["introduced"], TP["inherited"]),
         (k["introduced"] + EXC["totals"]["exception_cells"], k["propagated"] - EXC["totals"]["exception_cells"]))
    C.frag("non-E0 decomposition (pure)", "Of %s non-\\lv{E0} cells, %s are introduced, %s inherit an earlier difference, %s are cascades (%s name errors after an earlier cell failed and %d cells at or after an engine stop), %d are uncomparable outputs"
           % (n(TX["counts"]["non_e0_cells"]), n(TP["introduced"]), n(TP["inherited"]), n(k["cascade"]),
              n(cz["cascade_undefined_name"]["n_cells"]), cz["resource_memory_cap"]["n_cells"], k["harness"]))
    C.eq("cascade = name errors + engine stops", k["cascade"], cz["cascade_undefined_name"]["n_cells"] + cz["resource_memory_cap"]["n_cells"])
    C.eq("engine stops add up", cz["resource_memory_cap"]["n_cells"], st["nb_memory"] + st["nb_crash"] + st["nb_timeout"])
    pil = sum(v_ for e_, v_ in cz["capture_cap"]["by_engine"].items() if e_.startswith("pilot:"))
    C.frag("uncomparable from the pilot", "%d of them from the pilot), and %d are non-deterministic" % (pil, k["nondet"]))
    OR = R3["order_rule"]
    C.eq("order rule: cells = taxonomy order_propagated", cz["order_propagated"]["n_cells"], OR["cells"])
    C.frag("unattributed (pure)", "%d introduced cells (%s\\%%) stay unattributed: %d match no rule (%d engine cells and one pandas 1.5.3 cell), and %d \\cls{DIFF} cells whose inputs agree only modulo row order (%d) or the index (%d; %d apply"
           % (TP["unattributed"], p1(TP["unattributed_share"]), cz["unattributed"]["n_cells"],
              sum(v_ for e_, v_ in cz["unattributed"]["by_engine"].items() if not e_.startswith("drift:")),
              OR["cells"], OR["by_clean"].get("E1", 0), OR["by_clean"].get("E4", 0), OR["positional_op_in_code"]))
    C.eq("order rule: clean levels are E1 or E4 only", OR["cells"], OR["by_clean"].get("E1", 0) + OR["by_clean"].get("E4", 0))
    dc = R3["localization"]["introduced_by_cause_clean_class"]["str_dtype_object_checks"]
    dct = sum(dc.values())
    dc0 = sum(v_ for k_, v_ in dc.items() if k_.startswith("E0|"))
    C.eq("dtype-name checks: non-pilot cells = taxonomy minus pilot", cz["str_dtype_object_checks"]["n_cells"] - cz["str_dtype_object_checks"]["by_engine"].get("pilot:bodo_dw", 0), dct)
    C.frag("dtype-name checks: inputs at E2 or coarser", "%d of the %d non-pilot dtype-name-check cells read inputs that agree only at \\lv{E2} or coarser" % (dct - dc0, dct))
    C.eq("dtype-name checks: no non-pilot cell with E1 inputs", 0, sum(v_ for k_, v_ in dc.items() if k_.startswith("E1|")))
    C.eq("five symptom-level groups", 5, len(PP["taxonomy"]["engine_symptom_level_cells"]))
    C.frag("five symptom-level groups (text)", "fall into %d causes, five of them symptom-level groups" % pt["root_causes"])
    C.eq("Table II: the five symptom rows carry the mark", 5, T.count("$^\\S$ &"))
    CE = R3["cause_evidence"]
    C.frag("mechanism causes reproduced", "(of the %d causes that name a mechanism, %d are reproduced)" % (CE["mechanism_causes"], CE["mechanism_causes_reproduced"]))
    C.eq("mechanism causes: 44 - 5 symptom-level", pt["root_causes"] - 5, CE["mechanism_causes"])
    C.frag("single-rater caveat (Section VII)", "no second rater has labeled these cells, so we report them apart from the rule counts")
    C.frag("Section VII: diagnostic hypotheses", "Each introduced cell receives exactly one cause, a diagnostic hypothesis rather than a verified explanation (audited below)")
    C.frag("Table III caption: original capture", "Taxonomy of introduced divergences (cells whose grade worsens; original capture)")
    eb = EXC["by_variant"]["base"]["by_label"]
    tt = EXC["totals"]
    C.eq("exception off: 2,147 + 59 introduced, 117 + 59 unattributed", (TX["counts"]["by_kind"]["introduced"] + 59, TX["causes"]["unattributed"]["n_cells"] + 59),
         (tt["introduced"]["off"], tt["unattributed_by_rules"]["off"]))
    nn = {l: (eb[l]["on"]["notebooks_introduced_DIFF"]["num"], eb[l]["off"]["notebooks_introduced_DIFF"]["num"]) for l in LAB7}
    # pass 2: the notebook counts of the heuristic alternative on Table V's basis (exact, known artifacts excluded)
    xh = {l: (XX["notebooks"][l]["introduced_DIFF_heuristic"], XX["notebooks"][l]["introduced_DIFF"]) for l in LAB7}
    C.frag("heuristic alternative: notebooks", "it lowers the introduced cells to %s and the notebooks with an introduced \\cls{DIFF} of Table~\\ref{tab:profile} by at most three (pandas 1.5.3 %d to %d, pyarrow backend %d to %d, FireDucks %d to %d, Bodo %d to %d)"
           % ((n(tt["introduced"]["on"]),) + tuple(x for l in ("p15", "pyarrow_backend", "fireducks", "bodo") for x in (xh[l][1], xh[l][0]))))
    C.eq("heuristic alternative (exact basis): at most three; pandas 3.0.6, Modin, Dask unchanged; the four named change", (True, True, True),
         (max(xh[l][1] - xh[l][0] for l in LAB7) == 3, all(xh[l][0] == xh[l][1] for l in ("modin", "p30", "dask")),
          all(xh[l][1] > xh[l][0] for l in ("p15", "pyarrow_backend", "fireducks", "bodo"))))
    C.eq("heuristic alternative: at most three notebooks", True, max(nn[l][1] - nn[l][0] for l in LAB7) == 3)
    C.eq("exception off: Modin, pandas 3.0.6 and Dask unchanged", True, all(nn[l][0] == nn[l][1] for l in ("modin", "p30", "dask")))
    C.eq("exception off: the four named configurations change", True, all(nn[l][1] > nn[l][0] for l in ("p15", "pyarrow_backend", "fireducks", "bodo")))
    C.eq("exception off: paired contrasts and clean@E2 shares recomputed equal (audit consistency)", 0, R4["consistency_checks"]["mismatches"])
    un = cz["unattributed"]
    une = sum(v_ for e_, v_ in un["by_engine"].items() if not e_.startswith("drift:"))
    roots = [c for c in cz.values() if c.get("family") not in ("not_a_root_cause", "nondeterminism") and c["cause"] != "unattributed"]
    C.frag("44 causes", "the other %s fall into %d causes" % (n(k["introduced"] - un["n_cells"]), len(roots)))
    C.eq("44 root causes (provenance)", len(roots), pt["root_causes"])
    dl = {}
    for c in roots + [cz["nondeterminism"]]:
        dl[c.get("documented_level")] = dl.get(c.get("documented_level"), 0) + 1
    C.frag("documentation levels", "Of the %d rows (%d causes plus non-determinism), %d are documented, %d partly and %d not at all; for %d causes"
           % (len(roots) + 1, len(roots), dl.get("yes", 0), dl.get("partial", 0), dl.get("no", 0), dl.get("not_searched", 0)))
    rc = pt["reproducer_coverage"]
    C.frag("reproducers", "The %d pandas reproducers ran in all four pandas environments (%d runs" % (rc["pandas_reproducer"], 4 * rc["pandas_reproducer"]))
    sm = EPO["summary"]
    C.frag("probes", "ran as %d probes on small synthetic inputs, outside the capture harness, of which %d reproduce the difference and %d do not"
           % (sm["confirmed"] + sm["not_reproduced"] + sm.get("inconclusive", 0), sm["confirmed"], sm["not_reproduced"]))
    C.frag("confirmed causes", "so %d causes are confirmed on at least one engine. In all, %d of the %d causes are reproduced by a script, the probes of %d do not reproduce, and %d causes have no reproducer"
           % (rc["engine_confirmed"], rc["reproduced"], len(roots), len(rc["engine_probe_not_reproduced_only"]), len(rc["no_reproducer"])))
    C.eq("no categorical-ordering cause", [], pt["categorical_ordering_causes"])
    czd = TXD["causes"]
    C.frag("str dtype cause", "the pandas~3 \\texttt{str} dtype (%d cells in %d notebooks" % (czd["str_default_dtype"]["n_cells"], czd["str_default_dtype"]["n_notebooks"]))
    C.frag("value_counts cause", "result of pandas~2.0 (%d cells in %d notebooks" % (czd["value_counts_naming"]["n_cells"], czd["value_counts_naming"]["n_notebooks"]))
    fr = czd["float_rounding_within_tolerance"]
    C.frag("float rounding p15", "account for %d pandas 1.5.3 cells, %d of them within our tolerance"
           % (fr["by_engine"]["drift:p15"], fr["by_engine"]["drift:p15"] - sum(1 for x in pt["float_rounding"]["diff_cells"] if x[1] == "p15")))
    cw = czd["cow_chained_assignment"]
    cw30 = [c for c in cw["cells"] if c[0] == "drift" and c[1] == "p30"]
    C.frag("CoW p30", "chained assignment no longer writes through (%d cells in %d notebooks); pandas warns in all %d"
           % (len(cw30), len({c[2] for c in cw30}),
              R1["warnings_silent_causes"]["cow_chained_assignment"]["drift:p30"]["engine_chained_assignment_warning"]))
    C.eq("CoW p30: 2.3.3 warned in the same cells", 19, R1["warnings_silent_causes"]["cow_chained_assignment"]["drift:p30"]["reference_warned"])
    ws = R1["warnings_silent_causes"]
    C.frag("dtype object checks", "picks different columns (%d cells, a warning in one)" % czd["str_dtype_object_checks"]["by_engine"]["drift:p30"])
    C.eq("dtype object checks: one warned", 1, ws["str_dtype_object_checks"]["drift:p30"]["engine_warned"])
    C.frag("datetime resolution", "without a warning (%d cells" % czd["datetime_resolution_inference"]["n_cells"])
    C.eq("datetime resolution: none warned", 0, ws["datetime_resolution_inference"]["drift:p30"]["engine_warned"])
    C.frag("read_csv None p15", "is not read as missing (%d cells)" % czd["read_csv_none_as_na"]["by_engine"]["drift:p15"])
    C.frag("get_dummies p15", "instead of \\texttt{bool} (%d cells)" % czd["get_dummies_bool"]["n_cells"])
    C.eq("FireDucks CoW: 13 cells, no chained-assignment warning", (13, 0), (cz["cow_chained_assignment"]["by_engine"]["conf_1x:fireducks"],
                                                     ws["cow_chained_assignment"]["conf_1x:fireducks"]["engine_chained_assignment_warning"]))
    C.frag("FireDucks CoW fragment", "(13 cells, none with a chained-assignment warning)")
    ab = cz["arrow_backed_dtypes"]
    C.frag("Arrow-backed dtypes", "the largest engine cause (%d cells in %d notebooks)" % (ab["n_cells"], ab["n_notebooks"]))
    C.eq("Arrow-backed dtypes: the four parts add up", ab["n_cells"], sum(ab["by_engine"].values()))
    eb = cz["engine_bug_error"]
    C.frag("engine errors", "followed by errors on supported API (%d cells; Table~\\ref{tab:rootcauses})" % eb["n_cells"])
    fw = cz["float_rounding_within_tolerance"]["by_engine"]
    C.frag("float rounding engines", "float rounding within our tolerance (%d and %d cells)" % (fw["conf_1x:modin"], fw["conf_1x:fireducks"]))
    C.frag("tie order Modin", "the order of ties (%d Modin cells, mostly \\lv{E1}" % cz["row_order_ties"]["by_engine"]["conf_1x:modin"])
    ties_m = [c for c in cz["row_order_ties"]["cells"] if c[0] == "conf_1x" and c[1] == "modin"]
    C.eq("Modin tie cells mostly E1", True, sum(1 for c in ties_m if c[4] == "E1") > len(ties_m) / 2)
    ms = cz["missing_sentinel_repr"]
    C.frag("None instead of NaN", "for missing strings (%d cells in %d notebooks)" % (ms["by_engine"]["conf_1x:fireducks"], ms["n_notebooks"]))
    C.frag("Dask causes", "unsupported API (%d cells), partitioned dtype inference (%d) and lazy partition semantics (%d)"
           % (cz["engine_unsupported_api"]["by_engine"]["conf_1x:dask"], cz["partitioned_type_inference"]["by_engine"]["conf_1x:dask"],
              cz["lazy_partition_model"]["by_engine"]["conf_1x:dask"]))
    C.frag("symptom-level engine rows (pure)", "%d of the %s engine-introduced cells (%s\\%%)"
           % (TP["engine_symptom_or_unattributed"], n(TP["engine_introduced"]), p1(TP["engine_symptom_or_unattributed_share"])))
    DI, DK = EV["drop_in_engines_cells"], EV["by_configuration_cells"]["dask"]
    C.eq("drop-in evidence classes add up", DI["with_cause"], DI["partly documented"] + DI["contradicts a compatibility claim"] + DI["documented incompatibility"])
    C.eq("no drop-in cell fully documented by the engine, none without a claim", (0, 0), (DI["documented incompatibility"], DI["no applicable promise found"]))
    C.frag("evidence classes", "the drop-in engines' %d introduced cells with a cause split into %d that the engine documents for some operations"
           % (DI["with_cause"], DI["partly documented"]))
    C.frag("evidence classes: conflicts and Dask", "%d that conflict with its general pandas-compatibility claim, not an API-specific promise, without a covering statement (for example FireDucks' chained assignments); of Dask's %d, %d are documented at least in part and %d have no applicable statement"
           % (DI["contradicts a compatibility claim"], DK["with_cause"], DK["documented incompatibility"] + DK["partly documented"], DK["no applicable promise found"]))
    aq = cz["approximate_quantile"]["by_engine"]
    C.frag("approximate quantiles", "(Bodo %d cells; Dask, which documents approximate quantiles, %d)" % (aq["conf_1x:bodo"], aq["conf_1x:dask"]))
    se = CPC["str_extract_unnamed_groups"]
    # 2026-11-10: the "smaller findings" sentence (str.extract, CR-only line endings, pd.NA filters) was cut
    hb = HA["by_cause"]
    C.frag("hand attribution totals", "and attributed %d, %d of them with direct evidence" % (HA["cells"] - und if isinstance(HA["cells"], int) else len(HA["rows"]) - und, HA["by_confidence"]["verified"]))
    C.frag("hand: printed form", "Sixteen are a harness artifact")
    C.eq("hand: printed form = 16", 16, hb["printed_form_comparison"])
    for txt, key, cnt in (("(4 cells; a global list", "apply_side_effects_lost", 4), ("an in-place update (6;", "stale_after_inplace_update", 6),
                          ("reads as missing (6)", "read_csv_none_as_na", 6), ("\\texttt{nunique()} (4;", "unique_nunique_missing", 4),
                          ("(pyarrow backend and Bodo, 4)", "arrow_int_keeps_type", 4), ("instead of \\texttt{'nan'} (8)", "str_of_missing_sentinel", 8),
                          ("sample-size correction (4)", "biased_skew", 4)):
        C.frag("hand fragment %s" % key, txt)
        C.eq("hand count %s" % key, cnt, hb[key])
    # 2026-11-10: probes outside the harness (icde27/analysis/r4_probes.json)
    PV, PC = PRB["verdicts"], PRB["checks"]
    C.eq("probes: two repetitions, every run ok", (2, True), (PRB["repetitions"], all(r_["status"] == "ok" for e_ in PRB["environments"].values() for r_ in e_["runs"])))
    C.frag("probes: scope", "probes outside the harness (synthetic inputs, two runs each) reproduce the first four, though not each attribution")
    C.frag("probes: Modin apply", "keeps 5 of 124,234 elements, %s of %s in the probe" % (PC["apply_extend_global_list"]["modin"]["value"], n(int(PC["apply_extend_global_list"]["pandas"]))))
    C.eq("probes: Modin repetitions agree", True, PC["apply_extend_global_list"]["modin"]["repetitions_agree"])
    sb = PV["stale_after_inplace_update_bodo"]
    C.frag("probes: Bodo stale", "(6; in the probes, %d of %d Bodo patterns, and FireDucks' group-by and filters after \\texttt{.at})" % (sb["reproduced_checks"], sb["n_checks"]))
    C.eq("probes: FireDucks stale group-by, unstack and filter all reproduced", {"reproduced"}, set(PV["stale_after_inplace_update_fireducks"]["checks"].values()))
    C.eq("probes: Bodo positions reproduced", "reproduced", PV["positions_instead_of_labels"]["verdict"])
    uq = PV["unique_nunique_missing"]["checks"]
    C.eq("probes: FireDucks unique() not reproduced, every nunique() check reproduced", ("not reproduced", {"reproduced"}),
         (uq["unique_with_missing"], {v_ for k_, v_ in uq.items() if k_.startswith("nunique")}))
    C.frag("probes: unique/nunique", "(4; the probe reproduces only \\texttt{nunique()} counting them)")
    C.eq("hand index_not_preserved: one Bodo cell", {"bodo": 1}, HA["causes"]["index_not_preserved"]["labels"])
    for key, labs in (("apply_side_effects_lost", {"modin"}), ("stale_after_inplace_update", {"bodo", "fireducks"}),
                      ("read_csv_none_as_na", {"fireducks"}), ("unique_nunique_missing", {"fireducks"}),
                      ("arrow_int_keeps_type", {"pyarrow_backend", "bodo"}), ("biased_skew", {"bodo", "dask", "pyarrow_backend"})):
        C.eq("hand labels %s" % key, labs, set(HA["causes"][key]["labels"]))

    # ---------------------------------------------------------------- Section VIII
    rrd = S["campaigns"]["drift"]["run_records"]
    C.eq("drift: 408 completed runs", 408, sum(rrd[l]["by_status"].get("completed", 0) for l in ("p15", "ref", "ref#2", "p30")))
    C.frag("drift bit-exact", "only %s\\%% of scored cells are bit-exact, against %s\\%% under 1.5.3" % (p1(a["p30"]["share"]["E0"]), p1(a["p15"]["share"]["E0"])))
    C.frag("drift E2", "%s\\%% of 3.0.6 cells equal the reference only modulo a value-preserving widening" % p1(a["p30"]["share"]["E2"]))
    C.eq("str dtype: almost all of its introduced cells at E2 (Section VII wording)", True,
         czd["str_default_dtype"]["by_class"]["E2"] > 0.9 * czd["str_default_dtype"]["n_cells"])
    C.frag("drift <=E2", "3.0.6 agrees on %s\\%% of scored cells and 1.5.3 on %s\\%%" % (p1(a["p30"]["cum_share"]["<=E2"]), p1(a["p15"]["cum_share"]["<=E2"])))
    C.frag("strict clean p30", "only %d of %s scored cells have bit-identical inputs" % (view("p30", "clean_strict")["cells"], n(a["p30"]["cells"])))
    C.frag("clean@E2 p30 cells", "recovers to %s cells" % n(e2["p30"]["cells"]))
    C.frag("p15 signature", "%s\\%% \\lv{E2} cells and %s\\%% (%d) \\lv{E4} cells" % (p1(a["p15"]["share"]["E2"]), p1(a["p15"]["share"]["E4"]), a["p15"]["counts"]["E4"]))
    vc4 = sum(1 for c in czd["value_counts_naming"]["cells"] if c[1] == "p15" and c[4] == "E4")
    C.frag("p15 E4 decomposition", "Of these, %d are introduced by pandas 2.0's renamed \\texttt{value\\_counts} results~\\cite{pandas20}, 3 by the 2.2 merge row-order rules, and %d are inherited"
           % (vc4 if vc4 is not None else -1, a["p15"]["counts"]["E4"] - (vc4 or 0) - 3))
    C.eq("E3 at most 0.1% in both directions", True, max(a["p15"]["share"]["E3"], a["p30"]["share"]["E3"]) < 0.0015)
    C.frag("drift DIFF all", "%s\\%% (1.5.3) and %s\\%% (3.0.6) are \\cls{DIFF}" % (p1(a["p15"]["share"]["DIFF"]), p1(a["p30"]["share"]["DIFF"])))
    C.frag("drift DIFF clean@E2", "the shares fall to %s\\%% %s and %s\\%% %s, a reduction by a factor of about %s and %s"
           % (p1(e2["p15"]["share"]["DIFF"]), ci(e2["p15"]["ci95"]["DIFF"]), p1(e2["p30"]["share"]["DIFF"]), ci(e2["p30"]["ci95"]["DIFF"]),
              q(ratios["p15"]), q(ratios["p30"])))
    fdd = {l: dr[l]["first_divergence"] for l in ("p15", "p30")}
    f30, f15 = fdd["p30"]["E4"]["class_at_first_divergence"], fdd["p15"]["E4"]["class_at_first_divergence"]
    C.frag("drift notebooks E4 and first class", "%d notebooks diverge under 3.0.6 and %d under 1.5.3; the first such cell is a \\cls{DIFF} in %d (%d raise, %d cannot be compared) and %d of them"
           % (fdd["p30"]["E4"]["notebooks_diverged"], fdd["p15"]["E4"]["notebooks_diverged"], f30["DIFF"], f30["ERR"], f30["UNCOMPARABLE"], f15["DIFF"]))
    C.frag("p30 errors", "pandas 3.0.6 raises on %d scored cells, %s\\%% %s, and on %s\\%% of the cells that are clean at \\lv{E2}; pandas 1.5.3 raises on %d cells (%s\\%%)"
           % (a["p30"]["counts"]["ERR"], p1(a["p30"]["share"]["ERR"]), ci(a["p30"]["ci95"]["ERR"]), p1(e2["p30"]["share"]["ERR"]),
              a["p15"]["counts"]["ERR"], p1(a["p15"]["share"]["ERR"])))
    C.eq("p30 ERR decomposition 103 + 22 + 47 = 172", a["p30"]["counts"]["ERR"], 103 + 22 + 47)
    C.eq("p30 introduced errors 47 = profile", 47, B["p30"].get("introduced_ERR_cells", 47))
    # 2026-11-10: the sentence "of the 19 such cells, 18 are DIFF and one raises" was cut (Table II gives the classes)

    # ---------------------------------------------------------------- Section IX (RQ4)
    tdf = S["timing"]["by_cpus"]["default"]
    su = RQ["startup"]["timing"]
    C.frag("RQ4: timing boundary for lazy values", "a value that is assigned but never displayed, printed or used later is never computed by a lazy engine")

    def gci(g):
        return "%s [%s, %s]" % (q(g["geomean_speedup_vs_ref"], 2), q(g["ci95"][0], 2), q(g["ci95"][1], 2))
    C.frag("geomeans 8 CPUs", "At 8 CPUs, Modin's speed-up is %s over %d of the 30 notebooks and FireDucks' %s over %d"
           % (gci(t8["modin"]), t8["modin"]["notebooks_both_ok"], gci(t8["fireducks"]), t8["fireducks"]["notebooks_both_ok"]))
    C.frag("geomeans default", "(at engine defaults %s and %s)" % (gci(tdf["modin"]), gci(tdf["fireducks"])))
    C.eq("both geomeans below 1", True, all(g[e]["geomean_speedup_vs_ref"] < 1 for g in (t8, tdf) for e in ("modin", "fireducks")))
    for cpus, g in (("8", t8), ("default", tdf)):
        for e in ("modin", "fireducks"):
            rs = g[e]["not_ok_by_reason"]
            C.eq("not-ok errors = 10 (%s %s)" % (cpus, e), 10, len(rs["error_cells"]))
            C.eq("not-ok accounted (%s %s)" % (cpus, e), 30, g[e]["notebooks_both_ok"] + len(rs["error_cells"]) + len(rs["timeout"]) + len(rs["crash"]) + len(rs["other"]))
    ub = {(c, e): sorted(x["speedup_upper_bound"] for x in g[e]["not_ok_by_reason"]["timeout"]) for c, g in (("8", t8), ("default", tdf)) for e in ("modin", "fireducks")}
    allub = sorted(x for v_ in ub.values() for x in v_)
    C.eq("timeouts: one Modin and three FireDucks timeouts per budget", (1, 1, 3, 3), tuple(len(ub[(c_, e_)]) for e_ in ("modin", "fireducks") for c_ in ("8", "default")))
    pn = RQ["per_notebook"]
    sp = sorted(x["speedup"] for x in pn["8|fireducks"]["notebooks"])
    C.frag("FireDucks per notebook", "FireDucks is faster than pandas on %d of its %d notebooks (up to %s times), Modin on %d of %d"
           % (pn["8|fireducks"]["n_faster_than_ref"], pn["8|fireducks"]["n"], q(pn["8|fireducks"]["speedup_max"]), pn["8|modin"]["n_faster_than_ref"], pn["8|modin"]["n"]))
    C.eq("FireDucks: two notebooks below 0.1", 2, sum(1 for x in sp if x < 0.1))
    cf = S["timing"]["conformance_on_timing30_clean_E2"]
    hl = S["timing"]["host_load"]["by_cpus_engine"]

    def hm(t):
        return t[11:16]
    win = [(hl["8|" + e]["first_start_utc"], hl["8|" + e]["last_end_utc"]) for e in ("ref", "modin", "fireducks")]
    C.eq("8-CPU runs: sequential windows on 4 October", (True, {"2026-10-04"}),
         (all(win[i][1] <= win[i + 1][0] for i in range(2)), {w[0][:10] for w in win} | {w[1][:10] for w in win}))
    C.eq("8-CPU runs not covered by load samples", (0, 0, 0), tuple(hl["8|" + e]["covered"] for e in ("ref", "modin", "fireducks")))
    w0 = RQ["host_load_overall"]["windows"][0]
    C.frag("first load window", "(a median 1-minute load of %s on 32 cores in the first window;" % q(w0["load1_median"]))
    gap = RQ["host_load_overall"]["gaps_over_1h"][0]
    C.eq("sampling gap 7-26 October", ("2026-10-07", "2026-10-26"), (gap["from_utc"][:10], gap["to_utc"][:10]))
    dmed = sorted(hl["default|" + e]["load1_median"] for e in ("ref", "modin", "fireducks"))
    C.eq("default runs covered", (30, 30, 30), tuple(hl["default|" + e]["covered"] for e in ("ref", "modin", "fireducks")))
    rdft = S["timing"]["ref_drift_default_over_8"]
    C.frag("reference drift", "pandas took a median %s times as long in one period as in the other" % q(rdft["ratio_median"], 2))
    rs_ = RQ["rep_spread"]
    lo, hi = min(rs_["8|" + e]["max_over_min_median"] for e in ("ref", "modin", "fireducks")), max(rs_["8|" + e]["max_over_min_median"] for e in ("ref", "modin", "fireducks"))
    C.eq("repetition spread: median max/min at most 1.025", True, hi <= 1.025)
    C.frag("repetition spread", "back-to-back repetitions agree within a median %s\\%%" % q(100 * (hi - 1)))
    C.eq("Bodo 8-CPU: 90 crash records", {"nb_crash": 90}, RQ["completeness"]["8|bodo"]["by_status"])
    # Bodo after the transport fix (filled 2026-10-27): the 8-CPU rerun with its pandas rerun (timing_bodo_r2), and the
    # default budget against the pandas run closer in time (bodo_default_same_period)
    BR, BD = RQ["bodo_r2"], RQ["bodo_default_same_period"]
    bdf = BD["vs_same_period_ref"]
    C.eq("Bodo rerun and default comparison complete", ("complete", "complete"), (BR["status"], BD["status"]))
    for lab, g in (("8", b8), ("default", bdf)):
        rs = g["not_ok_by_reason"]
        C.eq("Bodo not-ok accounted (%s)" % lab, 30, g["notebooks_both_ok"] + len(rs["error_cells"]) + len(rs["timeout"]) + len(rs["crash"]) + len(rs["other"]))
    C.eq("Bodo: the same both-ok notebooks at 8 CPUs and default", True, set(b8["notebooks_not_ok"]) == set(bdf["notebooks_not_ok"]))
    C.eq("Bodo geomeans and their intervals below 1", True, all(g["geomean_speedup_vs_ref"] < 1 and g["ci95"][1] < 1 for g in (b8, bdf)))
    ubb = {lab: sorted(x["speedup_upper_bound"] for x in g["not_ok_by_reason"]["timeout"]) for lab, g in (("8", b8), ("default", bdf))}
    r8 = b8["not_ok_by_reason"]
    C.frag("Bodo 8 CPUs", "reaches %s over only %d notebooks; in the others it raised (%d), crashed (%d) or timed out (%d)"
           % (gci(b8), b8["notebooks_both_ok"], len(r8["error_cells"]), len(r8["crash"]), len(r8["timeout"])))
    rg, rd = BD["reference_group_by_notebook"], bdf["not_ok_by_reason"]
    C.eq("Bodo default: reference closer in time for every notebook (rerun or default-period run)", 30, rg["timing_bodo_r2|8"] + rg["timing|default"])
    hb, hr = BR["host_load"]["by_cpus_engine"]["8|bodo"], BR["host_load"]["by_cpus_engine"]["8|ref"]
    C.eq("Bodo and its pandas rerun on 27 October, pandas first", ("2026-10-27", "2026-10-27", True),
         (hr["first_start_utc"][:10], hb["last_end_utc"][:10], hr["last_end_utc"] <= hb["first_start_utc"]))
    dr8 = BR["ref_drift_r2_over_timing_cpu8"]
    C.eq("Bodo reruns: 90 records, all covered", (90, 90), (hb["records"], hb["covered"]))

    # ---------------------------------------------------------------- Section VI, conf_5x (filled 2026-10-28)
    c5 = S["campaigns"]["conf_5x"]
    C.eq("conf_5x complete with one excluded notebook", ("complete", ["jirakst/book-recommendation"]),
         (c5["status"], sorted(c5.get("notebooks_excluded", {}))))
    rr = {e: c5["run_records"][e]["by_status"] for e in ("ref", "ref#2", "modin", "fireducks", "bodo")}
    C.eq("conf_5x run outcomes", ({"completed": 29}, {"completed": 29}, {"completed": 28, "nb_memory": 1},
                                  {"completed": 27, "nb_crash": 2}, {"completed": 26, "nb_crash": 3}),
         tuple(rr[e] for e in ("ref", "ref#2", "modin", "fireducks", "bodo")))
    C.frag("conf_5x: 29 of 30", "29 of the 30 notebooks ran")
    C.frag("conf_5x outcomes", "Modin completed %d (one memory stop), FireDucks %d and Bodo %d (two and three crashes)"
           % (rr["modin"]["completed"], rr["fireducks"]["completed"], rr["bodo"]["completed"]))
    se = S["scale_effect"]
    E3 = ("modin", "fireducks", "bodo")
    C.eq("scale_effect on the 29 notebooks", True, all(se[e][x]["notebooks"] == 29 for e in E3 for x in ("1x", "5x")))

    def le2(e, x):
        return p1(se[e][x]["cum_share"]["<=E2"])
    C.frag("conf_5x shares", "the share at \\lv{E2} or finer went from %s\\%% at 1x to %s\\%% at 5x for Modin and changed by less than one point for FireDucks and Bodo"
           % (le2("modin", "1x"), le2("modin", "5x")))
    C.eq("conf_5x: FireDucks and Bodo shares at E2 or finer change by less than one point", True,
         all(abs(100 * (se[e]["5x"]["cum_share"]["<=E2"] - se[e]["1x"]["cum_share"]["<=E2"])) < 1.0 for e in ("fireducks", "bodo")))
    C.eq("DIFF share changed by less than one point", True,
         all(abs(100 * (se[e]["5x"]["share"]["DIFF"] - se[e]["1x"]["share"]["DIFF"])) < 1.0 for e in E3))

    # 2026-11-10: the change from 1x to 5x paired by notebook (icde27/analysis/r3_sensitivity.json scale_paired)
    SP = R3["scale_paired"]["by_engine"]
    md = SP["modin"]["le_E2"]
    C.eq("paired 1x/5x: Modin's drop at E2 or finer excludes 0", True, md["ci95_pp"][1] < 0)
    C.eq("paired 1x/5x: every other change interval contains 0", True,
         all(SP[e][k]["ci95_pp"][0] <= 0 <= SP[e][k]["ci95_pp"][1] for e in E3 for k in ("DIFF", "le_E2") if (e, k) != ("modin", "le_E2")))
    C.eq("paired 1x/5x: Modin's one notebook stopped at the memory cap", 1, len(SP["modin"]["notebooks_stopped_at_5x"]))
    mw = SP["modin"]["without_stopped"]["le_E2"]

    def sz(x):
        return "$0.0$" if q(x) in ("0.0", "-0.0") else sg(x)
    C.frag("paired 1x/5x: Modin", "paired by notebook, only Modin's drop at \\lv{E2} or finer is distinguishable (%s points [%s, %s]), mostly from the cells left unrun after its memory stop (without that notebook, %s [%s, %s], which includes 0)"
           % (sz(md["change_pp_5x_minus_1x"]), sz(md["ci95_pp"][0]), sz(md["ci95_pp"][1]),
              sz(mw["change_pp_5x_minus_1x"]), sz(mw["ci95_pp"][0]), sz(mw["ci95_pp"][1])))
    C.eq("paired 1x/5x: Modin without its stopped notebook, the interval includes 0", True, mw["ci95_pp"][0] <= 0 <= mw["ci95_pp"][1])
    C.eq("paired 1x/5x: pooled shares equal summary.json scale_effect (Modin <=E2 change)", q(md["change_pp_5x_minus_1x"]),
         q(100 * (se["modin"]["5x"]["cum_share"]["<=E2"] - se["modin"]["1x"]["cum_share"]["<=E2"])))

    # ---------------------------------------------------------------- Section X (Table IV) and XI
    # Table IV rows are checked with Table V above (r5_tables.py); its cells come from summary.json, r1_cells.json,
    # r4_audit.json and r5_reliability.json
    XF = XX["failure_decomposition"]
    C.eq("Table V (profile, exact basis): EF = r1 no_engine_failure; NB = exact introduced DIFF without known artifacts", True,
         all(XX["notebooks"][l]["error_free"] == nf[l] for l in LAB7))
    C.eq("Table V (profile, exact basis): each row's first failures add up to 102 - EF (FireDucks one other)", True,
         all(sum(XF[l].values()) == 102 - ef[l] for l in LAB7) and XF["fireducks"].get("other") == 1
         and all(XF[l].get("other", 0) == 0 for l in LAB7 if l != "fireducks"))
    C.eq("Table V (profile): the exact basis changes first failures only for pandas 1.5.3 and Bodo (one notebook each)", ["bodo", "p15"],
         sorted(l for l in LAB7 if XF[l] != FD_[l]["not_error_free"]))
    C.frag("Table V (profile) caption: exact basis", "Profile (102 notebooks; nested values recaptured exactly, Section~\\ref{sec:conformance})")
    C.frag("Table V (profile) caption: no approximate-equality glyph", "$\\Delta$: paired difference against pandas 3.0.6 (points; Table~\\ref{tab:variants}, Exact)")
    C.eq("Table V (profile): no approximate-equality glyph left", False, "\\approx" in T)
    rob = {l: B[l]["clean_E2_DIFF_robustness"] for l in LAB7}
    mac = {l: p1(rob[l]["macro_mean_over_notebooks"]) for l in LAB7}
    trio = sorted(float(mac[l]) for l in ("pyarrow_backend", "fireducks", "modin"))
    loo = max(max(abs(rob[l]["leave_one_notebook_out_min_max"][0] - rob[l]["pooled"]), abs(rob[l]["leave_one_notebook_out_min_max"][1] - rob[l]["pooled"])) for l in LAB7)
    C.eq("leave-one-out moves no share by more than 0.9 points", True, 100 * loo <= 0.9)
    C.frag("LOO wording", "moves no pooled share by more than 0.9 points")
    mr = {l: 100 * rob[l]["macro_mean_over_notebooks"] for l in LAB7}
    trio_l = ("pyarrow_backend", "fireducks", "modin")
    C.eq("per notebook: drop-in configurations within two points of both pandas versions", True,
         all(abs(mr[e] - mr[p]) <= 2.0 for e in trio_l for p in ("p15", "p30")))
    C.eq("per notebook: Bodo exceeds both pandas versions", True, mr["bodo"] > max(mr["p15"], mr["p30"]))
    C.eq("Modin lowest of the three pooled, highest per notebook", ("modin", "modin"),
         (min(trio_l, key=lambda l: rob[l]["pooled"]), max(trio_l, key=lambda l: rob[l]["macro_mean_over_notebooks"])))
    C.eq("per notebook: Dask below pandas 3.0.6", True, mr["dask"] < mr["p30"])
    dlo = min(R3V[v]["readings"]["drop_in_diff_pp_range"][0] for v in R3V)
    dhi = max(R3V[v]["readings"]["drop_in_diff_pp_range"][1] for v in R3V)
    agx_ = {l: XX["notebooks"][l]["agreeing"] for l in LAB7}
    nbx_ = {l: XX["notebooks"][l]["introduced_DIFF"] for l in LAB7}
    C.frag("lessons: local and notebook-level views", "yet %d to %d of the 102 notebooks run without error under them and %d to %d also agree in every cell (%d and %d under 3.0.6; Table~\\ref{tab:profile}), and %d to %d contain a silent difference under each"
           % (min(ef[l] for l in DROP), max(ef[l] for l in DROP), min(agx_[l] for l in DROP), max(agx_[l] for l in DROP), ef["p30"], agx_["p30"],
              min(nbx_[l] for l in DROP), max(nbx_[l] for l in DROP)))
    C.frag("lessons: four single-rater behaviours reproduce in probes and on the notebooks", "each took one ordinary notebook cell to trigger, and each reproduces in a probe and on its notebook without the harness")
    C.eq("lessons: the four named behaviours are reproduced", {"reproduced"},
         {PRB["verdicts"][k_]["verdict"] for k_ in ("apply_side_effects_lost", "stale_after_inplace_update_bodo", "stale_after_inplace_update_fireducks", "positions_instead_of_labels", "unique_nunique_missing")})
    C.eq("lessons: drop-in configurations ran fewer notebooks without failure than either pandas version", True,
         all(nf[e] < min(nf["p15"], nf["p30"]) for e in ("modin", "fireducks", "pyarrow_backend")))
    C.frag("conclusion: drop-in and notebook reliability", "yet they run %d to %d notebooks without error against %d under pandas 3.0.6; Bodo (one worker) differs more often than 3.0.6, and Bodo and Dask raise far more often (%d and %d notebooks without error)"
           % (min(ef[l] for l in DROP), max(ef[l] for l in DROP), ef["p30"], ef["bodo"], ef["dask"]))
    C.frag("conclusion: exact notebook range", "Second, silent differences are common: under every configuration %d to %d of the 102 notebooks contain a cell that introduces a \\cls{DIFF} without raising (nested values recaptured exactly)" % tuple(xr_))
    C.frag("conclusion: timing", "no engine's geometric-mean speed-up exceeded one, though FireDucks' interval includes one")
    C.frag("threats: margins exploratory", "so the equivalence reading is exploratory and does not survive every variant")
    C.frag("threats: diagnostic hypotheses", "so cause counts are diagnostic hypotheses, not causal prevalence")
    C.frag("threats: probes and replays", "the probes and the replays of Section~\\ref{sec:rootcause} run without the harness")
    pt_ = PFM["totals"]
    C.eq("printed-form census: the 16 artifact cells are found, one unstored column", (16, True), (PFM["printed16_found"], PFM["obj_columns_missing"] <= 1))
    C.eq("printed-form census: scored and clean@E2 cells equal summary.json", (pt_["scored_cells"], pt_["clean_E2_cells"]),
         (sum(view(l, "all")["cells"] for l in LAB7), sum(view(l, "clean_E2")["cells"] for l in LAB7)))
    C.frag("threats: printed-form census", "compared by their printed form in %s of the %s scored cells and read by %d more: a matching printed form can hide what it does not print"
           % (n(pt_["printed_form_cells"]), n(pt_["scored_cells"]), UT["readers_only"]))
    cmx, cdx = C1R["census_categories"]["matching"], C1R["census_categories"]["DIFF"]
    unres = lambda d_: sum(v_ for k_, v_ in d_.items() if k_.startswith("not recaptured") or k_ == "not exactly encodable")
    C.frag("threats: what the exact recapture resolved", "but an exact recapture found no such case among %d matching forms, found %d differing ones to be artifacts, and left %d matching and %d differing forms unresolved"
           % (cmx["exact match"] + cmx["exact match, finer level"] + cmx["exact match, coarser level"],
              sum(v_ for k_, v_ in cdx.items() if k_.startswith("exact match (DIFF came from the printed form")), unres(cmx), unres(cdx)))
    C.frag("threats: reduced capture", "(never in the %d notebooks without input capture)" % PP["corpus"]["input_over_capture_cap"]["n"])
    C.frag("Table V (profile) caption: notebook counts", "NB: notebooks with an introduced \\cls{DIFF} (known capture artifacts excluded)")
    C.eq("Table V NB: the known artifacts left in the exact basis are the one without an exact encoding (Modin)", ["modin|j0thu777/onlineretailanalysis|20"],
         EX["known_artifacts_without_override"])
    C.frag("figure 1 caption: exploratory margin", "the exploratory $\\pm 2$-point margin (dashed), chosen after the unpaired shares were known")
    C.eq("float rounding: 3 DIFF cells", 3, pt["float_rounding"]["by_class"]["DIFF"])
    C.frag("threats float", "so 3 cells attributed to float rounding are \\cls{DIFF}")
    C.frag("threats NOOUT share", "(%s\\%% of executed cells are not scored)" % q(100.0 * no / ex))

    # ---------------------------------------------------------------- end-to-end capture suite (C2) and uncaptured replays (D2)
    C2 = load("icde27", "analysis", "r5_capture", "c2_results.json")
    C2C = load("icde27", "analysis", "r5_capture", "c2_cases.json")
    c2n = C2C["cases"] if isinstance(C2C.get("cases"), list) else list(C2C.get("cases", {}).values())
    C.eq("C2: 33 planted cases in six notebooks", (33, 6), (len(c2n), len({x.get("notebook") or x.get("nb") for x in c2n})))
    for e_ in ("p30", "fireducks"):
        C.eq("C2: original harness on %s: 9 exact, 16 flagged, 5 late, 3 missed" % e_,
             {"captured exactly": 9, "flagged": 16, "late": 5, "missed": 3}, C2["summary"]["orig:%s" % e_])
    o30 = [r_ for r_ in C2["by_case"] if r_["harness"] == "orig" and r_["engine"] == "p30"]
    C.eq("C2: late cases (mutation through a function or lambda, global, exec and globals() bindings)",
         ["alias_function", "apply_append", "dynamic_exec_store", "dynamic_globals_store", "global_statement"],
         sorted(r_["case"] for r_ in o30 if r_["outcome"] == "late"))
    C.eq("C2: missed cases (unread mutation, reads through globals() or a closure)",
         ["alias_function_no_reader", "dynamic_globals_read", "hidden_global_closure"],
         sorted(r_["case"] for r_ in o30 if r_["outcome"] == "missed"))
    und_ = [r_ for r_ in o30 if r_["verdict"] == "understated" and "printed" in (r_.get("flag") or [])]
    C.eq("C2: matching printed forms hid 4 value and 4 dtype differences (pandas 3.0.6)", (4, 4),
         (sum(r_["truth"] == "DIFF" for r_ in und_), sum(r_["truth"] != "DIFF" for r_ in und_)))
    C.frag("C2: threats text", "in 33 planted cases in six small notebooks, a mutation through a called function or a lambda, a \\texttt{global} statement or a binding through \\texttt{exec} or \\texttt{globals()} was caught only when a later cell read the value")
    C.frag("C2: printed forms in planted cases", "(in the planted cases it hid 4 value and 4 dtype differences)")
    D2 = {x_["id"]: x_ for x_ in load("icde27", "analysis", "r5_replay", "d2_results.json")["cases"]}

    def d2v(cid, eng):
        return D2[cid]["configs"][eng]["verdict"]
    C.eq("D2: Modin corr diagonal confirmed without capture in two notebooks, entries outside [-1, 1]", True,
         all(d2v(k_, "modin").startswith("confirmed") and all(u_["ok"] and list(u_["value"].values())[0]["n_outside"] > 0
                                                               for u_ in D2[k_]["configs"]["modin"]["uncaptured"])
             for k_ in ("corr_diag_deffro", "corr_diag_ev")))
    rb_ = D2["read_rows_bodo_dw"]
    C.eq("D2: bodo_dw reads 1,692 of 1,693 rows in both uncaptured runs, one worker all",
         ([1692, 1692], [1693, 1693], 1693),
         ([u_["value"]["landslides"] for u_ in rb_["configs"]["bodo_dw"]["uncaptured"]],
          [u_["value"]["landslides"] for u_ in rb_["configs"]["bodo"]["uncaptured"]], rb_["pandas_uncaptured"]["landslides"]))
    C.frag("D2: read_csv text", "\\eng{bodo\\_dw}'s \\texttt{read\\_csv} returns 1,692 of 1,693 rows while one worker reads all")
    aq_ = D2["approx_quantile_deffro"]
    kept = [u_["value"]["_"] for u_ in aq_["configs"]["bodo"]["uncaptured"]] + [aq_["configs"]["bodo"]["captured_conf_1x"]["_"],
                                                                              aq_["configs"]["bodo"]["captured_d1_replay"]["_"]]
    C.eq("D2: two uncaptured and two captured Bodo quantile runs", 4, len(kept))
    C.frag("D2: quantile filter text", "Bodo's quantile filter keeps %s to %s rows in two uncaptured and two captured runs against %s" % (n(min(kept)), n(max(kept)), n(aq_["pandas_uncaptured"]["_"])))
    C.eq("D2: 16 cases, every one engine behaviour (Bodo with one worker the no-difference control)", (16, True),
         (len(D2), all(c_["verdict"].startswith("confirmed engine behaviour") or (x_["id"] == "read_rows_bodo_dw" and e_ == "bodo")
                       for x_ in D2.values() for e_, c_ in x_["configs"].items())))
    C.frag("D2: all cases engine behaviour", "all 16 cases tested are engine behavior")
    C.eq("D2: FireDucks int64 slices and chained assignments confirmed; no Modin int64 case", (True, False),
         (all(d2v(k_, "fireducks").startswith("confirmed") for k_ in ("int_float_slice_fireducks", "chained_assignment_tweet", "chained_assignment_scout")),
          any("int_float" in k_ and "modin" in D2[k_]["configs"] for k_ in D2)))
    C.frag("D2: int64 slices text", "FireDucks' int64 slices and silent chained assignments, Modin's \\texttt{value\\_counts} and \\texttt{pivot\\_table} results, a lost index name and four single-rater behaviors reproduce on one cell each (Modin's int64 slices were not replayed)")
    C.eq("D2: the lessons' four behaviours reproduce on their notebooks", True,
         all(d2v(k_, e_).startswith("confirmed") for k_, e_ in (("stale_head_bodo", "bodo"), ("stale_groupby_fireducks", "fireducks"),
                                                               ("apply_side_effects_modin", "modin"), ("positions_labels_bodo", "bodo"),
                                                               ("nunique_fireducks", "fireducks"))))
    C.eq("D2: every Bodo quantile run differs from pandas", True, all(k_ != aq_["pandas_uncaptured"]["_"] for k_ in kept))
    C.eq("D2: Modin value_counts, pivot_table, index name and four single-rater behaviours confirmed on one cell each", True,
         all(d2v(k_, e_).startswith("confirmed") for k_, e_ in (("value_counts_cut_modin", "modin"), ("pivot_table_size_modin", "modin"),
                                                               ("index_name_modin", "modin"), ("apply_side_effects_modin", "modin"),
                                                               ("stale_head_bodo", "bodo"), ("stale_groupby_fireducks", "fireducks"),
                                                               ("positions_labels_bodo", "bodo"))))
    C.eq("D2: no case decided as a capture or conversion artifact", False,
         any("artifact" in c_["verdict"] for x_ in D2.values() for c_ in x_["configs"].values()))
    D1 = load("icde27", "analysis", "r5_replay", "d1_results.json")
    D1P = load("icde27", "analysis", "r5_replay", "d1_plan.json")
    cat_ = {}
    for e_ in D1["engines"].values():
        for k_, v_ in e_["categories_pure"].items():
            cat_[k_] = cat_.get(k_, 0) + v_
    C.eq("D1: 184 notebooks with an engine's introduced DIFF, 15 controls", (184, 15),
         (sum(len(v_["notebooks"]) for v_ in D1P["engines"].values()), sum(len(v_["controls"]) for v_ in D1P["engines"].values())))
    C.eq("D1: 331 of 332 compared cells reproduce as introduced DIFF, 285 bit-identical, 1 not reproduced", (332, 331, 285, 1),
         (cat_.get("R-id", 0) + cat_.get("R-var", 0) + cat_.get("N", 0) + cat_.get("M", 0) + cat_.get("F", 0),
          cat_.get("R-id", 0) + cat_.get("R-var", 0), cat_.get("R-id", 0), cat_.get("N", 0)))
    C.eq("D1: no new introduced DIFF in controls or disputed notebooks", 0,
         sum(v_["new_in_controls"] + v_["new_in_disputed_notebooks"] for v_ in D1["engines"].values()))
    sv_ = {k_: D1["engines"][k_]["self_differing_value_share"] for k_ in ("modin", "fireducks", "dask", "bodo")}
    ncmp = sum(cat_.values()) - (cat_["R-id"] + cat_["R-var"] + cat_["N"] + cat_.get("M", 0) + cat_.get("F", 0))
    C.eq("D1: 9 disputed cells not replayed (7 in four long notebooks) or not compared (2)", (9, 7, 4, 2),
         (ncmp, cat_.get("not replayed (long)", 0), sum(len(v_["not_replayed_long"]) for v_ in D1P["engines"].values()), cat_.get("pending comparison", 0)))
    C.frag("D1: second execution text", "A second execution of the %d notebook-engine runs that hold introduced \\cls{DIFF} cells, with %d controls, reproduced %d of the %d compared cells as introduced \\cls{DIFF} (%d bit for bit; %d cells not replayed or compared) and added none"
           % (sum(len(v_["notebooks"]) for v_ in D1P["engines"].values()), sum(len(v_["controls"]) for v_ in D1P["engines"].values()),
              cat_["R-id"] + cat_["R-var"], cat_["R-id"] + cat_["R-var"] + cat_["N"], cat_["R-id"], ncmp))
    C.frag("D1: values change between runs", "although values changed between the runs in %s--%s\\%% of Modin's, FireDucks' and Dask's scored cells (Bodo %s\\%%)"
           % (p1(min(sv_[k_] for k_ in ("modin", "fireducks", "dask"))), p1(max(sv_[k_] for k_ in ("modin", "fireducks", "dask"))), p1(sv_["bodo"])))
    C.frag("threats: D1 replay", "a second execution reproduced all but one of the %d compared introduced \\cls{DIFF} cells of the engines" % (cat_["R-id"] + cat_["R-var"] + cat_["N"]))

    # ---------------------------------------------------------------- report
    for label, msg in C.fail:
        print("FAIL %-60s %s" % (label, msg))
    print("check_icde_numbers: %d checks, %d failed; %d \\pending{} markers in main.tex (not checked)" % (C.n, len(C.fail), len(pend)))
    return 1 if C.fail else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Print the markdown tables of RESULTS.md from d1_results.json and d3_results.json (stdlib only).
    python3 report_tables.py d1|d3"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENG = ["pyarrow_backend", "modin", "fireducks", "bodo", "dask"]
NAME = {"pyarrow_backend": "pyarrow backend", "modin": "Modin", "fireducks": "FireDucks", "bodo": "Bodo (1 worker)", "dask": "Dask"}


def d1():
    d = json.load(open(os.path.join(HERE, "d1_results.json")))
    print("| Configuration | disputed cells (pure; exception-on, no printed) | replayed | R-id | R-var | M | N | F | not replayed |")
    print("|---|---|---|---|---|---|---|---|---|")
    tot = {}
    for e in ENG:
        v = d["engines"][e]
        c = v["categories_pure"]
        n = sum(c.values())
        nr = c.get("not replayed (long)", 0) + c.get("not replayed (budget or no record)", 0) + c.get("pending comparison", 0)
        on = sum(v["categories_exception_on_no_printed"].values())
        row = [c.get(k, 0) for k in ("R-id", "R-var", "M", "N", "F")]
        for k, x in zip(("n", "on", "rep", "R-id", "R-var", "M", "N", "F", "nr"), [n, on, n - nr] + row + [nr]):
            tot[k] = tot.get(k, 0) + x
        print("| %s | %d; %d | %d | %d | %d | %d | %d | %d | %d |" % ((NAME[e], n, on, n - nr) + tuple(row) + (nr,)))
    print("| all | %d; %d | %d | %d | %d | %d | %d | %d | %d |" % tuple(tot[k] for k in ("n", "on", "rep", "R-id", "R-var", "M", "N", "F", "nr")))
    print()
    print("| Configuration | notebooks replayed (+controls) | hash-identical | scored cells | differing between runs | of which identical failures / token-only / value changes | new introduced DIFF (controls / disputed nbs) |")
    print("|---|---|---|---|---|---|---|")
    for e in ENG:
        v = d["engines"][e]
        det = v.get("self_differing_detail", {})
        same = det.get("same failure in both runs (not a difference)", 0)
        tok = det.get("token-only printed difference", 0)
        print("| %s | %d (+%d) | %d | %d | %d (%.2f%%) | %d / %d / %d (%.2f%%) | %d / %d |" % (
            NAME[e], v["notebooks_replayed"], v["controls_replayed"], v["notebooks_identical"], v["self_scored_cells"],
            v["self_differing_cells"], 100 * (v["self_differing_share"] or 0), same, tok, v.get("self_differing_value_changes", 0),
            100 * (v.get("self_differing_value_share") or 0), v["new_in_controls"], v["new_in_disputed_notebooks"]))
    print()
    print("| Configuration | introduced DIFF, no printed (paper -> without M, N) | NB corrected (paper -> without) | NB raw (paper -> without) |")
    print("|---|---|---|---|")
    for e in ENG:
        p = d["principal_counts"][e]
        a, b, c = p["introduced_DIFF_no_printed"], p["notebooks_introduced_DIFF_no_printed"], p["notebooks_introduced_DIFF_raw"]
        print("| %s | %d -> %d | %d -> %d | %d -> %d |" % (NAME[e], a["paper"], a["without_nondet"], b["paper"], b["without_nondet"], c["paper"], c["without_nondet"]))
    print()
    print("| Contrast (clean@E2, paired) | published: diff [95%] (engine DIFF / cells) | without M and N cells |")
    print("|---|---|---|")
    for k in sorted(d["paired"]["base"]):
        b, x = d["paired"]["base"][k], d["paired"]["without_nondet"][k]
        print("| %s | %+.2f [%.2f, %.2f] (%d/%d), %s | %+.2f [%.2f, %.2f] (%d/%d), %s |" % (
            k, b["diff_pp"], b["ci95_pp"][0], b["ci95_pp"][1], b["engine_DIFF"], b["cells"], b["reading"],
            x["diff_pp"], x["ci95_pp"][0], x["ci95_pp"][1], x["engine_DIFF"], x["cells"], x["reading"]))


def d3():
    d = json.load(open(os.path.join(HERE, "d3_results.json")))
    print("| Stratum | cells | agree | disagree | mixed | inconclusive | untested | agreement (decided) | outcomes by check |")
    print("|---|---|---|---|---|---|---|---|---|")
    for s in ("P", "Q", "C", "S", "R", "H"):
        x = d["strata"][s]
        o = x["overall"]
        print("| %s | %d | %d | %d | %d | %d | %d | %s (%d) | %s |" % (s, x["cells"], o.get("agree", 0), o.get("disagree", 0), o.get("mixed", 0),
              o.get("inconclusive", 0), o.get("untested", 0), x["agreement"], x["decided"],
              "; ".join("%s %s" % (k, ", ".join("%s %d" % (kk, vv) for kk, vv in sorted(v.items()))) for k, v in x["by_test"].items() if k not in ("N9",))))
    print()
    print("| Configuration | paper | P vanish / persist / other | Q vanish (of) | interval (cells) | interval (share) |")
    print("|---|---|---|---|---|---|")
    for e in ENG:
        x = d["parallel_or_lazy"][e]
        den = x["paper"][1]
        print("| %s | %d/%d = %.1f%% | %d / %d / %d | %d (%d) | [%d, %d] | [%.1f%%, %.1f%%] |" % (
            NAME[e], x["paper"][0], den, 100.0 * x["paper"][0] / den, x["P_vanish"], x["P_persist"], x["P_inconclusive_or_untested"],
            x["Q_vanish"], x["Q_cells"], x["interval_cells"][0], x["interval_cells"][1], 100.0 * x["interval_cells"][0] / den,
            100.0 * x["interval_cells"][1] / den))


def d3dis():
    """Every disagreement (and mixed cell) of D3, one line each, for d3_disagreements.md."""
    d = json.load(open(os.path.join(HERE, "d3_results.json")))
    print("# D3 disagreements (mechanical audit; generated by report_tables.py d3dis from d3_results.json)")
    print()
    print("Cell = configuration, notebook (PandasBench slug), 0-based code-cell index (the ID in the JSON files is")
    print("configuration|notebook|index). Source: rule, curated, none (= single rater).")
    print("Only checks whose outcome disagrees with the attribution are listed per cell; `mixed` = another check agrees.")
    print()
    print("| Cell | strata | class | source | attributed cause | overall | disagreeing checks (outcome, detail) |")
    print("|---|---|---|---|---|---|---|")
    for v in sorted(d["disagreements"], key=lambda v: (v["label"], v["cause"], v["id"])):
        bad = ["%s: %s%s" % (k, t.get("outcome"), (" (%s)" % t.get("detail")) if t.get("detail") else "")
               for k, t in v["tests"].items() if t.get("agree") is False]
        print("| %s `%s` #%d | %s | %s | %s | %s | %s | %s |" % (v["label"], v["nb"], v["cell"], ",".join(v["strata"]), v["cls"], v["assigned_by"],
              v["cause"], v["overall"], "; ".join(bad)))
    print()
    print("%d cells." % len(d["disagreements"]))


if __name__ == "__main__":
    {"d1": d1, "d3": d3, "d3dis": d3dis}[sys.argv[1]]()

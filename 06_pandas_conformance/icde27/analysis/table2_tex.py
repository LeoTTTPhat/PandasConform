#!/usr/bin/env python3
"""Rows of the ICDE copy's Table II (root-cause taxonomy, compact form; written 2026-10-26).

Reads results/rootcause/taxonomy_conf1x.json (read-only) and reuses the labels and column helpers of
scripts/table1_tex.py (the SIGMOD table generator, imported, not changed). Writes icde27/analysis/table2_rows.tex,
whose rows are pasted into icde27/main.tex between the header \\midrule and \\bottomrule of tab:rootcauses.

    cd ..
    .venv/bin/python 06_pandas_conformance/icde27/analysis/table2_tex.py

Differences from the SIGMOD table (review R1, items A7 and B5): the a-priori Kind column is replaced by the observed
classes of the introduced cells (the two most frequent, with counts); the strict-clean column is dropped; causes
seen only in a pandas version with fewer than 100 cells are grouped per version, and engine causes with fewer than
10 cells are grouped, each group listing its number of causes, its documented causes (yes or partly) and its
reproducers. Symptom-level groups carry $^\\S$ (results/rootcause/paper_provenance.json taxonomy.engine_symptom_level_cells).
Every cause stays listed with its counts in results/rootcause/taxonomy_conf1x.md (artifact).
Since review round R5 (2026-11-10) the table counts introduced cells by the pure definition (the grade worsens): the
59 DIFF cells that the taxonomy's heuristic exception counts as inherited (no cause rule, inputs agreeing only
modulo row order or the index; icde27/analysis/r4_audit.json membership.exception_cells) get their own row after
the unattributed row.
"""
import collections
import importlib.util
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "table2_rows.tex")
PANDAS_MIN, ENGINE_MIN = 100, 10


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def classes(by_class, top=2):
    items = sorted(by_class.items(), key=lambda kv: (-kv[1], kv[0]))
    s = ", ".join("%s %d" % (k if k in ("E0", "E1", "E2", "E3", "E4") else "\\cls{%s}" % k, v) for k, v in items[:top])
    return s + (", \\ldots" if len(items) > top else "")


def main():
    T = load_module("table1_tex", os.path.join(PROJ, "scripts", "table1_tex.py"))
    t = json.load(open(os.path.join(PROJ, "results", "rootcause", "taxonomy_conf1x.json")))
    # symptom-level groups (engine error, API not implemented, other value, crash or timeout, other inferred dtype),
    # as counted in paper_provenance.json taxonomy.engine_symptom_level_cells; marked $^\S$ (added 2026-11-10)
    symptom = set(json.load(open(os.path.join(PROJ, "results", "rootcause", "paper_provenance.json")))["taxonomy"]["engine_symptom_level_cells"])
    roots = [c for c in t["causes"].values()
             if c.get("family") not in ("not_a_root_cause", "nondeterminism") and c["cause"] != "unattributed"]
    roots.sort(key=lambda c: (-c["n_cells"], -c["n_notebooks"], c["cause"]))

    def versions(c):
        return {k.split(":", 1)[1] for k in c["by_engine"]}

    keep, groups = [], collections.OrderedDict([("p15", []), ("p30", []), ("engines", [])])
    for c in roots:
        v = versions(c)
        if v <= {"p15", "p30"}:
            if c["n_cells"] >= PANDAS_MIN:
                keep.append(c)
            else:
                groups["p15" if v == {"p15"} else "p30" if v == {"p30"} else "p30"].append(c)
        elif c["n_cells"] >= ENGINE_MIN:
            keep.append(c)
        else:
            groups["engines"].append(c)
    lines = []
    for c in keep:
        cfg, only_pilot = T.configs(c["by_engine"])
        lab = T.LABEL[c["cause"]] + ("$^\\dagger$" if only_pilot else "") + ("$^\\S$" if c["cause"] in symptom else "")
        lines.append("%s & %s & %d & %d & %s & %s & %s \\\\" % (
            lab, T.DOC.get(c.get("documented_level"), "no"), c["n_cells"], c["n_notebooks"], classes(c["by_class"]),
            cfg, T.repro(c)))
    lines.append("\\midrule")
    names = {"p15": "other pandas 2.0--2.2 changes", "p30": "other pandas 3.0 changes", "engines": "other engine causes"}
    meta = {}
    for g, cs in groups.items():
        if not cs:
            continue
        by_engine, by_class, nbs = collections.Counter(), collections.Counter(), set()
        for c in cs:
            by_engine.update(c["by_engine"])
            by_class.update(c["by_class"])
            nbs.update(c["notebooks"])
        cfg, _ = T.configs(dict(by_engine))
        doc = sum(1 for c in cs if c.get("documented_level") in ("yes", "partial"))
        rep = sum(1 for c in cs if c.get("repro_runs") or c.get("engine_probe_outcome"))
        lines.append("%s (%d) & %d/%d & %d & %d & %s & %s & %d/%d \\\\" % (
            names[g], len(cs), doc, len(cs), sum(c["n_cells"] for c in cs), len(nbs), classes(dict(by_class)), cfg,
            rep, len(cs)))
        meta[g] = [c["cause"] for c in cs]
    u = t["causes"].get("unattributed")
    cfg, _ = T.configs(u["by_engine"])
    lines.append("unattributed by the rules$^\\ddagger$ & -- & %d & %d & %s & %s & -- \\\\" % (
        u["n_cells"], u["n_notebooks"], classes(u["by_class"]), cfg))
    # the 59 exception cells: introduced and unattributed under the pure definition (review round R5)
    exc = json.load(open(os.path.join(HERE, "r4_audit.json")))["membership"]["exception_cells"]
    ex_eng = collections.Counter("%s:%s" % (x["campaign"], x["label"]) for x in exc)
    ex_cls = collections.Counter(x["cls"] for x in exc)
    cfg, _ = T.configs(dict(ex_eng))
    parts = cfg.split(", ")
    cfg = ", ".join(parts[:5]) + (", \\ldots" if len(parts) > 5 else "")   # full list in r4_audit.md
    lines.append("no rule, inputs differ in order or index & -- & %d & %d & %s & %s & -- \\\\" % (
        len(exc), len({x["nb"] for x in exc}), classes(dict(ex_cls)), cfg))
    nd = t["causes"]["nondeterminism"]
    cfg, _ = T.configs(nd["by_engine"])
    lines.append("%s & no & %d & %d & %s & %s & -- \\\\" % (T.LABEL["nondeterminism"], nd["n_cells"], nd["n_notebooks"],
                                                          classes(nd["by_class"]), cfg))
    with open(OUT, "w") as f:
        f.write("%% generated by icde27/analysis/table2_tex.py from results/rootcause/taxonomy_conf1x.json (%s)\n" % t["generated"])
        f.write("%% grouped causes: %s\n" % json.dumps(meta))
        f.write("\n".join(lines) + "\n")
    print("wrote %s: %d cause rows, %d groups (%s)" % (OUT, len(keep), len(meta), {g: len(v) for g, v in meta.items()}))


if __name__ == "__main__":
    main()

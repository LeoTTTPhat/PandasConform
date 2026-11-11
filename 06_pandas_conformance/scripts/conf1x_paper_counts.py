#!/usr/bin/env python3
"""Derived conf_1x counts quoted in the paper that are not stored directly in summary.json (2026-10-04).

Reads results/summary.json, results/rootcause/taxonomy_conf1x.json and the conf_1x compare outputs (read-only);
writes results/rootcause/conf1x_paper_counts.json:
  * fallback_split: per engine, level shares of fallback-flagged vs other comparable cells (all view), from
    summary.json campaigns.conf_1x.engines.<e>.{views.all.counts, fallback.by_class_all}
  * fallback_split_clean_E2 (audit A12, 2026-10-05): the same split over cells clean at E2 (post-timeout
    cascades removed), from summary.json campaigns.conf_1x.engines.<e>.{views.clean_E2.counts,
    fallback.by_class_clean_E2} (written by analyze.py since 2026-10-05)
  * attribution_kinds: per engine, non-E0 cells by kind (introduced / propagated / cascade / harness) and the
    introduced share, from taxonomy_conf1x.json per_engine
  * str_extract_unnamed_groups: pyarrow_backend cells whose engine error says the pattern must contain a
    symbolic group name (str.extract with unnamed groups), all classes, from the compare outputs
Usage (from the project folder): ../.venv/bin/python scripts/conf1x_paper_counts.py
"""
import glob
import json
import os

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CMP = os.path.join(PROJ, "results", "conf_1x", "raw", "compare__hd1c421ecb5ee__d92c8db54d45b")


def main():
    s = json.load(open(os.path.join(PROJ, "results", "summary.json")))
    t = json.load(open(os.path.join(PROJ, "results", "rootcause", "taxonomy_conf1x.json")))
    eng = s["campaigns"]["conf_1x"]["engines"]
    out = {"fallback_split": {}, "fallback_split_clean_E2": {}, "attribution_kinds": {},
           "str_extract_unnamed_groups": {}}
    for e, d in eng.items():
        if e == "ref#2":
            continue
        for key, view, fbkey in (("fallback_split", "all", "by_class_all"),
                                 ("fallback_split_clean_E2", "clean_E2", "by_class_clean_E2")):
            if fbkey not in d["fallback"]:
                raise SystemExit("summary.json lacks fallback.%s: rerun analyze.py (2026-10-05 or later)" % fbkey)
            allc = d["views"][view]["counts"]
            fb = d["fallback"][fbkey]
            n_all, n_fb = sum(allc.values()), sum(fb.values())
            if n_fb:
                rest = {k: allc.get(k, 0) - fb.get(k, 0) for k in allc}
                n_rest = n_all - n_fb
                out[key][e] = {
                    "fallback_cells": n_fb, "other_cells": n_rest,
                    "fallback_counts": dict(sorted(fb.items())),
                    "other_counts": {k: v for k, v in sorted(rest.items()) if v},
                    "fallback_share": {k: round(v / n_fb, 4) for k, v in fb.items()},
                    "other_share": {k: round(v / n_rest, 4) for k, v in rest.items() if v}}
        pe = t["per_engine"].get("conf_1x:" + e)
        if pe:
            kinds = {k: v for k, v in pe.items() if ":" not in k}
            tot = sum(kinds.values())
            out["attribution_kinds"][e] = {"non_e0_cells": tot, **kinds,
                                          "introduced_share": round(kinds.get("introduced", 0) / tot, 4)}
    n, nbs = 0, set()
    for p in glob.glob(os.path.join(CMP, "pyarrow_backend", "sf1", "*.json")):
        r = json.load(open(p))
        for c in r["cells"]:
            if "must contain a symbolic group name" in (c.get("eng_msg") or ""):
                n += 1
                nbs.add(r["meta"]["nb"])
    out["str_extract_unnamed_groups"] = {"engine": "pyarrow_backend", "cells": n, "notebooks": len(nbs)}
    path = os.path.join(PROJ, "results", "rootcause", "conf1x_paper_counts.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()

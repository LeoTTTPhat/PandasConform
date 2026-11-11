"""Paired clean@E2 DIFF contrasts and unpaired clean@E2 DIFF shares, re-implemented from r3_sensitivity.py (variant
"base": same cell loading through rootcause_taxonomy.select_outputs, same views, same pairing rule, same bootstrap
seeds and resample count from r1_cells.py), with an optional set of cells to exclude from numerator and denominator.
`check_against_r4()` verifies that with no exclusion every contrast equals r4_audit.json sensitivity.base exactly.
Runs with the shared venv (numpy)."""
import collections
import importlib.util
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
AN = os.path.join(PROJ, "icde27", "analysis")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R1 = _load("r1_cells", os.path.join(AN, "r1_cells.py"))
T = _load("rootcause_taxonomy", os.path.join(PROJ, "scripts", "rootcause_taxonomy.py"))
N_BOOT, SEED, ENGINES, PANDAS, LABELS, EXCLUDED = R1.N_BOOT, R1.SEED, R1.ENGINES, R1.PANDAS, R1.LABELS, R1.EXCLUDED
boot_share, stable_key = R1.boot_share, R1.stable_key
_CACHE = {}


def load_cells():
    if "cells" in _CACHE:
        return _CACHE["cells"], _CACHE["meta"]
    cells, meta = {}, {}
    for campaign in ("conf_1x", "drift"):
        root, best = T.select_outputs(campaign, T.COMPARE)
        for (label, nb, sc), (_, r, p) in sorted(best.items()):
            if (campaign, label) not in LABELS:
                continue
            meta[(campaign, label, nb)] = r["meta"]
            cl = r["cells"]
            t_idx = next((k for k, c in enumerate(cl) if c.get("cls") == "TIMEOUT" or c.get("cls_raw") == "TIMEOUT"), None)
            for k, c in enumerate(cl):
                cells.setdefault((campaign, label), []).append(
                    {"nb": nb, "i": c["i"], "cls": c["cls"], "clean": c.get("clean_level"),
                     "post_timeout": t_idx is not None and k > t_idx})
    _CACHE["cells"], _CACHE["meta"] = cells, meta
    return cells, meta


def compute(exclude=frozenset()):
    """exclude: set of (label, nb, i). Returns {"pairs": {...}, "unpaired": {...}} for the base variant."""
    cells, meta = load_cells()

    def view(label, cl):
        for c in cl:
            if c["cls"] in EXCLUDED or (label, c["nb"], c["i"]) in exclude:
                continue
            if not c["post_timeout"] and c["clean"] in ("E0", "E1", "E2"):
                yield c

    out = {"pairs": {}, "unpaired": {}}
    for (campaign, label), cl in sorted(cells.items()):
        num, den = collections.Counter(), collections.Counter()
        for c in view(label, cl):
            den[c["nb"]] += 1
            num[c["nb"]] += c["cls"] == "DIFF"
        out["unpaired"][label] = boot_share(num, den, "%s|clean_E2|DIFF" % label)

    def ce2(campaign, label):
        return {(c["nb"], c["i"]): c["cls"] == "DIFF" for c in view(label, cells[(campaign, label)])}

    for e in ENGINES:
        de = ce2("conf_1x", e)
        for v in PANDAS:
            dv = ce2("drift", v)
            ok_nb = {nb for (camp, lab, nb), m in meta.items() if camp == "conf_1x" and lab == e
                     and os.path.basename(m.get("ref_record") or "") == os.path.basename((meta.get(("drift", v, nb)) or {}).get("ref_record") or "")}
            common = sorted(k for k in de if k in dv and k[0] in ok_nb)
            by_nb = collections.defaultdict(lambda: [0, 0, 0])
            for k in common:
                b = by_nb[k[0]]
                b[0] += 1
                b[1] += de[k]
                b[2] += dv[k]
            nbs = sorted(by_nb)
            n = np.array([by_nb[x][0] for x in nbs], float)
            a = np.array([by_nb[x][1] for x in nbs], float)
            b = np.array([by_nb[x][2] for x in nbs], float)
            rng = np.random.default_rng([SEED, stable_key("pair|%s|%s" % (e, v))])
            idx = rng.integers(0, len(nbs), size=(N_BOOT, len(nbs)))
            diff = (a[idx].sum(1) - b[idx].sum(1)) / n[idx].sum(1) * 100
            est = (a.sum() - b.sum()) / n.sum() * 100
            ci95 = [float(np.percentile(diff, 2.5)), float(np.percentile(diff, 97.5))]
            ci90 = [float(np.percentile(diff, 5)), float(np.percentile(diff, 95))]
            out["pairs"]["%s-%s" % (e, v)] = {
                "cells": int(n.sum()), "notebooks": len(nbs), "engine_DIFF": int(a.sum()), "pandas_DIFF": int(b.sum()),
                "engine_DIFF_pct": round(a.sum() / n.sum() * 100, 3), "pandas_DIFF_pct": round(b.sum() / n.sum() * 100, 3),
                "diff_pp": round(est, 3), "ci95_pp": [round(x, 3) for x in ci95], "ci90_pp": [round(x, 3) for x in ci90],
                "reading": "more often" if ci95[0] > 0 else ("less often" if ci95[1] < 0 else "not distinguishable")}
    return out


def check_against_r4():
    r4 = json.load(open(os.path.join(AN, "r4_audit.json")))["sensitivity"]["base"]["pairs"]
    mine = compute()["pairs"]
    bad = []
    for k, v in r4.items():
        m = mine.get(k)
        for f in ("cells", "notebooks", "engine_DIFF", "pandas_DIFF", "diff_pp", "ci95_pp", "ci90_pp", "reading"):
            if m is None or m.get(f) != v.get(f):
                bad.append((k, f, v.get(f), None if m is None else m.get(f)))
    return {"contrasts": len(r4), "mismatches": bad}


if __name__ == "__main__":
    print(check_against_r4())

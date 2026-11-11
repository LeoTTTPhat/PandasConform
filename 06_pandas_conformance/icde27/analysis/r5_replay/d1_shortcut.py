#!/usr/bin/env python3
"""D1: classify a disputed cell of a replayed notebook WITHOUT decoding when the comparator's result for that cell
cannot have changed. classify.classify_run computes cell i from the reference records (unchanged), the engine run's
status, the engine cell i (status, exception type, captured inputs and outputs) and the engine's last captured value of
every name the cell reads through `last_eng` (inputs of runs without pre-cell capture, and globals read by user
functions the cell calls). If all of these are identical (same content hashes) in the replay and in the original
engine run, the replay's class and clean level for cell i equal the published ones. This script checks exactly that,
with classify's own _update_last and _hidden_globals, for the disputed cells of the notebooks that are not
hash-identical as a whole. envs/ref (imports pconf.classify), no decoding. Writes d1_shortcut.json.
    env PYTHONPATH=06_pandas_conformance-ICDE/src nice 06_pandas_conformance-ICDE/envs/ref/bin/python \
        06_pandas_conformance-ICDE/icde27/analysis/r5_replay/d1_shortcut.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import r5common as R  # noqa: E402

sys.path.insert(0, R.SRC)
OUT = os.path.join(HERE, "d1_shortcut.json")


def key(v):
    if isinstance(v, dict):
        return ("obj", v.get("kind"), v.get("type"), str(v.get("error"))[:200])
    return ("h", v)


def main():
    from pconf import classify as K
    plan = R.read_json(os.path.join(HERE, "d1_plan.json"))
    hc = R.read_json(os.path.join(HERE, "d1_hashcheck.json"))
    nonid = {(n["engine"], n["nb"]): n for n in hc["notebooks"] if not n["identical"]}
    out = {"item": "D1", "method": __doc__.strip(), "cells": []}
    for eng, e in plan["engines"].items():
        meta = {n["nb"]: n for n in e["notebooks"]}
        for d in e["disputed_cells"]:
            if (eng, d["nb"]) not in nonid:
                continue
            m = meta[d["nb"]]
            ref = R.read_json(os.path.join(R.PROJ, m["ref_record"]))
            org = R.read_json(os.path.join(R.PROJ, m["eng_record"]))
            rep = R.read_json(os.path.join(R.PROJ, nonid[(eng, d["nb"])]["record"]))
            i = d["cell"]
            why = []
            if org.get("status") != rep.get("status"):
                why.append("run status %s/%s" % (org.get("status"), rep.get("status")))
            oc = {c["i"]: c for c in org.get("cells", [])}
            ec = {c["i"]: c for c in rep.get("cells", [])}
            a, b = oc.get(i), ec.get(i)
            if a is None or b is None:
                why.append("cell missing")
            else:
                for f in ("status", "exc_type"):
                    if a.get(f) != b.get(f):
                        why.append(f)
                for f in ("inputs", "outputs"):
                    ka = {n: key(v) for n, v in (a.get(f) or {}).items()} if a.get(f) is not None else None
                    kb = {n: key(v) for n, v in (b.get(f) or {}).items()} if b.get(f) is not None else None
                    if ka != kb:
                        why.append(f)
            # last captured values of the names the cell can read through last_eng
            last_o, last_e, fn_defs = {}, {}, {}
            names = set()
            for cr in ref.get("cells", []):
                j = cr["i"]
                if j == i:
                    static = cr.get("static") or {}
                    names = set(static.get("loads") or []) | set(K._hidden_globals(static, fn_defs))
                    break
                for n, dd in ((cr.get("static") or {}).get("fn_globals") or {}).items():
                    fn_defs[n] = list(dd)
                if j in oc:
                    K._update_last(last_o, oc[j])
                if j in ec:
                    K._update_last(last_e, ec[j])
            diff_last = sorted(n for n in names if key(last_o.get(n)) != key(last_e.get(n)))
            if diff_last:
                why.append("last_captured:" + ",".join(diff_last[:5]))
            out["cells"].append({"engine": eng, "nb": d["nb"], "cell": i, "unchanged": not why, "why": why})
    R.write_json(OUT, out)
    n_ok = sum(c["unchanged"] for c in out["cells"])
    print("disputed cells in non-identical notebooks:", len(out["cells"]), "provably unchanged:", n_ok)
    for c in out["cells"]:
        if not c["unchanged"]:
            print("  changed inputs:", c["engine"], c["nb"], c["cell"], c["why"][:4])


if __name__ == "__main__":
    main()

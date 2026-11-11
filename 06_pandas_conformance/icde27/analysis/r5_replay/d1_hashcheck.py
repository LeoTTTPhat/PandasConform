#!/usr/bin/env python3
"""D1 hash-level self-comparison (stdlib only, no blob decoding): replay record vs original engine record, cell by
cell. A cell is identical when its status, exception type, every captured output entry (content hash or status
string) and every captured input entry are equal. If EVERY cell of a notebook is identical, the comparator's result
for the replay equals the published one exactly (classify is a function of these entries and the blobs they name), so
no re-comparison is needed; notebooks with any difference are listed for the full comparator (d1_compare.py).
Writes d1_hashcheck.json.   Usage: python3 d1_hashcheck.py --tags d1b
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import r5common as R  # noqa: E402

OUT = os.path.join(HERE, "d1_hashcheck.json")


def entry_key(v):
    if isinstance(v, dict):
        return ("obj", v.get("kind"), v.get("type"), str(v.get("error"))[:80])
    return ("h", v)


def cell_sig(c):
    return {"status": c.get("status"), "exc": c.get("exc_type"),
            "out": {k: entry_key(v) for k, v in (c.get("outputs") or {}).items()},
            "in": {k: entry_key(v) for k, v in (c.get("inputs") or {}).items()}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", default="d1b")
    a = ap.parse_args()
    plan = R.read_json(os.path.join(HERE, "d1_plan.json"))
    meta = {(eng, n["nb"]): n for eng, e in plan["engines"].items() for n in e["notebooks"] + e["controls"]}
    seen, nbs = set(), []
    for tag in a.tags.split(","):
        for r in (R.read_json(os.path.join(HERE, "d1_run_%s.json" % tag)) or {}).get("results", []):
            k = (r["engine"], r["nb"])
            if not r.get("record") or k in seen:
                continue
            seen.add(k)
            m = meta[k]
            rep = R.read_json(os.path.join(R.PROJ, r["record"]))
            org = R.read_json(os.path.join(R.PROJ, m["eng_record"]))
            rc = {c["i"]: c for c in rep.get("cells", [])}
            oc = {c["i"]: c for c in org.get("cells", [])}
            diff_cells = []
            for i in sorted(set(rc) | set(oc)):
                a_, b_ = rc.get(i), oc.get(i)
                if a_ is None or b_ is None:
                    diff_cells.append({"i": i, "what": "missing in %s" % ("replay" if a_ is None else "original")})
                    continue
                sa, sb = cell_sig(a_), cell_sig(b_)
                if sa != sb:
                    what = [k for k in ("status", "exc") if sa[k] != sb[k]]
                    what += ["out:" + n for n in sorted(set(sa["out"]) | set(sb["out"])) if sa["out"].get(n) != sb["out"].get(n)]
                    what += ["in:" + n for n in sorted(set(sa["in"]) | set(sb["in"])) if sa["in"].get(n) != sb["in"].get(n)]
                    diff_cells.append({"i": i, "what": what[:12]})
            nbs.append({"engine": r["engine"], "nb": r["nb"], "role": r["role"], "record": r["record"],
                        "replay_status": rep.get("status"), "orig_status": org.get("status"),
                        "n_cells": len(rc), "n_cells_differing": len(diff_cells), "diff_cells": diff_cells,
                        "identical": not diff_cells and rep.get("status") == org.get("status")})
    out = {"item": "D1", "method": __doc__.strip(), "tags": a.tags, "notebooks": nbs,
           "n_notebooks": len(nbs), "n_identical": sum(1 for n in nbs if n["identical"]),
           "need_full_compare": [[n["engine"], n["nb"]] for n in nbs if not n["identical"]]}
    R.write_json(OUT, out)
    by = {}
    for n in nbs:
        b = by.setdefault(n["engine"], [0, 0, 0])
        b[0] += 1
        b[1] += n["identical"]
        b[2] += n["n_cells_differing"]
    for e, (t, i, d) in sorted(by.items()):
        print("%-16s notebooks %3d identical %3d differing cells %d" % (e, t, i, d))
    for n in nbs:
        if not n["identical"]:
            print("  differs: %-16s %-60s %s cells %s" % (n["engine"], n["nb"], n["n_cells_differing"],
                                                         [(d["i"], d["what"][:3]) for d in n["diff_cells"][:4]]))


if __name__ == "__main__":
    main()

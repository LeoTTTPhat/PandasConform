#!/usr/bin/env python3
"""D1: what differs between an engine's two executions? For every output that is not E0 in a self comparison
(work/r5_replay/compare/self), classify the difference from the capture records alone where possible:
  same_failure_both  neither run has a content hash and both record the same failure (for example the same error of
                    the engine's own conversion): identical behaviour that the comparator can only call UNCOMPARABLE
  different_failure_both  neither run has a content hash, with different failures
  uncapturable_in_original / _replay   no content hash in that run only
  token_only        both are scalars/containers (printed forms) whose text differs only in hexadecimal tokens
                    (for example Dask expression names such as FromMapProjectable(11fc3c7)) or memory addresses
  printed_other     scalars/containers whose text differs otherwise
  frame_like        frames, series, arrays or indexes (not decoded here; the level comes from the comparator)
Decodes only scalar and container records (small). envs/ref, read only. Writes d1_selfdiff.json.
    env PYTHONPATH=06_pandas_conformance-ICDE/src nice 06_pandas_conformance-ICDE/envs/ref/bin/python \
        06_pandas_conformance-ICDE/icde27/analysis/r5_replay/d1_selfdiff.py
"""
import collections
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import r5common as R  # noqa: E402

sys.path.insert(0, R.SRC)
OUT = os.path.join(HERE, "d1_selfdiff.json")
TOKEN = re.compile(r"0x[0-9a-fA-F]+|\b[0-9a-f]{7,}\b")
SMALL = {"scalar", "container", "list", "tuple", "dict", "set", "other"}


def main():
    C = R.patch_union_store(R.REPLAY_STORE, R.SHARED_STORE)
    root = os.path.join(R.WORK, "compare", "self")
    out = {"item": "D1", "by_engine": {}, "examples": {}}
    percell = []
    for eng in sorted(os.listdir(root)):
        cnt = collections.Counter()
        cells = collections.Counter()
        for n in sorted(os.listdir(os.path.join(root, eng))):
            if not n.endswith(".json") or n.startswith("."):
                continue
            res = R.read_json(os.path.join(root, eng, n))
            if res is None:
                continue
            ref = R.read_json(os.path.join(R.PROJ, res["meta"]["ref_record"]))      # original engine run
            rep = R.read_json(os.path.join(R.PROJ, res["meta"]["eng_record"]))      # replay
            rc = {c["i"]: c for c in ref.get("cells", [])}
            ec = {c["i"]: c for c in rep.get("cells", [])}
            for c in res["cells"]:
                if c["cls"] in ("E0", "NOOUT", "REF_ERR", "NONDET"):
                    continue
                kinds = set()
                for name, o in (c.get("outputs") or {}).items():
                    if o.get("level") == "E0":
                        continue
                    a = ((rc.get(c["i"]) or {}).get("outputs") or {}).get(name)
                    b = ((ec.get(c["i"]) or {}).get("outputs") or {}).get(name)
                    if not isinstance(a, str) and not isinstance(b, str):
                        same = isinstance(a, dict) and isinstance(b, dict) and \
                            (a.get("kind"), str(a.get("error"))[:200]) == (b.get("kind"), str(b.get("error"))[:200])
                        k = "same_failure_both" if same else "different_failure_both"
                    elif not isinstance(a, str) or not isinstance(b, str):
                        k = "uncapturable_in_" + ("original" if not isinstance(a, str) else "replay")
                    else:
                        ra, rb = ref["objects"].get(a, {}), rep["objects"].get(b, {})
                        if ra.get("kind") in SMALL and rb.get("kind") in SMALL:
                            try:
                                ta = repr(C.decode_to_pandas(R.SHARED_STORE, ra))
                                tb = repr(C.decode_to_pandas(R.SHARED_STORE, rb))
                                k = "token_only" if TOKEN.sub("#", ta) == TOKEN.sub("#", tb) else "printed_other"
                                if k == "token_only" and eng not in out["examples"]:
                                    out["examples"][eng] = [res["meta"]["nb"], c["i"], name, ta[:160], tb[:160]]
                            except Exception as e:
                                k = "printed_other"
                        else:
                            k = "frame_like"
                    cnt[k] += 1
                    kinds.add(k)
                if kinds == {"same_failure_both"}:
                    cat = "same failure in both runs (not a difference)"
                elif kinds == {"token_only"}:
                    cat = "token-only printed difference"
                elif len(kinds - {"same_failure_both"}) > 1:
                    cat = "mixed"
                elif kinds:
                    cat = next(iter(kinds - {"same_failure_both"}))
                else:
                    cat = "no output detail"
                cells[cat] += 1
                percell.append([eng, res["meta"]["nb"], c["i"], c["cls"], cat])
        out["by_engine"][eng] = {"outputs": dict(cnt), "cells": dict(cells)}
        print(eng, "outputs", dict(cnt), "cells", dict(cells))
    out["cells"] = percell
    R.write_json(OUT, out)


if __name__ == "__main__":
    main()

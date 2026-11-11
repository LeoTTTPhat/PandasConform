#!/usr/bin/env python3
"""Oracle and integrity check of one campaign step (2026-10-02). Reads only; run with the shared venv:

    .venv/bin/python 06_pandas_conformance/scripts/check_campaign.py --campaign pilot --set pilot \\
        --engines ref,ref#2,modin,... [--ref2 ref#2] [--sample-blobs 300]

Checks (all counted in the output JSON, written to results/<campaign>/check__<tag>.json):
  records        every (engine, notebook) has a run record under the current harness and run config;
                 status counts (completed / nb_timeout / nb_crash / nb_killed / engine_setup_error)
  oracle         every non-reference record has a dfeq/classify output computed WITH ref#2 (when
                 --ref2 is given); no output-level comparator failure (compare_error); match_limit hits
  self-check     ref#2 compared as an engine: every cell must be E0/NOOUT/REF_ERR/NONDET (the oracle is
                 reflexive on deterministic cells); any other class is an oracle failure
  store          every column blob referenced by a stored column exists; a random sample of blobs
                 re-hashes to its content address
"""
import argparse
import collections
import glob
import json
import os
import random
import sys

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJ, "src"))
sys.path.insert(0, os.path.join(PROJ, "tests"))
from pconf import datasets, orchestrate, util  # noqa: E402
from pconf import capture as C  # noqa: E402


class A:
    pass


def verify_blob(store, h):
    import pyarrow as pa
    with pa.memory_map(C.blob_path(store, h), "r") as src:
        tbl = pa.ipc.open_file(src).read_all()
    meta = json.loads(tbl.schema.metadata[b"pconf"])
    arrays = {n: tbl.column(n).combine_chunks() for n in tbl.column_names if n != "_empty"}
    hx = {k: (v["h"] if isinstance(v, dict) and "h" in v else v) for k, v in meta["x"].items()}
    return C.column_hash(meta["enc"], meta["dtype"], hx, arrays) == h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--set", required=True)
    ap.add_argument("--engines", required=True)
    ap.add_argument("--ref", default="ref")
    ap.add_argument("--ref2", default=None)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--cell-timeout", type=float, default=600)
    ap.add_argument("--nb-timeout", type=float, default=3600)
    ap.add_argument("--sample-blobs", type=int, default=300)
    a = ap.parse_args()
    nbs = datasets.notebook_set(a.set)[a.offset:]
    if a.limit:
        nbs = nbs[:a.limit]
    cfg_args = A()
    cfg_args.cell_timeout, cfg_args.nb_timeout, cfg_args.no_input_capture, cfg_args.cpus = a.cell_timeout, a.nb_timeout, False, None
    cfg = orchestrate.run_cfg(cfg_args)
    engs = a.engines.split(",")
    out = {"campaign": a.campaign, "set": a.set, "notebooks": len(nbs), "engines": engs,
           "harness_tag": orchestrate.harness_tag(), "compare_tag": orchestrate.compare_tag(),
           "records": {}, "oracle": {}, "self_check": {}, "store": {}}
    cmp_root = os.path.join(orchestrate.raw_dir(a.campaign), "compare__" + orchestrate.compare_tag())
    referenced = set()
    problems = []
    for e in engs:
        st = collections.Counter()
        oc = collections.Counter()
        for nb in nbs:
            rp, fp, _ = orchestrate.find_record(a.campaign, e, nb, a.scale, cfg)
            if not rp:
                st["missing"] += 1
                problems.append("record_missing:%s:%s" % (e, nb))
                continue
            r = util.read_json(rp)
            st[r.get("status")] += 1
            for obj in (r.get("objects") or {}).values():
                for c in (obj.get("cols") or []) + (obj.get("idx") or []):
                    stack = [c]
                    while stack:
                        d = stack.pop()
                        if d.get("stored"):
                            referenced.add(d["h"])
                        sub = (d.get("x") or {}).get("cats")
                        if isinstance(sub, dict):
                            stack.append(sub)
            if e == a.ref:
                continue
            fpr = orchestrate.find_record(a.campaign, a.ref, nb, a.scale, cfg)[1]
            fpr2 = orchestrate.find_record(a.campaign, a.ref2, nb, a.scale, cfg) if a.ref2 else (None, None)
            tail = fpr2[1][:8] if (a.ref2 and fpr2[0]) else "noref2"
            cp = os.path.join(cmp_root, orchestrate.engine_tag(e), datasets.scale_tag(a.scale),
                              "%s__%s_%s_%s.json" % (util.nb_key(nb), fpr[:8], fp[:8], tail))
            res = util.read_json(cp)
            if res is None:
                oc["compare_missing"] += 1
                problems.append("compare_missing:%s:%s" % (e, nb))
                continue
            oc["compared"] += 1
            if a.ref2 and tail == "noref2":
                oc["without_ref2"] += 1
            for c in res["cells"]:
                oc["cells"] += 1
                for o in (c.get("outputs") or {}).values():
                    oc["outputs"] += 1
                    if str(o.get("reason", "")).startswith("compare_error"):
                        oc["compare_error"] += 1
                        problems.append("compare_error:%s:%s:cell%s" % (e, nb, c["i"]))
                    if o.get("match_limit"):
                        oc["match_limit"] += 1
                    if o.get("match"):
                        oc["match_" + o["match"]] += 1
                if e == a.ref2:
                    if c["cls"] not in ("E0", "NOOUT", "REF_ERR", "NONDET"):
                        oc["self_check_fail"] += 1
                        problems.append("self_check:%s:cell%s:%s" % (nb, c["i"], c["cls"]))
                    if c["cls"] == "NONDET":
                        oc["nondet_cells"] += 1
        out["records"][e] = dict(st)
        if e != a.ref:
            (out["self_check"] if e == a.ref2 else out["oracle"])[e] = dict(oc)
    missing_blobs = [h for h in referenced if not os.path.exists(C.blob_path(util.CAPTURES, h))]
    rng = random.Random(0)
    small = [h for h in sorted(referenced) if os.path.exists(C.blob_path(util.CAPTURES, h))
             and os.path.getsize(C.blob_path(util.CAPTURES, h)) < 50e6]
    sample = rng.sample(small, min(a.sample_blobs, len(small)))
    bad = [h for h in sample if not verify_blob(util.CAPTURES, h)]
    out["store"] = {"referenced_blobs": len(referenced), "missing": len(missing_blobs),
                    "sample_verified": len(sample), "sample_hash_mismatch": len(bad)}
    problems += ["blob_missing:%s" % h for h in missing_blobs[:20]] + ["blob_hash:%s" % h for h in bad]
    out["problems"] = problems[:200]
    out["n_problems"] = len(problems)
    tag = "%s_%s" % (a.set if not a.set.endswith(".json") else "custom", orchestrate.compare_tag())
    path = os.path.join(util.RESULTS, a.campaign, "check__%s.json" % tag)
    util.atomic_write_json(path, out, indent=1)
    print(json.dumps({k: out[k] for k in ("records", "oracle", "self_check", "store", "n_problems")}, indent=1))
    print("wrote", path)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())

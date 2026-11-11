#!/usr/bin/env python3
"""D2: apply each case's observation expressions to the DECODED captured values (envs/ref, read only):
the original conf_1x engine run, the original reference run, the pilot run for bodo_dw, and the D1 captured replay
where one exists. Writes d2_captured.json.
    env PYTHONPATH=06_pandas_conformance-ICDE/src 06_pandas_conformance-ICDE/envs/ref/bin/python \
        06_pandas_conformance-ICDE/icde27/analysis/r5_replay/d2_captured.py
"""
import builtins
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import r5common as R  # noqa: E402
import d2_cases as DC  # noqa: E402

sys.path.insert(0, R.SRC)
OUT = os.path.join(HERE, "d2_captured.json")
PILOT_RUNS = os.path.join(R.PROJ, "results", "pilot", "raw", "runs__hd1c421ecb5ee")


def observe(rec_path, cell, values):
    from pconf import capture as C
    rec = R.read_json(rec_path)
    if rec is None:
        return {"error": "no record"}
    cc = [c for c in rec.get("cells", []) if c["i"] == cell]
    if not cc:
        return {"error": "cell not in record (status %s)" % rec.get("status")}
    c = cc[0]
    outs = c.get("outputs") or {}
    res = {"cell_status": c.get("status")}
    for name, code in values.items():
        h = outs.get(name)
        if not isinstance(h, str) or h not in rec.get("objects", {}):
            res[name] = {"ok": False, "error": "not captured: %r" % (h,)}
            continue
        try:
            v = C.decode_to_pandas(R.SHARED_STORE, rec["objects"][h])
            res[name] = {"ok": True, "value": eval(code, {"v": v, "__builtins__": builtins})}
        except BaseException as e:
            res[name] = {"ok": False, "error": "%s: %s" % (type(e).__name__, str(e)[:200])}
    return res


def main():
    R.patch_union_store(R.REPLAY_STORE, R.SHARED_STORE)
    d1 = {}
    for tag in ("d1b", "d1c"):
        for r in (R.read_json(os.path.join(HERE, "d1_run_%s.json" % tag)) or {}).get("results", []):
            if r.get("record"):
                d1[(r["engine"], r["nb"])] = os.path.join(R.PROJ, r["record"])
    out = {"item": "D2", "cases": {}}
    for case in DC.CASES:
        nb, cell, vals = case["nb"], case["cell"], case["values"]
        e = {"ref_conf_1x": observe(R.original_record("ref", nb), cell, vals)}
        for cfg in case["configs"]:
            e["%s_conf_1x" % cfg] = observe(R.original_record(cfg, nb), cell, vals)
            if cfg == "bodo_dw":
                e["bodo_dw_pilot"] = observe(R.original_record("bodo_dw", nb, PILOT_RUNS), cell, vals)
            if (cfg, nb) in d1:
                e["%s_d1_replay" % cfg] = observe(d1[(cfg, nb)], cell, vals)
        out["cases"][case["id"]] = e
        print(case["id"], {k: {n: (o.get("value") if isinstance(o, dict) and o.get("ok") else (o.get("error") if isinstance(o, dict) else o))
                                for n, o in v.items() if n != "cell_status"} for k, v in e.items()})
    R.write_json(OUT, out)
    print("wrote", OUT)


if __name__ == "__main__":
    main()

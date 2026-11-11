#!/usr/bin/env python3
"""D2 analysis: classify each case from d2_raw.json (uncaptured replays) and d2_captured.json (the same observations
on the decoded captured values), with the rules pre-declared in RESULTS.md. Stdlib only. Writes d2_results.json.
    python3 d2_analyze.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import r5common as R  # noqa: E402
import d2_cases as DC  # noqa: E402

OUT = os.path.join(HERE, "d2_results.json")


def obs_of(run, case_id):
    """-> (ok, {name: value} or error string, warnings)"""
    if run is None:
        return False, "no run", []
    if run["status"] != "ok":
        tgt = [e for e in run["events"] if e.get("event") == "target" and e.get("case") == case_id]
        if not tgt:
            return False, "run %s; events %s" % (run["status"], [e.get("event") for e in run["events"]][-4:]), []
    tgt = [e for e in run["events"] if e.get("event") == "target" and e.get("case") == case_id]
    if not tgt:
        fatal = [e for e in run["events"] if e.get("event") in ("fatal", "cell_error")]
        return False, "target not reached: %s" % (json.dumps(fatal)[:300] if fatal else "no event"), []
    t = tgt[0]
    if t["status"] != "ok":
        return False, "target cell %s: %s" % (t["status"], t.get("error")), t.get("warnings", [])
    vals, errs = {}, []
    for n, o in t["observations"].items():
        if o.get("ok"):
            vals[n] = o["value"]
        else:
            errs.append("%s: %s" % (n, o.get("error")))
    if errs:
        return False, "; ".join(errs), t.get("warnings", [])
    return True, vals, t.get("warnings", [])


def cap_vals(entry):
    if not entry or "error" in entry:
        return None
    out = {}
    for n, o in entry.items():
        if n == "cell_status":
            continue
        if not o.get("ok"):
            return None
        out[n] = o["value"]
    return out


def main():
    raw = R.read_json(os.path.join(HERE, "d2_raw.json"))
    cap = R.read_json(os.path.join(HERE, "d2_captured.json"))
    runs = {}
    for r in raw["results"]:
        runs[(r["config"], r["nb"], r["rep"])] = r
    rerun = R.read_json(os.path.join(HERE, "d2_raw_rerun.json"))
    rerun_keys = set()
    if rerun:   # infrastructure rerun (observation globals lacked __name__): its runs replace the failed ones
        for r in rerun["results"]:
            runs[(r["config"], r["nb"], r["rep"])] = r
            rerun_keys.add((r["config"], r["nb"]))
    res = {"item": "D2", "cases": []}
    for case in DC.CASES:
        cid, nb = case["id"], case["nb"]
        c = cap["cases"][cid]
        ok_pd, u_pd, w_pd = obs_of(runs.get(("pandas", nb, 1)), cid)
        c_ref = cap_vals(c.get("ref_conf_1x"))
        entry = {"id": cid, "group": case["group"], "nb": nb, "cell": case["cell"], "claim": case["claim"],
                 "pandas_uncaptured": u_pd if ok_pd else None, "pandas_uncaptured_error": None if ok_pd else u_pd,
                 "pandas_warnings": w_pd, "ref_captured": c_ref,
                 "baseline_matches_capture": ok_pd and c_ref is not None and u_pd == c_ref, "configs": {}}
        for cfg in case["configs"]:
            reps = []
            for k in range(1, DC.REPS + 1):
                ok, v, w = obs_of(runs.get((cfg, nb, k)), cid)
                reps.append({"rep": k, "ok": ok, "value": v if ok else None, "error": None if ok else v, "warnings": w})
            c_eng = cap_vals(c.get("%s_conf_1x" % cfg))
            c_d1 = cap_vals(c.get("%s_d1_replay" % cfg))
            c_pilot = cap_vals(c.get("%s_pilot" % cfg))
            if not entry["baseline_matches_capture"]:
                verdict = "inconclusive (uncaptured pandas value differs from the captured reference or failed)"
            elif not all(r["ok"] for r in reps):
                verdict = "inconclusive (run or observation failed)"
            else:
                diffs = [r["value"] != u_pd for r in reps]
                cap_diff = c_eng is not None and c_eng != c_ref
                if all(diffs):
                    same = [r["value"] == c_eng for r in reps]
                    verdict = "confirmed engine behaviour" + ("" if all(same) else " (uncaptured value differs from the captured one in %d of %d runs)" % (len(same) - sum(same), len(same)))
                elif not any(diffs):
                    if not cap_diff:
                        verdict = "no difference (captured run agrees with pandas too)"
                    elif c_d1 is not None and c_d1 != c_ref:
                        verdict = "capture or conversion artifact"
                    elif c_d1 is not None:
                        verdict = "not reproduced (the D1 captured replay agrees with pandas too)"
                    else:
                        verdict = "not reproduced"
                else:
                    verdict = "not reproduced (nondeterministic: %d of %d runs differ)" % (sum(diffs), len(diffs))
            entry["configs"][cfg] = {"rerun": (cfg, nb) in rerun_keys, "uncaptured": reps, "captured_conf_1x": c_eng, "captured_pilot": c_pilot,
                                     "captured_d1_replay": c_d1, "verdict": verdict}
        res["cases"].append(entry)
    R.write_json(OUT, res)
    for e in res["cases"]:
        for cfg, v in e["configs"].items():
            print("%-28s %-8s %-60s pandas=%s eng=%s cap=%s d1=%s" % (e["id"], cfg, v["verdict"][:60],
                  json.dumps(e["pandas_uncaptured"])[:60], json.dumps([r["value"] for r in v["uncaptured"]])[:90],
                  json.dumps(v["captured_conf_1x"])[:50], json.dumps(v["captured_d1_replay"])[:40]))


if __name__ == "__main__":
    main()

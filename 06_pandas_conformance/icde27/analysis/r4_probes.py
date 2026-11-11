#!/usr/bin/env python3
"""Run icde27/analysis/r4_probe_cases.py in envs/ref and the engine environments and judge each single-rater
behaviour as reproduced or not reproduced outside the capture harness (review round R4, 2026-11-10).

Run ONLY under the memory guard (Modin starts Ray workers, Bodo an MPI worker):
    cd .. && python3 tools/memory_guard.py --start-if-fits --wait-lock 3600 \
        --limit-gb 24 --state runs/06_pandas_conformance_icde27_r4_probes.json -- \
        .venv/bin/python 06_pandas_conformance-ICDE/icde27/analysis/r4_probes.py
Each environment runs the probe twice (REPS), in its own process group with a timeout; leftover workers are killed
with the group. Writes icde27/analysis/r4_probes.json (and the raw output to r4_probes.log); the probe inputs are
synthetic, so the outputs hold no notebook data.

Judgement per behaviour, on the engine named in the single-rater attribution:
  reproduced      the engine's line differs from pandas' in every repetition in the way the rater described (for a
                  stale-data check: equal to an "_if_stale" line, that is, the data from before the update);
  other difference  the engine differs from pandas, but not in the described way (reported as such);
  not reproduced  the engine's line equals pandas' in every repetition;
  inconclusive    the check raised, or the repetitions disagree.
"""
import json
import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
CASES = os.path.join(HERE, "r4_probe_cases.py")
OUT = os.path.join(HERE, "r4_probes.json")
LOG = os.path.join(HERE, "r4_probes.log")
REPS = 2
TIMEOUT_S = 600
ENVS = {
    "pandas": ("ref", {}),
    "modin": ("modin", {"RAY_ENABLE_MAC_LARGE_OBJECT_STORE": "1", "RAY_USAGE_STATS_ENABLED": "0"}),
    "fireducks": ("fireducks", {"FIREDUCKS_FLAGS": "-Wfallback"}),
    # one MPI worker as in the conformance runs; Open MPI's TCP transport is restricted to the loopback interface
    "bodo": ("bodo", {"BODO_NUM_WORKERS": "1", "OMPI_MCA_btl_tcp_if_include": "lo0"}),
}
# behaviour -> (engine of the attribution, checks, kind, the paper's description)
BEHAVIOURS = {
    "apply_side_effects_lost": ("modin", ["apply_extend_global_list", "apply_mutate_list_element"], "smaller",
                                "a function passed to apply extends or mutates a driver-side list"),
    "stale_after_inplace_update_bodo": ("bodo", ["stale_map_head", "stale_multiply_head", "stale_assign_head"], "stale",
                                        "head() after a column update shows the data from before the update"),
    "stale_after_inplace_update_fireducks": ("fireducks", ["stale_at_groupby", "stale_at_groupby_unstack", "stale_at_filter"],
                                             "stale", "group-by and filter after two .at assignments use the data from before them"),
    "positions_instead_of_labels": ("bodo", ["filter_index_drop"], "differs",
                                    "a Boolean filter's index holds positions, so drop() removes other rows"),
    "unique_nunique_missing": ("fireducks", ["unique_with_missing", "nunique_column", "nunique_loop_over_columns",
                                             "nunique_select_dtypes_apply"], "differs",
                               "unique() and nunique() treat missing values differently"),
}


def run(label, env_name, extra, rep):
    py = os.path.join(PROJ, "envs", env_name, "bin", "python")
    env = dict(os.environ, PCONF_REPRO_MODE=label, PYTHONHASHSEED="0", **extra)
    t0 = time.time()
    p = subprocess.Popen([py, "-I", CASES], cwd=HERE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, errors="replace", start_new_session=True)
    try:
        out, _ = p.communicate(timeout=TIMEOUT_S)
        status = "ok" if p.returncode == 0 else "error rc=%s" % p.returncode
    except subprocess.TimeoutExpired:
        status = "timeout"
        os.killpg(p.pid, signal.SIGTERM)
        out, _ = p.communicate()
    try:
        os.killpg(p.pid, signal.SIGKILL)   # leftover Ray or MPI workers of this probe
    except (ProcessLookupError, PermissionError):
        pass
    lines = {}
    for line in (out or "").splitlines():
        if line.startswith("RESULT ") and ": " in line:
            k, v = line[len("RESULT "):].split(": ", 1)
            lines[k] = v
    with open(LOG, "a") as f:
        f.write("===== %s rep %d %s %.1fs %s\n%s\n" % (label, rep, time.strftime("%Y-%m-%d %H:%M:%S"), time.time() - t0,
                                                      status, out))
    return {"status": status, "seconds": round(time.time() - t0, 1), "lines": lines}


def main():
    if os.path.exists(LOG):
        os.remove(LOG)
    runs = {label: [run(label, e, extra, r + 1) for r in range(REPS)] for label, (e, extra) in ENVS.items()}
    ref = runs["pandas"][0]["lines"]
    assert all(r["lines"] == ref for r in runs["pandas"]), "pandas repetitions disagree"
    checks = {}
    for name, ref_val in ref.items():
        if name == "env" or "_if_stale" in name:
            continue
        stale = [v for k, v in sorted(ref.items()) if k == name + "_if_stale" or k.startswith(name + "_if_stale_")]
        row = {"pandas": ref_val, "if_stale": stale}
        for label in ENVS:
            if label == "pandas":
                continue
            vals = [r["lines"].get(name, "missing (probe stopped)") for r in runs[label]]
            same = all(v == vals[0] for v in vals)
            row[label] = {"value": vals[0], "repetitions_agree": same, "equals_pandas": same and vals[0] == ref_val,
                          "raised": any(v.startswith("raised") or v.startswith("missing") for v in vals),
                          "equals_if_stale": same and vals[0] in row["if_stale"]}
        checks[name] = row
    verdicts = {}
    for b, (eng, names, kind, desc) in BEHAVIOURS.items():
        per = {}
        for n in names:
            c = checks[n][eng]
            if c["raised"] or not c["repetitions_agree"]:
                v = "inconclusive"
            elif c["equals_pandas"]:
                v = "not reproduced"
            elif kind == "stale":
                v = "reproduced" if c["equals_if_stale"] else "other difference"
            elif kind == "smaller":
                try:
                    v = "reproduced" if int(c["value"]) < int(checks[n]["pandas"]) else "other difference"
                except ValueError:
                    v = "other difference"
            else:
                v = "reproduced"
            per[n] = v
        overall = "reproduced" if any(v == "reproduced" for v in per.values()) else (
            "other difference" if any(v == "other difference" for v in per.values()) else (
                "not reproduced" if all(v == "not reproduced" for v in per.values()) else "inconclusive"))
        verdicts[b] = {"engine": eng, "description": desc, "checks": per, "verdict": overall,
                       "reproduced_checks": sum(v == "reproduced" for v in per.values()), "n_checks": len(per),
                       "other_engines_differ": sorted({lab for n in names for lab in ENVS if lab not in ("pandas", eng)
                                                       and not checks[n][lab]["equals_pandas"]})}
    out = {"script": "icde27/analysis/r4_probes.py", "cases": "icde27/analysis/r4_probe_cases.py",
           "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "repetitions": REPS,
           "environments": {lab: {"env": e, "settings": extra, "runs": [{k: v for k, v in r.items() if k != "lines"}
                                                                          for r in runs[lab]],
                                  "env_line": runs[lab][0]["lines"].get("env")} for lab, (e, extra) in ENVS.items()},
           "checks": checks, "verdicts": verdicts,
           "summary": {"behaviours": len(verdicts),
                       "reproduced": sorted(b for b, v in verdicts.items() if v["verdict"] == "reproduced"),
                       "not_reproduced": sorted(b for b, v in verdicts.items() if v["verdict"] == "not reproduced"),
                       "other": sorted(b for b, v in verdicts.items() if v["verdict"] not in ("reproduced", "not reproduced"))}}
    with open(OUT + ".tmp", "w") as f:
        json.dump(out, f, indent=1)
    os.replace(OUT + ".tmp", OUT)
    for b, v in verdicts.items():
        print("%-40s %-10s %-16s %s  others differ: %s" % (b, v["engine"], v["verdict"], v["checks"], v["other_engines_differ"]))
    for n, row in checks.items():
        print("  %-28s pandas %s" % (n, row["pandas"][:90]))
        for lab in ENVS:
            if lab != "pandas":
                print("      %-10s %s %s" % (lab, "==" if row[lab]["equals_pandas"] else "!=", row[lab]["value"][:110]))


if __name__ == "__main__":
    sys.exit(main())

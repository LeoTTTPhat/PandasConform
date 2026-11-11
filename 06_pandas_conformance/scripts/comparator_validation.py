"""Re-run the comparator-vs-oracle differential validation on the CURRENT comparator sources
(the compare tag used for every reported result) and record the outcome as a result file.

Written 2026-10-04 (audit fix A15/A16): the earlier oracle trial counts lived only in plan.md.
This script reruns work/fix_20261002/diff_validate.py (unchanged) for fixed seeds, in parallel,
and writes results/rootcause/comparator_validation.json. It reads src/ but never writes it.

Usage (from 06_pandas_conformance/):  ../.venv/bin/python scripts/comparator_validation.py
Cost on 2026-10-04: about 1-2 minutes wall, < 200 MB RSS per worker (8 workers).
"""
import json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
from pconf import util  # noqa: E402

SCRIPT = "work/fix_20261002/diff_validate.py"
TRIALS, NMAX = 1250, 40
# (python, seed, env overrides): pandas 2.3.3 (ref env) with every large-table shortcut forced,
# pandas 3.0.6 (shared venv) with default settings.
FORCED = {"PCONF_LARGE_ROWS": "0", "PCONF_HASH_SORT_ROWS": "0"}
JOBS = [("envs/ref/bin/python", s, FORCED) for s in (1101, 1102, 1103, 1104)] + \
       [(os.path.join("..", ".venv", "bin", "python"), s, {}) for s in (1201, 1202, 1203, 1204)]
LINE = re.compile(r"^pandas (\S+) seed (\d+) trials (\d+) nmax (\d+) oracle (\{.*?\}) match (\{.*?\}) MISMATCHES (\d+)")


def run(job):
    py, seed, extra = job
    env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", **extra)
    t0 = time.time()
    p = subprocess.run([py, SCRIPT, str(seed), str(TRIALS), str(NMAX)], cwd=HERE, env=env,
                       capture_output=True, text=True)
    out = p.stdout.strip().splitlines()
    m = LINE.match(out[0]) if out else None
    rec = {"python": py, "seed": seed, "env": extra, "rc": p.returncode, "wall_s": round(time.time() - t0, 1)}
    if m:
        import ast
        rec.update(pandas=m.group(1), trials=int(m.group(3)), nmax=int(m.group(4)),
                   oracle_levels=ast.literal_eval(m.group(5)), match=ast.literal_eval(m.group(6)),
                   mismatches=int(m.group(7)), mismatch_lines=out[1:20])
    else:
        rec.update(error=(p.stdout + p.stderr)[-2000:])
    return rec


def main():
    with ThreadPoolExecutor(8) as ex:
        runs = list(ex.map(run, JOBS))
    ok = [r for r in runs if "trials" in r and r["rc"] == 0]
    levels = {}
    for r in ok:
        for k, v in r["oracle_levels"].items():
            levels[k] = levels.get(k, 0) + v
    res = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "script": "scripts/comparator_validation.py",
           "driver": SCRIPT, "compare_sha12": util.compare_sha()[:12], "compare_tag": "d" + util.compare_sha()[:12], "harness_sha12": util.harness_sha()[:12],
           "trials_total": sum(r["trials"] for r in ok), "mismatches_total": sum(r["mismatches"] for r in ok),
           "runs_ok": len(ok), "runs_total": len(runs), "oracle_levels_total": levels,
           "by_pandas": {v: sum(r["trials"] for r in ok if r["pandas"] == v) for v in sorted({r["pandas"] for r in ok})},
           "runs": runs}
    out = os.path.join(HERE, "results", "rootcause", "comparator_validation.json")
    with open(out + ".tmp", "w") as f:
        json.dump(res, f, indent=1, sort_keys=True)
    os.replace(out + ".tmp", out)
    print(json.dumps({k: res[k] for k in ("compare_sha12", "trials_total", "mismatches_total", "runs_ok",
                                          "runs_total", "by_pandas", "oracle_levels_total")}))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Write results/<campaign>/environment.json: host, Python and package versions of every engine
environment (envs.lock.json) and of the shared parent venv, sha256 of every source file, the
harness/compare tags, engine specifications, the run configurations found in the campaign's
records, the guard settings and the data provenance. Run with the shared venv after a campaign
step (it only reads files):

    .venv/bin/python 06_pandas_conformance/scripts/write_environment.py --campaign pilot
"""
import argparse
import glob
import hashlib
import json
import os
import platform
import subprocess
import sys
import time

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJ, "src"))
from pconf import engines, orchestrate, util  # noqa: E402


def sh(cmd):
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", required=True)
    a = ap.parse_args()
    root = os.path.join(util.RESULTS, a.campaign)
    src = {}
    for p in sorted(glob.glob(os.path.join(PROJ, "src", "pconf", "*.py")) + glob.glob(os.path.join(PROJ, "scripts", "*"))):
        if os.path.isfile(p):
            src[os.path.relpath(p, PROJ)] = util.sha256_file(p)
    cfgs, harness, n_records, statuses = {}, set(), 0, {}
    for p in glob.glob(os.path.join(root, "raw", "*__h*", "*", "*", "*.json")) + \
            glob.glob(os.path.join(root, "*__h*", "*", "*", "*.json")):
        if "/compare__" in p:
            continue
        r = util.read_json(p) or {}
        if "fingerprint" not in r:
            continue
        n_records += 1
        cfgs[util.canon_json(r.get("cfg"))] = r.get("cfg")
        harness.add(r.get("harness_sha"))
        statuses[r.get("status")] = statuses.get(r.get("status"), 0) + 1
    import numpy, pandas
    try:
        import pyarrow
        pav = pyarrow.__version__
    except Exception:
        pav = None
    prov = util.read_json(os.path.join(util.DATA, "provenance.json"), {}) or {}
    env = {
        "written": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "campaign": a.campaign,
        "host": {"platform": platform.platform(), "machine": platform.machine(),
                 "cpu_brand": sh(["sysctl", "-n", "machdep.cpu.brand_string"]),
                 "ncpu": sh(["sysctl", "-n", "hw.ncpu"]), "perf_cores": sh(["sysctl", "-n", "hw.perflevel0.physicalcpu"]),
                 "eff_cores": sh(["sysctl", "-n", "hw.perflevel1.physicalcpu"]),
                 "mem_bytes": sh(["sysctl", "-n", "hw.memsize"]), "os": sh(["sw_vers", "-productVersion"])},
        "parent_venv": {"python": sys.version.split()[0], "executable": sys.executable, "pandas": pandas.__version__,
                        "numpy": numpy.__version__, "pyarrow": pav},
        "engine_envs": util.read_json(os.path.join(PROJ, "envs.lock.json"), {}),
        "engines": {k: {kk: vv for kk, vv in engines.engine_spec(k).items()} for k in engines.ENGINES},
        "harness_sha": util.harness_sha(), "compare_sha": util.compare_sha(),
        "harness_tag": orchestrate.harness_tag(), "compare_tag": orchestrate.compare_tag(),
        "harness_files": util.HARNESS_FILES, "compare_files": util.COMPARE_FILES,
        "source_sha256": src,
        "records": {"n": n_records, "statuses": statuses, "harness_shas": sorted(h for h in harness if h),
                    "run_configs": list(cfgs.values())},
        "guard": {"tool": "tools/memory_guard.py", "limit_gb": 120, "wait_lock_s": 14400,
                  "note": "every run/compare invocation went through the guard (state files runs/06_pandas_conformance_*.json)"},
        "data": {"pandasbench_commit": (prov.get("code") or {}).get("commit"),
                 "archive_sha256": (prov.get("data_archive") or {}).get("sha256"),
                 "manifest_files": prov.get("data_manifest_files"), "manifest_bytes": prov.get("data_manifest_bytes")},
        "dfeq": {"float_rtol": 1e-9, "max_exact_int": 2 ** 53, "match_limit": 2000, "match_budget": 20_000_000},
    }
    out = os.path.join(root, "environment.json")
    util.atomic_write_json(out, env, indent=1)
    print("wrote %s (%d records, statuses %s)" % (out, n_records, statuses))


if __name__ == "__main__":
    main()

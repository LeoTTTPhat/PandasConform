"""Pin every engine environment: python version, `uv pip freeze`, import smoke test.

Writes envs.lock.json: {env: {python, packages: [..], freeze_sha256, import_ok, versions}}.
The per-env freeze_sha256 is part of every result fingerprint (plan.md Section 12), so
changing an environment re-runs its notebooks into new records instead of mixing results.
"""
import argparse
import hashlib
import json
import os
import subprocess

PROBE = r"""
import json, sys, importlib
out = {"python": sys.version.split()[0]}
for m in ["pandas", "numpy", "pyarrow", "modin", "ray", "fireducks", "bodo", "dask", "psutil"]:
    try:
        mod = importlib.import_module(m)
        out[m] = getattr(mod, "__version__", "?")
    except Exception as e:
        out[m] = None
print(json.dumps(out))
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--envs", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    lock = {}
    for e in sorted(os.listdir(a.envs)):
        py = os.path.join(a.envs, e, "bin", "python")
        if not os.path.isfile(py):
            continue
        ok = os.path.exists(os.path.join(a.envs, e, ".pconf_ok"))
        fr = subprocess.run(["uv", "pip", "freeze", "--python", py], capture_output=True, text=True)
        pk = sorted(l for l in fr.stdout.splitlines() if l.strip())
        pr = subprocess.run([py, "-c", PROBE], capture_output=True, text=True, timeout=600)
        try:
            versions = json.loads(pr.stdout.strip().splitlines()[-1])
        except Exception:
            versions = {"probe_error": (pr.stderr or "")[-500:]}
        lock[e] = {
            "install_ok": ok,
            "python": versions.get("python"),
            "versions": versions,
            "packages": pk,
            "freeze_sha256": hashlib.sha256("\n".join(pk).encode()).hexdigest(),
        }
    tmp = a.out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(lock, f, indent=1, sort_keys=True)
    os.replace(tmp, a.out)
    req = os.path.join(os.path.dirname(a.out), "requirements")
    os.makedirs(req, exist_ok=True)
    for e, v in lock.items():
        with open(os.path.join(req, "%s.txt" % e), "w") as f:
            f.write("# exact freeze of envs/%s (python %s), generated from envs.lock.json\n" % (e, v["python"]))
            f.write("\n".join(v["packages"]) + "\n")
    for e, v in lock.items():
        print("[lock] %-10s ok=%s %s" % (e, v["install_ok"], {k: x for k, x in v["versions"].items() if x}))


if __name__ == "__main__":
    main()

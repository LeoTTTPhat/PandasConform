import json
import os
import shutil
import subprocess
import sys
import tempfile

TESTS = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(TESTS)
SRC = os.path.join(PROJ, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
ENVS = os.path.join(PROJ, "envs")
SHARED_PY = sys.executable
ALL_ENVS = ["ref", "p15", "p30", "modin", "fireducks", "bodo", "dask"]


def env_python(env):
    p = os.path.join(ENVS, env, "bin", "python")
    return p if os.path.exists(p) and os.path.exists(os.path.join(ENVS, env, ".pconf_ok")) else None


class TempStore:
    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="pconf_test_")

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def isolated_env(root):
    """Environment for subprocess runs with results/work/captures under `root`."""
    env = dict(os.environ)
    env["PCONF_RESULTS"] = os.path.join(root, "results")
    env["PCONF_WORK"] = os.path.join(root, "work")
    env["PCONF_CAPTURES"] = os.path.join(root, "captures")
    env["PYTHONPATH"] = SRC
    return env


def write_probe_notebook(work_root, pid, cells):
    """Fixture notebook in probe layout: work/probes/nb/<pid>/old.ipynb (cell 0 = setup cell)."""
    d = os.path.join(work_root, "probes", "nb", pid)
    os.makedirs(d, exist_ok=True)
    nb = {"nbformat": 4, "nbformat_minor": 5, "metadata": {},
          "cells": [{"cell_type": "code", "metadata": {}, "source": c, "outputs": [], "execution_count": None}
                    for c in cells]}
    with open(os.path.join(d, "old.ipynb"), "w") as f:
        json.dump(nb, f)
    return "probe:" + pid


def write_set(root, name, nbs):
    p = os.path.join(root, name + ".json")
    with open(p, "w") as f:
        json.dump({"notebooks": nbs}, f)
    return p


def run_orch(root, args, timeout=600, popen=False):
    cmd = [SHARED_PY, "-m", "pconf.orchestrate"] + args
    if popen:
        return subprocess.Popen(cmd, env=isolated_env(root), cwd=PROJ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, start_new_session=True)
    return subprocess.run(cmd, env=isolated_env(root), cwd=PROJ, capture_output=True, text=True, timeout=timeout)

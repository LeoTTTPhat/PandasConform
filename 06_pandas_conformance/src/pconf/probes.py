"""Targeted micro-probes (plan.md Section 4: ~200 probes generated from the root causes found,
not random snippets). Each probe is a tiny synthetic notebook run through the SAME harness
(runner_child -> capture -> dfeq -> classify), so probe outcomes are directly comparable.

Probe files: probes/*.json  {"probes": [{"id", "family", "source", "documented", "setup", "code"}]}
  setup  builds the inputs from literal data with `pd`/`np` (engine-agnostic)
  code   the operation under test (its assigned names and last expression are compared)
  source 'seed:<reason>' for hand-written seeds, 'rootcause:<id>' for probes emitted by rootcause.py

    python -m pconf.probes build                # writes work/probes/nb/<id>/old.ipynb + data/notebook_sets/probes.json
    python -m pconf.orchestrate run --campaign probes --set probes --engines ref,modin,...
"""
import argparse
import glob
import json
import os

from pconf import util

PROBE_DIR = os.path.join(util.PROJ, "probes")


def load_probes(pattern=None):
    out = []
    files = sorted(glob.glob(pattern)) if pattern else sorted(glob.glob(os.path.join(PROBE_DIR, "*.json")) +
                                                              glob.glob(os.path.join(PROBE_DIR, "rootcause", "*.json")))
    for p in files:
        with open(p) as f:
            for pr in json.load(f)["probes"]:
                pr = dict(pr)
                pr["file"] = os.path.relpath(p, util.PROJ)
                out.append(pr)
    ids = [p["id"] for p in out]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ValueError("duplicate probe ids: %s" % sorted(dup))
    return out


def probe_notebook(pr):
    cells = [
        "import os\n# probe %s (%s)\n" % (pr["id"], pr.get("source", "")),
        "exec(os.environ['IREWR_IMPORTS'])\nimport numpy as np\n",
        pr["setup"],
        pr["code"],
    ]
    return {"nbformat": 4, "nbformat_minor": 5, "metadata": {"pconf_probe": {k: v for k, v in pr.items() if k != "file"}},
            "cells": [{"cell_type": "code", "metadata": {}, "source": c, "outputs": [], "execution_count": None}
                      for c in cells]}


def build(pattern=None, set_name="probes", set_path=None):
    probes = load_probes(pattern)
    names = []
    for pr in probes:
        d = os.path.join(util.WORK, "probes", "nb", pr["id"])
        os.makedirs(d, exist_ok=True)
        util.atomic_write_json(os.path.join(d, "old.ipynb"), probe_notebook(pr), indent=1)
        names.append("probe:" + pr["id"])
    util.atomic_write_json(set_path or os.path.join(util.DATA, "notebook_sets", set_name + ".json"),
                           {"notebooks": names, "rule": "probes from %s" % (pattern or "probes/*.json")}, indent=1)
    return names


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--pattern", default=None)
    b.add_argument("--set", default="probes")
    b.add_argument("--set-path", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "build":
        names = build(a.pattern, a.set, a.set_path)
        print("built %d probe notebooks" % len(names))


if __name__ == "__main__":
    main()

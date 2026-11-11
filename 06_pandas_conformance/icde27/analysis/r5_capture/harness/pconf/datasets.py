"""Notebook catalogue and scaled-input preparation.

PandasBench layout (data/PandasBench at the pinned commit + data/raw/PandasBench_data):
    notebooks/<user>/<slug>/{updated,old}.ipynb       cell 0 scales ./input/X.csv -> ./input/X.scaled.csv
    PandasBench_data/<user>/<slug>/input/...           original Kaggle inputs
Prepared inputs live in work/scaled/sf<scale>/<user>/<slug>/input/: raw files are hard links (no
copy) and the `.scaled.*` files are produced by executing the notebook's own cell 0 in the `ref`
environment with INPUT_SCALE_FACTOR=<scale> (PandasBench's scaling mechanism). For scale 1.0
cell 0 would copy each file; we substitute a hard link (identical bytes, no disk cost).
A marker JSON with a fingerprint makes preparation idempotent.

    <envs/ref/bin/python> -m pconf.datasets prep --nb user/slug --scale 1.0
"""
import argparse
import json
import os
import shutil
import sys
import time

from pconf import nbsource, util

PB_REPO = os.path.join(util.DATA, "PandasBench")
PB_DATA = os.path.join(util.DATA, "raw", "PandasBench_data")
SCALED = util.PROJECT_SCALED   # R5 B1 copy: the prepared inputs of the original campaigns, read only
SETS = os.path.join(util.DATA, "notebook_sets")


def all_notebooks():
    with open(os.path.join(PB_REPO, "runner", "scales", "nbs_to_run_default.json")) as f:
        return [e["nb"] for e in json.load(f)["notebooks"]]


def notebook_file(nb):
    if nb.startswith("probe:"):
        return os.path.join(util.WORK, "probes", "nb", nb.split(":", 1)[1], "old.ipynb")
    return nbsource.notebook_path(os.path.join(PB_REPO, "notebooks", nb))


def raw_input_dir(nb):
    return os.path.join(PB_DATA, nb, "input")


def input_bytes(nb):
    tot = 0
    for dp, _, fn in os.walk(raw_input_dir(nb)):
        for n in fn:
            tot += os.path.getsize(os.path.join(dp, n))
    return tot


def scale_tag(scale):
    return ("sf%g" % float(scale)).replace(".", "p")


def scaled_dir(nb, scale):
    if nb.startswith("probe:"):
        return os.path.join(util.WORK, "probes", "nb", nb.split(":", 1)[1])
    return os.path.join(SCALED, scale_tag(scale), nb)


def _raw_manifest(nb):
    out = []
    root = raw_input_dir(nb)
    for dp, dn, fn in os.walk(root):
        dn.sort()
        for n in sorted(fn):
            p = os.path.join(dp, n)
            out.append([os.path.relpath(p, root), os.path.getsize(p)])
    return out


PREP_VERSION = 3   # v2 (2026-10-02): per-file sha256 in markers; v3: scaling cell from old.ipynb when needed


def scale_cell(nb):
    """PandasBench's input-scaling cell -> (source, origin).

    PandasBench runs cell 0 of the run notebook (updated.ipynb, else old.ipynb) untimed as the
    scaling slot. In 68 of the 102 benchmark notebooks that cell is the scaling cell. In the other
    34, updated.ipynb starts with ordinary notebook code (imports, sometimes reads, three with a
    direct `import pandas as pd`) and the scaling cell exists only as cell 0 of old.ipynb (found
    2026-10-02 in the pilot: prep raised KeyError 'IREWR_IMPORTS' and the inputs were missing).
    For those notebooks the scaling cell is taken from old.ipynb and the run notebook's cell 0 is
    executed as a normal, captured cell (setup_cells -> [])."""
    run_cells = nbsource.load_cells(notebook_file(nb))
    if run_cells and "INPUT_SCALE_FACTOR" in run_cells[0]:
        return run_cells[0], "run:0"
    if nb.startswith("probe:"):
        return "", "none"
    old = os.path.join(PB_REPO, "notebooks", nb, "old.ipynb")
    if os.path.exists(old):
        oc = nbsource.load_cells(old)
        if oc and "INPUT_SCALE_FACTOR" in oc[0]:
            return oc[0], "old:0"
    return "", "none"


def setup_cells(nb):
    """Cells the runner executes as untimed, uncaptured setup: cell 0 when it is the scaling cell
    (PandasBench semantics) or for probe notebooks (cell 0 = `import os`); none otherwise."""
    if nb.startswith("probe:"):
        return [0]
    return [0] if scale_cell(nb)[1] == "run:0" else []


def prep_fingerprint(nb, scale):
    src, origin = scale_cell(nb)
    return util.sha256_json({"nb": nb, "scale": float(scale), "cell0": src, "scale_cell_origin": origin,
                             "raw": _raw_manifest(nb), "v": PREP_VERSION})


_PROV = None


def _provenance_manifest():
    global _PROV
    if _PROV is None:
        _PROV = (util.read_json(os.path.join(util.DATA, "provenance.json"), {}) or {}).get("data_manifest", {})
    return _PROV


def _inputs_sha256(nb, tmp):
    """sha256 of every prepared input file. Hard links of raw files reuse the provenance
    manifest's sha256 (same inode and size); other files (scaled copies) are hashed."""
    prov = _provenance_manifest()
    raw_root = raw_input_dir(nb)
    raw_by_inode = {}
    for dp, _, fn in os.walk(raw_root):
        for n in fn:
            p = os.path.join(dp, n)
            st = os.stat(p)
            key = "%s/input/%s" % (nb, os.path.relpath(p, raw_root))
            if key in prov and prov[key].get("bytes") == st.st_size:
                raw_by_inode[(st.st_dev, st.st_ino)] = prov[key]["sha256"]
    out = {}
    for dp, _, fn in os.walk(os.path.join(tmp, "input")):
        for n in sorted(fn):
            p = os.path.join(dp, n)
            st = os.stat(p)
            sha = raw_by_inode.get((st.st_dev, st.st_ino))
            out[os.path.relpath(p, tmp)] = sha or util.sha256_file(p)
    return out


def input_fingerprint(nb, scale):
    """Content fingerprint of a notebook's prepared inputs (part of every run fingerprint)."""
    if nb.startswith("probe:"):
        return "probe"
    m = util.read_json(os.path.join(scaled_dir(nb, scale), ".pconf_prepared.json")) or {}
    shas = m.get("inputs_sha256")
    return util.sha256_json(shas) if shas is not None else None


def is_prepared(nb, scale):
    if nb.startswith("probe:"):
        return True
    m = util.read_json(os.path.join(scaled_dir(nb, scale), ".pconf_prepared.json"))
    return bool(m) and m.get("fingerprint") == prep_fingerprint(nb, scale) and m.get("status") == "ok"


def prep(nb, scale):
    """Create the scaled input directory by executing cell 0 (runs in the ref env)."""
    # R5 B1 copy: never (re)prepare inputs in the project's work/scaled; every re-executed notebook was prepared by
    # the original campaigns, and a missing or stale preparation stops the run instead.
    raise RuntimeError("R5 B1 harness copy does not prepare inputs (%s sf=%s not prepared)" % (nb, scale))
    scale = float(scale)
    dest = scaled_dir(nb, scale)
    marker = os.path.join(dest, ".pconf_prepared.json")
    fp = prep_fingerprint(nb, scale)
    m = util.read_json(marker)
    if m and m.get("fingerprint") == fp and m.get("status") == "ok":
        return m
    t0 = time.time()
    tmp = dest + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    src_root = raw_input_dir(nb)
    for dp, dn, fn in os.walk(src_root):
        rel = os.path.relpath(dp, src_root)
        os.makedirs(os.path.join(tmp, "input", rel), exist_ok=True)
        for n in fn:
            os.link(os.path.join(dp, n), os.path.join(tmp, "input", rel, n))
    scale_src, scale_origin = scale_cell(nb)
    status, err = "ok", None
    old_cwd = os.getcwd()
    old_copy = shutil.copyfile
    os.environ["INPUT_SCALE_FACTOR"] = repr(scale)
    try:
        os.chdir(tmp)
        if scale == 1.0:
            def _link_copy(a, b, *args, **kw):
                if os.path.exists(b):
                    os.unlink(b)
                os.link(os.path.realpath(a), b)
                return b
            shutil.copyfile = _link_copy
        if scale_origin == "none":
            raise RuntimeError("no PandasBench scaling cell found (updated.ipynb or old.ipynb cell 0)")
        ns = {"__name__": "__pconf_prep__"}
        exec(compile(scale_src, "<scale cell %s>" % scale_origin, "exec"), ns)
    except BaseException as e:
        status, err = "error", "%s: %s" % (type(e).__name__, str(e)[:500])
    finally:
        shutil.copyfile = old_copy
        os.chdir(old_cwd)
        os.environ.pop("INPUT_SCALE_FACTOR", None)
    produced = sorted(os.path.relpath(os.path.join(dp, n), tmp) for dp, _, fn in os.walk(tmp) for n in fn)
    rec = {"nb": nb, "scale": scale, "fingerprint": fp, "status": status, "error": err, "scale_cell_origin": scale_origin,
           "inputs_sha256": _inputs_sha256(nb, tmp) if status == "ok" else None,
           "files": produced, "seconds": round(time.time() - t0, 3),
           "scaled_bytes": sum(os.path.getsize(os.path.join(tmp, p)) for p in produced),
           "hardlinked_scale1": scale == 1.0}
    util.atomic_write_json(os.path.join(tmp, ".pconf_prepared.json"), rec)
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    os.replace(tmp, dest)
    return rec


def notebook_set(name):
    """Named notebook lists: data/notebook_sets/<name>.json, or 'all'."""
    if name == "all":
        return all_notebooks()
    p = name if name.endswith(".json") else os.path.join(SETS, name + ".json")
    with open(p) as f:
        return json.load(f)["notebooks"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prep")
    p.add_argument("--nb", action="append", required=True)
    p.add_argument("--scale", type=float, default=1.0)
    s = sub.add_parser("sizes")
    a = ap.parse_args(argv)
    if a.cmd == "prep":
        rc = 0
        for nb in a.nb:
            r = prep(nb, a.scale)
            print(json.dumps({k: r.get(k) for k in ("nb", "scale", "status", "error", "seconds", "scaled_bytes")}))
            sys.stdout.flush()
            rc |= r["status"] != "ok"
        sys.exit(rc)
    if a.cmd == "sizes":
        for nb in all_notebooks():
            print(input_bytes(nb), nb)


if __name__ == "__main__":
    main()

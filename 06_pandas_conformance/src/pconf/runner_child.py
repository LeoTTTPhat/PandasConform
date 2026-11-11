"""Child runner: executes ONE notebook cell by cell inside an engine environment.

    <envs/E/bin/python> -m pconf.runner_child --job job.json

Job keys: engine (spec dict from engines.py), nb, nb_file, cwd, store, out, progress,
cell_timeout, capture (bool), capture_inputs (bool), seed, skip_cells, limits, fingerprint.

In timing mode (capture off) the last expression value and every display() argument are
rendered with repr() inside the timed region, as a notebook front end would (fix of review
finding T1, 2026-10-02), so lazy engines are charged for displayed work like pandas is.

Per cell it records: status (ok|error|timeout|skipped|syntax_error), exception class/message,
wall time, RSS after the cell, warnings (deduplicated), fallback flags, static analysis
(loads/stores/mutates/attrs), and captured *inputs* (pre-cell values of the names the cell
reads) and *outputs* (names the cell binds or mutates, plus the last expression as
'__last__'), as object-record hashes into the run's object table. Progress is appended to a
JSONL file after every cell so a crash or kill still leaves per-cell evidence; the final record
is written atomically to `out`.
"""
import argparse
import builtins
import io
import json
import os
import random
import resource
import signal
import sys
import time
import traceback
import types
import warnings

from pconf import nbsource
from pconf.util import atomic_write_json

FALLBACK_PATTERNS = (
    ("modin_default_to_pandas", "defaulting to pandas"),
    ("bodo_fallback", "falling back to pandas"),
)
MISMATCH_PATTERNS = (("modin_documented_mismatch", "implementation has mismatches with pandas"),)


class CellTimeout(BaseException):
    """Raised by SIGALRM; BaseException so notebook `except Exception` cannot swallow it."""


def _on_alarm(signum, frame):
    raise CellTimeout()


class _BoundedIO(io.TextIOBase):
    def __init__(self, cap=4000):
        self.cap = cap
        self.buf = []
        self.size = 0
        self.total = 0

    def write(self, s):
        s = str(s)
        self.total += len(s)
        if self.size < self.cap:
            piece = s[: self.cap - self.size]
            self.buf.append(piece)
            self.size += len(piece)
        return len(s)

    def flush(self):
        pass

    def isatty(self):
        return False

    def text(self):
        return "".join(self.buf)


def _install_stubs(ns, materialize=False):
    """IPython display stubs (the corpus only uses `display`) and plotting no-ops.
    materialize=True (timing mode): display(x) renders repr(x) as a notebook front end would,
    so lazy engines pay for the work a displayed value needs (review finding T1)."""
    def display(*a, **k):
        if materialize:
            for x in a:
                repr(x)
        return None

    ipy = types.ModuleType("IPython")
    ipy_display = types.ModuleType("IPython.display")
    ipy_core = types.ModuleType("IPython.core")
    ipy_core_display = types.ModuleType("IPython.core.display")
    for m in (ipy_display, ipy_core_display):
        m.display = display
        m.Markdown = m.HTML = m.Image = lambda *a, **k: None
        m.set_matplotlib_formats = lambda *a, **k: None
    ipy.display = ipy_display
    ipy.core = ipy_core
    ipy_core.display = ipy_core_display
    ipy.get_ipython = lambda: None
    sys.modules.setdefault("IPython", ipy)
    sys.modules.setdefault("IPython.display", ipy_display)
    sys.modules.setdefault("IPython.core", ipy_core)
    sys.modules.setdefault("IPython.core.display", ipy_core_display)
    ns["display"] = display
    ns["get_ipython"] = lambda: None


def _patch_plotting():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.show = lambda *a, **k: None
        return True
    except Exception:
        return False


def _rss_bytes():
    try:
        import psutil
        p = psutil.Process()
        total = p.memory_info().rss
        for c in p.children(recursive=True):
            try:
                total += c.memory_info().rss
            except Exception:
                pass
        return total
    except Exception:
        return None


def _maxrss_bytes():
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r if sys.platform == "darwin" else r * 1024


def _flags_from_warnings(wlist):
    flags, out, seen = set(), [], set()
    for w in wlist:
        cat = w.category.__name__
        msg = str(w.message)
        low = msg.lower()
        if cat in ("FallbackWarning",) or cat.endswith("FallbackWarning"):
            flags.add("fireducks_fallback" if "Bodo" not in cat else "bodo_fallback")
        for flag, pat in FALLBACK_PATTERNS:
            if pat in low:
                flags.add(flag)
        for flag, pat in MISMATCH_PATTERNS:
            if pat in low:
                flags.add(flag)
        key = (cat, msg[:200])
        if key not in seen and len(out) < 20:
            seen.add(key)
            out.append({"category": cat, "message": msg[:300]})
    return sorted(flags), out, len(wlist)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    args = ap.parse_args(argv)
    with open(args.job) as f:
        job = json.load(f)
    run(job)


def run(job):
    t_start = time.time()
    eng = job["engine"]
    capture_on = job.get("capture", True)
    capture_inputs = job.get("capture_inputs", True) and capture_on
    cell_timeout = float(job.get("cell_timeout", 600))
    skip = set(job.get("skip_cells", [0]))
    delay = float(os.environ.get("MEMGUARD_DELAY_SECONDS", "0") or 0)
    record = {
        "fingerprint": job.get("fingerprint"), "engine": eng["name"], "nb": job["nb"],
        "scale": job.get("scale"), "mode": "capture" if capture_on else "timing",
        "python": sys.version.split()[0], "pid": os.getpid(), "started": t_start,
        "cells": [], "objects": {}, "status": "running",
    }
    progress = open(job["progress"], "a") if job.get("progress") else None

    def emit(cell_rec):
        if progress:
            progress.write(json.dumps({"cell": cell_rec, "objects": {h: record["objects"][h] for h in cell_rec.get("_new", [])}},
                                      default=str) + "\n")
            progress.flush()
        cell_rec.pop("_new", None)

    cells = nbsource.load_cells(job["nb_file"])
    record["n_cells"] = len(cells)

    # namespace + stubs + engine
    ns = {"__name__": "__main__", "__builtins__": builtins}
    _install_stubs(ns, materialize=not capture_on)
    if any(("matplotlib" in c or "seaborn" in c or "plt." in c) for c in cells):
        record["plotting_patched"] = _patch_plotting()
    os.chdir(job["cwd"])
    random.seed(job.get("seed", 0))
    t0 = time.time()
    setup_ns = {}
    try:
        exec(compile(eng["setup"], "<engine-setup>", "exec"), setup_ns)
        pd_module = setup_ns["pd"]
        record["engine_setup_s"] = round(time.time() - t0, 3)
    except BaseException as e:
        record["status"] = "engine_setup_error"
        record["error"] = "%s: %s" % (type(e).__name__, str(e)[:500])
        record["finished"] = time.time()
        atomic_write_json(job["out"], record)
        return
    try:
        import numpy as np
        np.random.seed(job.get("seed", 0))
        record["numpy"] = np.__version__
    except Exception:
        pass
    try:
        import pandas as _p
        record["pandas"] = _p.__version__
    except Exception:
        pass
    ns["__pconf_pd__"] = pd_module
    lazy_body = eng.get("evaluate_lazy", "return lazy")
    os.environ["IREWR_IMPORTS"] = "pd = __pconf_pd__\ndef evaluate_lazy(lazy):\n    %s\n" % lazy_body

    cap = None
    if capture_on:
        from pconf.capture import Capturer
        cap = Capturer(job["store"], job.get("limits"))

    def capture_names(names, record_absent=True):
        out, new = {}, []
        for n in names:
            if n not in ns:
                if record_absent and not n.startswith("__pconf"):
                    out[n] = "absent"
                continue
            if n.startswith("__pconf") or n in ("__builtins__",):
                continue
            rec = cap.capture(ns[n])
            h = rec.get("h")
            if h is None:
                out[n] = {"kind": rec["kind"], "type": rec.get("info", {}).get("type"),
                          "error": rec.get("info", {}).get("error")}
            else:
                if h not in record["objects"]:
                    record["objects"][h] = rec
                    new.append(h)
                out[n] = h
        return out, new

    old_handler = signal.signal(signal.SIGALRM, _on_alarm)
    peak_rss = 0
    for i, src in enumerate(cells):
        c = {"i": i, "status": "ok", "src_len": len(src)}
        if i in skip:
            # PandasBench's cell 0 (input scaling): executed with INPUT_SCALE_FACTOR unset, so it
            # only imports `os` and defines the scaling function (scaling is done by datasets.prep).
            os.environ.pop("INPUT_SCALE_FACTOR", None)
            c["status"] = "setup"
            try:
                exec(compile(src, "<cell %d>" % i, "exec"), ns)
            except BaseException as e:
                c.update(status="setup_error", exc_type=type(e).__name__, exc_msg=str(e)[:300])
            record["cells"].append(c)
            emit(c)
            continue
        if not src.strip():
            c["status"] = "empty"
            record["cells"].append(c)
            emit(c)
            continue
        try:
            tree, info = nbsource.prepare_cell(src)
        except SyntaxError as e:
            c.update(status="syntax_error", exc_type="SyntaxError", exc_msg=str(e)[:500])
            record["cells"].append(c)
            emit(c)
            continue
        an = nbsource.analyze(tree)
        c["static"] = {k: an[k] for k in ("loads", "stores", "mutates", "defs", "attrs", "last_expr",
                                          "fn_globals", "bound_loads")}
        if info["magics_replaced"] or info["pandas_imports_rewritten"]:
            c["rewrites"] = info
        new_objs = []
        present_before = {n for n in an["stores"] + an["mutates"] if n in ns}
        if capture_inputs:
            ti = time.time()
            c["inputs"], nn = capture_names(an["loads"], record_absent=False)
            new_objs += nn
            c["t_capture_in"] = round(time.time() - ti, 4)
        head, expr = nbsource.split_last_expr(tree)
        out_buf = _BoundedIO()
        old_out, old_err = sys.stdout, sys.stderr
        last_val, has_last = None, False
        with warnings.catch_warnings(record=True) as wl:
            warnings.simplefilter("always")
            sys.stdout, sys.stderr = out_buf, out_buf
            tc = time.perf_counter()
            try:
                signal.setitimer(signal.ITIMER_REAL, cell_timeout)
                if head is not None:
                    exec(compile(head, "<cell %d>" % i, "exec"), ns)
                if expr is not None:
                    last_val = eval(compile(expr, "<cell %d>" % i, "eval"), ns)
                    has_last = True
                    if not capture_on and last_val is not None:
                        # timing mode: the notebook front end displays the last value; render it
                        # inside the timed region for every engine alike (review finding T1)
                        repr(last_val)
                signal.setitimer(signal.ITIMER_REAL, 0)
            except CellTimeout:
                signal.setitimer(signal.ITIMER_REAL, 0)
                c.update(status="timeout", exc_type="CellTimeout", exc_msg="cell exceeded %.0fs" % cell_timeout)
            except BaseException as e:  # SystemExit, KeyboardInterrupt included: a cell result
                signal.setitimer(signal.ITIMER_REAL, 0)
                if isinstance(e, KeyboardInterrupt) and os.environ.get("PCONF_CHILD_INTERRUPT") == "1":
                    raise
                tb = traceback.extract_tb(e.__traceback__)
                frame = next((f for f in reversed(tb) if f.filename.startswith("<cell")), tb[-1] if tb else None)
                c.update(status="error", exc_type="%s.%s" % (type(e).__module__, type(e).__name__),
                         exc_msg=str(e)[:500],
                         exc_where=("%s:%s" % (frame.filename, frame.lineno)) if frame else None,
                         exc_origin=(tb[-1].filename.split("site-packages/")[-1] + ":%d" % tb[-1].lineno) if tb else None)
            finally:
                c["wall_s"] = round(time.perf_counter() - tc, 6)
                sys.stdout, sys.stderr = old_out, old_err
        c["flags"], c["warnings"], c["n_warnings"] = _flags_from_warnings(wl)
        if out_buf.total:
            c["stdout_chars"] = out_buf.total
            c["stdout_head"] = out_buf.text()[:1000]
        if capture_on and c["status"] in ("ok", "error", "timeout"):
            to = time.time()
            names = [n for n in an["stores"] + an["mutates"] if not n.startswith("__pconf")]
            c["outputs"], nn = capture_names(names)
            new_objs += nn
            for n in names:
                if n not in ns:
                    c["outputs"][n] = "deleted" if n in present_before else "absent"
            if has_last and c["status"] == "ok":
                lrec = cap.capture(last_val)
                if lrec.get("h") is None:
                    c["outputs"]["__last__"] = {"kind": lrec["kind"], "type": lrec.get("info", {}).get("type"),
                                                "error": lrec.get("info", {}).get("error")}
                else:
                    if lrec["h"] not in record["objects"]:
                        record["objects"][lrec["h"]] = lrec
                        new_objs.append(lrec["h"])
                    c["outputs"]["__last__"] = lrec["h"]
            c["t_capture_out"] = round(time.time() - to, 4)
        last_val = None
        rss = _rss_bytes()
        c["rss_after"] = rss
        if rss:
            peak_rss = max(peak_rss, rss)
        c["_new"] = new_objs
        record["cells"].append(c)
        emit(c)
        if delay > 0:
            time.sleep(delay)
    signal.signal(signal.SIGALRM, old_handler)

    if eng.get("teardown"):
        try:
            exec(compile(eng["teardown"], "<engine-teardown>", "exec"), {})
        except BaseException as e:
            record["teardown_error"] = "%s: %s" % (type(e).__name__, str(e)[:300])
    record["status"] = "completed"
    record["finished"] = time.time()
    record["wall_s"] = round(record["finished"] - t_start, 3)
    record["peak_rss_sampled"] = peak_rss
    record["maxrss_self"] = _maxrss_bytes()
    if cap is not None:
        record["capture_stats"] = {"bytes_written": cap.bytes_written, "blobs_written": cap.blobs_written,
                                   "capped_columns": cap.capped_columns}
    if progress:
        progress.close()
    atomic_write_json(job["out"], record)


if __name__ == "__main__":
    main()
    # Engines may leave non-daemon threads (Ray, MPI); the record is already on disk.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)

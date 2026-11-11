"""D2 uncaptured replay child (runs inside an engine environment; no capture harness).

    <envs/E/bin/python> d2_child.py job.json

Executes the notebook's code cells in order up to the last target cell, as the harness does but WITHOUT any capture:
no AST-driven input or output capture, no hashing, no conversion to pandas, no materialisation of bound values. What
is shared with the harness: the pandas-import rewrite (`import pandas as pd` -> the engine module, nbsource.prepare_cell,
which only strips magics and rewrites imports), PandasBench's `evaluate_lazy` hook (IREWR_IMPORTS, as in the harness),
seeds (random.seed(0), numpy.random.seed(0), PYTHONHASHSEED=0 from the parent), the setup-cell rule, Agg plotting with
plt.show disabled, a no-op display(), the 600 s cell alarm and the working directory with the prepared inputs.
After each target cell, and only then, each listed value is observed with its expression (v = the value); the
observation is the only extra computation. Prints one line per observation: D2RESULT {json}.
"""
import builtins
import json
import os
import random
import signal
import sys
import time
import traceback
import types
import warnings


class CellTimeout(BaseException):
    pass


def _alarm(signum, frame):
    raise CellTimeout()


def emit(obj):
    sys.__stdout__.write("D2RESULT " + json.dumps(obj, default=str) + "\n")
    sys.__stdout__.flush()


def main():
    with open(sys.argv[1]) as f:
        job = json.load(f)
    from pconf import nbsource
    cells = nbsource.load_cells(job["nb_file"])
    targets = {}
    for t in job["targets"]:
        targets.setdefault(int(t["cell"]), []).append(t)
    last_cell = max(targets)
    ns = {"__name__": "__main__", "__builtins__": builtins}

    def display(*a, **k):
        return None
    ipy = types.ModuleType("IPython")
    ipyd = types.ModuleType("IPython.display")
    ipyd.display = display
    ipyd.Markdown = ipyd.HTML = ipyd.Image = lambda *a, **k: None
    ipy.display = ipyd
    ipy.get_ipython = lambda: None
    sys.modules.setdefault("IPython", ipy)
    sys.modules.setdefault("IPython.display", ipyd)
    ns["display"] = display
    ns["get_ipython"] = lambda: None
    if any(("matplotlib" in c or "seaborn" in c or "plt." in c) for c in cells):
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            plt.show = lambda *a, **k: None
        except Exception:
            pass
    os.chdir(job["cwd"])
    random.seed(job.get("seed", 0))
    setup_ns = {}
    t0 = time.time()
    exec(compile(job["setup"], "<engine-setup>", "exec"), setup_ns)
    pd_module = setup_ns["pd"]
    try:
        import numpy as np
        np.random.seed(job.get("seed", 0))
    except Exception:
        pass
    emit({"event": "setup", "seconds": round(time.time() - t0, 3), "pd_module": getattr(pd_module, "__name__", str(pd_module))})
    ns["__pconf_pd__"] = pd_module
    os.environ["IREWR_IMPORTS"] = "pd = __pconf_pd__\ndef evaluate_lazy(lazy):\n    %s\n" % job["evaluate_lazy"]
    signal.signal(signal.SIGALRM, _alarm)
    skip = set(job.get("skip_cells", []))
    for i, src in enumerate(cells[: last_cell + 1]):
        if i in skip:
            os.environ.pop("INPUT_SCALE_FACTOR", None)
            try:
                exec(compile(src, "<cell %d>" % i, "exec"), ns)
            except BaseException as e:
                emit({"event": "setup_error", "cell": i, "error": "%s: %s" % (type(e).__name__, str(e)[:300])})
            continue
        if not src.strip():
            continue
        tree, _info = nbsource.prepare_cell(src)
        head, expr = nbsource.split_last_expr(tree)
        status, err, last, has_last = "ok", None, None, False
        old_out, old_err = sys.stdout, sys.stderr
        import io
        buf = io.StringIO()
        tc = time.perf_counter()
        with warnings.catch_warnings(record=True) as wl:
            warnings.simplefilter("always")
            sys.stdout = sys.stderr = buf
            try:
                signal.setitimer(signal.ITIMER_REAL, float(job.get("cell_timeout", 600)))
                if head is not None:
                    exec(compile(head, "<cell %d>" % i, "exec"), ns)
                if expr is not None:
                    last = eval(compile(expr, "<cell %d>" % i, "eval"), ns)
                    has_last = True
                signal.setitimer(signal.ITIMER_REAL, 0)
            except CellTimeout:
                signal.setitimer(signal.ITIMER_REAL, 0)
                status, err = "timeout", "cell exceeded"
            except BaseException as e:
                signal.setitimer(signal.ITIMER_REAL, 0)
                status, err = "error", "%s: %s" % (type(e).__name__, str(e)[:300])
            finally:
                sys.stdout, sys.stderr = old_out, old_err
        wall = round(time.perf_counter() - tc, 4)
        if i in targets:
            warns = []
            for w in wl:
                k = (w.category.__name__, str(w.message)[:240])
                if k not in warns:
                    warns.append(k)
            for t in targets[i]:
                obs = {}
                for name, code in t["values"].items():
                    try:
                        if name == "__last__":
                            if not has_last:
                                raise KeyError("cell has no last expression value")
                            v = last
                        else:
                            v = ns[name]
                        obs[name] = {"ok": True, "value": eval(code, {"v": v, "__builtins__": builtins, "__name__": "__main__"})}
                    except BaseException as e:
                        obs[name] = {"ok": False, "error": "%s: %s" % (type(e).__name__, str(e)[:300])}
                emit({"event": "target", "case": t["case"], "cell": i, "status": status, "error": err, "wall_s": wall,
                      "warnings": warns[:12], "observations": obs})
        elif status != "ok":
            emit({"event": "cell_error", "cell": i, "status": status, "error": err})
        last = None
    if job.get("teardown"):
        try:
            exec(compile(job["teardown"], "<engine-teardown>", "exec"), {})
        except BaseException:
            pass
    emit({"event": "done", "seconds": round(time.time() - t0, 3)})


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        emit({"event": "fatal", "traceback": traceback.format_exc()[-1500:]})
        raise

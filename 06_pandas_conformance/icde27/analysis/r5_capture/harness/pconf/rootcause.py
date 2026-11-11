"""Root-cause tooling: minimise a divergent cell into a standalone reproducer (plan.md RQ2).

    python -m pconf.rootcause minimize --campaign conf_1x --engine fireducks --nb user/slug --cell 7

1. Take the reference run's PRE-CELL inputs of the cell (captured object records) and the cell code.
2. Start one persistent server per environment (ref and the engine; `serve` mode below), which
   decodes the inputs once, and per trial applies a row subset / column drop, converts inputs
   to engine objects (engine's own constructor), executes the cell, captures its outputs.
3. Delta-debug: shrink every DataFrame/Series input by halves (then single rows), then drop
   columns, keeping a reduction only while the dfeq outcome signature (level + first failing
   check at E0) between reference and engine is unchanged.
4. Emit probes/rootcause/<id>.json (a probe, so the reproducer re-runs on every engine) and a
   human-readable .py with literal data. The taxonomy itself is curated in results/rootcauses.json.
"""
import argparse
import json
import os
import subprocess
import sys
import time

from pconf import classify, datasets, dfeq, engines, nbsource, orchestrate, util

FROM_PANDAS = r'''
def _to_engine(pd, obj):
    import pandas as _p
    if not isinstance(obj, (_p.DataFrame, _p.Series)):
        return obj
    for name in ("from_pandas",):
        f = getattr(pd, name, None)
        if f is not None:
            try:
                return f(obj, npartitions=2) if pd.__name__.startswith("dask") else f(obj)
            except TypeError:
                return f(obj)
    return (pd.DataFrame if isinstance(obj, _p.DataFrame) else pd.Series)(obj)
'''


def serve(job_path):
    """Server loop inside an engine env: one JSON request per stdin line, one JSON reply per line."""
    from pconf.capture import Capturer, decode_to_pandas
    with open(job_path) as f:
        job = json.load(f)
    setup_ns = {}
    exec(compile(job["engine"]["setup"], "<engine-setup>", "exec"), setup_ns)
    pd = setup_ns["pd"]
    helper = {}
    exec(FROM_PANDAS, helper)
    import pandas as _p
    originals = {n: decode_to_pandas(job["store"], rec) for n, rec in job["inputs"].items()}
    cap = Capturer(job["store"])
    tree, _ = nbsource.prepare_cell(job["code"])
    head, expr = nbsource.split_last_expr(tree)
    an = nbsource.analyze(tree)
    sys.stdout.write(json.dumps({"ready": True}) + "\n")
    sys.stdout.flush()
    for line in sys.stdin:
        req = json.loads(line)
        if req.get("cmd") == "quit":
            break
        ns = {"__builtins__": __builtins__, "__pconf_pd__": pd, "pd": pd}
        import numpy as np
        ns["np"] = np
        inputs = {}
        for n, obj in originals.items():
            o = obj
            if isinstance(o, (_p.DataFrame, _p.Series)):
                rows = req.get("rows", {}).get(n)
                if rows is not None:
                    o = o.iloc[rows]
                drop = req.get("drop_cols", {}).get(n)
                if drop and isinstance(o, _p.DataFrame):
                    keep = [j for j in range(o.shape[1]) if j not in set(drop)]
                    o = o.iloc[:, keep]
                o = o.copy()
            inputs[n] = o
        if req.get("cmd") == "emit":
            sys.stdout.write(json.dumps({"literal": {n: _literal(o) for n, o in inputs.items()}}) + "\n")
            sys.stdout.flush()
            continue
        for n, o in inputs.items():
            ns[n] = helper["_to_engine"](pd, o)
        res = {"status": "ok"}
        try:
            if head is not None:
                exec(compile(head, "<cell>", "exec"), ns)
            last = eval(compile(expr, "<cell>", "eval"), ns) if expr is not None else None
            outs = {}
            for n in an["stores"] + an["mutates"]:
                if n in ns:
                    outs[n] = cap.capture(ns[n])
            if expr is not None:
                outs["__last__"] = cap.capture(last)
            res["outputs"] = outs
        except BaseException as e:
            res = {"status": "error", "exc_type": type(e).__name__, "exc_msg": str(e)[:300]}
        sys.stdout.write(json.dumps(res, default=str) + "\n")
        sys.stdout.flush()


SETUP_PRELUDE = ("nan = float('nan')\nNaT = pd.NaT\nNA = pd.NA\nTimestamp = pd.Timestamp\n"
                 "Timedelta = pd.Timedelta\n")


def _literal(o):
    """Python source that rebuilds `o` with plain constructors (dtype restored by name)."""
    import pandas as _p
    if isinstance(o, _p.DataFrame):
        data = "{%s}" % ", ".join("%r: %r" % (k, o.iloc[:, j].tolist()) for j, k in enumerate(o.columns))
        dt = {k: str(v) for k, v in zip(o.columns, o.dtypes)}
        return "pd.DataFrame(%s, index=%r).astype(%r)" % (data, o.index.tolist(), dt)
    if isinstance(o, _p.Series):
        return "pd.Series(%r, index=%r, name=%r, dtype=%r)" % (o.tolist(), o.index.tolist(), o.name, str(o.dtype))
    return repr(o)


class Server:
    def __init__(self, engine, job):
        self.engine = engine
        jp = os.path.join(util.WORK, "rootcause", "job_%s_%d.json" % (orchestrate.engine_tag(engine), os.getpid()))
        util.atomic_write_json(jp, dict(job, engine=engines.engine_spec(engine)))
        self.p = subprocess.Popen([engines.engine_python(engine), "-m", "pconf.rootcause", "serve", "--job", jp],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  env=engines.child_env(engine), text=True, start_new_session=True,
                                  cwd=os.path.join(util.WORK, "rootcause"))
        line = self._readline()
        if not line or not json.loads(line).get("ready"):
            raise RuntimeError("server %s failed to start" % engine)

    def _readline(self):
        while True:
            line = self.p.stdout.readline()
            if not line:
                return None
            if line.startswith("{"):
                return line

    def ask(self, req):
        self.p.stdin.write(json.dumps(req) + "\n")
        self.p.stdin.flush()
        return json.loads(self._readline())

    def close(self):
        try:
            self.p.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
            self.p.stdin.flush()
            self.p.wait(timeout=30)
        except Exception:
            orchestrate._kill_known(self.p.pid)


def signature(ref_res, eng_res, store):
    if ref_res["status"] != "ok":
        return ("REF_ERR",)
    if eng_res["status"] != "ok":
        return ("ERR", eng_res.get("exc_type"))
    worst, first = "E0", None
    for n, rr in sorted(ref_res["outputs"].items()):
        er = eng_res["outputs"].get(n)
        if er is None:
            return ("DIFF", "missing:" + n)
        r = dfeq.compare(rr, er, store)
        if dfeq.worst([worst, r["level"]]) != worst:
            worst, first = r["level"], (n, (r.get("fails") or {}).get("E0", "").split(":")[0])
    return (worst, first)


def minimize(campaign, engine, nb, cell, ref="ref", scale=1.0, cfg=None, max_trials=200, out_dir=None):
    cfg = cfg or {"cell_timeout": 600, "nb_timeout": 3600, "seed": 0, "capture_inputs": True, "limits": None, "cpus": None}
    rref = orchestrate.find_record(campaign, ref, nb, scale, cfg)[0]
    if not rref:
        raise SystemExit("no reference record for %s %s" % (campaign, nb))
    R = util.read_json(rref)
    cr = next(c for c in R["cells"] if c["i"] == cell)
    code = nbsource.load_cells(datasets.notebook_file(nb))[cell]
    inputs = {}
    for n, h in (cr.get("inputs") or {}).items():
        if isinstance(h, str) and h in R["objects"]:
            inputs[n] = R["objects"][h]
    os.makedirs(os.path.join(util.WORK, "rootcause"), exist_ok=True)
    job = {"store": util.CAPTURES, "inputs": inputs, "code": code}
    sref, seng = Server(ref, job), Server(engine, job)
    try:
        def trial(rows, drop):
            req = {"rows": rows, "drop_cols": drop}
            return signature(sref.ask(req), seng.ask(req), util.CAPTURES)

        sizes = {n: rec["meta"]["shape"][0] for n, rec in inputs.items() if rec["kind"] in ("DataFrame", "Series")}
        rows = {n: list(range(k)) for n, k in sizes.items()}
        drop = {}
        target = trial(rows, drop)
        log = [{"step": "original", "sig": target, "rows": {n: len(v) for n, v in rows.items()}}]
        if target[0] in ("E0", "REF_ERR"):
            return {"status": "not_divergent", "signature": target, "log": log}
        n_trials = 1
        for n in list(rows):
            chunk = len(rows[n]) // 2
            while chunk >= 1 and n_trials < max_trials:
                i, removed = 0, False
                while i < len(rows[n]) and n_trials < max_trials:
                    cand = rows[n][:i] + rows[n][i + chunk:]
                    if cand:
                        n_trials += 1
                        if trial(dict(rows, **{n: cand}), drop) == target:
                            rows[n] = cand
                            removed = True
                            continue
                    i += chunk
                chunk = min(chunk, len(rows[n]) // 2) if removed else chunk // 2
        for n, rec in inputs.items():
            if rec["kind"] != "DataFrame":
                continue
            for j in range(rec["meta"]["shape"][1]):
                if n_trials >= max_trials:
                    break
                cand = dict(drop, **{n: sorted(set(drop.get(n, [])) | {j})})
                n_trials += 1
                if trial(rows, cand) == target:
                    drop = cand
        lit = sref.ask({"cmd": "emit", "rows": rows, "drop_cols": drop})["literal"]
    finally:
        sref.close()
        seng.close()
    rid = "rc_%s_%s_c%d" % (orchestrate.engine_tag(engine), util.nb_key(nb), cell)
    setup = SETUP_PRELUDE + "".join("%s = %s\n" % (n, src) for n, src in sorted(lit.items()))
    probe = {"id": rid, "family": ",".join(classify.op_families((cr.get("static") or {}).get("attrs"))),
             "source": "rootcause:%s:%s:%s:cell%d" % (campaign, engine, nb, cell), "documented": None,
             "setup": setup, "code": code}
    res = {"id": rid, "engine": engine, "ref": ref, "nb": nb, "cell": cell, "code": code, "signature": list(target),
           "rows": {n: len(v) for n, v in rows.items()}, "dropped_cols": drop, "trials": n_trials,
           "campaign": campaign, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "probes": [probe]}
    out_dir = out_dir or os.path.join(util.PROJ, "probes", "rootcause")
    util.atomic_write_json(os.path.join(out_dir, rid + ".json"), res, indent=1)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--job", required=True)
    m = sub.add_parser("minimize")
    m.add_argument("--campaign", required=True)
    m.add_argument("--engine", required=True)
    m.add_argument("--nb", required=True)
    m.add_argument("--cell", type=int, required=True)
    m.add_argument("--ref", default="ref")
    m.add_argument("--scale", type=float, default=1.0)
    m.add_argument("--max-trials", type=int, default=200)
    m.add_argument("--cell-timeout", type=float, default=600)
    m.add_argument("--nb-timeout", type=float, default=3600)
    m.add_argument("--out-dir", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "serve":
        serve(a.job)
        return 0
    cfg = {"cell_timeout": a.cell_timeout, "nb_timeout": a.nb_timeout, "seed": 0, "capture_inputs": True, "limits": None, "cpus": None}
    res = minimize(a.campaign, a.engine, a.nb, a.cell, a.ref, a.scale, cfg=cfg, max_trials=a.max_trials, out_dir=a.out_dir)
    print(json.dumps({k: res.get(k) for k in ("id", "status", "signature", "rows", "dropped_cols", "trials")}, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

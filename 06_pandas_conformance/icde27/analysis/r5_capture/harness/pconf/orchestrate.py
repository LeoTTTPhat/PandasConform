"""Campaign orchestrator (parent process, shared venv). Checkpointed and resumable.

    python -m pconf.orchestrate run     --campaign smoke --set smoke --engines ref,ref#2,modin --scale 1
    python -m pconf.orchestrate compare --campaign smoke --set smoke --engines modin,fireducks --scale 1
    python -m pconf.orchestrate summarize --campaign smoke
    python -m pconf.orchestrate status  --campaign smoke

run: for each (engine, notebook, scale) launch runner_child with the engine's interpreter,
enforce a per-notebook timeout, and record ONE atomic result per notebook at
    results/<campaign>/raw/runs__h<harness12>/<engine>/<sfX>/<user>__<slug>__<fp12>.json
(campaigns before 2026-10-02 15:40, i.e. smoke and smoke_timing, used results/<campaign>/runs__...
without the raw/ level; they are left in place)
fingerprinted by (engine env lock, notebook sha256, scale, harness source sha256, run config).
Completed fingerprints are skipped; an interrupted notebook (orchestrator killed) leaves no
record and is rerun from scratch. Crashes and timeouts ARE results (status nb_crash/nb_timeout,
with the per-cell progress salvaged). A child killed from OUTSIDE (SIGKILL/SIGTERM with no Python
traceback: OOM killer, stray signal) leaves no record the first time (status killed_external,
counted in work/kills/); a second such kill of the same fingerprint is recorded as nb_killed
(fix of review finding A5, 2026-10-02).

Fingerprints cover the engine, env freeze, notebook sha256, the content hash of the prepared
inputs (datasets.input_fingerprint), scale, harness sha and the run config (timeouts, input
capture, seed, cpus). Compare outputs are named by the ref, engine AND ref#2 fingerprints
('noref2' when absent), so a comparison made before ref#2 existed is recomputed once it does
(fix of review finding A4); summarize keeps one output per (engine, notebook, scale): the one
with ref#2, newest first.

Concurrency (plan.md Section 4): up to --max-concurrency notebooks at once for single-threaded
engines (ref, p15, p30, pyarrow_backend); Modin, FireDucks, Bodo and Dask one at a time. When
MEMGUARD_RESTART>0 everything runs one at a time with MEMGUARD_DELAY_SECONDS pauses.
"""
import argparse
import concurrent.futures as cf
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time

from pconf import datasets, engines, util

LOCK = threading.Lock()
RUNNING = {}          # pid -> Popen
SEEN_DESC = {}        # pid -> {desc pid: create_time}
STOP = threading.Event()
HARD_DEADLINE = [None]   # absolute time after which in-flight notebooks are interrupted (no record)
# Per-notebook memory cap (pilot 2026-10-02: Modin on yonelanuba/elo-merchant pushed the guarded
# process tree past the 120 GB guard limit in all 3 guard attempts, which kills the whole campaign
# invocation). The orchestrator samples the notebook's process-tree RSS (sum over the runner and
# all descendants, the same quantity the guard sums; Ray's shared object-store pages are counted
# once per process that maps them) every 0.5 s and stops the notebook above this cap, recording
# status nb_memory (class MEMORY). Every record carries peak_tree_rss_gb (sampled).
NB_MEM_LIMIT_GB = 96.0
# R5 B1 copy: per (engine, notebook) last cell to execute ("engine|nb" -> cell index), from --stop-plan; part of the
# run config (and so of the fingerprint) of that notebook.
STOP_PLAN = {}


def stop_cfg(cfg, engine, nb):
    k = STOP_PLAN.get("%s|%s" % (engine, nb), STOP_PLAN.get("*|%s" % nb))
    return dict(cfg, stop_after=k) if k is not None else cfg


def harness_tag():
    return "h" + util.harness_sha()[:12]


def compare_tag():
    return "h%s__d%s" % (util.harness_sha()[:12], util.compare_sha()[:12])


def engine_tag(name):
    return name.replace("#", "_r")


def runs_dir(campaign, mode="capture"):
    return os.path.join(raw_dir(campaign), ("runs__" if mode == "capture" else "timing__") + harness_tag())


def raw_dir(campaign):
    """Raw results of a campaign: run records, compare outputs, the campaign manifest."""
    return os.path.join(util.RESULTS, campaign, "raw")


def nb_sha(nb):
    return util.sha256_file(datasets.notebook_file(nb))


# Pre-cell input capture re-encodes and hashes every frame a cell reads (O(data) per cell). Pilot
# 2026-10-02, ref on yonelanuba/elo-merchant (3.1 GB input, 171 cells): 104 s executing cells,
# 258 s input capture, 81 s output capture. Engines must also convert to pandas at every capture.
# Notebooks whose scaled input exceeds this many GB therefore run WITHOUT pre-cell input capture
# (their fingerprint carries capture_inputs=False); classify then takes a cell's inputs from the
# last captured values of the names it reads (AST-visible bindings only).
INPUT_CAPTURE_MAX_GB = 1.0


def nb_cfg(cfg, nb, scale):
    """Run config resolved for one notebook (input-capture rule above)."""
    if cfg.get("capture_inputs") and not nb.startswith("probe:") and INPUT_CAPTURE_MAX_GB and \
            datasets.input_bytes(nb) * float(scale) > INPUT_CAPTURE_MAX_GB * 1e9:
        return dict(cfg, capture_inputs=False, capture_inputs_rule="off:input>%gGB" % INPUT_CAPTURE_MAX_GB)
    return cfg


def fingerprint(engine, nb, scale, cfg):
    cfg = nb_cfg(cfg, nb, scale)
    spec = engines.engine_spec(engine)
    lock = engines.env_lock(engine)
    return util.sha256_json({
        "engine": engine, "setup": spec["setup"], "teardown": spec["teardown"], "env_vars": spec["env_vars"],
        "threads": spec["threads"], "evaluate_lazy": spec["evaluate_lazy"],
        "env_freeze": lock.get("freeze_sha256"), "nb": nb, "nb_sha256": nb_sha(nb), "scale": float(scale),
        "inputs": datasets.input_fingerprint(nb, scale), "setup_cells": datasets.setup_cells(nb),
        "harness": util.harness_sha(), "cfg": cfg})


def run_cfg(a):
    """Run configuration (part of the fingerprint); identical construction for run and compare."""
    return {"cell_timeout": a.cell_timeout, "nb_timeout": a.nb_timeout, "seed": 0,
            "capture_inputs": not a.no_input_capture, "limits": None, "cpus": getattr(a, "cpus", None)}


def _kill_path(campaign, engine, nb, scale, fp):
    return os.path.join(util.WORK, "kills", campaign, engine_tag(engine), datasets.scale_tag(scale),
                        "%s__%s.json" % (util.nb_key(nb), fp[:12]))


def _log_has_traceback(path):
    try:
        with open(path, "rb") as f:
            return b"Traceback (most recent call last)" in f.read()
    except OSError:
        return False


def record_path(campaign, engine, nb, scale, fp, mode="capture"):
    return os.path.join(runs_dir(campaign, mode), engine_tag(engine), datasets.scale_tag(scale),
                        "%s__%s.json" % (util.nb_key(nb), fp[:12]))


def find_record(campaign, engine, nb, scale, cfg, mode="capture"):
    fp = fingerprint(engine, nb, scale, cfg)
    p = record_path(campaign, engine, nb, scale, fp, mode)
    return (p if os.path.exists(p) else None), fp, p


# ----------------------------------------------------------------------------- process control

def _descendants(pid):
    try:
        import psutil
        p = psutil.Process(pid)
        return {c.pid: c.create_time() for c in p.children(recursive=True)}
    except Exception:
        return {}


def _tree_rss(pid):
    """RSS summed over a process and all its descendants (bytes)."""
    try:
        import psutil
        p = psutil.Process(pid)
        tot = p.memory_info().rss
        for c in p.children(recursive=True):
            try:
                tot += c.memory_info().rss
            except Exception:
                pass
        return tot
    except Exception:
        return 0


def _kill_known(pid, group=True):
    """Kill the child's process group (only while the child is alive, group=True) and every
    descendant seen while it ran (orphans included; create_time guards against pid reuse)."""
    try:
        import psutil
    except Exception:
        psutil = None
    if group:
        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    seen = dict(SEEN_DESC.get(pid, {}))
    seen.update(_descendants(pid))
    for dpid, ctime in seen.items():
        try:
            if psutil is not None:
                q = psutil.Process(dpid)
                if abs(q.create_time() - ctime) > 1e-3:
                    continue
                q.kill()
            else:
                os.kill(dpid, signal.SIGKILL)
        except Exception:
            pass


def _input_listing(d):
    out = []
    for dp, _, fn in os.walk(d):
        for n in sorted(fn):
            p = os.path.join(dp, n)
            st = os.stat(p)
            out.append((os.path.relpath(p, d), st.st_size, st.st_mtime_ns))
    return sorted(out)


def run_one(campaign, engine, nb, scale, cfg, mode="capture", rep=1, reuse_from=()):
    """Run one notebook for one engine. Returns (status, record path).
    reuse_from: other campaigns whose record with the IDENTICAL fingerprint (same engine, env,
    notebook, inputs, scale, harness and run config) is adopted instead of rerunning; the copy
    is marked with reused_from, the original stays in place."""
    cfg = stop_cfg(cfg, engine, nb)
    existing, fp, rpath = find_record(campaign, engine, nb, scale, cfg, mode)
    if existing:
        return "skipped", existing
    cfg = nb_cfg(cfg, nb, scale)
    for other in reuse_from:
        src = record_path(other, engine, nb, scale, fp, mode)
        rec = util.read_json(src)
        if rec and rec.get("fingerprint") == fp and rec.get("status") != "nb_killed":
            rec["reused_from"] = os.path.relpath(src, util.PROJ)
            util.atomic_write_json(rpath, rec)
            return "reused", rpath
    spec = engines.engine_spec(engine)
    py = engines.engine_python(engine)
    key = util.nb_key(nb)
    scratch = os.path.join(util.WORK, "run_cwd", campaign, engine_tag(engine), datasets.scale_tag(scale), key)
    shutil.rmtree(scratch, ignore_errors=True)
    os.makedirs(scratch)
    cwd = os.path.join(scratch, "cwd")
    os.makedirs(cwd)
    in_dir = os.path.join(datasets.scaled_dir(nb, scale), "input")
    if os.path.isdir(in_dir):
        os.symlink(in_dir, os.path.join(cwd, "input"))
    before = _input_listing(in_dir) if os.path.isdir(in_dir) else []
    job = {
        "engine": spec, "nb": nb, "nb_file": datasets.notebook_file(nb), "cwd": cwd, "scale": float(scale),
        "store": util.CAPTURES, "out": os.path.join(scratch, "record.json"),
        "progress": os.path.join(scratch, "progress.jsonl"), "cell_timeout": cfg["cell_timeout"],
        "capture": mode == "capture", "capture_inputs": cfg.get("capture_inputs", True) and mode == "capture",
        "seed": cfg.get("seed", 0), "skip_cells": datasets.setup_cells(nb), "limits": cfg.get("limits"), "fingerprint": fp,
        "stop_after": cfg.get("stop_after"),
    }
    jpath = os.path.join(scratch, "job.json")
    util.atomic_write_json(jpath, job)
    env = engines.child_env(engine, cpus=cfg.get("cpus"))
    if mode == "timing":
        env.pop("FIREDUCKS_FLAGS", None)  # engine defaults for timing (fallback logging off)
    log_path = os.path.join(scratch, "child.log")
    t0 = time.time()
    with open(log_path, "wb") as log:
        proc = subprocess.Popen([py, "-m", "pconf.runner_child", "--job", jpath], cwd=cwd, env=env,
                                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        with LOCK:
            RUNNING[proc.pid] = proc
            SEEN_DESC[proc.pid] = {}
        status = None
        deadline = t0 + cfg["nb_timeout"]
        peak_tree = 0
        last_desc = 0.0
        while True:
            try:
                proc.wait(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                if time.time() - last_desc > 2.0:
                    last_desc = time.time()
                    with LOCK:
                        SEEN_DESC[proc.pid].update(_descendants(proc.pid))
                rss = _tree_rss(proc.pid)
                peak_tree = max(peak_tree, rss)
                if NB_MEM_LIMIT_GB and rss > NB_MEM_LIMIT_GB * 1e9:
                    _kill_known(proc.pid)
                    proc.wait()
                    status = "nb_memory"
                    break
                if STOP.is_set() or (HARD_DEADLINE[0] and time.time() > HARD_DEADLINE[0]):
                    _kill_known(proc.pid)
                    proc.wait()
                    status = "interrupted"
                    break
                if time.time() > deadline:
                    _kill_known(proc.pid)
                    proc.wait()
                    status = "nb_timeout"
                    break
        if status is None and STOP.is_set():
            status = "interrupted"  # child died because the orchestrator is being stopped
        _kill_known(proc.pid, group=False)  # orphans (Ray/MPI helpers) must not outlive the notebook
        with LOCK:
            RUNNING.pop(proc.pid, None)
            SEEN_DESC.pop(proc.pid, None)
    wall = time.time() - t0
    if status == "interrupted":
        return "interrupted", None
    rec = util.read_json(job["out"])
    if rec is None:
        if status is None and proc.returncode in (-signal.SIGKILL, -signal.SIGTERM) and not _log_has_traceback(log_path):
            kp = _kill_path(campaign, engine, nb, scale, fp)
            k = util.read_json(kp, {}) or {}
            k.setdefault("events", []).append({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "rc": proc.returncode,
                                               "wall_s": round(wall, 3)})
            util.atomic_write_json(kp, k, indent=1)
            if len(k["events"]) < 2:
                print("[run] %s %s: child killed externally (rc %s); no record, will rerun"
                      % (engine, nb, proc.returncode), flush=True)
                shutil.rmtree(scratch, ignore_errors=True)
                return "killed_external", None
            status = "nb_killed"
        rec = _salvage(job, engine, nb, scale, fp)
        rec["status"] = status or "nb_crash"
        rec["returncode"] = proc.returncode
    rec["returncode"] = proc.returncode
    rec["orchestrator_wall_s"] = round(wall, 3)
    rec["peak_tree_rss_gb"] = round(peak_tree / 1e9, 3)
    rec["nb_mem_limit_gb"] = NB_MEM_LIMIT_GB
    rec["fingerprint"] = fp
    rec["campaign"] = campaign
    rec["engine"] = engine
    rec["scale"] = float(scale)
    rec["rep"] = rep
    rec["env_freeze_sha256"] = engines.env_lock(engine).get("freeze_sha256")
    rec["nb_sha256"] = nb_sha(nb)
    rec["harness_sha"] = util.harness_sha()
    rec["cfg"] = cfg
    try:
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            n = f.tell()
            f.seek(max(0, n - 4000))
            rec["log_tail"] = f.read().decode("utf-8", "replace")
    except OSError:
        pass
    after = _input_listing(in_dir) if os.path.isdir(in_dir) else []
    if after != before:
        rec["input_mutated"] = True
    rec["files_written"] = sorted(os.path.relpath(os.path.join(dp, n), cwd)
                                  for dp, _, fn in os.walk(cwd) for n in fn if not dp.startswith(os.path.join(cwd, "input")))[:200]
    util.atomic_write_json(rpath, rec)
    shutil.rmtree(scratch, ignore_errors=True)
    return rec.get("status", "?"), rpath


def _salvage(job, engine, nb, scale, fp):
    rec = {"fingerprint": fp, "engine": engine, "nb": nb, "scale": scale, "cells": [], "objects": {}, "nested": {},
           "salvaged_from_progress": True}
    try:
        with open(job["progress"]) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                rec["cells"].append(d["cell"])
                rec["objects"].update(d.get("objects", {}))
                rec["nested"].update(d.get("nested", {}))
    except OSError:
        pass
    return rec


# ----------------------------------------------------------------------------- campaign driver

def ensure_prepared(nbs, scale):
    todo = [nb for nb in nbs if not datasets.is_prepared(nb, scale)]
    if not todo:
        return {}
    py = engines.engine_python("ref")
    env = engines.child_env("ref")
    out = {}
    for nb in todo:
        r = subprocess.run([py, "-m", "pconf.datasets", "prep", "--nb", nb, "--scale", str(scale)],
                           env=env, capture_output=True, text=True)
        try:
            out[nb] = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            out[nb] = {"status": "error", "error": (r.stderr or "")[-500:]}
        print("[prep] %s sf=%s -> %s" % (nb, scale, out[nb].get("status")), flush=True)
    return out


def concurrency(cls, requested):
    restart = int(os.environ.get("MEMGUARD_RESTART", "0") or 0)
    if restart > 0 or cls != "single":
        return 1
    scale = float(os.environ.get("MEMGUARD_BATCH_SCALE", "1") or 1)
    return max(1, int(requested * min(1.0, scale)))


def campaign_manifest_path(campaign):
    return os.path.join(raw_dir(campaign), "campaign_%s.json" % harness_tag())


def update_manifest(campaign, key, value):
    with LOCK:
        p = campaign_manifest_path(campaign)
        m = util.read_json(p, {}) or {}
        m.setdefault("runs", {})[key] = value
        m["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        m["harness_sha"] = util.harness_sha()
        util.atomic_write_json(p, m, indent=1)


def cmd_run(a):
    nbs = datasets.notebook_set(a.set)
    if a.offset:
        nbs = nbs[a.offset:]
    if a.limit:
        nbs = nbs[: a.limit]
    engs = a.engines.split(",")
    cfg = run_cfg(a)
    reuse = [c for c in (a.reuse_from or "").split(",") if c]
    if a.deadline and a.deadline + a.nb_timeout > 5400 and not (a.hard_budget and a.hard_budget <= 5400):
        print("[run] WARNING: deadline %.0f s + nb_timeout %.0f s exceeds 90 min" % (a.deadline, a.nb_timeout), flush=True)
    reps = list(range(1, a.reps + 1)) if a.mode == "timing" else [1]
    prep = ensure_prepared(nbs, a.scale)
    bad_prep = [nb for nb, r in prep.items() if r.get("status") != "ok"]
    delay = float(os.environ.get("MEMGUARD_DELAY_SECONDS", "0") or 0)
    t_start = time.time()
    if a.hard_budget:
        HARD_DEADLINE[0] = t_start + a.hard_budget
    counts = {}

    def job(engine, nb, rep):
        if STOP.is_set():
            return "interrupted", None
        if nb in bad_prep:
            return "prep_failed", None   # never run a notebook on missing or partial inputs
        if a.deadline and time.time() - t_start > a.deadline:
            return "deferred", None
        if HARD_DEADLINE[0] and time.time() > HARD_DEADLINE[0]:
            return "deferred", None
        cfg_r = dict(cfg, rep=rep) if a.mode == "timing" else cfg
        st, path = run_one(a.campaign, engine, nb, a.scale, cfg_r, a.mode, rep, reuse)
        update_manifest(a.campaign, "%s|%s|%s|%s|%d" % (a.mode, engine, nb, a.scale, rep),
                        {"status": st, "record": os.path.relpath(path, util.PROJ) if path else None})
        print("[run] %-16s %-60s rep=%d -> %s" % (engine, nb, rep, st), flush=True)
        if delay:
            time.sleep(delay)
        return st, path

    big = {nb for nb in nbs if not nb.startswith("probe:") and datasets.input_bytes(nb) * a.scale > a.big_input_gb * 1e9}
    for engine in engs:
        spec = engines.engine_spec(engine)
        n_conc = concurrency(spec["class"], a.max_concurrency)
        tasks = [(engine, nb, r) for nb in nbs for r in reps]
        if n_conc == 1:
            results = [job(*t) for t in tasks]
        else:
            # notebooks with large inputs run alone (memory), the rest up to n_conc at a time
            small = [t for t in tasks if t[1] not in big]
            with cf.ThreadPoolExecutor(n_conc) as ex:
                results = list(ex.map(lambda t: job(*t), small))
            results += [job(*t) for t in tasks if t[1] in big]
        for st, _ in results:
            counts[st] = counts.get(st, 0) + 1
        if STOP.is_set():
            break
    summary = {"campaign": a.campaign, "mode": a.mode, "engines": engs, "notebooks": len(nbs), "scale": a.scale,
               "counts": counts, "prep_failures": bad_prep, "seconds": round(time.time() - t_start, 1)}
    print(json.dumps(summary), flush=True)
    return 130 if STOP.is_set() else 0


def cmd_compare(a):
    nbs = datasets.notebook_set(a.set)
    if a.offset:
        nbs = nbs[a.offset:]
    if a.limit:
        nbs = nbs[: a.limit]
    cfg = run_cfg(a)
    t_cmp0 = time.time()
    out_root = os.path.join(raw_dir(a.campaign), "compare__" + compare_tag())
    jobs, missing, missing_ref2 = [], [], []
    for engine in a.engines.split(","):
        for nb in nbs:
            rref, fpr, _ = find_record(a.campaign, a.ref, nb, a.scale, cfg)
            reng, fpe, _ = find_record(a.campaign, engine, nb, a.scale, cfg)
            rref2, fpr2 = (find_record(a.campaign, a.ref2, nb, a.scale, cfg)[:2]) if a.ref2 else (None, None)
            if not rref or not reng:
                missing.append((engine, nb, bool(rref), bool(reng)))
                continue
            if a.ref2 and not rref2:
                missing_ref2.append(nb)
            out = os.path.join(out_root, engine_tag(engine), datasets.scale_tag(a.scale),
                               "%s__%s_%s_%s.json" % (util.nb_key(nb), fpr[:8], fpe[:8],
                                                      fpr2[:8] if rref2 else "noref2"))
            jobs.append({"ref": rref, "eng": reng, "ref2": rref2, "out": out, "store": util.CAPTURES,
                         "meta": {"campaign": a.campaign, "engine": engine, "ref": a.ref, "ref2": a.ref2,
                                  "nb": nb, "scale": a.scale}})
    todo = [j for j in jobs if not os.path.exists(j["out"])]
    print("[compare] %d jobs, %d to do, %d missing records, %d without ref2" % (
        len(jobs), len(todo), len(missing), len(set(missing_ref2))), flush=True)
    for m in missing[:20]:
        print("[compare] missing", m, flush=True)
    if todo:
        # pilot 2026-10-03: 4 workers comparing elo-merchant/deffro jobs at once peaked at 104 GB
        # tree RSS. Notebooks whose scaled input exceeds --big-input-gb are compared after the
        # small ones by --big-workers workers (default 2); the per-worker decode cache is 2 GB.
        big = [j for j in todo if not j["meta"]["nb"].startswith("probe:")
               and datasets.input_bytes(j["meta"]["nb"]) * a.scale > a.big_input_gb * 1e9]
        small = [j for j in todo if j not in big]
        os.makedirs(os.path.join(util.WORK, "compare_jobs"), exist_ok=True)
        env = engines.child_env("ref")
        env.setdefault("PCONF_DECODE_CACHE_GB", "2")
        rc = 0
        for phase, jobs_p, n_req in (("small", small, a.workers), ("big", big, a.big_workers)):
            if not jobs_p:
                continue
            n_workers = min(concurrency("single", n_req), len(jobs_p))
            chunks = [jobs_p[i::n_workers] for i in range(n_workers)]
            procs = []
            for k, ch in enumerate(chunks):
                jp = os.path.join(util.WORK, "compare_jobs", "%s_%d_%s_%d.jsonl" % (a.campaign, os.getpid(), phase, k))
                with open(jp, "w") as f:
                    for j in ch:
                        f.write(json.dumps(j) + "\n")
                procs.append(subprocess.Popen([engines.engine_python("ref"), "-m", "pconf.compare_worker", "--jobs", jp],
                                              env=env, start_new_session=True))
            hard = (t_cmp0 + a.hard_budget) if a.hard_budget else None
            for p in procs:
                while True:
                    try:
                        rc |= p.wait(timeout=1.0)
                        break
                    except subprocess.TimeoutExpired:
                        if STOP.is_set() or (hard and time.time() > hard):
                            for q in procs:   # outputs are atomic: an interrupted job leaves nothing
                                try:
                                    os.killpg(q.pid, signal.SIGKILL)
                                except (ProcessLookupError, PermissionError):
                                    pass
                            p.wait()
                            break
            print("[compare] phase %s: %d jobs, %d workers" % (phase, len(jobs_p), n_workers), flush=True)
            if STOP.is_set() or (hard and time.time() > hard):
                print("[compare] budget spent; remaining jobs are done next time", flush=True)
                break
        if rc:
            print("[compare] a worker failed rc=%d" % rc, flush=True)
    done = sum(os.path.exists(j["out"]) for j in jobs)
    print(json.dumps({"compare_jobs": len(jobs), "done": done, "missing_records": len(missing), "out_root": out_root}))
    return 0 if done == len(jobs) else 1


def cmd_summarize(a):
    """Aggregate compare outputs of a campaign: per engine counts over all, strict clean-input
    and level-aware clean (clean@Ek) cells. One output per (engine, notebook, scale) is used:
    the one computed with ref#2, newest first (older fingerprints are listed, never counted)."""
    root = os.path.join(raw_dir(a.campaign), "compare__" + compare_tag())
    best, superseded = {}, []
    for dp, _, fn in os.walk(root):
        for n in fn:
            if not n.endswith(".json") or n.startswith(".tmp"):
                continue
            path = os.path.join(dp, n)
            r = util.read_json(path)
            if not r:
                continue
            ref = r["meta"].get("ref") or "ref"
            label = r["meta"]["engine"] if ref == "ref" else "%s~vs~%s" % (r["meta"]["engine"], ref)
            key = (label, r["meta"]["nb"], r["meta"].get("scale"))
            rank = (r["meta"].get("ref2_record") is not None, os.path.getmtime(path))
            if key in best:
                if rank > best[key][0]:
                    superseded.append(best[key][2])
                    best[key] = (rank, r, path)
                else:
                    superseded.append(path)
            else:
                best[key] = (rank, r, path)
    agg = {}
    for (e, nb, sc), (_, r, path) in sorted(best.items()):
        g = agg.setdefault(e, {"notebooks": 0, "by_class": {}, "clean_by_class": {}, "fallback_cells": 0,
                               "clean_cells": 0, "clean_cells_at": {}, "clean_at": {}, "nondet_cells": 0,
                               "hidden_global_cells": 0, "first_divergent": {}, "eng_status": {},
                               "notebooks_without_ref2": 0})
        g["notebooks"] += 1
        st = r["meta"].get("eng_status")
        g["eng_status"][st] = g["eng_status"].get(st, 0) + 1
        if r["meta"].get("ref2_record") is None:
            g["notebooks_without_ref2"] += 1
        sm = r["summary"]
        for k in ("by_class", "clean_by_class"):
            for c, v in sm[k].items():
                g[k][c] = g[k].get(c, 0) + v
        for L, v in sm.get("clean_cells_at", {}).items():
            g["clean_cells_at"][L] = g["clean_cells_at"].get(L, 0) + v
        for L, d in sm.get("clean_at", {}).items():
            gl = g["clean_at"].setdefault(L, {})
            for c, v in d.items():
                gl[c] = gl.get(c, 0) + v
        for k in ("fallback_cells", "clean_cells", "nondet_cells", "hidden_global_cells"):
            g[k] += sm.get(k, 0)
        g["first_divergent"][nb] = r["first_divergent"]
    agg["_meta"] = {"compare_root": os.path.relpath(root, util.PROJ), "outputs_used": len(best),
                    "outputs_superseded": sorted(os.path.relpath(p, util.PROJ) for p in superseded)}
    out = os.path.join(util.RESULTS, a.campaign, "summary__%s.json" % compare_tag())
    util.atomic_write_json(out, agg, indent=1)
    for e, g in sorted(agg.items()):
        if e.startswith("_"):
            continue
        print("%-16s nb=%d all=%s clean=%s clean@E2=%s fallback=%d" % (
            e, g["notebooks"], g["by_class"], g["clean_by_class"], g["clean_at"].get("E2"), g["fallback_cells"]))
    print("wrote %s (%d outputs used, %d superseded)" % (out, len(best), len(superseded)))
    return 0


def cmd_status(a):
    m = util.read_json(campaign_manifest_path(a.campaign), {}) or {}
    counts = {}
    for k, v in m.get("runs", {}).items():
        eng = k.split("|")[1]
        counts.setdefault(eng, {})
        counts[eng][v["status"]] = counts[eng].get(v["status"], 0) + 1
    print(json.dumps({"harness": harness_tag(), "manifest": campaign_manifest_path(a.campaign), "counts": counts}, indent=1))
    return 0


def _install_signal_handlers():
    def handler(signum, frame):
        STOP.set()
        with LOCK:
            pids = list(RUNNING)
        for pid in pids:
            _kill_known(pid)
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def main(argv=None):
    global INPUT_CAPTURE_MAX_GB, NB_MEM_LIMIT_GB
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "compare"):
        p = sub.add_parser(name)
        p.add_argument("--campaign", required=True)
        p.add_argument("--set", required=True)
        p.add_argument("--engines", required=True)
        p.add_argument("--scale", type=float, default=1.0)
        p.add_argument("--limit", type=int, default=0)
        p.add_argument("--offset", type=int, default=0, help="skip the first N notebooks of the set")
        p.add_argument("--cpus", default=None, help="CPU budget for parallel engines: N or 'default' (engines.py)")
        p.add_argument("--cell-timeout", type=float, default=600)
        p.add_argument("--nb-timeout", type=float, default=3600)
        p.add_argument("--no-input-capture", action="store_true")
        p.add_argument("--input-capture-max-gb", type=float, default=None,
                       help="override INPUT_CAPTURE_MAX_GB (%g); must be the same for run and compare" % INPUT_CAPTURE_MAX_GB)
        if name == "run":
            p.add_argument("--max-concurrency", type=int, default=6)
            p.add_argument("--mode", choices=["capture", "timing"], default="capture")
            p.add_argument("--reps", type=int, default=1)
            p.add_argument("--deadline", type=float, default=0, help="seconds; stop launching new notebooks after this")
            p.add_argument("--nb-mem-limit-gb", type=float, default=None,
                           help="per-notebook process-tree RSS cap (default %g GB; guard limit 120 GB)" % NB_MEM_LIMIT_GB)
            p.add_argument("--hard-budget", type=float, default=0,
                           help="seconds; interrupt notebooks still running after this (no record; rerun next time)")
            p.add_argument("--reuse-from", default="", help="comma-separated campaigns whose records with an "
                           "identical fingerprint are adopted instead of rerun")
            p.add_argument("--big-input-gb", type=float, default=0.5,
                           help="notebooks whose scaled input exceeds this run one at a time")
            p.add_argument("--stop-plan", default=None, help="R5 B1: JSON {'engine|nb': last cell index}")
        else:
            p.add_argument("--ref", default="ref")
            p.add_argument("--ref2", default=None)
            p.add_argument("--workers", type=int, default=4)
            p.add_argument("--big-input-gb", type=float, default=0.5,
                           help="notebooks whose scaled input exceeds this are compared by one worker")
            p.add_argument("--hard-budget", type=float, default=0,
                           help="seconds; workers start no new job after this (the rest is done next time)")
            p.add_argument("--big-workers", type=int, default=2,
                           help="workers for notebooks above --big-input-gb (pilot: 4 at once peaked at 104 GB)")
    for name in ("summarize", "status"):
        p = sub.add_parser(name)
        p.add_argument("--campaign", required=True)
    a = ap.parse_args(argv)
    if getattr(a, "input_capture_max_gb", None) is not None:
        INPUT_CAPTURE_MAX_GB = a.input_capture_max_gb
    if getattr(a, "nb_mem_limit_gb", None) is not None:
        NB_MEM_LIMIT_GB = a.nb_mem_limit_gb
    if getattr(a, "stop_plan", None):
        STOP_PLAN.update(util.read_json(a.stop_plan, {}) or {})
    _install_signal_handlers()
    return {"run": cmd_run, "compare": cmd_compare, "summarize": cmd_summarize, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())

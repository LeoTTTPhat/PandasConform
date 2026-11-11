#!/usr/bin/env python3
"""D1 comparisons with the UNCHANGED comparator (src/pconf classify/dfeq, compare tag d92c8db54d45b), in envs/ref.

For every replay record listed in d1_run_<tag>.json:
  vsref  classify_run(original ref record, replay record, ref2 = original ref#2 record)   (as the paper's compare)
  self   classify_run(original engine record, replay record, ref2 = None)                 (engine vs its own replay)
Blobs are read from work/r5_replay/captures first and else from the released store (read only; r5common.patch_union_store).
Outputs: work/r5_replay/compare/{vsref,self}/<engine>/<nb key>.json (existing outputs are kept: resumable).

Run under the memory guard (decodes large frames), from the workspace root:
    python3 tools/memory_guard.py --start-if-fits --wait-lock 3600 --limit-gb 60 \
      --state runs/06_pandas_conformance_r5_replay_d1cmp.json -- \
      env PYTHONPATH=06_pandas_conformance-ICDE/src 06_pandas_conformance-ICDE/envs/ref/bin/python \
      06_pandas_conformance-ICDE/icde27/analysis/r5_replay/d1_compare.py --tags d1 --workers 6
"""
import argparse
import multiprocessing as mp
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import r5common as R  # noqa: E402

sys.path.insert(0, R.SRC)
OUT = os.path.join(R.WORK, "compare")


def _init():
    R.patch_union_store(R.REPLAY_STORE, R.SHARED_STORE)


def one(job):
    from pconf import classify, util
    out = job["out"]
    if os.path.exists(out):
        return job["kind"], "skipped", 0.0
    t0 = time.time()
    try:
        ref = util.read_json(job["ref"])
        eng = util.read_json(job["eng"])
        ref2 = util.read_json(job["ref2"]) if job.get("ref2") else None
        res = classify.classify_run(ref, eng, R.SHARED_STORE, ref2=ref2)
        res["meta"] = {"kind": job["kind"], "engine": job["engine"], "nb": job["nb"], "role": job["role"],
                       "ref_record": os.path.relpath(job["ref"], R.PROJ), "eng_record": os.path.relpath(job["eng"], R.PROJ),
                       "ref2_record": os.path.relpath(job["ref2"], R.PROJ) if job.get("ref2") else None,
                       "compare_sha": util.compare_sha(), "seconds": round(time.time() - t0, 3),
                       "ref_status": ref.get("status"), "eng_status": eng.get("status")}
        util.atomic_write_json(out, res)
        return job["kind"], "done", time.time() - t0
    except Exception as e:  # recorded, never hidden
        return job["kind"], "error %s: %s" % (type(e).__name__, str(e)[:200]), time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", default="d1")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--d3", action="store_true", help="compare the D3 serial-variant records (d3_run_d3n2.json) "
                    "with the original reference (vsref only) into compare/serial/<variant>/")
    ap.add_argument("--self-all", action="store_true", help="with --only-need: still run the cheap self comparison "
                    "for every replayed notebook")
    ap.add_argument("--max-input-gb", type=float, default=None, help="only notebooks whose input is at most this")
    ap.add_argument("--min-input-gb", type=float, default=None, help="only notebooks whose input exceeds this")
    ap.add_argument("--only-need", action="store_true",
                    help="compare only the notebooks d1_hashcheck.json lists as not hash-identical to the original run")
    a = ap.parse_args()
    if int(os.environ.get("MEMGUARD_RESTART", "0") or 0) > 0:
        a.workers = 1          # after a memory stop the guard restarts the job: compare one notebook at a time
    need = None
    if a.only_need:
        hc = R.read_json(os.path.join(HERE, "d1_hashcheck.json"))
        need = {tuple(x) for x in hc["need_full_compare"]}
    plan = R.read_json(os.path.join(HERE, "d1_plan.json"))
    meta = {}
    for eng, e in plan["engines"].items():
        for nbe in e["notebooks"] + e["controls"]:
            meta[(eng, nbe["nb"])] = nbe
    jobs = []
    if a.d3:
        results = []
        for fn in ("d3_run_d3n2.json", "d3_run_ext.json"):
            results += (R.read_json(os.path.join(HERE, fn)) or {}).get("results", [])
        for r in results:
            if not r.get("record"):
                continue
            key = R.nb_key(r["nb"]) + ".json"
            jobs.append({"kind": "serial", "engine": r["variant"], "nb": r["nb"], "role": "d3n2",
                         "ref": R.original_record("ref", r["nb"]), "eng": os.path.join(R.PROJ, r["record"]),
                         "ref2": R.original_record("ref#2", r["nb"]), "out": os.path.join(OUT, "serial", r["variant"], key)})
        a.tags = ""
    for tag in [t for t in a.tags.split(",") if t]:
        run = R.read_json(os.path.join(HERE, "d1_run_%s.json" % tag)) or {}
        for r in run.get("results", []):
            if not r.get("record"):
                continue
            skip_vsref = need is not None and (r["engine"], r["nb"]) not in need
            if skip_vsref and not a.self_all:
                continue
            m = meta[(r["engine"], r["nb"])]
            rec = os.path.join(R.PROJ, r["record"])
            key = R.nb_key(r["nb"]) + ".json"
            if not skip_vsref:
                jobs.append({"kind": "vsref", "engine": r["engine"], "nb": r["nb"], "role": r["role"],
                             "ref": os.path.join(R.PROJ, m["ref_record"]), "eng": rec,
                             "ref2": os.path.join(R.PROJ, m["ref2_record"]) if m.get("ref2_record") else None,
                             "out": os.path.join(OUT, "vsref", r["engine"], key)})
            jobs.append({"kind": "self", "engine": r["engine"], "nb": r["nb"], "role": r["role"],
                         "ref": os.path.join(R.PROJ, m["eng_record"]), "eng": rec, "ref2": None,
                         "out": os.path.join(OUT, "self", r["engine"], key)})
    if a.max_input_gb is not None or a.min_input_gb is not None:
        from pconf import datasets
        size = {}
        def ok(nb):
            if nb not in size:
                size[nb] = datasets.input_bytes(nb) / 1e9
            if a.max_input_gb is not None and size[nb] > a.max_input_gb:
                return False
            if a.min_input_gb is not None and size[nb] <= a.min_input_gb:
                return False
            return True
        jobs = [j for j in jobs if ok(j["nb"])]
    print("jobs", len(jobs), flush=True)
    t0 = time.time()
    counts = {}
    with mp.Pool(a.workers, initializer=_init) as pool:
        for kind, st, sec in pool.imap_unordered(one, jobs):
            k = st if not st.startswith("error") else "error"
            counts[k] = counts.get(k, 0) + 1
            if st.startswith("error"):
                print("[cmp]", kind, st, flush=True)
    print({"jobs": len(jobs), "counts": counts, "seconds": round(time.time() - t0, 1)}, flush=True)


if __name__ == "__main__":
    main()

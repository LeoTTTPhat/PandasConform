#!/usr/bin/env python3
"""D3 checks N3, N1 and N6 on existing records (envs/ref, read only; no new runs). Writes d3_checks.json.
    env PYTHONPATH=06_pandas_conformance-ICDE/src nice 06_pandas_conformance-ICDE/envs/ref/bin/python \
        06_pandas_conformance-ICDE/icde27/analysis/r5_replay/d3_checks.py

N3 cross-configuration injection: classify_run(ref = partner record, eng = engine record) with the unchanged comparator;
   the partner differs from the reference only by the claimed mechanism (pyarrow backend: Arrow-backed dtypes; pandas
   3.0.6: Copy-on-Write). confirmed: the engine cell agrees with the partner at E4 or finer; not confirmed: DIFF against
   the partner; inconclusive: partner failed or outputs not comparable.
N1 single-mechanism sufficiency: each output of the cell that is not E0 against the reference is decoded on both sides;
   ONLY the claimed mechanism's relaxation is applied to both; confirmed if every such output is then equal (exact,
   or within rtol 1e-9 for float_tol), not confirmed otherwise.
N6 printed-form census: confirmed if r4_printed_forms.json lists the cell with class DIFF (its outputs are compared
   by printed form).
"""
import collections
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import r5common as R  # noqa: E402

sys.path.insert(0, R.SRC)
OUT = os.path.join(HERE, "d3_checks.json")
DRIFT_RUNS = os.path.join(R.PROJ, "results", "drift", "raw", "runs__hd1c421ecb5ee")
PILOT_RUNS = os.path.join(R.PROJ, "results", "pilot", "raw", "runs__hd1c421ecb5ee")


def record_for(label, nb, campaign):
    if label in ("p15", "p30"):
        return R.original_record(label, nb, DRIFT_RUNS)
    if campaign == "pilot":
        return R.original_record(label, nb, PILOT_RUNS)
    return R.original_record(label, nb)


def ref_record_for(nb, campaign):
    return R.original_record("ref", nb, PILOT_RUNS if campaign == "pilot" else (DRIFT_RUNS if campaign == "drift" else R.CONF1X_RUNS))


CACHE = os.path.join(R.WORK, "d3checks")


def _init():
    R.patch_union_store(R.REPLAY_STORE, R.SHARED_STORE)


def _n3_job(t):
    label, partner, nb, cp = t
    if os.path.exists(cp):
        return "cached %s %s %s" % (label, partner, nb)
    from pconf import classify
    ts = time.time()
    er = R.read_json(record_for(label, nb, "conf_1x"))
    pr = R.read_json(record_for(partner, nb, "drift" if partner in ("p15", "p30") else "conf_1x"))
    try:
        res = classify.classify_run(pr, er, R.SHARED_STORE, ref2=None)
        cells = {str(x["i"]): {"cls": x["cls"], "fails": {k: (v.get("fails") or {}).get("E4") for k, v in (x.get("outputs") or {}).items()
                                                          if v.get("level") not in ("E0", None)}} for x in res["cells"]}
        R.write_json(cp, {"label": label, "partner": partner, "nb": nb, "seconds": round(time.time() - ts, 1), "cells": cells})
        return "done %s %s %s %.0fs" % (label, partner, nb, time.time() - ts)
    except Exception as e:
        return "error %s %s %s: %s: %s" % (label, partner, nb, type(e).__name__, str(e)[:120])


# ---------------------------------------------------------------- N1 relaxations on decoded pandas values
def _canon_series(s, how):
    import numpy as np
    import pandas as pd
    if how == "canon_dtype":
        if pd.api.types.is_bool_dtype(s.dtype) or pd.api.types.is_numeric_dtype(s.dtype):
            try:
                return pd.Series(pd.to_numeric(s, errors="coerce").astype("float64").to_numpy(na_value=np.nan) if hasattr(s, "to_numpy") else s,
                                 index=s.index, name=s.name)
            except Exception:
                pass
        vals = [None if (v is None or v is pd.NA or (isinstance(v, float) and v != v) or v is pd.NaT) else
                (float(v) if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool) else
                 (str(v) if not isinstance(v, (bool, np.bool_)) else bool(v))) for v in s.astype(object).tolist()]
        return pd.Series(vals, index=s.index, name=s.name, dtype=object)
    if how == "unify_missing":
        if s.dtype == object:
            vals = [np.nan if (v is None or v is pd.NA or v is pd.NaT or (isinstance(v, float) and v != v)) else v for v in s.tolist()]
            return pd.Series(vals, index=s.index, name=s.name, dtype=object)
        return s
    return s


def relax(v, how):
    import pandas as pd
    if isinstance(v, pd.DataFrame):
        if how == "sort_rows":
            w = v.reset_index()
            try:
                w = w.sort_values(list(w.columns), kind="mergesort", na_position="last").reset_index(drop=True)
            except TypeError:
                w = w.astype(str).sort_values(list(w.columns), kind="mergesort").reset_index(drop=True)
            return w
        if how == "drop_index":
            return v.reset_index(drop=True)
        if how == "drop_names":
            w = v.copy()
            w.index = w.index.rename(None) if not isinstance(w.index, pd.MultiIndex) else w.index.set_names([None] * w.index.nlevels)
            w.columns = w.columns.rename(None) if not isinstance(w.columns, pd.MultiIndex) else w.columns.set_names([None] * w.columns.nlevels)
            return w
        if how in ("canon_dtype", "unify_missing"):
            w = pd.DataFrame({k: _canon_series(v.iloc[:, j], how) for j, k in enumerate(range(v.shape[1]))})
            w.columns = v.columns
            w.index = v.index if how == "unify_missing" else pd.Index([_canon_scalar(x) for x in v.index], dtype=object)
            return w
        return v
    if isinstance(v, pd.Series):
        if how == "sort_rows":
            return relax(v.to_frame(), how)
        if how == "drop_index":
            return v.reset_index(drop=True)
        if how == "drop_names":
            w = v.copy()
            w.name = None
            w.index = w.index.rename(None) if not isinstance(w.index, pd.MultiIndex) else w.index.set_names([None] * w.index.nlevels)
            return w
        if how in ("canon_dtype", "unify_missing"):
            w = _canon_series(v, how)
            if how == "canon_dtype":
                w.index = pd.Index([_canon_scalar(x) for x in v.index], dtype=object)
            return w
        return v
    if how == "canon_dtype":
        return _canon_scalar(v)
    return v


def _canon_scalar(x):
    import numpy as np
    import pandas as pd
    if x is None or x is pd.NA or x is pd.NaT or (isinstance(x, float) and x != x):
        return None
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x)
    return str(x) if not isinstance(x, (list, tuple, dict)) else x


def equal(a, b, how):
    import numpy as np
    import pandas as pd
    try:
        if isinstance(a, pd.DataFrame) and isinstance(b, pd.DataFrame):
            pd.testing.assert_frame_equal(a, b, check_exact=(how != "float_tol"), rtol=1e-9, atol=0.0)
            return True
        if isinstance(a, pd.Series) and isinstance(b, pd.Series):
            pd.testing.assert_series_equal(a, b, check_exact=(how != "float_tol"), rtol=1e-9, atol=0.0)
            return True
        if isinstance(a, (pd.Index,)) and isinstance(b, pd.Index):
            pd.testing.assert_index_equal(a, b, exact=True)
            return True
        if isinstance(a, np.ndarray) and isinstance(b, np.ndarray):
            if how == "float_tol" and a.dtype.kind == "f" and b.dtype.kind == "f" and a.shape == b.shape:
                return bool(np.allclose(a, b, rtol=1e-9, atol=0.0, equal_nan=True))
            return a.dtype == b.dtype and a.shape == b.shape and bool(np.array_equal(a, b, equal_nan=a.dtype.kind == "f"))
        if how == "float_tol" and isinstance(a, float) and isinstance(b, float):
            return a == b or abs(a - b) <= 1e-9 * max(abs(a), abs(b))
        return type(a) == type(b) and (a == b or (a != a and b != b))
    except AssertionError:
        return False
    except Exception:
        return False


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-input-gb", type=float, default=None, help="test mode: only notebooks with input at most this")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    t0 = time.time()
    from pconf import capture as C
    R.patch_union_store(R.REPLAY_STORE, R.SHARED_STORE)
    plan = R.read_json(os.path.join(HERE, "d3_plan.json"))
    pf = R.read_json(os.path.join(R.PROJ, "icde27", "analysis", "r4_printed_forms.json"))
    printed_diff = {(c[0], c[1], c[2]) for lab in pf["by_label"].values() for c in lab["cells"] if c[3] == "DIFF"}
    cells = plan["cells"]
    if a.max_input_gb is not None:
        from pconf import datasets
        cells = [c for c in cells if datasets.input_bytes(c["nb"]) <= a.max_input_gb * 1e9]
    out = {"item": "D3", "N3": {}, "N1": {}, "N6": {}, "test_mode_max_input_gb": a.max_input_gb}
    # ---- N3: one comparator run per (engine label, partner, notebook), cached per job (resumable), in a pool
    jobs = collections.defaultdict(list)
    for c in cells:
        if "N3" in c["tests"]:
            partner = plan["n3_partner"]["%s|%s" % (c["cause"], c["label"])]
            jobs[(c["label"], partner, c["nb"])].append(c)
    todo = []
    for (label, partner, nb), lst in sorted(jobs.items()):
        cp = os.path.join(CACHE, "N3", "%s__%s__%s.json" % (label, partner, R.nb_key(nb)))
        todo.append((label, partner, nb, cp))
    import multiprocessing as mp
    with mp.Pool(a.workers, initializer=_init) as pool:
        for st in pool.imap_unordered(_n3_job, todo):
            print("[N3]", st, flush=True)
    for (label, partner, nb), lst in sorted(jobs.items()):
        cp = os.path.join(CACHE, "N3", "%s__%s__%s.json" % (label, partner, R.nb_key(nb)))
        by_i = {int(k): v for k, v in (R.read_json(cp) or {}).get("cells", {}).items()}
        for c in lst:
            x = by_i.get(c["cell"])
            if x is None:
                verdict, cls = "inconclusive", None
            else:
                cls = x["cls"]
                verdict = "confirmed" if cls in ("E0", "E1", "E2", "E3", "E4") else ("not confirmed" if cls == "DIFF" else "inconclusive")
            out["N3"][c["id"]] = {"partner": partner, "cls_vs_partner": cls, "verdict": verdict,
                                  "fails_vs_partner": (x or {}).get("fails", {})}
    # ---- N1
    for c in cells:
        if "N1" not in c["tests"]:
            continue
        how = plan["n1_relax"][c["cause"]]
        er = R.read_json(record_for(c["label"], c["nb"], c["campaign"]))
        rr = R.read_json(ref_record_for(c["nb"], c["campaign"]))
        ec = next((x for x in er["cells"] if x["i"] == c["cell"]), None)
        rc = next((x for x in rr["cells"] if x["i"] == c["cell"]), None)
        verdicts, detail = [], {}
        for name, rh in ((rc or {}).get("outputs") or {}).items():
            eh = ((ec or {}).get("outputs") or {}).get(name)
            if not isinstance(rh, str) or not isinstance(eh, str) or rh == eh:
                continue
            try:
                rv = C.decode_to_pandas(R.SHARED_STORE, rr["objects"][rh])
                ev = C.decode_to_pandas(R.SHARED_STORE, er["objects"][eh])
                ok = equal(relax(rv, how), relax(ev, how), how)
                verdicts.append(ok)
                detail[name] = ok
            except Exception as e:
                detail[name] = "error %s: %s" % (type(e).__name__, str(e)[:120])
                verdicts.append(None)
        if not verdicts or any(v is None for v in verdicts):
            verdict = "inconclusive"
        else:
            verdict = "confirmed" if all(verdicts) else "not confirmed"
        out["N1"][c["id"]] = {"relaxation": how, "verdict": verdict, "outputs": detail}
    # ---- N6
    for c in cells:
        if "N6" in c["tests"]:
            out["N6"][c["id"]] = {"verdict": "confirmed" if (c["label"], c["nb"], c["cell"]) in printed_diff else "not confirmed"}
    out["seconds"] = round(time.time() - t0, 1)
    R.write_json(a.out, out)
    for k in ("N3", "N1", "N6"):
        print(k, dict(collections.Counter(v["verdict"] for v in out[k].values())))
    print("seconds", out["seconds"])


if __name__ == "__main__":
    main()

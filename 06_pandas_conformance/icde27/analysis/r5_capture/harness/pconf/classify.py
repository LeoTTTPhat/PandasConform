"""Per-cell classification of an engine run against the reference run (plan.md Section 2).

Outcome classes per cell (comparable cells are those where the reference cell ran without error):
  E0..E4        all captured outputs equal at that level (coarsest output decides)
  DIFF          some output not equal at E4 (or missing / of a different kind)
  ERR           engine raised, reference did not
  TIMEOUT       engine cell timed out, or the notebook timeout hit while this cell ran
  CRASH         the engine process died during this cell (native crash, abort)
  KILLED        the engine process was killed from outside during this cell, repeatedly
                (OOM killer / stray signal; see orchestrate: one retry before a record is kept)
  SETUP_ERR     the engine could not even start (all cells of the notebook)
  MEMORY        the engine's process tree exceeded the per-notebook memory cap during this cell
                (orchestrate.NB_MEM_LIMIT_GB, below the 120 GB guard limit)
  NOTRUN        not reached because the engine died at an earlier cell (never clean)
  UNCOMPARABLE  some output not serialisable or capped, none DIFF
  NOOUT         both ran, nothing capturable to compare (e.g. only prints or defs)
  REF_ERR       reference raised or timed out (cell excluded)
  NONDET        outputs (or status) differ between two reference runs: excluded for EVERY
                engine alike (decided from ref and ref#2 alone); the engine's own class is kept
                in cls_raw
FALLBACK is an orthogonal flag (engine fallback warnings in that cell).

Clean-input attribution. A cell's inputs are the names it reads (free AST loads, pre-cell
values captured by the runner) plus the globals read inside user functions it calls
(nbsource fn_globals, transitively; their last captured values before the cell). Module and
callable inputs are ignored; uncapturable or missing inputs make the cell unclean with an
explicit reason. Two flags are reported (fix of review finding A1, 2026-10-02):
  clean_input   strict: every input E0-equal (object hashes equal)  [plan definition]
  clean_level   the coarsest lattice level needed for the inputs to be equal (E0..E4), None if
                some input differs at E4 or is uncapturable. A cell is clean@Ek iff clean_level
                <= Ek; summaries report both the strict counts and clean@E0..E4.
For the cell where the engine died, inputs are taken from the engine's last captured values.
Runs without pre-cell input capture (notebooks with large inputs, orchestrate.INPUT_CAPTURE_MAX_GB)
take every cell's inputs from the last captured values of the names it reads (row inputs_from =
'last_captured'); mutations through aliases are then invisible to the clean-input test.
Per notebook we report the first divergent cell at each level (cascades are never double-counted).
"""
from pconf import dfeq

FAMILY_PATTERNS = [
    ("read", ("read_csv", "read_excel", "read_json", "read_parquet", "read_table")),
    ("merge_join", ("merge", "join", "concat", "append", "combine_first")),
    ("groupby_agg", ("groupby", "agg", "aggregate", "transform", "resample", "rolling", "expanding", "size", "nunique")),
    ("sort", ("sort_values", "sort_index", "nlargest", "nsmallest", "rank")),
    ("string", ("str",)),
    ("datetime", ("dt", "to_datetime", "to_timedelta", "date_range")),
    ("apply_map", ("apply", "map", "applymap", "replace", "where", "mask")),
    ("pivot_reshape", ("pivot", "pivot_table", "melt", "stack", "unstack", "crosstab", "explode", "get_dummies", "cut", "qcut")),
    ("describe_stats", ("describe", "mean", "median", "std", "var", "quantile", "corr", "cov", "sum", "min", "max", "count",
                        "value_counts", "mode", "cumsum", "skew", "kurt")),
    ("missing", ("isnull", "isna", "notnull", "notna", "fillna", "dropna", "interpolate", "ffill", "bfill")),
    ("dedup_unique", ("drop_duplicates", "duplicated", "unique")),
    ("indexing", ("loc", "iloc", "at", "iat", "query", "filter", "head", "tail", "sample", "reset_index", "set_index", "drop", "rename")),
    ("dtype_conv", ("astype", "to_numeric", "convert_dtypes", "infer_objects", "dtypes", "dtype")),
]


def op_families(attrs):
    s = set(attrs or [])
    fams = [name for name, keys in FAMILY_PATTERNS if s.intersection(keys)]
    return fams or ["other"]


def _resolve(run, key):
    """Output entry -> object record or a status string."""
    v = key
    if isinstance(v, str) and v in run["objects"]:
        return run["objects"][v]
    return v


_CMP_CACHE = {}   # (store, ref object hash, engine object hash) -> dfeq result (per process)


def _compare_cached(ra, ea, store):
    """dfeq.compare memoised on the two content hashes: identical object pairs recur across
    cells (a frame shown or mutated in many cells) and across the ref#2 non-determinism check."""
    key = (store, ra.get("h"), ea.get("h"))
    if key[1] is None or key[2] is None:
        return dfeq.compare(ra, ea, store)
    if key not in _CMP_CACHE:
        if len(_CMP_CACHE) > 20000:
            _CMP_CACHE.clear()
        _CMP_CACHE[key] = dfeq.compare(ra, ea, store)
    return dict(_CMP_CACHE[key])


def compare_outputs(ref, eng, cr, ce, store):
    """Compare all outputs of one cell. Returns (cell_level, per-output dict)."""
    outs = {}
    ro, eo = cr.get("outputs") or {}, ce.get("outputs") or {}
    for name in sorted(ro):
        rv = ro[name]
        if rv in ("absent",):
            continue
        if name not in eo:
            outs[name] = {"level": "DIFF", "reason": "missing_in_engine"}
            continue
        ev = eo[name]
        if rv == "deleted" or ev == "deleted":
            outs[name] = {"level": "E0" if rv == ev else "DIFF", "reason": "deleted:%s/%s" % (rv == "deleted", ev == "deleted")}
            continue
        if ev == "absent":
            outs[name] = {"level": "DIFF", "reason": "absent_in_engine"}
            continue
        if isinstance(rv, dict) and rv.get("kind") in ("module", "callable"):
            continue
        ra = _resolve(ref, rv)
        ea = _resolve(eng, ev)
        if isinstance(ra, dict) and "h" not in ra:
            ra = dict(ra, h=None)
        if isinstance(ea, dict) and "h" not in ea:
            ea = dict(ea, h=None)
        if (isinstance(ea, dict) and ea.get("kind") == "unconvertible" and ea.get("error")
                and isinstance(ra, dict) and ra.get("h") is not None):
            # the engine's own conversion raised: for lazy engines this is the error a notebook
            # would show when the cell's value is displayed -> the engine raised (ERR)
            outs[name] = {"level": "ERR", "reason": "materialize_error", "error": str(ea.get("error"))[:300]}
            continue
        if not isinstance(ra, dict) or not isinstance(ea, dict):
            outs[name] = {"level": "UNCOMPARABLE", "reason": "unresolved"}
            continue
        if ra.get("kind") in ("other",) and ea.get("kind") in ("other",) and ra.get("h") is None:
            continue  # neither side capturable (e.g. GroupBy objects): not an output under the plan
        try:
            res = _compare_cached(ra, ea, store)
        except Exception as e:  # comparator failure is recorded, never hidden
            res = {"level": "UNCOMPARABLE", "reason": "compare_error:%s: %s" % (type(e).__name__, str(e)[:200])}
        outs[name] = res
    levels = [o["level"] for o in outs.values()]
    if "ERR" in levels:
        return "ERR", outs
    return (dfeq.worst(levels) if levels else "NOOUT"), outs


_DEATH = {"nb_crash": "CRASH", "nb_killed": "KILLED", "nb_timeout": "TIMEOUT", "engine_setup_error": "SETUP_ERR",
          "nb_memory": "MEMORY"}
FAILURE_CLASSES = {"ERR", "TIMEOUT", "CRASH", "KILLED", "SETUP_ERR", "NOTRUN", "MEMORY"}
_VALUE_OK = set(dfeq.LEVELS)


class _Pairs:
    """Level of equality between two captured entries (hash strings / dicts), cached."""

    def __init__(self, ref, eng, store):
        self.ref, self.eng, self.store = ref, eng, store
        self.cache = {}

    def level(self, a, b):
        """-> (level in E0..E4 or None, reason or None, ignored: bool)"""
        if a is None or b is None:
            return None, "presence", False
        if isinstance(a, dict) or isinstance(b, dict):
            ka = a.get("kind") if isinstance(a, dict) else "obj"
            kb = b.get("kind") if isinstance(b, dict) else "obj"
            if ka in ("module", "callable") and kb in ("module", "callable"):
                return "E0", None, True
            return None, "uncapturable:%s/%s" % (ka, kb), False
        if a in ("absent", "deleted") or b in ("absent", "deleted"):
            return ("E0", None, False) if a == b else (None, "presence", False)
        if a == b:
            return "E0", None, False
        key = (a, b)
        if key not in self.cache:
            ra, rb = self.ref["objects"].get(a), self.eng["objects"].get(b)
            if ra is None or rb is None:
                self.cache[key] = (None, "unresolved")
            else:
                try:
                    lv = _compare_cached(ra, rb, self.store)["level"]
                except Exception as e:  # comparator failure: unclean, recorded
                    lv = "compare_error:%s" % type(e).__name__
                self.cache[key] = (lv, None) if lv in _VALUE_OK else (None, "differs:%s" % lv)
        lv, why = self.cache[key]
        return lv, why, False


def _coarsest(levels):
    if any(l is None for l in levels):
        return None
    return max(levels, key=lambda L: _RANK[L]) if levels else "E0"


def _inputs_level(pairs, items, levels_out=None):
    """items: [(name, ref_entry, eng_entry, tag)] -> (clean_level, reasons).
    Reasons: input_presence:<n>, uncapturable_input:<n>:<kinds>, input_differs:<n> (any level
    above E0; the level itself goes to levels_out), hidden_global_via_function:<n>."""
    levels, reasons = [], []
    for name, a, b, tag in items:
        lv, why, ignored = pairs.level(a, b)
        if ignored:
            continue
        levels.append(lv)
        if lv == "E0":
            continue
        if levels_out is not None:
            levels_out[name] = lv if lv is not None else (why or "DIFF")
        if tag != "input":
            reasons.append("%s:%s" % (tag, name))
        elif why == "presence":
            reasons.append("input_presence:%s" % name)
        elif why and why.startswith("uncapturable"):
            reasons.append("uncapturable_input:%s:%s" % (name, why.split(":", 1)[1]))
        else:
            reasons.append("input_differs:%s" % name)
    return _coarsest(levels), reasons


def _hidden_globals(static, fn_defs):
    """Globals read by user functions the cell calls (transitive closure), minus the cell's
    own loads (those are inputs already)."""
    called = [n for n in (static.get("loads") or []) if n in fn_defs]
    own = static.get("fn_globals") or {}
    called += [n for n in (static.get("bound_loads") or []) if n in own]
    seen, todo, out = set(), list(called), set()
    while todo:
        f = todo.pop()
        if f in seen:
            continue
        seen.add(f)
        for g in (own.get(f) if f in own else fn_defs.get(f, ())):
            if g in fn_defs or g in own:
                todo.append(g)
            else:
                out.add(g)
    return sorted(out - set(static.get("loads") or []) - seen)


def _update_last(last, cell):
    for k in ("inputs", "outputs"):
        for name, v in (cell.get(k) or {}).items():
            if name == "__last__":
                continue
            if v == "absent":
                continue
            last[name] = v


def classify_run(ref, eng, store, ref2=None):
    """ref, eng (and optional second reference replicate) are run records from runner_child.
    Returns {cells: [...], first_divergent: {level: cell}, summary: {...}}."""
    out_cells = []
    eng_cells = {c["i"]: c for c in eng.get("cells", [])}
    ref2_cells = {c["i"]: c for c in (ref2 or {}).get("cells", [])}
    eng_status = eng.get("status")
    death = None if eng_status == "completed" else _DEATH.get(eng_status, "CRASH")
    pairs = _Pairs(ref, eng, store)
    last_ref, last_eng, fn_defs = {}, {}, {}
    died_at = None
    for cr in ref.get("cells", []):
        i = cr["i"]
        ce = eng_cells.get(i)
        static = cr.get("static") or {}
        if cr["status"] in ("setup", "skipped", "empty", "setup_error"):
            _update_last(last_ref, cr)
            if ce is not None:
                _update_last(last_eng, ce)
            continue
        row = {"i": i, "families": op_families(static.get("attrs"))}
        # non-determinism: a property of the cell (ref vs ref#2), identical for every engine
        nondet, nondet_reason = False, None
        if ref2 is not None and cr["status"] not in ("error", "timeout", "syntax_error"):
            c2 = ref2_cells.get(i)
            if c2 is None or c2.get("status") != "ok":
                nondet, nondet_reason = True, "ref2_status:%s" % (c2 or {}).get("status")
            else:
                lvl2, _ = compare_outputs(ref, ref2, cr, c2, store)
                if lvl2 not in ("E0", "NOOUT"):
                    nondet, nondet_reason = True, "ref2_level:%s" % lvl2
        if cr["status"] in ("error", "timeout", "syntax_error"):
            row["cls"] = "REF_ERR"
            row["ref_exc"] = cr.get("exc_type")
            if ce is not None:
                row["eng_status"] = ce.get("status")
            elif death is not None and died_at is None:
                died_at = i
                row["eng_status"] = "died:%s" % eng_status
            out_cells.append(row)
        else:
            hidden = _hidden_globals(static, fn_defs)
            hidden_items = [(g, last_ref.get(g), last_eng.get(g), "hidden_global_via_function")
                            for g in hidden if g in last_ref or g in last_eng]
            in_levels = {}
            if ce is None:
                if death is None:
                    row["cls"], row["reason"] = "ERR", "engine_missing_cell"
                    lvl, reasons = None, ["engine_missing_cell"]
                elif death == "SETUP_ERR":
                    row["cls"] = "SETUP_ERR"
                    row["reason"] = (eng.get("error") or "")[:200]
                    lvl, reasons = None, ["engine_setup_error"]
                elif died_at is None:
                    died_at = i
                    row["cls"], row["reason"] = death, "engine_run_%s" % eng_status
                    # inputs of the dying cell: ref pre-cell values vs the engine's last values
                    if cr.get("inputs") is None:
                        items = [(n, last_ref.get(n), last_eng.get(n), "input") for n in (static.get("loads") or [])
                                 if n in last_ref or n in last_eng]
                    else:
                        items = [(n, v, last_eng.get(n), "input") for n, v in sorted((cr.get("inputs") or {}).items())]
                    lvl, reasons = _inputs_level(pairs, items + hidden_items, in_levels)
                else:
                    row["cls"], row["reason"] = "NOTRUN", "after_engine_%s_at_cell_%s" % (eng_status, died_at)
                    lvl, reasons = None, ["not_reached"]
            else:
                row["fallback"] = bool(ce.get("flags")) and any("fallback" in f or "default_to_pandas" in f
                                                               for f in ce.get("flags", []))
                if ce.get("flags"):
                    row["flags"] = ce["flags"]
                if cr.get("inputs") is None and ce.get("inputs") is None:
                    # run without pre-cell input capture (large inputs): AST-visible inputs, i.e.
                    # the last captured values of the names the cell reads
                    items = [(n, last_ref.get(n), last_eng.get(n), "input") for n in (static.get("loads") or [])
                             if n in last_ref or n in last_eng]
                    row["inputs_from"] = "last_captured"
                else:
                    ri, ei = cr.get("inputs") or {}, ce.get("inputs") or {}
                    items = [(n, ri.get(n), ei.get(n), "input") for n in sorted(set(ri) | set(ei))]
                lvl, reasons = _inputs_level(pairs, items + hidden_items, in_levels)
                if ce["status"] == "timeout":
                    row["cls"] = "TIMEOUT"
                elif ce["status"] in ("error", "syntax_error"):
                    row["cls"] = "ERR"
                    row["eng_exc"] = ce.get("exc_type")
                    row["eng_msg"] = (ce.get("exc_msg") or "")[:200]
                    row["eng_origin"] = ce.get("exc_origin")
                else:
                    cls, outs = compare_outputs(ref, eng, cr, ce, store)
                    row["cls"] = cls
                    row["outputs"] = outs
                    if cls == "ERR":
                        err = next(o for o in outs.values() if o["level"] == "ERR")
                        row["eng_exc"] = "materialize_error"
                        row["eng_msg"] = err.get("error", "")[:200]
            row["clean_level"] = lvl
            row["clean_input"] = lvl == "E0"
            if reasons:
                row["unclean"] = reasons[:10]
            if in_levels:
                row["input_levels"] = dict(list(sorted(in_levels.items()))[:20])
            if hidden_items:
                row["hidden_globals"] = [g for g, _, _, _ in hidden_items][:20]
            if nondet:
                row["nondet"] = True
                row["nondet_reason"] = nondet_reason
                row["cls_raw"] = row["cls"]
                row["cls"] = "NONDET"
            out_cells.append(row)
        for n, d in (static.get("fn_globals") or {}).items():
            fn_defs[n] = list(d)
        _update_last(last_ref, cr)
        if ce is not None:
            _update_last(last_eng, ce)
    return {"cells": out_cells, "first_divergent": first_divergent(out_cells), "summary": summarize(out_cells)}


_RANK = {L: i for i, L in enumerate(dfeq.LEVELS)}


def _fails_at(cls, level):
    """Does a cell outcome break equality at `level`?"""
    if cls in ("NOOUT", "REF_ERR", "NONDET"):
        return False
    if cls in _RANK:
        return _RANK[cls] > _RANK[level]
    return True  # DIFF, UNCOMPARABLE and the failure classes


def _divergence_class(c):
    """NONDET hides value differences, never an engine failure (error, crash, timeout)."""
    if c["cls"] == "NONDET" and c.get("cls_raw") in FAILURE_CLASSES:
        return c["cls_raw"]
    return c["cls"]


def first_divergent(cells):
    res = {}
    for L in dfeq.LEVELS:
        res[L] = next((c["i"] for c in cells if _fails_at(_divergence_class(c), L)), None)
    return res


def summarize(cells):
    s = {"n_cells": len(cells), "by_class": {}, "clean_by_class": {}, "fallback_cells": 0, "clean_cells": 0,
         "clean_at": {L: {} for L in dfeq.LEVELS}, "clean_cells_at": {L: 0 for L in dfeq.LEVELS},
         "nondet_cells": 0, "hidden_global_cells": 0}
    for c in cells:
        s["by_class"][c["cls"]] = s["by_class"].get(c["cls"], 0) + 1
        if c.get("fallback"):
            s["fallback_cells"] += 1
        if c.get("nondet"):
            s["nondet_cells"] += 1
        if c.get("hidden_globals"):
            s["hidden_global_cells"] += 1
        if c.get("clean_input"):
            s["clean_cells"] += 1
            s["clean_by_class"][c["cls"]] = s["clean_by_class"].get(c["cls"], 0) + 1
        lv = c.get("clean_level")
        if lv in _RANK:
            for L in dfeq.LEVELS:
                if _RANK[lv] <= _RANK[L]:
                    s["clean_cells_at"][L] += 1
                    s["clean_at"][L][c["cls"]] = s["clean_at"][L].get(c["cls"], 0) + 1
    return s

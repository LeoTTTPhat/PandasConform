"""Collect, from existing result files, every paper number that had no machine-readable source
(audit fix A15, 2026-10-04) and the derived counts the audit fixes need (A4, A6, A9, A16, A17,
A19, A21, A22). Writes results/rootcause/paper_provenance.json. Read-only on everything else:
it reads run records, compare outputs, check/metrics/environment/summary files, notebook sets,
prep markers and the taxonomy files; it imports src/pconf only to read constants.

Usage (from 06_pandas_conformance/):  ../.venv/bin/python scripts/paper_provenance.py
"""
import collections, glob, importlib.util, inspect, json, os, sys, time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
from pconf import capture, dfeq, engines, orchestrate  # noqa: E402  (constants only)

H = "hd1c421ecb5ee"
D = "d92c8db54d45b"
OLD_D = "da915cb28b4c6"
R = os.path.join(HERE, "results")


def jload(*p):
    with open(os.path.join(*p)) as f:
        return json.load(f)


def run_records(campaign, engine):
    """Latest record per notebook for one engine of one campaign."""
    d = os.path.join(R, campaign, "raw", "runs__" + H, orchestrate.engine_tag(engine), "sf1")
    best = {}
    for fn in glob.glob(os.path.join(d, "*.json")):
        r = jload(fn)
        if r.get("nb") is None:
            continue
        if r["nb"] not in best or r.get("finished", 0) > best[r["nb"]].get("finished", 0):
            best[r["nb"]] = r
    return best


def comparator_constants():
    env = jload(R, "drift", "environment.json")["dfeq"]
    return {"source": "results/drift/environment.json dfeq + src/pconf constants (read-only import)",
            "float_rtol": env["float_rtol"], "match_group_rows": env["match_limit"],
            "match_budget_pairs": env["match_budget"], "max_exact_int": env["max_exact_int"],
            "round_sig_digits": inspect.signature(dfeq._round_sig).parameters["sig"].default,
            "object_element_tags": capture.T_INTERVAL + 1,
            "capture_max_cells": capture.DEFAULT_LIMITS["max_cells"],
            "input_capture_max_gb": orchestrate.INPUT_CAPTURE_MAX_GB,
            "nb_mem_limit_gb": orchestrate.NB_MEM_LIMIT_GB,
            "run_cfg_timeouts": sorted({(r["cfg"].get("cell_timeout"), r["cfg"].get("nb_timeout"))
                                        for camp, eng in (("drift", "ref"), ("drift", "p15"), ("drift", "p30"),
                                                          ("conf_1x", "modin"), ("conf_1x", "bodo"))
                                        for r in run_records(camp, eng).values()}),
            "guard": jload(R, "drift", "environment.json")["guard"],
            "host": jload(R, "drift", "environment.json")["host"],
            "engine_env_versions": engine_versions(),
            "engine_settings": {k: {"doc": v.get("doc"), "env_vars": v.get("env_vars", {})}
                                for k, v in engines.ENGINES.items()}}


KEY_PACKAGES = ("pandas", "numpy", "pyarrow", "modin", "ray", "fireducks", "bodo", "dask", "numba")


def engine_versions():
    envs = jload(R, "conf_1x", "environment.json")["engine_envs"]
    envs.update({k: v for k, v in jload(R, "drift", "environment.json")["engine_envs"].items() if k not in envs})
    out = {}
    for name, e in sorted(envs.items()):
        pk = dict(x.split("==", 1) for x in e.get("packages", []) if "==" in x)
        out[name] = {k: pk[k] for k in KEY_PACKAGES if k in pk}
        if e.get("python"):
            out[name]["python"] = e["python"]
    return out


def corpus():
    sizes = jload(HERE, "data", "notebook_sets", "sizes.json")["input_bytes"]
    big = sorted(nb for nb, b in sizes.items() if b > orchestrate.INPUT_CAPTURE_MAX_GB * 1e9)
    # cross-check against the run configs actually used (drift ref records)
    recs = run_records("drift", "ref")
    off = sorted(nb for nb, r in recs.items() if r.get("cfg", {}).get("capture_inputs") is False)
    origins = collections.Counter()
    for fn in glob.glob(os.path.join(HERE, "work", "scaled", "sf1", "*", "*", ".pconf_prepared.json")):
        origins[jload(fn).get("scale_cell_origin")] += 1
    c5 = jload(HERE, "data", "notebook_sets", "conf5x.json")["notebooks"]
    mb = [sizes[nb] / 1e6 for nb in c5]
    met = jload(R, "drift", "metrics__runs__%s.json" % H)["per_engine"]
    p15 = met["p15"]
    ref = met["ref"]
    prov = jload(HERE, "data", "provenance.json")
    data = {"source": "data/provenance.json + data/notebook_sets/sizes.json",
            "commit": prov["code"]["commit"], "code_license": prov["code"]["license"],
            "archive_bytes": prov["data_archive"]["bytes"], "archive_gb": round(prov["data_archive"]["bytes"] / 1e9, 2),
            "archive_sha256": prov["data_archive"]["sha256"], "archive_tool": prov["data_archive"]["tool"],
            "mirror_tried": prov["data_archive"]["mirror_tried"], "data_license": prov["data_archive"]["license"],
            "extracted_files": prov["data_manifest_files"], "extracted_gb": round(prov["data_manifest_bytes"] / 1e9, 2),
            "notebook_input_gb_1x": round(jload(HERE, "data", "notebook_sets", "sizes.json")["total"] / 1e9, 1),
            "pandasbench_reported_cells": 3721,
            "pandasbench_reported_cells_source": "PandasBench paper (arXiv:2506.02345), verified on the web 2026-10-04"}
    return {"notebooks": len(sizes), "data": data,
            "input_over_capture_cap": {"n": len(big), "notebooks": big,
                                       "drift_ref_records_capture_inputs_false": len(off),
                                       "same_set": big == off},
            "scale_cell_origin": dict(origins),
            "conf5x": {"n": len(c5), "min_mb": round(min(mb), 1), "max_mb": round(max(mb), 1),
                       "total_gb": round(sum(mb) / 1e3, 2)},
            "cells_per_config_p15": {"executed": int(p15["cellstatus:ok"] + p15.get("cellstatus:error", 0)
                                                     + p15.get("cellstatus:syntax_error", 0)),
                                     "empty": int(p15["cellstatus:empty"]), "setup": int(p15["cellstatus:setup"]),
                                     "source": "results/drift/metrics__runs__%s.json per_engine.p15" % H},
            "drift_ref_time_s": {k: round(ref[k]) for k in ("cell_s", "capture_in_s", "capture_out_s", "wall_s")},
            "drift_ref_time_outside_cells_and_capture_s": round(ref["wall_s"] - ref["cell_s"] - ref["capture_in_s"]
                                                                - ref["capture_out_s"])}


def checks():
    out = {}
    for camp in ("drift", "conf_1x"):
        ck = jload(R, camp, "check__all_%s__%s.json" % (H, D))
        out[camp] = {"store": ck["store"],
                     "match_limit": {e: v.get("match_limit", 0) for e, v in ck["oracle"].items() if "cells" in v}}
    out["drift"]["hidden_global_cells"] = jload(R, "drift", "summary__%s__%s.json" % (H, D))["p15"]["hidden_global_cells"]
    return out


def reclassification():
    """Per-cell identity of the final comparator (D) and the earlier one (OLD_D) on pilot and drift."""
    out = {}
    for camp in ("pilot", "drift"):
        new_root = os.path.join(R, camp, "raw", "compare__%s__%s" % (H, D))
        old_root = os.path.join(R, camp, "raw", "compare__%s__%s" % (H, OLD_D))
        files = cells = differing = 0
        unmatched = 0
        for fn in glob.glob(os.path.join(new_root, "**", "*.json"), recursive=True):
            rel = os.path.relpath(fn, new_root)
            ofn = os.path.join(old_root, rel)
            if not os.path.exists(ofn):
                unmatched += 1
                continue
            a, b = jload(fn), jload(ofn)
            ka = {c["i"]: (c.get("cls"), c.get("clean_level"), c.get("cls_raw")) for c in a["cells"]}
            kb = {c["i"]: (c.get("cls"), c.get("clean_level"), c.get("cls_raw")) for c in b["cells"]}
            files += 1
            cells += len(ka)
            differing += sum(1 for i in set(ka) | set(kb) if ka.get(i) != kb.get(i))
        out[camp] = {"files_matched": files, "files_without_old_counterpart": unmatched,
                     "cells": cells, "cells_differing": differing}
    out["total_cells"] = out["pilot"]["cells"] + out["drift"]["cells"]
    return out


def validation():
    p = os.path.join(R, "rootcause", "comparator_validation.json")
    if not os.path.exists(p):
        return None
    v = jload(p)
    return {k: v[k] for k in ("compare_tag", "trials_total", "mismatches_total", "runs_ok", "runs_total",
                              "by_pandas", "oracle_levels_total", "generated")}


def memory_and_stops(tax):
    cells = tax["causes"]["resource_memory_cap"]["cells"]
    recs = {}
    split = collections.Counter()
    by = collections.Counter()
    for camp, eng, nb, cell, cls in cells:
        key = (camp, eng)
        if key not in recs:
            recs[key] = run_records(camp, eng)
        st = recs[key][nb]["status"]
        split[st] += 1
        by["%s:%s:%s:%s" % (camp, eng, st, cls)] += 1
    modin = run_records("conf_1x", "modin")
    mem = []
    for nb, r in sorted(modin.items()):
        if r["status"] != "nb_memory":
            continue
        rss = [c.get("rss_after") for c in r.get("cells", []) if c.get("rss_after")]
        mem.append({"nb": nb, "peak_tree_rss_gb": r.get("peak_tree_rss_gb"),
                    "runner_max_rss_after_gb": round(max(rss) / 1e9, 1) if rss else None})
    return {"resource_memory_cap_cells": len(cells), "by_run_status": dict(split), "detail": dict(by),
            "modin_nb_memory": mem,
            "note": "orchestrate tree RSS sums psutil RSS over the process tree (shared pages count once per process)"}


def first_e4(summary):
    out = {}
    for camp in ("drift", "conf_1x"):
        for eng, e in summary["campaigns"][camp]["engines"].items():
            if eng == "ref#2":
                continue
            cnt = collections.Counter()
            for nb, fd in e["first_divergence_per_notebook"].items():
                x = (fd or {}).get("E4")
                if x:
                    cnt[x["cls"]] += 1
            out["%s:%s" % (camp, eng)] = {"notebooks": sum(cnt.values()), "by_cls": dict(cnt)}
    return out


ROOT_FAMILY_EXCLUDED = ("not_a_root_cause", "nondeterminism")
SYMPTOM = ("engine_bug_error", "engine_unsupported_api", "engine_bug_silent", "engine_crash_timeout",
           "dtype_inference_differs")


def taxonomy_counts(tax, tax_drift):
    causes = {k: v for k, v in tax["causes"].items() if v.get("family") not in ROOT_FAMILY_EXCLUDED}
    pandas_rep = sorted(k for k, v in causes.items() if v.get("repro_runs"))
    eng_conf = sorted(k for k, v in causes.items() if (v.get("engine_probe_outcome") or {}).get("verdict") == "confirmed")
    eng_not = sorted(k for k, v in causes.items() if (v.get("engine_probe_outcome") or {}).get("verdict")
                     and v["engine_probe_outcome"]["verdict"] != "confirmed")
    reproduced = sorted(set(pandas_rep) | set(eng_conf))
    none = sorted(k for k in causes if k not in reproduced and k not in eng_not)
    eng_intro = {k: v["introduced"] for k, v in tax["per_engine"].items()
                 if (k.startswith("conf_1x:") or k == "pilot:bodo_dw") and "introduced" in v}
    n_eng = sum(eng_intro.values())
    symptom = {c: sum(n for lab, n in tax["causes"][c]["by_engine"].items() if not lab.startswith("drift:"))
               for c in SYMPTOM}
    un = sum(n for lab, n in tax["causes"]["unattributed"]["by_engine"].items() if not lab.startswith("drift:"))
    pilot_intro = sum(v.get("introduced", 0) for k, v in tax["per_engine"].items() if k.startswith("pilot:"))
    pilot_non_e0 = sum(n for k, v in tax["per_engine"].items() if k.startswith("pilot:")
                       for kk, n in v.items() if ":" not in kk and kk in ("introduced", "propagated", "harness",
                                                                          "cascade", "nondet"))
    fr = tax["causes"]["float_rounding_within_tolerance"]
    spec = importlib.util.spec_from_file_location("rct", os.path.join(HERE, "scripts", "rootcause_taxonomy.py"))
    rct = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rct)
    cat = sorted(k for k, v in tax["causes"].items() if "categor" in (k + " " + v.get("title", "")).lower())
    cat_order = sorted(k for k in cat if "order" in (k + " " + tax["causes"][k].get("title", "")).lower())
    return {"root_causes": len(causes),
            "reproducer_coverage": {"pandas_reproducer": len(pandas_rep), "engine_confirmed": len(eng_conf),
                                    "overlap": len(set(pandas_rep) & set(eng_conf)),
                                    "reproduced": len(reproduced), "engine_probe_not_reproduced_only": eng_not,
                                    "no_reproducer": none},
            "causes_mentioning_categorical": cat, "categorical_ordering_causes": cat_order,
            "engine_introduced_cells": n_eng, "engine_introduced_by_label": eng_intro,
            "engine_symptom_level_cells": symptom, "engine_unattributed_cells": un,
            "engine_symptom_or_unattributed": sum(symptom.values()) + un,
            "engine_symptom_or_unattributed_share": round((sum(symptom.values()) + un) / n_eng, 4),
            "pilot_label_cells": {"introduced": pilot_intro, "non_e0": pilot_non_e0,
                                  "introduced_bodo_dw": tax["per_engine"].get("pilot:bodo_dw", {}).get("introduced")},
            "float_rounding": {"by_class": fr["by_class"],
                               "diff_cells": [c for c in fr["cells"] if c[4] == "DIFF"]},
            "curated_cells": len(rct.CURATED),
            "rules": {"conf1x": len(tax["rules"]), "drift_only_taxonomy": len(tax_drift["rules"]),
                      "appended": len(tax["rules"]) - len(tax_drift["rules"]),
                      "prefix_unchanged": tax["rules"][:len(tax_drift["rules"])] == tax_drift["rules"]},
            "dask_cascade_cells": tax["per_engine"]["conf_1x:dask"].get("cascade"),
            "dask_top_introduced": sorted(((n, k.split(":", 1)[1]) for k, n in tax["per_engine"]["conf_1x:dask"].items()
                                           if k.startswith("introduced:")), reverse=True)[:5]}


def main():
    t0 = time.time()
    summary = jload(R, "summary.json")
    tax = jload(R, "rootcause", "taxonomy_conf1x.json")
    tax_drift = jload(R, "rootcause", "taxonomy.json")
    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "script": "scripts/paper_provenance.py",
           "harness_tag": H, "compare_tag": D,
           "comparator_constants": comparator_constants(), "corpus": corpus(), "checks": checks(),
           "reclassification_vs_" + OLD_D: reclassification(), "comparator_validation": validation(),
           "engine_stops": memory_and_stops(tax), "first_e4_divergent_class": first_e4(summary),
           "taxonomy": taxonomy_counts(tax, tax_drift)}
    out["runtime_s"] = round(time.time() - t0, 1)
    p = os.path.join(R, "rootcause", "paper_provenance.json")
    with open(p + ".tmp", "w") as f:
        json.dump(out, f, indent=1, sort_keys=True, default=str)
    os.replace(p + ".tmp", p)
    print(json.dumps({"written": p, "runtime_s": out["runtime_s"]}))


if __name__ == "__main__":
    main()

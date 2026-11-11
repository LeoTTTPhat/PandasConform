#!/usr/bin/env python3
"""Evidence classes of the taxonomy and the claim-to-contract-to-reproducer map (review round R5; ICDE 2027 copy;
written 2026-11-10).

Read-only on results/rootcause/{taxonomy_conf1x,engine_probe_outcomes}.json and icde27/analysis/r4_audit.json;
writes only icde27/analysis/r5_evidence.json and r5_claim_map.csv. Seconds; regenerates from the released files.

    cd ..
    .venv/bin/python 06_pandas_conformance-ICDE/icde27/analysis/r5_evidence.py

Each (cause, configuration) entry of the taxonomy with introduced cells gets one evidence class:
  documented incompatibility   a statement in the configuration's own documentation covers the difference (the
                               cause's doc_refs: pandas documentation for pandas 1.5.3, 3.0.6 and the pyarrow
                               backend, the engine's documentation for an engine) and the taxonomy rates the cause
                               documented ("yes");
  partly documented            such a statement exists but covers only some of the cause's operations (rated
                               "partial", for example Modin documents the precision of corr but not of sums);
  contradicts a compatibility claim  no such statement was found, and the configuration is a drop-in engine (Modin,
                               FireDucks, Bodo), whose documentation claims pandas compatibility after a one-line
                               import change: the observation conflicts with that stated claim, not with an
                               API-specific promise;
  no applicable promise found  neither (Dask, which is not a drop-in API, and pandas configurations without a
                               covering statement).
"Not searched" causes count by the same rule (no statement known). Entries outside the taxonomy's causes (the
cells the rules leave unattributed, and with the pure definition the 59 exception cells) are counted apart. Each
entry also carries its reproducer evidence (pandas reproducer differs on this configuration; engine probe confirms
or does not reproduce on this engine) and the documentation URL and quote.
"""
import collections
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "r5_evidence.json")
OUT_CSV = os.path.join(HERE, "r5_claim_map.csv")
NOT_CAUSES = {"cascade_undefined_name", "resource_memory_cap", "capture_cap", "unattributed", "order_propagated",
              "nondeterminism"}
DOC_HOSTS = {"p15": ("pandas.pydata.org", "github.com/pandas-dev"), "p30": ("pandas.pydata.org", "github.com/pandas-dev"),
             "pyarrow_backend": ("pandas.pydata.org", "github.com/pandas-dev"), "modin": ("modin.readthedocs.io",),
             "fireducks": ("fireducks-dev.github.io",), "dask": ("docs.dask.org", "github.com/dask"),
             "bodo": ("docs.bodo.ai",), "bodo_dw": ("docs.bodo.ai",)}
DROP_IN = {"modin", "fireducks", "bodo", "bodo_dw"}
ORDER = ["documented incompatibility", "partly documented", "contradicts a compatibility claim", "no applicable promise found"]


def main():
    tax = json.load(open(os.path.join(PROJ, "results", "rootcause", "taxonomy_conf1x.json")))
    probes = json.load(open(os.path.join(PROJ, "results", "rootcause", "engine_probe_outcomes.json")))
    r4 = json.load(open(os.path.join(HERE, "r4_audit.json")))
    rows, by_conf = [], collections.defaultdict(collections.Counter)
    for cause, c in sorted(tax["causes"].items()):
        if cause in NOT_CAUSES:
            continue
        be = c.get("by_engine") or {}
        if isinstance(be, str):
            be = json.loads(be.replace("'", '"'))
        refs = c.get("doc_refs") or []
        for key, n in sorted(be.items()):
            camp, conf = key.split(":", 1)
            if "~vs~" in conf or "#" in conf:
                continue
            own = [r for r in refs if any(h in r.get("url", "") for h in DOC_HOSTS.get(conf, ()))]
            if own and c.get("documented_level") == "yes":
                cls = "documented incompatibility"
            elif own:
                cls = "partly documented"
            elif conf in DROP_IN:
                cls = "contradicts a compatibility claim"
            else:
                cls = "no applicable promise found"
            rd = (c.get("repro_differs_from_ref") or {})
            eng = ((probes["causes"].get(cause) or {}).get("engines") or {}).get(conf) or {}
            ev = []
            if rd.get(conf):
                ev.append("pandas reproducer differs")
            if eng.get("verdict") == "confirmed":
                ev.append("engine probe confirms")
            elif eng.get("verdict") == "not_reproduced":
                ev.append("engine probe does not reproduce")
            rows.append({"cause": cause, "campaign": camp, "configuration": conf,
                         "cells": n, "documented_level": c.get("documented_level"), "evidence_class": cls,
                         "doc_url": own[0]["url"] if own else "", "doc_quote": own[0].get("quote", "") if own else "",
                         "reproducer": c.get("reproducer") or "", "reproducer_evidence": "; ".join(ev) or "none"})
            by_conf[conf][cls] += n
    unattr = collections.Counter()
    for key, n in (tax["causes"]["unattributed"].get("by_engine") or {}).items():
        unattr[key.split(":", 1)[1]] += n
    exc = collections.Counter(r4["exception"]["totals"]["exception_cells_by_label"])
    confs = ["p15", "p30", "pyarrow_backend", "modin", "fireducks", "bodo", "dask", "bodo_dw"]
    table = {}
    for conf in confs:
        t = {k: by_conf[conf].get(k, 0) for k in ORDER}
        t["unattributed_rules"] = unattr.get(conf, 0)
        t["exception_cells_pure"] = exc.get(conf, 0)
        t["with_cause"] = sum(by_conf[conf].values())
        table[conf] = t
    drop = ("modin", "fireducks", "bodo")
    agg = {k: sum(table[c][k] for c in drop) for k in ORDER}
    agg["with_cause"] = sum(table[c]["with_cause"] for c in drop)
    entries = collections.Counter((r["configuration"] in DROP_IN, r["evidence_class"]) for r in rows)
    # taxonomy totals under the pure definition (the 59 exception cells introduced and unattributed)
    prov = json.load(open(os.path.join(PROJ, "results", "rootcause", "paper_provenance.json")))["taxonomy"]
    kinds = tax["counts"]["by_kind"]
    n_exc = r4["exception"]["totals"]["exception_cells"]
    exc_engine = sum(v for k, v in r4["exception"]["totals"]["exception_cells_by_label"].items() if k not in ("p15", "p30"))
    pure = {"non_e0_cells": tax["counts"]["non_e0_cells"], "introduced": kinds["introduced"] + n_exc,
            "inherited": kinds["propagated"] - n_exc, "cascade": kinds["cascade"], "harness": kinds["harness"],
            "nondet": kinds.get("nondet", 0), "unattributed": tax["causes"]["unattributed"]["n_cells"] + n_exc,
            "engine_introduced": prov["engine_introduced_cells"] + exc_engine,
            "engine_symptom_or_unattributed": prov["engine_symptom_or_unattributed"] + exc_engine}
    pure["unattributed_share"] = round(pure["unattributed"] / pure["introduced"], 4)
    pure["engine_symptom_or_unattributed_share"] = round(pure["engine_symptom_or_unattributed"] / pure["engine_introduced"], 4)
    assert pure["introduced"] == r4["exception"]["totals"]["introduced"]["off"]
    out = {"definition": __doc__.split("Each (cause")[1].split('"Not searched"')[0].strip(),
           "by_configuration_cells": table, "drop_in_engines_cells": agg,
           "entries": len(rows), "entries_by_class": dict(collections.Counter(r["evidence_class"] for r in rows)),
           "entries_by_drop_in_and_class": {"%s|%s" % k: v for k, v in sorted(entries.items())},
           "claim_map": "icde27/analysis/r5_claim_map.csv", "taxonomy_pure": pure}
    with open(OUT + ".tmp", "w") as f:
        json.dump(out, f, indent=1)
    os.replace(OUT + ".tmp", OUT)
    with open(OUT_CSV + ".tmp", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    os.replace(OUT_CSV + ".tmp", OUT_CSV)
    print(json.dumps({k: v for k, v in out.items() if k != "definition"}, indent=1))


if __name__ == "__main__":
    sys.exit(main())

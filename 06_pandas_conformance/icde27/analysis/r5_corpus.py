#!/usr/bin/env python3
"""Distinct underlying datasets of the 102 PandasBench notebooks (review round R5; ICDE 2027 copy; written 2026-11-10).

Read-only on data/provenance.json (one sha256 per input file of the PandasBench data archive, keyed by
<user>/<notebook>/input/<file>) and data/notebook_sets/sizes.json (the 102 notebooks); writes only
icde27/analysis/r5_corpus.json. Seconds, below 0.1 GB; regenerates from the released files.

    cd ..
    .venv/bin/python 06_pandas_conformance-ICDE/icde27/analysis/r5_corpus.py

Two notebooks are counted as working on the same dataset when they read at least one byte-identical input file
(same sha256); the groups are the connected components of that relation. Reported: input files, distinct file
contents, dataset groups, their sizes and members, and the number of distinct input-file sets.
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "r5_corpus.json")


def main():
    prov = json.load(open(os.path.join(PROJ, "data", "provenance.json")))
    nbs = sorted(json.load(open(os.path.join(PROJ, "data", "notebook_sets", "sizes.json")))["input_bytes"])
    assert len(nbs) == 102
    files = collections.defaultdict(set)
    for path, v in prov["data_manifest"].items():
        files["/".join(path.split("/")[:2])].add(v["sha256"])
    assert all(nb in files for nb in nbs)
    parent = {nb: nb for nb in nbs}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    owner = {}
    for nb in nbs:
        for h in sorted(files[nb]):
            if h in owner:
                parent[find(nb)] = find(owner[h])
            else:
                owner[h] = nb
    groups = collections.defaultdict(list)
    for nb in nbs:
        groups[find(nb)].append(nb)
    sizes = sorted((len(v) for v in groups.values()), reverse=True)
    sets = collections.Counter(frozenset(files[nb]) for nb in nbs)
    out = {"definition": "notebooks that read at least one byte-identical input file (sha256) share a dataset group",
           "notebooks": len(nbs), "input_files": len(prov["data_manifest"]),
           "distinct_file_contents": len({v["sha256"] for v in prov["data_manifest"].values()}),
           "dataset_groups": len(groups), "group_sizes": sizes, "singleton_groups": sizes.count(1),
           "notebooks_in_shared_groups": sum(s for s in sizes if s > 1),
           "largest_groups": sorted((sorted(v) for v in groups.values() if len(v) > 1), key=lambda v: (-len(v), v)),
           "distinct_input_sets": len(sets)}
    with open(OUT + ".tmp", "w") as f:
        json.dump(out, f, indent=1)
    os.replace(OUT + ".tmp", OUT)
    print(json.dumps({k: v for k, v in out.items() if k != "largest_groups"}))


if __name__ == "__main__":
    sys.exit(main())

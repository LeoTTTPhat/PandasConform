#!/usr/bin/env python3
"""Write manifest.json: SHA-256 and size of every file in icde27/analysis/r5_replay/ (except the manifest itself) and
of every raw run record and comparison output under work/r5_replay/ (records, compare outputs; capture blobs are
content-addressed by their SHA-256 file names and are only counted). Stdlib only.   Usage: python3 manifest.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r5common as R  # noqa: E402

OUT = os.path.join(R.HERE, "manifest.json")


def walk(root, skip=()):
    for dp, dn, fn in os.walk(root):
        dn[:] = sorted(d for d in dn if d not in skip)
        for n in sorted(fn):
            if n.startswith(".") or n.endswith(".tmp") or n.endswith(".pyc"):
                continue
            yield os.path.join(dp, n)


def main():
    files = {}
    for p in walk(R.HERE, skip=("__pycache__",)):
        if os.path.basename(p) == "manifest.json":
            continue
        files[os.path.relpath(p, R.PROJ)] = {"sha256": R.sha256_file(p), "bytes": os.path.getsize(p)}
    raw = {}
    for sub in ("results", "compare"):
        for p in walk(os.path.join(R.WORK, sub)):
            raw[os.path.relpath(p, R.PROJ)] = {"sha256": R.sha256_file(p), "bytes": os.path.getsize(p)}
    blobs = [p for p in walk(os.path.join(R.WORK, "captures")) if p.endswith(".arrow")]
    R.write_json(OUT, {"analysis_files": files, "raw_files": raw, "replay_store_blobs": len(blobs),
                       "replay_store_bytes": sum(os.path.getsize(p) for p in blobs),
                       "note": "replay store blobs identical to released blobs were removed (dedupe_store.py); "
                               "comparisons read the replay store first and else the released store"})
    print("wrote", OUT, len(files), "analysis files,", len(raw), "raw files,", len(blobs), "blobs")


if __name__ == "__main__":
    main()

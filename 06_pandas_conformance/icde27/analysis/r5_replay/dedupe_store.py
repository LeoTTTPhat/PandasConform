#!/usr/bin/env python3
"""Remove from the replay store (work/r5_replay/captures) every column blob whose content-addressed path also exists,
with the same size, in the released store (captures/, read only). The two files hold the same content (the file name
is the SHA-256 content hash), so no evidence is lost: comparisons read the replay store first and else the released
store (r5common.patch_union_store). Only complete *.arrow files are touched. Usage: python3 dedupe_store.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r5common as R  # noqa: E402

removed = kept = freed = 0
root = os.path.join(R.REPLAY_STORE, "cols")
for d in sorted(os.listdir(root)) if os.path.isdir(root) else []:
    for n in os.listdir(os.path.join(root, d)):
        if not n.endswith(".arrow"):
            continue
        p = os.path.join(root, d, n)
        q = os.path.join(R.SHARED_STORE, "cols", d, n)
        try:
            sp = os.path.getsize(p)
            if os.path.exists(q) and os.path.getsize(q) == sp:
                os.unlink(p)
                removed += 1
                freed += sp
            else:
                kept += 1
        except OSError:
            pass
print({"removed_duplicates": removed, "kept_new_blobs": kept, "freed_gb": round(freed / 1e9, 2)})

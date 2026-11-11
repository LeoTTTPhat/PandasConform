"""Shared helpers for the R5 replay and audit experiments (round REV-06-R5B2-2026-11-10, agent B2).

Read-only on every released file. New outputs go to icde27/analysis/r5_replay/ (scripts, JSON, RESULTS.md) and
work/r5_replay/ (raw records and capture blobs of new runs). Stdlib only, so it imports in every environment.
"""
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))          # 06_pandas_conformance-ICDE
WS = os.path.dirname(PROJ)                                               # workspace root
SRC = os.path.join(PROJ, "src")
ENVS = os.path.join(PROJ, "envs")
WORK = os.path.join(PROJ, "work", "r5_replay")
REPLAY_RESULTS = os.path.join(WORK, "results")
REPLAY_STORE = os.path.join(WORK, "captures")
REPLAY_PWORK = os.path.join(WORK, "work")                 # PCONF_WORK for replay runs (scaled -> project work/scaled)
SHARED_STORE = os.path.join(PROJ, "captures")             # released content-addressed store (read only)
CONF1X_RUNS = os.path.join(PROJ, "results", "conf_1x", "raw", "runs__hd1c421ecb5ee")
CONF1X_COMPARE = os.path.join(PROJ, "results", "conf_1x", "raw", "compare__hd1c421ecb5ee__d92c8db54d45b")
PILOT_RAW = os.path.join(PROJ, "results", "pilot", "raw")
CELL_FLAGS = os.path.join(PROJ, "icde27", "analysis", "r4_cell_flags.csv")
HAND = os.path.join(PROJ, "icde27", "analysis", "r1_hand_attribution.json")
TAXONOMY = os.path.join(PROJ, "results", "rootcause", "taxonomy_conf1x.json")
HARNESS_TAG = "d1c421ecb5ee"
ENGINES = ["pyarrow_backend", "modin", "fireducks", "bodo", "dask"]
RANK = {"E0": 0, "E1": 1, "E2": 2, "E3": 3, "E4": 4, "DIFF": 5}
FAIL = {"ERR", "TIMEOUT", "CRASH", "KILLED", "MEMORY", "NOTRUN", "SETUP_ERR"}
# r1_cells.py MECHANISM: causes counted as "parallel or lazy execution" (rule and curated assignments)
PARALLEL_LAZY_CAUSES = {"approximate_quantile", "float_rounding_within_tolerance", "row_order_ties",
                        "partitioned_type_inference", "lazy_partition_model"}


def read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True, default=str)
    os.replace(tmp, path)


def sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def cell_flags():
    with open(CELL_FLAGS) as f:
        return list(csv.DictReader(f))


def hand_rows():
    return {(r["label"], r["nb"], int(r["cell"])): r for r in read_json(HAND)["rows"]}


def introduced(cls, clean):
    """rootcause_taxonomy.introduced: the pure criterion (the class is coarser than the clean level)."""
    if cls not in RANK:
        return False
    return clean is not None and RANK[cls] > RANK.get(clean, 9)


def nb_key(nb):
    return nb.replace("/", "__").replace(":", "__")


def original_record(engine, nb, runs_root=CONF1X_RUNS):
    """The conf_1x run record of (engine, notebook): newest file with this notebook key."""
    tag = engine.replace("#", "_r")
    d = os.path.join(runs_root, tag, "sf1")
    k = nb_key(nb) + "__"
    cands = [os.path.join(d, n) for n in os.listdir(d) if n.startswith(k) and n.endswith(".json")]
    cands = [c for c in cands if len(os.path.basename(c)) == len(k) + 12 + 5]
    if not cands:
        return None
    return max(cands, key=os.path.getmtime)


def patch_union_store(primary, fallback):
    """Make pconf.capture read a blob from `primary` and else from `fallback` (comparisons only; the replay
    children write only to their own store). Called in the comparing process; changes no file."""
    from pconf import capture as C
    orig = C.blob_path

    def blob_path(store, h):
        p = orig(primary, h)
        if os.path.exists(p):
            return p
        return orig(fallback, h)

    C.blob_path = blob_path
    return C

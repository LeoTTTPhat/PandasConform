"""Small shared helpers: atomic writes, hashing, paths. Stdlib only (imported in every env)."""
import hashlib
import json
import os
import tempfile

PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(PROJ, "src")
ENVS = os.path.join(PROJ, "envs")
DATA = os.path.join(PROJ, "data")
# Overridable for tests (isolated temp roots); campaigns use the project defaults.
WORK = os.environ.get("PCONF_WORK") or os.path.join(PROJ, "work")
RESULTS = os.environ.get("PCONF_RESULTS") or os.path.join(PROJ, "results")
CAPTURES = os.environ.get("PCONF_CAPTURES") or os.path.join(PROJ, "captures")
SHARED_PY = str(__import__('pathlib').Path(__file__).resolve().parents[3] / '.venv/bin/python')


def atomic_write_bytes(path, data):
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp.", dir=d)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path, obj, indent=None):
    atomic_write_bytes(path, json.dumps(obj, indent=indent, sort_keys=True, default=str).encode("utf-8"))


def read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path, bufsize=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(bufsize)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def canon_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha256_json(obj):
    return sha256_bytes(canon_json(obj).encode("utf-8"))


# Files whose content determines what a child run records. Changing any of them changes the
# harness fingerprint and therefore the raw-results directory (plan: never overwrite results).
HARNESS_FILES = ["capture.py", "nbsource.py", "runner_child.py", "engines.py"]
COMPARE_FILES = ["dfeq.py", "classify.py", "capture.py", "compare_worker.py"]


def source_sha(files):
    h = hashlib.sha256()
    here = os.path.dirname(os.path.abspath(__file__))
    for n in sorted(files):
        h.update(n.encode())
        with open(os.path.join(here, n), "rb") as f:
            h.update(f.read())
    return h.hexdigest()


def harness_sha():
    return source_sha(HARNESS_FILES)


def compare_sha():
    return source_sha(COMPARE_FILES)


def nb_key(nb):
    """'user/slug' -> filesystem key 'user__slug'."""
    return nb.replace("/", "__").replace(":", "__")

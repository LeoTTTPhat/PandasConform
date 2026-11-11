"""Adversarial review of the orchestrator, checkpoints, determinism and the blob store
(review 2026-10-02): MEMGUARD variables never change the workload or the fingerprint, seeded
replicates are bit-identical, external kills, compare resume, concurrent writers of the
content-addressed store, and timing-mode materialisation."""
import glob
import json
import multiprocessing as mp
import os
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from unittest import mock

import numpy as np
import pandas as pd

from _common import env_python, isolated_env, run_orch, write_probe_notebook, write_set, PROJ, SHARED_PY
from pconf import capture as C
from pconf import orchestrate

HEAD = ["import os\n", "exec(os.environ['IREWR_IMPORTS'])\nimport numpy as np\nimport random\n"]
NB_RANDOM = HEAD + [
    "a = np.random.rand(5)\nb = random.random()\nc = sorted(hash(s) % 1000 for s in ['x', 'y', 'z'])\nd = list({'alpha', 'beta', 'gamma', 'delta'})",
    "df = pd.DataFrame({'k': list('abcabcabca'), 'v': np.random.randn(10)})\ns = df.sample(frac=0.5)\ns",
    "g = df.groupby('k')['v'].agg(['mean', 'sum'])\ng",
    "u = df['k'].unique()\nu",
]
NB_SLOW = HEAD + ["import time\ntime.sleep(30)\nx = 1", "y = 2"]


def load(p):
    with open(p) as f:
        return json.load(f)


def recs(root, campaign, engine, kind="runs"):
    return sorted(glob.glob(os.path.join(root, "results", campaign, "raw", kind + "__*", engine.replace("#", "_r"), "*", "*.json")))


def cell_hashes(rec):
    return {c["i"]: c.get("outputs") for c in rec["cells"]}


@unittest.skipUnless(env_python("ref"), "ref env missing")
class TestWorkloadInvariance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="pconf_adv_orch_")
        cls.nb = write_probe_notebook(os.path.join(cls.root, "work"), "adv_rand", NB_RANDOM)
        cls.set = write_set(cls.root, "advrand", [cls.nb])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def _run(self, campaign, engines, extra_env=None):
        env = isolated_env(self.root)
        env.update(extra_env or {})
        return subprocess.run([SHARED_PY, "-m", "pconf.orchestrate", "run", "--campaign", campaign, "--set", self.set,
                               "--engines", engines, "--cell-timeout", "60", "--nb-timeout", "300"],
                              env=env, cwd=PROJ, capture_output=True, text=True, timeout=600)

    def test_seeded_replicates_identical_and_memguard_invariant(self):
        r = self._run("det", "ref,ref#2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        a, b = load(recs(self.root, "det", "ref")[0]), load(recs(self.root, "det", "ref#2")[0])
        self.assertEqual(a["status"], "completed")
        self.assertEqual(cell_hashes(a), cell_hashes(b), "seeded replicates must be bit-identical")
        # restart settings of the guard: same fingerprint -> skipped (no rerun, no new record)
        slow = {"MEMGUARD_RESTART": "2", "MEMGUARD_BATCH_SCALE": "0.25", "MEMGUARD_DELAY_SECONDS": "0.06"}
        r = self._run("det", "ref", slow)
        self.assertEqual(json.loads(r.stdout.strip().splitlines()[-1])["counts"], {"skipped": 1}, r.stdout)
        # a fresh campaign under restart settings: same fingerprint, same outputs
        r = self._run("det_slow", "ref", slow)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        c = load(recs(self.root, "det_slow", "ref")[0])
        self.assertEqual(c["fingerprint"], a["fingerprint"])
        self.assertEqual(cell_hashes(c), cell_hashes(a), "MEMGUARD pacing must not change the workload")


class TestConcurrencyPolicy(unittest.TestCase):
    def test_concurrency_follows_guard(self):
        cases = [({}, "single", 6), ({"MEMGUARD_BATCH_SCALE": "0.5"}, "single", 3),
                 ({"MEMGUARD_BATCH_SCALE": "0.1"}, "single", 1), ({"MEMGUARD_RESTART": "1"}, "single", 1),
                 ({}, "parallel", 1)]
        for env, cls, want in cases:
            with mock.patch.dict(os.environ, env, clear=False):
                for k in ("MEMGUARD_BATCH_SCALE", "MEMGUARD_RESTART"):
                    if k not in env:
                        os.environ.pop(k, None)
                self.assertEqual(orchestrate.concurrency(cls, 6), want, (env, cls))


@unittest.skipUnless(env_python("ref"), "ref env missing")
class TestExternalKill(unittest.TestCase):
    def _kill_child(self, p):
        import psutil
        child = None
        deadline = time.time() + 60
        while time.time() < deadline and child is None:
            for c in psutil.Process(p.pid).children(recursive=True):
                if "pconf.runner_child" in " ".join(c.cmdline()):
                    child = c
            time.sleep(0.2)
        self.assertIsNotNone(child)
        time.sleep(2.0)
        child.send_signal(signal.SIGKILL)
        out, _ = p.communicate(timeout=120)
        return out

    def test_child_killed_externally_is_retried_then_recorded_fixed(self):
        """Review documented: an external SIGKILL of the runner child (OOM killer, stray kill) was
        stored permanently as nb_crash. Fixed (A5): the first such kill leaves no record
        (killed_external, rerun later); a second kill of the same fingerprint is recorded as
        nb_killed (classified KILLED, distinct from an engine crash) and skipped afterwards."""
        root = tempfile.mkdtemp(prefix="pconf_adv_kill_")
        try:
            nb = write_probe_notebook(os.path.join(root, "work"), "adv_slow", NB_SLOW)
            st = write_set(root, "slow", [nb])
            args = ["run", "--campaign", "kill", "--set", st, "--engines", "ref", "--cell-timeout", "120",
                    "--nb-timeout", "300"]
            out = self._kill_child(run_orch(root, args, popen=True))
            self.assertEqual(json.loads(out.strip().splitlines()[-1])["counts"], {"killed_external": 1}, out)
            self.assertEqual(recs(root, "kill", "ref"), [])
            out = self._kill_child(run_orch(root, args, popen=True))
            rec = load(recs(root, "kill", "ref")[0])
            self.assertEqual(rec["status"], "nb_killed")
            self.assertEqual(rec["returncode"], -9)
            r = run_orch(root, args)
            self.assertEqual(json.loads(r.stdout.strip().splitlines()[-1])["counts"], {"skipped": 1})
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestCpuBudget(unittest.TestCase):
    """Fix of review finding T2: matched CPU budgets for timing runs."""

    def test_child_env_cpu_budget(self):
        from pconf import engines
        base = {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1"}
        conf = {e: engines.child_env(e, base_env=dict(base)) for e in ("ref", "modin", "fireducks", "bodo", "dask")}
        self.assertEqual(conf["ref"]["OMP_NUM_THREADS"], "1")
        self.assertNotIn("OMP_NUM_THREADS", conf["fireducks"])          # conformance: engine default
        self.assertEqual(conf["bodo"]["BODO_NUM_WORKERS"], "1")          # documented cap
        self.assertNotIn("PCONF_CPUS", conf["modin"])
        t = {e: engines.child_env(e, base_env=dict(base), cpus="8") for e in ("ref", "modin", "fireducks", "bodo", "dask")}
        self.assertEqual(t["fireducks"]["OMP_NUM_THREADS"], "8")
        self.assertEqual(t["bodo"]["BODO_NUM_WORKERS"], "8")
        for e in ("modin", "bodo", "dask"):
            self.assertEqual(t[e]["PCONF_CPUS"], "8")
            self.assertEqual(t[e]["OMP_NUM_THREADS"], "1")
        self.assertEqual(t["ref"]["OMP_NUM_THREADS"], "1")
        self.assertNotIn("PCONF_CPUS", t["ref"])
        d = engines.child_env("bodo", base_env=dict(base), cpus="default")
        self.assertNotIn("BODO_NUM_WORKERS", d)
        self.assertIn("num_cpus", engines.ENGINES["modin"]["setup"])
        self.assertIn("num_workers", engines.ENGINES["dask"]["setup"])


# --------------------------------------------------------------------------- blob store
def _verify_blob(store, h):
    """Recompute the content hash of a stored column blob from its own bytes and metadata."""
    import pyarrow as pa
    with pa.memory_map(C.blob_path(store, h), "r") as src:
        tbl = pa.ipc.open_file(src).read_all()
    meta = json.loads(tbl.schema.metadata[b"pconf"])
    arrays = {n: tbl.column(n).combine_chunks() for n in tbl.column_names if n != "_empty"}
    hx = {k: (v["h"] if isinstance(v, dict) and "h" in v else v) for k, v in meta["x"].items()}
    return C.column_hash(meta["enc"], meta["dtype"], hx, arrays) == h


def _writer(args):
    store, seed = args
    rng = np.random.default_rng(seed % 2)        # two writers per frame family -> overlapping blobs
    cap = C.Capturer(store)
    hs = []
    for k in range(5):
        df = pd.DataFrame({"f": rng.normal(size=2000), "s": rng.choice(["a", "b", "c"], 2000).astype(object),
                           "i": rng.integers(0, 9, 2000), "c": pd.Categorical(rng.choice(["x", "y"], 2000))})
        rec = cap.capture(df)
        hs.append(rec["h"])
    return hs


class TestBlobStoreConcurrency(unittest.TestCase):
    def test_concurrent_writers_produce_valid_content_addressed_blobs(self):
        store = tempfile.mkdtemp(prefix="pconf_adv_store_")
        try:
            with mp.get_context("spawn").Pool(6) as pool:
                res = pool.map(_writer, [(store, s) for s in range(6)])
            self.assertEqual(res[0], res[2])     # same seed family -> same object hashes
            blobs = glob.glob(os.path.join(store, "cols", "*", "*.arrow"))
            self.assertGreater(len(blobs), 0)
            self.assertEqual(glob.glob(os.path.join(store, "cols", "*", "*.tmp.*")), [])
            for p in blobs:
                h = os.path.basename(p)[:-6]
                self.assertTrue(_verify_blob(store, h), p)
        finally:
            shutil.rmtree(store, ignore_errors=True)


# --------------------------------------------------------------------------- compare resume
@unittest.skipUnless(env_python("ref"), "ref env missing")
class TestCompareResume(unittest.TestCase):
    def test_compare_redoes_only_missing_outputs(self):
        root = tempfile.mkdtemp(prefix="pconf_adv_cmp_")
        try:
            nbs = [write_probe_notebook(os.path.join(root, "work"), "adv_c%d" % k, NB_RANDOM[:3 + k]) for k in range(3)]
            st = write_set(root, "cmp", nbs)
            r = run_orch(root, ["run", "--campaign", "cmp", "--set", st, "--engines", "ref,ref#2",
                                "--cell-timeout", "60", "--nb-timeout", "300"])
            self.assertEqual(r.returncode, 0, r.stderr)
            args = ["compare", "--campaign", "cmp", "--set", st, "--engines", "ref#2", "--cell-timeout", "60",
                    "--nb-timeout", "300"]
            r = run_orch(root, args)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            outs = recs(root, "cmp", "ref#2", kind="compare")
            self.assertEqual(len(outs), 3)
            mt = {p: os.path.getmtime(p) for p in outs}
            os.unlink(outs[1])
            r = run_orch(root, args)
            self.assertIn("3 jobs, 1 to do", r.stdout)
            outs2 = recs(root, "cmp", "ref#2", kind="compare")
            self.assertEqual(len(outs2), 3)
            for p in (outs[0], outs[2]):
                self.assertEqual(os.path.getmtime(p), mt[p])
            for p in outs2:  # replicate vs replicate: every comparable cell is E0
                d = load(p)
                self.assertTrue(all(c["cls"] in ("E0", "NOOUT") for c in d["cells"]), d["summary"])
        finally:
            shutil.rmtree(root, ignore_errors=True)


@unittest.skipUnless(env_python("ref"), "ref env missing")
class TestCompareStaleReplicate(unittest.TestCase):
    def test_compare_output_is_recomputed_when_ref2_appears(self):
        """The compare output path is <nb>__<fp_ref8>_<fp_eng8>.json: it does not depend on the
        second reference run. A compare made while ref#2 was missing (split campaigns) is never
        redone, so its non-deterministic cells stay classified against the engine (observed: the
        time.time() cell is reported E2 instead of NONDET after ref#2 exists)."""
        root = tempfile.mkdtemp(prefix="pconf_adv_ref2_")
        try:
            cells = HEAD + ["import time\nt = time.time()\nt", "z = 1"]
            nb = write_probe_notebook(os.path.join(root, "work"), "adv_nd", cells)
            st = write_set(root, "nd", [nb])
            common = ["--campaign", "nd", "--set", st, "--cell-timeout", "60", "--nb-timeout", "300"]
            self.assertEqual(run_orch(root, ["run", "--engines", "ref,ref#3"] + common).returncode, 0)
            run_orch(root, ["compare", "--engines", "ref#3", "--ref2", "ref#2"] + common)   # ref#2 not run yet
            self.assertEqual(run_orch(root, ["run", "--engines", "ref#2"] + common).returncode, 0)
            r = run_orch(root, ["compare", "--engines", "ref#3", "--ref2", "ref#2"] + common)
            out = load(recs(root, "nd", "ref#3", kind="compare")[0])
            cls = {c["i"]: c["cls"] for c in out["cells"]}
            self.assertEqual(cls[2], "NONDET", (cls, r.stdout))
        finally:
            shutil.rmtree(root, ignore_errors=True)


# --------------------------------------------------------------------------- timing mode
@unittest.skipUnless(env_python("ref"), "ref env missing")
class TestTimingMaterialisation(unittest.TestCase):
    def test_timing_mode_materialises_the_displayed_value(self):
        """Lazy engines (FireDucks, Bodo, Dask) defer work until a value is needed. Timing mode
        evaluates each cell's last expression but never materialises/displays it, so work whose
        result is only displayed is never charged to lazy engines while pandas pays for it.
        Measured 2026-10-02 (10M rows): pandas sort_values 1.54 s in the statement; FireDucks
        0.000 s in the statement + 0.142 s at repr; Bodo 0.007 s + 6.6 s at repr."""
        root = tempfile.mkdtemp(prefix="pconf_adv_tim_")
        try:
            marker = os.path.join(root, "displayed.txt")
            cells = HEAD + ["class Lazy:\n    def __repr__(self):\n        open(%r, 'w').write('x')\n        return 'Lazy'\n" % marker,
                            "Lazy()"]
            nb = write_probe_notebook(os.path.join(root, "work"), "adv_lazy", cells)
            st = write_set(root, "lazy", [nb])
            r = run_orch(root, ["run", "--campaign", "tim", "--set", st, "--engines", "ref", "--mode", "timing",
                                "--cell-timeout", "60", "--nb-timeout", "300"])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(os.path.exists(marker), "the last expression was never materialised in timing mode")
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

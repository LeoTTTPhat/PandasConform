"""Orchestrator: 3-notebook end-to-end smoke (run -> capture -> compare -> summarize),
checkpoint/resume (skip completed fingerprints), crash/resume (orchestrator killed mid-campaign),
cell and notebook timeouts, fingerprint change -> new records (old records preserved)."""
import glob
import json
import os
import shutil
import signal
import tempfile
import time
import unittest

from _common import env_python, run_orch, write_probe_notebook, write_set

HEAD = ["import os\n", "exec(os.environ['IREWR_IMPORTS'])\nimport numpy as np\nimport io\n"]
NB_READ = HEAD + [
    "csv = 'k,v,s\\n1,0.5,x\\n2,,y\\n1,1.5,\\n3,2.0,z\\n'\ndf = pd.read_csv(io.StringIO(csv))\ndf.head()",
    "g = df.groupby('k')['v'].sum()\ng",
    "df['w'] = df['v'] * 2\ndf.describe()",
    "vc = df['s'].value_counts()\nvc",
]
NB_MERGE = HEAD + [
    "l = pd.DataFrame({'k': [3, 1, 2, 1], 'a': range(4)})\nr = pd.DataFrame({'k': [1, 3, 2], 'b': [0.1, 0.2, 0.3]})",
    "m = l.merge(r, on='k')\nm",
    "m.sort_values('k').reset_index(drop=True)",
    "raise_here = undefined_name",
    "after = len(m)\nafter",
]
NB_NONDET = HEAD + [
    "import time\nt = time.time()\nt",
    "s = pd.Series([1, 2, 3])\ns.sum()",
]
NB_SLOW = HEAD + ["import time\ntime.sleep(4)\nx = 1", "y = x + 1\ny"]


def load(p):
    with open(p) as f:
        return json.load(f)


def records(root, campaign, engine):
    return sorted(glob.glob(os.path.join(root, "results", campaign, "raw", "runs__*", engine.replace("#", "_r"), "*", "*.json")))


class TestOrchestrator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="pconf_orch_")
        work = os.path.join(cls.root, "work")
        cls.nbs = [write_probe_notebook(work, "t_read", NB_READ),
                   write_probe_notebook(work, "t_merge", NB_MERGE),
                   write_probe_notebook(work, "t_nondet", NB_NONDET)]
        cls.slow = write_probe_notebook(work, "t_slow", NB_SLOW)
        cls.set3 = write_set(cls.root, "three", cls.nbs)
        cls.set_slow = write_set(cls.root, "slowset", [cls.nbs[0], cls.slow, cls.nbs[1]])
        cls.engines = [e for e in ["ref", "ref#2", "p30", "fireducks"] if env_python(e.split("#")[0])]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_1_end_to_end_three_notebooks(self):
        eng = ",".join(self.engines)
        r = run_orch(self.root, ["run", "--campaign", "e2e", "--set", self.set3, "--engines", eng,
                                 "--cell-timeout", "60", "--nb-timeout", "300"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        summary = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(summary["counts"].get("completed"), 3 * len(self.engines), summary)
        for e in self.engines:
            self.assertEqual(len(records(self.root, "e2e", e)), 3)
        others = [e for e in self.engines if e not in ("ref", "ref#2")]
        r = run_orch(self.root, ["compare", "--campaign", "e2e", "--set", self.set3, "--engines", ",".join(others),
                                 "--ref2", "ref#2", "--cell-timeout", "60", "--nb-timeout", "300"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        outs = glob.glob(os.path.join(self.root, "results", "e2e", "raw", "compare__*", "*", "*", "*.json"))
        self.assertEqual(len(outs), 3 * len(others))
        by_nb = {}
        for p in outs:
            d = load(p)
            by_nb[(d["meta"]["engine"], d["meta"]["nb"])] = d
            for c in d["cells"]:
                self.assertIn(c["cls"], {"E0", "E1", "E2", "E3", "E4", "DIFF", "ERR", "TIMEOUT", "UNCOMPARABLE",
                                         "NOOUT", "REF_ERR", "NONDET"})
        # reference raised in t_merge cell 5 -> REF_ERR; t_nondet cell 2 (time.time()) -> NONDET
        d = by_nb[(others[0], "probe:t_merge")]
        self.assertEqual({c["i"]: c["cls"] for c in d["cells"]}[5], "REF_ERR")
        d = by_nb[(others[0], "probe:t_nondet")]
        self.assertEqual({c["i"]: c["cls"] for c in d["cells"]}[2], "NONDET")
        if "p30" in others:
            d = by_nb[("p30", "probe:t_read")]
            c2 = {c["i"]: c for c in d["cells"]}[2]
            self.assertIn(c2["cls"], ("E2", "E3"))  # pandas 3 default string dtype
        r = run_orch(self.root, ["summarize", "--campaign", "e2e"])
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_2_resume_skips_completed(self):
        r = run_orch(self.root, ["run", "--campaign", "resume", "--set", self.set3, "--engines", "ref",
                                 "--cell-timeout", "60", "--nb-timeout", "300"])
        self.assertEqual(r.returncode, 0, r.stderr)
        first = records(self.root, "resume", "ref")
        mtimes = {p: os.path.getmtime(p) for p in first}
        r = run_orch(self.root, ["run", "--campaign", "resume", "--set", self.set3, "--engines", "ref",
                                 "--cell-timeout", "60", "--nb-timeout", "300"])
        summary = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(summary["counts"], {"skipped": 3})
        self.assertEqual({p: os.path.getmtime(p) for p in records(self.root, "resume", "ref")}, mtimes)
        # changed configuration -> new fingerprints, new records, old ones preserved
        r = run_orch(self.root, ["run", "--campaign", "resume", "--set", self.set3, "--engines", "ref",
                                 "--cell-timeout", "61", "--nb-timeout", "300"])
        summary = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(summary["counts"], {"completed": 3})
        self.assertEqual(len(records(self.root, "resume", "ref")), 6)
        for p in first:
            self.assertTrue(os.path.exists(p))

    def test_3_crash_and_resume(self):
        p = run_orch(self.root, ["run", "--campaign", "crash", "--set", self.set_slow, "--engines", "ref",
                                 "--max-concurrency", "1", "--cell-timeout", "60", "--nb-timeout", "300"], popen=True)
        # wait until the first notebook is recorded and the slow one is running, then kill the orchestrator
        deadline = time.time() + 120
        while time.time() < deadline and len(records(self.root, "crash", "ref")) < 1:
            time.sleep(0.2)
        time.sleep(1.0)
        os.killpg(p.pid, signal.SIGTERM)
        p.wait(timeout=60)
        recs = records(self.root, "crash", "ref")
        self.assertEqual(len(recs), 1, "only the finished notebook may have a record")
        self.assertTrue(load(recs[0])["status"] == "completed")
        r = run_orch(self.root, ["run", "--campaign", "crash", "--set", self.set_slow, "--engines", "ref",
                                 "--max-concurrency", "1", "--cell-timeout", "60", "--nb-timeout", "300"])
        summary = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(summary["counts"], {"skipped": 1, "completed": 2}, r.stdout)
        for path in records(self.root, "crash", "ref"):
            load(path)  # every record is complete JSON (atomic writes)

    def test_4_timeouts(self):
        # cell timeout: the slow cell times out, the next cell still runs
        r = run_orch(self.root, ["run", "--campaign", "tmo", "--set", write_set(self.root, "s1", [self.slow]),
                                 "--engines", "ref", "--cell-timeout", "1", "--nb-timeout", "300"])
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = load(records(self.root, "tmo", "ref")[0])
        st = {c["i"]: c["status"] for c in rec["cells"]}
        self.assertEqual(st[2], "timeout")
        self.assertEqual(st[3], "error")  # x undefined after the timed-out cell: a result, not a crash
        # notebook timeout: orchestrator kills the child, salvages per-cell progress
        r = run_orch(self.root, ["run", "--campaign", "nbtmo", "--set", write_set(self.root, "s2", [self.slow]),
                                 "--engines", "ref", "--cell-timeout", "60", "--nb-timeout", "2"])
        rec = load(records(self.root, "nbtmo", "ref")[0])
        self.assertEqual(rec["status"], "nb_timeout")
        self.assertTrue(rec.get("salvaged_from_progress"))
        self.assertGreaterEqual(len(rec["cells"]), 2)


class TestTiming(unittest.TestCase):
    def test_timing_mode_no_capture_reps(self):
        root = tempfile.mkdtemp(prefix="pconf_timing_")
        try:
            nb = write_probe_notebook(os.path.join(root, "work"), "t_time", NB_MERGE)
            st = write_set(root, "tset", [nb])
            from _common import SHARED_PY, PROJ, isolated_env
            import subprocess
            r = subprocess.run([SHARED_PY, "-m", "pconf.timing", "run", "--campaign", "tim", "--set", st, "--engines", "ref",
                                "--reps", "2"], env=isolated_env(root), cwd=PROJ, capture_output=True, text=True, timeout=600)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            recs = sorted(glob.glob(os.path.join(root, "results", "tim", "raw", "timing__*", "ref", "*", "*.json")))
            self.assertEqual(len(recs), 2)
            for p in recs:
                d = load(p)
                self.assertEqual(d["mode"], "timing")
                self.assertEqual(d["objects"], {})
                self.assertTrue(all("outputs" not in c for c in d["cells"]))
            r = subprocess.run([SHARED_PY, "-m", "pconf.timing", "report", "--campaign", "tim"], env=isolated_env(root),
                               cwd=PROJ, capture_output=True, text=True, timeout=600)
            self.assertEqual(r.returncode, 0, r.stderr)
            rep = load(glob.glob(os.path.join(root, "results", "tim", "timing_report__*.json"))[0])
            self.assertEqual(rep[0]["reps"], 2)
            self.assertFalse(rep[0]["all_ok"])  # the notebook has a cell that raises
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

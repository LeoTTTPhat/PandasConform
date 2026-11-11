"""Probe path (build -> run -> compare), root-cause minimisation into a runnable probe, and
scaled-input preparation (hard links at 1x, PandasBench cell-0 replication at 2x)."""
import glob
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from _common import PROJ, SHARED_PY, env_python, isolated_env, run_orch, write_set
from pconf import datasets


def load(p):
    with open(p) as f:
        return json.load(f)


PROBES = {"probes": [
    {"id": "t_vc_name", "family": "describe_stats", "source": "test", "documented": True,
     "setup": "s = pd.Series(['x', 'y', 'x', 'z', 'x', 'y', 'q', 'r'] * 4, name='col')",
     "code": "res = s.value_counts()\nres"},
    {"id": "t_sum", "family": "describe_stats", "source": "test", "documented": False,
     "setup": "df = pd.DataFrame({'a': [1, 2, 3]})", "code": "tot = df['a'].sum()\ntot"},
]}


@unittest.skipUnless(env_python("ref") and env_python("p15"), "needs ref and p15 envs")
class TestProbesAndRootcause(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="pconf_probe_")
        cls.pfile = os.path.join(cls.root, "probes_test.json")
        with open(cls.pfile, "w") as f:
            json.dump(PROBES, f)
        cls.set_path = os.path.join(cls.root, "probe_set.json")
        r = subprocess.run([SHARED_PY, "-m", "pconf.probes", "build", "--pattern", cls.pfile, "--set-path", cls.set_path],
                           env=isolated_env(cls.root), cwd=PROJ, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        r = run_orch(cls.root, ["run", "--campaign", "pr", "--set", cls.set_path, "--engines", "ref,p15",
                                "--cell-timeout", "60", "--nb-timeout", "300"])
        assert r.returncode == 0, r.stdout + r.stderr

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_probe_compare(self):
        r = run_orch(self.root, ["compare", "--campaign", "pr", "--set", self.set_path, "--engines", "p15",
                                 "--cell-timeout", "60", "--nb-timeout", "300"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        outs = {load(p)["meta"]["nb"]: load(p) for p in glob.glob(os.path.join(self.root, "results", "pr", "raw", "compare__*", "*", "*", "*.json"))}
        vc = {c["i"]: c for c in outs["probe:t_vc_name"]["cells"]}[3]
        # pandas 1.5.3 names value_counts() by the column, 2.x calls it 'count': names-only difference
        self.assertEqual(vc["cls"], "E4")
        self.assertTrue(vc["clean_input"])
        tot = {c["i"]: c for c in outs["probe:t_sum"]["cells"]}[3]
        self.assertEqual(tot["cls"], "E0")

    def test_minimize_to_probe(self):
        out_dir = os.path.join(self.root, "rc")
        r = subprocess.run([SHARED_PY, "-m", "pconf.rootcause", "minimize", "--campaign", "pr", "--engine", "p15",
                            "--nb", "probe:t_vc_name", "--cell", "3", "--cell-timeout", "60", "--nb-timeout", "300",
                            "--out-dir", out_dir, "--max-trials", "60"],
                           env=isolated_env(self.root), cwd=PROJ, capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        files = glob.glob(os.path.join(out_dir, "*.json"))
        self.assertEqual(len(files), 1)
        rc = load(files[0])
        self.assertEqual(rc["signature"][0], "E4")
        self.assertEqual(rc["rows"]["s"], 1)  # one row suffices to show the naming difference
        # the reproducer is itself a runnable probe
        set2 = os.path.join(self.root, "rc_set.json")
        r = subprocess.run([SHARED_PY, "-m", "pconf.probes", "build", "--pattern", files[0], "--set-path", set2],
                           env=isolated_env(self.root), cwd=PROJ, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_orch(self.root, ["run", "--campaign", "rc", "--set", set2, "--engines", "ref,p15",
                                 "--cell-timeout", "60", "--nb-timeout", "300"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run_orch(self.root, ["compare", "--campaign", "rc", "--set", set2, "--engines", "p15",
                                 "--cell-timeout", "60", "--nb-timeout", "300"])
        out = load(glob.glob(os.path.join(self.root, "results", "rc", "raw", "compare__*", "*", "*", "*.json"))[0])
        self.assertEqual({c["i"]: c["cls"] for c in out["cells"]}[3], "E4")


class TestDatasetsPrep(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="pconf_ds_")
        self.saved = (datasets.PB_DATA, datasets.SCALED, datasets.notebook_file)
        datasets.PB_DATA = os.path.join(self.root, "raw")
        datasets.SCALED = os.path.join(self.root, "scaled")
        nbdir = os.path.join(self.root, "nb")
        os.makedirs(nbdir)
        cell0 = ("import os\n\ndef scale_input_data(scale_factor):\n  file_bases = ['./input/t']\n  for file_base in file_bases:\n"
                 "    import pandas as pd\n    import shutil\n    if scale_factor == 1.0:\n"
                 "      shutil.copyfile(file_base + '.csv', file_base + '.scaled.csv')\n      continue\n"
                 "    df_to_scale = pd.read_csv(file_base + '.csv')\n    new_num_rows = int(scale_factor * len(df_to_scale))\n"
                 "    while len(df_to_scale) < new_num_rows:\n"
                 "      df_to_scale = pd.concat([df_to_scale, df_to_scale[:min(new_num_rows - len(df_to_scale), len(df_to_scale))]])\n"
                 "    df_to_scale.to_csv(file_base + '.scaled.csv', index=False)\n\n"
                 "if 'INPUT_SCALE_FACTOR' in os.environ:\n  scale_input_data(float(os.environ['INPUT_SCALE_FACTOR']))\n")
        nb = {"cells": [{"cell_type": "code", "source": cell0}, {"cell_type": "code", "source": "x = 1"}]}
        with open(os.path.join(nbdir, "old.ipynb"), "w") as f:
            json.dump(nb, f)
        datasets.notebook_file = lambda name: os.path.join(nbdir, "old.ipynb")
        os.makedirs(os.path.join(datasets.PB_DATA, "u", "s", "input"))
        with open(os.path.join(datasets.PB_DATA, "u", "s", "input", "t.csv"), "w") as f:
            f.write("a,b\n1,x\n2,y\n3,z\n")

    def tearDown(self):
        datasets.PB_DATA, datasets.SCALED, datasets.notebook_file = self.saved
        shutil.rmtree(self.root, ignore_errors=True)

    def test_scale1_hardlinks(self):
        r = datasets.prep("u/s", 1.0)
        self.assertEqual(r["status"], "ok", r)
        d = datasets.scaled_dir("u/s", 1.0)
        raw = os.path.join(datasets.PB_DATA, "u", "s", "input", "t.csv")
        self.assertEqual(os.stat(os.path.join(d, "input", "t.scaled.csv")).st_ino, os.stat(raw).st_ino)
        self.assertTrue(datasets.is_prepared("u/s", 1.0))
        self.assertEqual(datasets.prep("u/s", 1.0)["fingerprint"], r["fingerprint"])  # idempotent

    def test_scale2_replicates(self):
        r = datasets.prep("u/s", 2.0)
        self.assertEqual(r["status"], "ok", r)
        with open(os.path.join(datasets.scaled_dir("u/s", 2.0), "input", "t.scaled.csv")) as f:
            lines = f.read().strip().splitlines()
        self.assertEqual(len(lines), 1 + 6)

    def test_raw_change_invalidates(self):
        datasets.prep("u/s", 1.0)
        with open(os.path.join(datasets.PB_DATA, "u", "s", "input", "t2.csv"), "w") as f:
            f.write("a\n1\n")
        self.assertFalse(datasets.is_prepared("u/s", 1.0))


if __name__ == "__main__":
    unittest.main()

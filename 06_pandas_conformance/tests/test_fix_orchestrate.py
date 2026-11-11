"""Fix stage (2026-10-02): record reuse across campaigns, input content hash in the fingerprint,
compare outputs keyed by ref#2, summarize keeping one output per notebook."""
import glob
import json
import os
import shutil
import tempfile
import unittest

from _common import env_python, run_orch, write_probe_notebook, write_set

HEAD = ["import os\n", "exec(os.environ['IREWR_IMPORTS'])\nimport numpy as np\n"]
CELLS = HEAD + ["df = pd.DataFrame({'k': list('abca'), 'v': [1.0, 2.0, 3.0, 4.0]})\ndf", "g = df.groupby('k')['v'].sum()\ng"]


def load(p):
    with open(p) as f:
        return json.load(f)


@unittest.skipUnless(env_python("ref"), "ref env missing")
class TestReuseAndSummarize(unittest.TestCase):
    def test_reuse_from_other_campaign_and_summary(self):
        root = tempfile.mkdtemp(prefix="pconf_fix_orch_")
        try:
            nb = write_probe_notebook(os.path.join(root, "work"), "fix_reuse", CELLS)
            st = write_set(root, "reuse", [nb])
            common = ["--set", st, "--cell-timeout", "60", "--nb-timeout", "300"]
            r = run_orch(root, ["run", "--campaign", "A", "--engines", "ref,ref#2"] + common)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = run_orch(root, ["run", "--campaign", "B", "--engines", "ref,ref#2,p30", "--reuse-from", "A"] + common)
            self.assertEqual(json.loads(r.stdout.strip().splitlines()[-1])["counts"], {"reused": 2, "completed": 1}, r.stdout)
            recs = glob.glob(os.path.join(root, "results", "B", "raw", "runs__*", "ref", "*", "*.json"))
            self.assertIn("/results/A/", load(recs[0])["reused_from"])
            self.assertTrue(load(recs[0])["fingerprint"])
            # compare before and after ref#2 is known: two outputs, summarize uses the ref#2 one
            r = run_orch(root, ["compare", "--campaign", "B", "--engines", "p30"] + common)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = run_orch(root, ["compare", "--campaign", "B", "--engines", "p30", "--ref2", "ref#2"] + common)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            outs = glob.glob(os.path.join(root, "results", "B", "raw", "compare__*", "p30", "*", "*.json"))
            self.assertEqual(len(outs), 2)
            self.assertEqual(sum(o.endswith("_noref2.json") for o in outs), 1)
            r = run_orch(root, ["summarize", "--campaign", "B"])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            summ = load(glob.glob(os.path.join(root, "results", "B", "summary__*.json"))[0])
            self.assertEqual(summ["p30"]["notebooks"], 1)
            self.assertEqual(summ["p30"]["notebooks_without_ref2"], 0)
            self.assertEqual(len(summ["_meta"]["outputs_superseded"]), 1)
            self.assertIn("E2", summ["p30"]["clean_cells_at"])
        finally:
            shutil.rmtree(root, ignore_errors=True)


@unittest.skipUnless(env_python("ref") and env_python("p30"), "envs missing")
class TestCheckCampaign(unittest.TestCase):
    def test_check_campaign_reports_oracle_and_self_check(self):
        import subprocess
        from _common import PROJ, SHARED_PY, isolated_env
        root = tempfile.mkdtemp(prefix="pconf_fix_check_")
        try:
            nb = write_probe_notebook(os.path.join(root, "work"), "fix_check", CELLS)
            st = write_set(root, "chk", [nb])
            common = ["--campaign", "K", "--set", st, "--cell-timeout", "60", "--nb-timeout", "300"]
            self.assertEqual(run_orch(root, ["run", "--engines", "ref,ref#2,p30"] + common).returncode, 0)
            r = run_orch(root, ["compare", "--engines", "p30,ref#2", "--ref2", "ref#2"] + common)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = subprocess.run([SHARED_PY, os.path.join(PROJ, "scripts", "check_campaign.py"), "--engines", "ref,ref#2,p30",
                                "--ref2", "ref#2"] + common, env=isolated_env(root), cwd=PROJ, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            chk = load(glob.glob(os.path.join(root, "results", "K", "check__*.json"))[0])
            self.assertEqual(chk["n_problems"], 0)
            self.assertEqual(chk["records"]["p30"], {"completed": 1})
            self.assertEqual(chk["oracle"]["p30"]["compared"], 1)
            self.assertEqual(chk["self_check"]["ref#2"].get("self_check_fail", 0), 0)
            self.assertGreater(chk["store"]["sample_verified"], 0)
            self.assertEqual(chk["store"]["sample_hash_mismatch"], 0)
        finally:
            shutil.rmtree(root, ignore_errors=True)


@unittest.skipUnless(env_python("ref"), "ref env missing")
class TestHardBudget(unittest.TestCase):
    def test_hard_budget_interrupts_without_record(self):
        import time as _t
        root = tempfile.mkdtemp(prefix="pconf_fix_budget_")
        try:
            nb = write_probe_notebook(os.path.join(root, "work"), "fix_slow", HEAD + ["import time\ntime.sleep(30)\nx = 1"])
            st = write_set(root, "slow", [nb])
            t0 = _t.time()
            r = run_orch(root, ["run", "--campaign", "S", "--set", st, "--engines", "ref", "--cell-timeout", "120",
                                "--nb-timeout", "300", "--hard-budget", "5"])
            self.assertLess(_t.time() - t0, 25)
            self.assertEqual(json.loads(r.stdout.strip().splitlines()[-1])["counts"], {"interrupted": 1}, r.stdout)
            self.assertEqual(glob.glob(os.path.join(root, "results", "S", "raw", "runs__*", "ref", "*", "*.json")), [])
        finally:
            shutil.rmtree(root, ignore_errors=True)


@unittest.skipUnless(env_python("ref"), "ref env missing")
class TestNotebookMemoryCap(unittest.TestCase):
    def test_memory_cap_records_nb_memory(self):
        import pandas as pd
        from _common import TempStore
        from pconf import classify
        root = tempfile.mkdtemp(prefix="pconf_fix_mem_")
        try:
            cells = HEAD + ["a = 1", "import time\nbig = np.ones(60_000_000)\ntime.sleep(20)\nb = 2", "c = 3"]
            nb = write_probe_notebook(os.path.join(root, "work"), "fix_mem", cells)
            st = write_set(root, "mem", [nb])
            r = run_orch(root, ["run", "--campaign", "M", "--set", st, "--engines", "ref", "--cell-timeout", "120",
                                "--nb-timeout", "300", "--nb-mem-limit-gb", "0.3"])
            self.assertEqual(json.loads(r.stdout.strip().splitlines()[-1])["counts"], {"nb_memory": 1}, r.stdout)
            rec = load(glob.glob(os.path.join(root, "results", "M", "raw", "runs__*", "ref", "*", "*.json"))[0])
            self.assertEqual(rec["status"], "nb_memory")
            self.assertGreater(rec["peak_tree_rss_gb"], 0.3)
            self.assertEqual([c["i"] for c in rec["cells"]], [0, 1, 2])
            ref = dict(rec, status="completed", cells=rec["cells"] + [{"i": 3, "status": "ok", "static": {}, "outputs": {}},
                                                                     {"i": 4, "status": "ok", "static": {}, "outputs": {}}])
            rows = {c["i"]: c["cls"] for c in classify.classify_run(ref, rec, os.path.join(root, "captures"))["cells"]}
            self.assertEqual(rows[3], "MEMORY")
            self.assertEqual(rows[4], "NOTRUN")
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestInputCaptureRule(unittest.TestCase):
    def test_large_inputs_run_without_input_capture(self):
        from pconf import datasets, orchestrate
        if not os.path.isdir(datasets.PB_DATA):
            self.skipTest("data missing")
        cfg = {"cell_timeout": 600, "nb_timeout": 3600, "seed": 0, "capture_inputs": True, "limits": None, "cpus": None}
        big, small = "yonelanuba/elo-merchant-by-yonela", "deffro/eda-is-fun"
        self.assertFalse(orchestrate.nb_cfg(cfg, big, 1.0)["capture_inputs"])
        self.assertIs(orchestrate.nb_cfg(cfg, small, 1.0), cfg)
        self.assertFalse(orchestrate.nb_cfg(cfg, small, 5.0)["capture_inputs"])   # 3.3 GB at 5x
        self.assertTrue(orchestrate.nb_cfg(cfg, "probe:x", 1.0)["capture_inputs"])


class TestClassifyWithoutInputCapture(unittest.TestCase):
    def test_inputs_from_last_captured_values(self):
        import pandas as pd
        from _common import TempStore
        from pconf import classify
        from pconf.capture import Capturer
        from test_classify import RunBuilder
        ts = TempStore()
        try:
            cap = Capturer(ts.dir)
            d_ref = pd.DataFrame({"s": pd.Series(["a", "b"], dtype=object), "v": [1.0, 2.0]})
            d_eng = d_ref.astype({"s": "string"})
            ref = RunBuilder(cap).cell(1, outputs={"df": d_ref}).cell(2, outputs={"__last__": 3.0})
            eng = RunBuilder(cap).cell(1, outputs={"df": d_eng}).cell(2, outputs={"__last__": 3.0})
            for rec in (ref.rec, eng.rec):
                for c in rec["cells"]:
                    c.pop("inputs")
                rec["cells"][1]["static"]["loads"] = ["df", "len"]
            rows = {c["i"]: c for c in classify.classify_run(ref.rec, eng.rec, ts.dir)["cells"]}
            self.assertEqual(rows[2]["inputs_from"], "last_captured")
            self.assertEqual(rows[2]["clean_level"], "E2")
            self.assertFalse(rows[2]["clean_input"])
            self.assertEqual(rows[1]["clean_level"], "E0")
        finally:
            ts.cleanup()


class TestScaleCell(unittest.TestCase):
    """Pilot finding 2026-10-02: 34 of 102 notebooks keep the scaling cell only in old.ipynb."""

    def test_scale_cell_origin_and_setup_cells(self):
        from pconf import datasets
        if not os.path.isdir(datasets.PB_REPO):
            self.skipTest("PandasBench repo missing")
        self.assertEqual(datasets.scale_cell("deffro/eda-is-fun")[1], "run:0")
        self.assertEqual(datasets.setup_cells("deffro/eda-is-fun"), [0])
        src, origin = datasets.scale_cell("corazzon/how-to-use-pandas-filter-in-survey-eda")
        self.assertEqual(origin, "old:0")
        self.assertIn("INPUT_SCALE_FACTOR", src)
        self.assertEqual(datasets.setup_cells("corazzon/how-to-use-pandas-filter-in-survey-eda"), [])
        self.assertEqual(datasets.setup_cells("probe:x"), [0])
        import collections
        c = collections.Counter(datasets.scale_cell(nb)[1] for nb in datasets.all_notebooks())
        self.assertEqual(c, {"run:0": 68, "old:0": 34})


if __name__ == "__main__":
    unittest.main()

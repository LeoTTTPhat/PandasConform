"""Static cell analysis: loads (inputs), stores, mutations, magics, import shim rewriting."""
import ast
import unittest

import _common  # noqa: F401  (sys.path)
from pconf import nbsource


def an(src):
    return nbsource.analyze_source(src)


class TestAnalysis(unittest.TestCase):
    def test_load_before_store_is_input(self):
        r = an("df = df.dropna()\nx = df.shape")
        self.assertEqual(r["loads"], ["df"])
        self.assertEqual(r["stores"], ["df", "x"])

    def test_store_before_load_not_input(self):
        r = an("x = 1\ny = x + z")
        self.assertEqual(r["loads"], ["z"])

    def test_mutations(self):
        r = an("df['a'] = 1\ndf2.drop(columns=['b'], inplace=True)\nlst.append(3)\ndel df3['c']\ndf4.loc[df4.a > 0, 'b'] = 2")
        self.assertEqual(set(r["mutates"]), {"df", "df2", "lst", "df3", "df4"})
        self.assertIn("df", r["loads"])

    def test_augassign_and_for(self):
        r = an("total += 1\nfor i, row in df.iterrows():\n    acc = row")
        self.assertIn("total", r["loads"])
        self.assertIn("df", r["loads"])
        self.assertEqual(set(r["stores"]), {"total", "i", "row", "acc"})

    def test_lambda_and_comprehension_scopes(self):
        r = an("res = df.apply(lambda r: r.a + k)\nsq = [v * v for v in vals if v > t]")
        self.assertEqual(set(r["loads"]), {"df", "k", "vals", "t"})

    def test_defs_not_outputs(self):
        r = an("import numpy as np\ndef f(x):\n    global G\n    G = x\nclass K: pass")
        self.assertEqual(set(r["defs"]), {"np", "f", "K"})
        self.assertIn("G", r["stores"])

    def test_last_expression(self):
        self.assertTrue(an("df.head()")["last_expr"])
        self.assertFalse(an("x = 1")["last_expr"])
        tree, _ = nbsource.prepare_cell("x = 1\nx + 1")
        head, expr = nbsource.split_last_expr(tree)
        ns = {}
        exec(compile(head, "<t>", "exec"), ns)
        self.assertEqual(eval(compile(expr, "<t>", "eval"), ns), 2)

    def test_magics_stripped(self):
        src = "%matplotlib inline\n!pip install foo\nx = 1\n%time y = x + 1\nif x:\n    %ls"
        py, n = nbsource.strip_magics(src)
        self.assertEqual(n, 4)
        ns = {}
        exec(compile(ast.parse(py), "<t>", "exec"), ns)
        self.assertEqual(ns["y"], 2)
        py2, _ = nbsource.strip_magics("%%time\nx = 1")
        self.assertEqual(py2.strip(), "x = 1")

    def test_pandas_import_rewrite(self):
        tree, info = nbsource.prepare_cell("import pandas as pd\nimport os, pandas\nfrom pandas import DataFrame as DF")
        self.assertEqual(info["pandas_imports_rewritten"], 3)
        ns = {"__pconf_pd__": type("M", (), {"DataFrame": 42})}
        exec(compile(tree, "<t>", "exec"), ns)
        self.assertIs(ns["pd"], ns["__pconf_pd__"])
        self.assertIs(ns["pandas"], ns["__pconf_pd__"])
        self.assertEqual(ns["DF"], 42)
        _, info2 = nbsource.prepare_cell("import pandas.api.types\nfrom pandas.api.types import is_numeric_dtype")
        self.assertEqual(info2["pandas_imports_rewritten"], 0)  # submodules resolve to real pandas

    def test_syntax_error_reported(self):
        r = an("def (:")
        self.assertIn("syntax_error", r)


if __name__ == "__main__":
    unittest.main()

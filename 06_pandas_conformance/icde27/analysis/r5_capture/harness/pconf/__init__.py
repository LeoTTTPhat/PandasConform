"""PandasConform: graded conformance and semantic drift of pandas-API engines.

Modules that run inside every engine environment (stdlib + numpy + pandas + pyarrow only):
    nbsource, capture, runner_child
Modules that run in the parent (shared venv) or in the `ref` environment:
    engines, dfeq, classify, orchestrate, compare_worker, datasets, rootcause, probes, timing
"""
__version__ = "0.1.0"

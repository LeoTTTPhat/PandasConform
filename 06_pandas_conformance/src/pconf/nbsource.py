"""Notebook loading and static (AST) analysis of cells. Stdlib only; runs in every env.

Cell model (same as PandasBench's runner): the code cells of `updated.ipynb` (or `old.ipynb`)
in order; markdown cells are dropped; cell 0 is PandasBench's input-scaling cell and cell 1
executes `exec(os.environ['IREWR_IMPORTS'])`, which is how the import shim binds `pd`.

For each cell we compute
  stores   names bound by the cell (assignment targets, for/with targets, walrus, del)
  mutates  base names of subscript/attribute targets and of mutating method calls
           (`x.drop(..., inplace=True)`, `lst.append(..)`), i.e. names whose object may change
  loads    free loads: names read before the cell binds them (evaluation order), i.e. the
           names whose pre-cell values are the cell's inputs (clean-input attribution)
  defs     names bound to functions/classes/modules (never captured)
  attrs    attribute names used (operation families for Figure 2)
  last_expr whether the last statement is an expression (its value is an output)
  fn_globals  {name: [global names read in the body]} for functions/classes (and lambdas bound
           to a name) defined at module level in the cell: the hidden inputs of a later cell
           that calls them (fix of review finding A2, 2026-10-02)
  bound_loads names read after the cell itself bound them (e.g. a function defined and called
           in the same cell)
"""
import ast
import json
import os
import re
import symtable

MUTATING_METHODS = {
    # pandas objects mutated regardless of inplace=
    "insert", "pop", "update", "set_axis_inplace", "__setitem__", "__delitem__",
    # python containers
    "append", "extend", "remove", "sort", "reverse", "clear", "add", "discard",
    "setdefault", "popitem", "fill", "resize", "put", "itemset", "setflags",
}


def notebook_path(nb_dir):
    upd = os.path.join(nb_dir, "updated.ipynb")
    return upd if os.path.exists(upd) else os.path.join(nb_dir, "old.ipynb")


def load_cells(nb_file):
    """Return the list of code-cell sources (PandasBench semantics: markdown dropped,
    null sources dropped, empty code cells kept so indices stay stable)."""
    with open(nb_file) as f:
        nb = json.load(f)
    cells = []
    for c in nb["cells"]:
        if c.get("cell_type") != "code":
            continue
        src = c.get("source")
        if src is None:
            continue
        cells.append("".join(src) if isinstance(src, list) else str(src))
    return cells


_MAGIC_LINE = re.compile(r"^(\s*)([%!])")


def strip_magics(src):
    """Replace IPython line magics / shell escapes with `pass`, drop cell magics' first line.
    Returns (python_source, n_lines_replaced)."""
    lines = src.split("\n")
    out, n = [], 0
    for i, line in enumerate(lines):
        m = _MAGIC_LINE.match(line)
        if m:
            n += 1
            stripped = line.lstrip()
            if stripped.startswith("%%") and i == 0:
                continue  # cell magic header (e.g. %%time): run the body
            tm = re.match(r"%(time|timeit|prun)\s+(-\S+\s+)*(.+)$", stripped)
            if tm:
                out.append(m.group(1) + tm.group(3))  # timing magics: run the statement once
            else:
                out.append(m.group(1) + "pass")
        elif line.rstrip().endswith("?") and not line.lstrip().startswith("#") and re.match(r"^\s*[\w.]+\?{1,2}\s*$", line):
            n += 1
            out.append(re.match(r"^(\s*)", line).group(1) + "pass")
        else:
            out.append(line)
    return "\n".join(out), n


class _PandasImportRewriter(ast.NodeTransformer):
    """`import pandas as X` -> `X = __pconf_pd__`; `import pandas` -> `pandas = __pconf_pd__`;
    `from pandas import a as b` -> `b = __pconf_pd__.a`. Submodule imports are left alone."""

    def __init__(self):
        self.n = 0

    def visit_Import(self, node):
        keep, assigns = [], []
        for a in node.names:
            if a.name == "pandas":
                tgt = a.asname or "pandas"
                assigns.append(ast.Assign(targets=[ast.Name(id=tgt, ctx=ast.Store())],
                                          value=ast.Name(id="__pconf_pd__", ctx=ast.Load())))
                self.n += 1
            else:
                keep.append(a)
        if not assigns:
            return node
        res = []
        if keep:
            res.append(ast.Import(names=keep))
        res.extend(assigns)
        return res

    def visit_ImportFrom(self, node):
        if node.module != "pandas" or node.level:
            return node
        res = []
        for a in node.names:
            if a.name == "*":
                return node
            res.append(ast.Assign(targets=[ast.Name(id=a.asname or a.name, ctx=ast.Store())],
                                  value=ast.Attribute(value=ast.Name(id="__pconf_pd__", ctx=ast.Load()),
                                                      attr=a.name, ctx=ast.Load())))
            self.n += 1
        return res


def prepare_cell(src):
    """Source -> (module AST ready to compile, info dict). Raises SyntaxError if unparsable."""
    py, n_magic = strip_magics(src)
    tree = ast.parse(py)
    rw = _PandasImportRewriter()
    tree = rw.visit(tree)
    ast.fix_missing_locations(tree)
    return tree, {"magics_replaced": n_magic, "pandas_imports_rewritten": rw.n}


def _base_name(node):
    while isinstance(node, (ast.Subscript, ast.Attribute, ast.Starred)):
        node = node.value
    if isinstance(node, ast.Call):  # df.loc[...] where loc is attribute of Name
        return _base_name(node.func)
    return node.id if isinstance(node, ast.Name) else None


class _Analyzer(ast.NodeVisitor):
    """Visits in (approximate) evaluation order so a load that precedes a store in the same
    cell counts as an input (`df = df.dropna()` reads the pre-cell `df`)."""

    def __init__(self):
        self.bound = set()        # names bound so far (in evaluation order)
        self.free_loads = []      # ordered unique
        self.stores = []
        self.mutates = []
        self.defs = []
        self.attrs = []
        self.local_stack = []     # lambda / comprehension scopes
        self.bound_loads = []     # names read after the cell bound them

    # helpers
    def _load(self, name):
        if any(name in s for s in self.local_stack):
            return
        if name in self.bound:
            if name not in self.bound_loads:
                self.bound_loads.append(name)
        elif name not in self.free_loads:
            self.free_loads.append(name)

    def _store(self, name, kind="store"):
        if self.local_stack:
            self.local_stack[-1].add(name)
            return
        self.bound.add(name)
        lst = self.defs if kind == "def" else self.stores
        if name not in lst:
            lst.append(name)

    def _mut(self, name):
        if name and not self.local_stack and name not in self.mutates:
            self.mutates.append(name)

    def _targets(self, t):
        if isinstance(t, ast.Name):
            self._store(t.id)
        elif isinstance(t, (ast.Tuple, ast.List)):
            for e in t.elts:
                self._targets(e)
        elif isinstance(t, ast.Starred):
            self._targets(t.value)
        elif isinstance(t, (ast.Subscript, ast.Attribute)):
            # evaluate the container expression (a load) and record the mutation
            self.visit(t.value)
            if isinstance(t, ast.Subscript):
                self.visit(t.slice)
            self._mut(_base_name(t))

    # statements
    def visit_Assign(self, node):
        self.visit(node.value)
        for t in node.targets:
            self._targets(t)

    def visit_AnnAssign(self, node):
        if node.value is not None:
            self.visit(node.value)
            self._targets(node.target)

    def visit_AugAssign(self, node):
        if isinstance(node.target, ast.Name):
            self._load(node.target.id)
            self.visit(node.value)
            self._store(node.target.id)
        else:
            self.visit(node.value)
            self._targets(node.target)

    def visit_For(self, node):
        self.visit(node.iter)
        self._targets(node.target)
        for s in node.body + node.orelse:
            self.visit(s)

    visit_AsyncFor = visit_For

    def visit_With(self, node):
        for it in node.items:
            self.visit(it.context_expr)
            if it.optional_vars is not None:
                self._targets(it.optional_vars)
        for s in node.body:
            self.visit(s)

    def visit_NamedExpr(self, node):
        self.visit(node.value)
        self._targets(node.target)

    def visit_Delete(self, node):
        for t in node.targets:
            if isinstance(t, ast.Name):
                self._store(t.id)
            else:
                self._targets(t)

    def visit_FunctionDef(self, node):
        for d in node.decorator_list:
            self.visit(d)
        for d in node.args.defaults + [x for x in node.args.kw_defaults if x is not None]:
            self.visit(d)
        # globals declared inside the body may be rebound when the function is called
        for sub in ast.walk(node):
            if isinstance(sub, ast.Global):
                for n in sub.names:
                    if n not in self.stores:
                        self.stores.append(n)
        self._store(node.name, "def")

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        for d in node.decorator_list + node.bases:
            self.visit(d)
        self._store(node.name, "def")

    def visit_Import(self, node):
        for a in node.names:
            self._store((a.asname or a.name).split(".")[0], "def")

    def visit_ImportFrom(self, node):
        for a in node.names:
            if a.name != "*":
                self._store(a.asname or a.name, "def")

    def visit_Global(self, node):
        pass

    # expressions
    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            self._load(node.id)
        elif isinstance(node.ctx, ast.Store):
            self._store(node.id)

    def visit_Attribute(self, node):
        self.attrs.append(node.attr)
        self.visit(node.value)

    def visit_Call(self, node):
        self.visit(node.func)
        for a in node.args:
            self.visit(a)
        for k in node.keywords:
            self.visit(k.value)
        if isinstance(node.func, ast.Attribute):
            meth = node.func.attr
            inplace = any(k.arg == "inplace" and isinstance(k.value, ast.Constant) and k.value.value is True
                          for k in node.keywords)
            if inplace or meth in MUTATING_METHODS:
                self._mut(_base_name(node.func.value))

    def visit_Lambda(self, node):
        for d in node.args.defaults:
            self.visit(d)
        params = {a.arg for a in node.args.args + node.args.kwonlyargs + node.args.posonlyargs}
        if node.args.vararg:
            params.add(node.args.vararg.arg)
        if node.args.kwarg:
            params.add(node.args.kwarg.arg)
        self.local_stack.append(params)
        self.visit(node.body)
        self.local_stack.pop()

    def _comp(self, node, elts):
        self.local_stack.append(set())
        for g in node.generators:
            self.visit(g.iter)
            self._targets(g.target)
            for c in g.ifs:
                self.visit(c)
        for e in elts:
            self.visit(e)
        self.local_stack.pop()

    def visit_ListComp(self, node):
        self._comp(node, [node.elt])

    visit_SetComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp

    def visit_DictComp(self, node):
        self._comp(node, [node.key, node.value])


def _symtable_globals(node):
    """Global names read inside a function/class/lambda body (all nested scopes), via symtable."""
    try:
        src = ast.unparse(node)
        top = symtable.symtable(src, "<def>", "exec").get_children()
    except Exception:
        return None
    out = set()

    def walk(t):
        for sym in t.get_symbols():
            if sym.is_referenced() and sym.is_global():
                out.add(sym.get_name())
        for c in t.get_children():
            walk(c)

    for t in top:
        walk(t)
    return out


def function_globals(body):
    """{name: sorted global reads} for defs/classes at module level of a cell (including inside
    if/for/try/with blocks) and for `name = lambda ...` assignments."""
    out = {}

    def visit(stmts):
        for st in stmts:
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                g = _symtable_globals(st)
                if g is not None:
                    g.discard(st.name)
                    out[st.name] = sorted(g)
            elif isinstance(st, ast.Assign) and isinstance(st.value, ast.Lambda):
                g = _symtable_globals(ast.Expr(value=st.value))
                for t in st.targets:
                    if isinstance(t, ast.Name) and g is not None:
                        out[t.id] = sorted(g - {t.id})
            for field in ("body", "orelse", "finalbody"):
                sub = getattr(st, field, None)
                if isinstance(sub, list) and not isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    visit(sub)
            for h in getattr(st, "handlers", []) or []:
                visit(h.body)

    visit(body)
    return out


def analyze(tree):
    a = _Analyzer()
    body = tree.body if isinstance(tree, ast.Module) else [tree]
    for stmt in body:
        a.visit(stmt)
    last_expr = bool(body) and isinstance(body[-1], ast.Expr)
    stores = [s for s in a.stores if s not in a.defs]
    return {
        "loads": a.free_loads,
        "stores": stores,
        "mutates": [m for m in a.mutates if m not in stores],
        "defs": a.defs,
        "attrs": sorted(set(a.attrs)),
        "last_expr": last_expr,
        "fn_globals": function_globals(body),
        "bound_loads": a.bound_loads,
    }


def analyze_source(src):
    """Static analysis of a raw cell (after magic stripping). Returns dict or {'syntax_error':..}."""
    try:
        tree, info = prepare_cell(src)
    except SyntaxError as e:
        return {"syntax_error": "%s: %s" % (type(e).__name__, e), "loads": [], "stores": [], "mutates": [],
                "defs": [], "attrs": [], "last_expr": False, "fn_globals": {}, "bound_loads": []}
    res = analyze(tree)
    res.update(info)
    return res


def split_last_expr(tree):
    """Module -> (exec_module or None, eval_expression or None)."""
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        head = ast.Module(body=tree.body[:-1], type_ignores=[])
        expr = ast.Expression(body=tree.body[-1].value)
        ast.fix_missing_locations(head)
        ast.fix_missing_locations(expr)
        return (head if head.body else None), expr
    return tree, None

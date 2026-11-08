"""Export explicit development features out of runtime source before deployment.

This is deliberately not a Python optimizer or dead-code guesser. Only code
behind the literal DEVELOPMENT feature is specialized. Assertions and ordinary
error handling are preserved, regardless of the Python interpreter's -O flags.
"""
import ast
from pathlib import Path

DEVELOPMENT_MODULES = {'draw_metrics.py', 'pointer_trace.py', 'flurry_trial.py'}


class ReleaseFeatures(ast.NodeTransformer):
    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load) and node.id == 'DEVELOPMENT':
            return ast.copy_location(ast.Constant(False), node)
        return node

    def visit_Assign(self, node):
        if any(isinstance(t, ast.Name) and t.id == 'DEVELOPMENT' for t in node.targets):
            node.value = ast.Constant(False)
        return self.generic_visit(node)

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        # Only fold a leading literal: never discard effects to its left.
        first = node.values[0]
        if isinstance(first, ast.Constant):
            if isinstance(node.op, ast.And) and not first.value:
                return first
            if isinstance(node.op, ast.Or) and first.value:
                return first
        return node

    def visit_If(self, node):
        self.generic_visit(node)
        if isinstance(node.test, ast.Constant):
            return node.body if node.test.value else node.orelse
        if not node.body:
            node.body = [ast.Pass()]
        return node

    def visit_IfExp(self, node):
        self.generic_visit(node)
        if isinstance(node.test, ast.Constant):
            return node.body if node.test.value else node.orelse
        return node


def release_source(raw, filename):
    tree = ast.parse(raw, filename=filename)
    if not any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'DEVELOPMENT' for t in n.targets) for n in tree.body):
        return raw
    tree = ast.fix_missing_locations(ReleaseFeatures().visit(tree))
    compile(tree, filename, 'exec')  # Reject invalid exports before packaging.
    # Keep copyright, licensing and source attribution comments in exports.
    comments = '\n'.join(line for line in raw.decode().splitlines() if line.lstrip().startswith('#'))
    return (comments + '\n' + ast.unparse(tree) + '\n').encode()


def profile_files(files, profile='release'):
    if profile not in ('release', 'dev'):
        raise ValueError('profile must be release or dev')
    if profile == 'dev':
        return dict(files)
    return {name: release_source(raw, name) if name.endswith('.py') else raw
            for name, raw in files.items()
            if Path(name).name not in DEVELOPMENT_MODULES}

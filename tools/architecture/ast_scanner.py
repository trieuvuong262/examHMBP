"""AST-based source scanner used by the architecture map command."""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field
from pathlib import Path


IGNORED_DIRS = {
    '.git', '.venv', '__pycache__', 'media', 'media_local_backup', 'staticfiles',
    'build', 'node_modules', 'tmp_prod_deploy', '.codegraph', 'backups',
}


@dataclass
class FunctionInfo:
    qualified_name: str
    kind: str
    file: str
    line: int
    end_line: int | None
    calls: list[str] = field(default_factory=list)
    model_names: list[str] = field(default_factory=list)


@dataclass
class ModuleInfo:
    module: str
    file: str
    imports: list[str] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)


class _ModuleVisitor(ast.NodeVisitor):
    def __init__(self, module: str, relative_file: str):
        self.module = module
        self.relative_file = relative_file
        self.imports: set[str] = set()
        self.functions: list[FunctionInfo] = []
        self.classes: list[str] = []
        self.scope: list[str] = []

    def visit_Import(self, node: ast.Import):
        self.imports.update(alias.name for alias in node.names)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        prefix = '.' * node.level + (node.module or '')
        self.imports.update(prefix + '.' + alias.name for alias in node.names)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        qualified = '.'.join([self.module, *self.scope, node.name])
        self.classes.append(qualified)
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._record_function(node, 'function')

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._record_function(node, 'async_function')

    def _record_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, kind: str):
        qualified = '.'.join([self.module, *self.scope, node.name])
        calls = sorted({name for name in (_call_name(call) for call in ast.walk(node)) if name})
        model_names = sorted({name for name in (_model_name(call) for call in ast.walk(node)) if name})
        self.functions.append(FunctionInfo(
            qualified_name=qualified,
            kind=kind,
            file=self.relative_file,
            line=node.lineno,
            end_line=getattr(node, 'end_lineno', None),
            calls=calls,
            model_names=model_names,
        ))
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()


def _call_name(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    target = node.func
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        parts = []
        while isinstance(target, ast.Attribute):
            parts.append(target.attr)
            target = target.value
        if isinstance(target, ast.Name):
            parts.append(target.id)
            return '.'.join(reversed(parts))
    return None


def _model_name(node: ast.AST) -> str | None:
    name = _call_name(node)
    if not name:
        return None
    parts = name.split('.')
    if 'objects' in parts:
        index = parts.index('objects')
        if index > 0 and parts[index - 1][:1].isupper():
            return parts[index - 1]
    if 'DoesNotExist' in parts and parts[0][:1].isupper():
        return parts[0]
    return None




def _module_name(root: Path, path: Path) -> str:
    relative = path.relative_to(root).with_suffix('')
    parts = list(relative.parts)
    if parts[-1] == '__init__':
        parts.pop()
    return '.'.join(parts)


def scan_python_tree(root: str | Path) -> list[ModuleInfo]:
    root = Path(root).resolve()
    results: list[ModuleInfo] = []
    for path in sorted(root.rglob('*.py')):
        relative_parts = path.relative_to(root).parts
        if any(part in IGNORED_DIRS for part in relative_parts):
            continue
        try:
            source = path.read_text(encoding='utf-8')
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        visitor = _ModuleVisitor(_module_name(root, path), path.relative_to(root).as_posix())
        visitor.visit(tree)
        results.append(ModuleInfo(
            module=visitor.module,
            file=visitor.relative_file,
            imports=sorted(visitor.imports),
            functions=visitor.functions,
            classes=sorted(visitor.classes),
        ))
    return results


def serialize_modules(modules: list[ModuleInfo]) -> list[dict]:
    return [asdict(module) for module in modules]

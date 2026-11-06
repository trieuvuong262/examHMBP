"""Build a safe, read-only architecture view for superusers."""

from __future__ import annotations

from pathlib import Path

from django.apps import apps
from django.urls import get_resolver

from tools.architecture.ast_scanner import scan_python_tree, serialize_modules


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _collect_urls(patterns, prefix='', result=None):
    result = result if result is not None else []
    for pattern in patterns:
        route = prefix + str(pattern.pattern)
        callback = getattr(pattern, 'callback', None)
        if callback and hasattr(callback, '__name__'):
            result.append({
                'route': '/' + route.lstrip('/'),
                'name': getattr(pattern, 'name', None) or '',
                'callback': f'{callback.__module__}.{callback.__name__}',
            })
        nested = getattr(pattern, 'url_patterns', None)
        if nested is not None:
            _collect_urls(nested, route, result)
    return sorted(result, key=lambda item: item['route'])


def _models():
    result = []
    for model in apps.get_models():
        fields = []
        for field in model._meta.get_fields():
            if not getattr(field, 'concrete', False) and not getattr(field, 'auto_created', False):
                continue
            remote = getattr(field, 'remote_field', None)
            related = getattr(getattr(remote, 'model', None), '_meta', None)
            fields.append({
                'name': field.name,
                'type': field.__class__.__name__,
                'column': getattr(field, 'column', None) or '',
                'related_model': related.label if related else '',
                'many_to_many': bool(getattr(field, 'many_to_many', False)),
            })
        result.append({
            'label': model._meta.label,
            'app': model._meta.app_label,
            'name': model.__name__,
            'table': model._meta.db_table,
            'fields': fields,
        })
    return sorted(result, key=lambda item: item['label'])


def build_architecture_map(app_label=''):
    selected = {app_label} if app_label else set()
    modules = scan_python_tree(PROJECT_ROOT)
    if selected:
        modules = [item for item in modules if item.module.split('.')[0] in selected]
    app_rows = []
    model_rows = _models()
    for config in apps.get_app_configs():
        if selected and config.label not in selected:
            continue
        config_path = Path(config.path)
        try:
            display_path = config_path.relative_to(PROJECT_ROOT)
        except ValueError:
            # Django's built-in apps live in site-packages, outside the project root.
            display_path = config_path
        app_rows.append({
            'label': config.label,
            'name': config.name,
            'path': str(display_path).replace('\\', '/'),
            'models': [model.__name__ for model in config.get_models()],
        })
    if selected:
        model_rows = [item for item in model_rows if item['app'] in selected]
    return {
        'apps': sorted(app_rows, key=lambda item: item['label']),
        'urls': _collect_urls(get_resolver().url_patterns),
        'models': model_rows,
        'modules': serialize_modules(modules),
        'meta': {
            'static_analysis': True,
            'root': PROJECT_ROOT.name,
            'limitations': [
                'AST không giải quyết hoàn hảo alias, decorator, dynamic import và query runtime.',
                'Model hints là gợi ý từ biểu thức Model.objects..., không phải SQL trace.',
                'Trang chỉ hiển thị metadata, không hiển thị nội dung source hoặc secret.',
            ],
        },
    }


def model_mermaid(models):
    lines = ['erDiagram']
    for model in models:
        source = model['label'].replace('.', '_').replace('-', '_')
        lines.append(f'    {source} {{')
        for field in model['fields']:
            lines.append(f"        string {(field['column'] or field['name']).replace('-', '_')}")
        lines.append('    }')
    for model in models:
        source = model['label'].replace('.', '_').replace('-', '_')
        for field in model['fields']:
            if field['related_model']:
                target = field['related_model'].replace('.', '_').replace('-', '_')
                lines.append(f"    {source} }}o--|| {target} : {field['name']}")
    return '\n'.join(lines)

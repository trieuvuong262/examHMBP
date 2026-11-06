"""Generate a static architecture map.

Usage: python manage.py architecture_map --output architecture_output
"""

from __future__ import annotations

import json
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.urls import get_resolver

from tools.architecture.ast_scanner import scan_python_tree, serialize_modules


class Command(BaseCommand):
    help = 'Sinh bản đồ app, URL, function, model/table và quan hệ bằng Django + AST.'

    def add_arguments(self, parser):
        parser.add_argument('--output', default='architecture_output', help='Thư mục output.')
        parser.add_argument('--app', action='append', dest='app_labels', help='Chỉ quét app label này; lặp lại được.')
        parser.add_argument('--open-function', dest='open_function', help='In các file/line chứa function khớp tên.')

    def handle(self, *args, **options):
        root = Path.cwd().resolve()
        output = (root / options['output']).resolve()
        output.mkdir(parents=True, exist_ok=True)
        selected = set(options.get('app_labels') or [])

        modules = scan_python_tree(root)
        if selected:
            modules = [item for item in modules if item.module.split('.')[0] in selected]

        payload = {
            'meta': {
                'generator': 'python manage.py architecture_map',
                'root': root.name,
                'static_analysis': True,
                'limitations': [
                    'AST calls are syntactic and do not resolve every alias, decorator or dynamic import.',
                    'Model usage is inferred from common Model.objects expressions.',
                    'URL entries are collected from the loaded Django resolver.',
                ],
            },
            'apps': self._apps(selected),
            'urls': self._urls(),
            'models': self._models(selected),
            'modules': serialize_modules(modules),
        }
        self._write_json(output / 'architecture.json', payload)
        (output / 'models.mmd').write_text(self._models_mermaid(payload['models']), encoding='utf-8')
        (output / 'apps.mmd').write_text(self._apps_mermaid(payload['apps']), encoding='utf-8')
        (output / 'index.html').write_text(self._html(payload), encoding='utf-8')

        needle = options.get('open_function')
        if needle:
            matches = [
                function for module in payload['modules']
                for function in module['functions']
                if needle.lower() in function['qualified_name'].lower()
            ]
            for function in matches:
                self.stdout.write(f"{function['qualified_name']} - {function['file']}:{function['line']}")

        self.stdout.write(self.style.SUCCESS(
            f"Architecture map: {len(payload['apps'])} apps, "
            f"{len(payload['models'])} models, {len(payload['urls'])} URL patterns, "
            f"{len(payload['modules'])} Python modules -> {output}"
        ))

    def _apps(self, selected):
        result = []
        for config in apps.get_app_configs():
            if selected and config.label not in selected:
                continue
            result.append({
                'label': config.label,
                'name': config.name,
                'path': str(Path(config.path).relative_to(Path.cwd().resolve())).replace('\\', '/'),
                'models': [model.__name__ for model in config.get_models()],
            })
        return sorted(result, key=lambda item: item['label'])

    def _models(self, selected):
        result = []
        for model in apps.get_models():
            if selected and model._meta.app_label not in selected:
                continue
            fields = []
            for field in model._meta.get_fields():
                if not getattr(field, 'concrete', False) and not getattr(field, 'auto_created', False):
                    continue
                relation = getattr(field, 'remote_field', None)
                fields.append({
                    'name': field.name,
                    'type': field.__class__.__name__,
                    'db_column': getattr(field, 'column', None),
                    'related_model': getattr(getattr(relation, 'model', None), '_meta', None) and relation.model._meta.label,
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

    def _urls(self):
        result = []
        self._collect_urls(get_resolver().url_patterns, '', result)
        return sorted(result, key=lambda item: item['route'])

    def _collect_urls(self, patterns, prefix, result):
        for pattern in patterns:
            route = prefix + str(pattern.pattern)
            callback = getattr(pattern, 'callback', None)
            if callback and hasattr(callback, '__name__'):
                result.append({
                    'route': '/' + route.lstrip('/'),
                    'name': getattr(pattern, 'name', None),
                    'callback': f'{callback.__module__}.{callback.__name__}',
                })
            nested = getattr(pattern, 'url_patterns', None)
            if nested is not None:
                self._collect_urls(nested, route, result)

    @staticmethod
    def _write_json(path, data):
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    @staticmethod
    def _models_mermaid(models):
        lines = ['erDiagram']
        for model in models:
            safe = model['label'].replace('.', '_').replace('-', '_')
            lines.append(f'    {safe} {{')
            for field in model['fields']:
                column = (field['db_column'] or field['name']).replace('-', '_')
                lines.append(f'        string {column}')
            lines.append('    }')
        for model in models:
            source = model['label'].replace('.', '_').replace('-', '_')
            for field in model['fields']:
                related = field.get('related_model')
                if related:
                    target = related.replace('.', '_').replace('-', '_')
                    lines.append(f'    {source} }}o--|| {target} : {field["name"]}')
        return '\n'.join(lines) + '\n'

    @staticmethod
    def _apps_mermaid(apps_data):
        lines = ['flowchart LR']
        for item in apps_data:
            node = item['label'].replace('-', '_')
            lines.append(f'    {node}[{item["label"]}]')
        return '\n'.join(lines) + '\n'

    @staticmethod
    def _html(payload):
        data = json.dumps(payload, ensure_ascii=False).replace('</', '<\\/')
        html = '''<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>PortalJustPlay Architecture Map</title>
<style>body{font:14px system-ui;max-width:1200px;margin:2rem auto;padding:0 1rem;color:#172033}input{padding:.6rem;width:min(100%,32rem)}table{border-collapse:collapse;width:100%;margin-top:1rem}td,th{border:1px solid #ccd3df;padding:.45rem;text-align:left;vertical-align:top}th{background:#eef2f7}code{background:#eef2f7;padding:.1rem .25rem}.muted{color:#687386}</style></head>
<body><h1>PortalJustPlay Architecture Map</h1><p class="muted">Generated by Django introspection + static AST analysis. Không phải runtime trace.</p>
<input id="filter" placeholder="Lọc app, model, function, file..."><h2>Models / database tables</h2><table><thead><tr><th>Model</th><th>Table</th><th>Fields / relations</th></tr></thead><tbody id="models"></tbody></table>
<h2>Functions</h2><table><thead><tr><th>Function</th><th>File</th><th>Calls</th><th>Model hints</th></tr></thead><tbody id="functions"></tbody></table>
<script>const data=__DATA__;const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({&:'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));function render(){const q=document.querySelector('#filter').value.toLowerCase();document.querySelector('#models').innerHTML=data.models.filter(x=>(x.label+x.table+JSON.stringify(x.fields)).toLowerCase().includes(q)).map(x=>`<tr><td><code>${esc(x.label)}</code></td><td><code>${esc(x.table)}</code></td><td>${x.fields.map(f=>esc(f.name)+(f.related_model?' → '+esc(f.related_model):'')).join('<br>')}</td></tr>`).join('');const fs=data.modules.flatMap(m=>m.functions).filter(x=>(x.qualified_name+x.file+x.calls+x.model_names).toLowerCase().includes(q));document.querySelector('#functions').innerHTML=fs.map(x=>`<tr><td><code>${esc(x.qualified_name)}</code></td><td>${esc(x.file)}:${x.line}</td><td>${x.calls.map(esc).join(', ')}</td><td>${x.model_names.map(esc).join(', ')}</td></tr>`).join('')}document.querySelector('#filter').addEventListener('input',render);render();</script></body></html>'''
        return html.replace('__DATA__', data)


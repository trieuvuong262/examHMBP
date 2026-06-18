"""Thu thập và dọn file media không còn được tham chiếu."""

from __future__ import annotations

import re
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.db.models import FileField, ImageField

from ckeditor.fields import RichTextField

SKIP_FILENAMES = {'.gitkeep', '.keep', 'README', 'README.md'}

# TextField HTML (không phải RichTextField) — ảnh inline báo cáo VP
EXTRA_HTML_TEXT_FIELDS = (
    ('reports', 'DailyWorkReport', 'document_html'),
)


def _media_url_path() -> str:
    return settings.MEDIA_URL.rstrip('/').lstrip('/')


def normalize_media_relative_path(raw: str | None) -> str:
    if not raw:
        return ''
    name = str(raw).replace('\\', '/').strip()
    if not name:
        return ''

    for prefix in (
        f'/{_media_url_path()}/',
        f'{_media_url_path()}/',
        'media/',
        '/media/',
    ):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break

    if name.startswith('http://') or name.startswith('https://'):
        marker = f'/{_media_url_path()}/'
        idx = name.find(marker)
        if idx >= 0:
            name = name[idx + len(marker):]
        else:
            return ''

    return name.lstrip('/')


def _extract_paths_from_html(html: str) -> set[str]:
    if not html:
        return set()
    paths: set[str] = set()
    media_prefix = re.escape(_media_url_path())
    pattern = re.compile(
        rf'(?:https?://[^"\']+)?/{media_prefix}/([^"\')\s<>]+)',
        re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        paths.add(normalize_media_relative_path(match.group(1)))

    for match in re.finditer(
        r'/reports/doc-image/\d+/([^"\')\s<>]+)',
        html,
        re.IGNORECASE,
    ):
        paths.add(normalize_media_relative_path(match.group(1)))

    for match in re.finditer(
        r'/reports/inline-image/([^"\')\s<>]+)',
        html,
        re.IGNORECASE,
    ):
        paths.add(normalize_media_relative_path(match.group(1)))

    for match in re.finditer(
        r'(\d{4}/\d{4}-\d{2}-\d{2}/[^/"\'\s<>]+/vanban/inline/[^"\')\s<>]+)',
        html,
        re.IGNORECASE,
    ):
        paths.add(normalize_media_relative_path(match.group(1)))

    return {path for path in paths if path}


def collect_referenced_media_paths() -> set[str]:
    referenced: set[str] = set()

    for model in apps.get_models():
        file_fields: list[str] = []
        rich_fields: list[str] = []
        for field in model._meta.concrete_fields:
            if isinstance(field, (FileField, ImageField)):
                file_fields.append(field.name)
            elif isinstance(field, RichTextField):
                rich_fields.append(field.name)

        if not file_fields and not rich_fields:
            continue

        field_names = file_fields + rich_fields
        for row in model._default_manager.values_list(*field_names).iterator():
            for index, value in enumerate(row):
                field_name = field_names[index]
                if field_name in file_fields:
                    if value:
                        referenced.add(normalize_media_relative_path(value))
                elif value:
                    referenced.update(_extract_paths_from_html(value))

    for app_label, model_name, field_name in EXTRA_HTML_TEXT_FIELDS:
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            continue
        for value in model._default_manager.values_list(field_name, flat=True).iterator():
            if value:
                referenced.update(_extract_paths_from_html(value))

    return {path for path in referenced if path}


def iter_orphan_media_files(referenced: set[str] | None = None) -> list[Path]:
    root = Path(settings.MEDIA_ROOT)
    if not root.exists():
        return []

    referenced = referenced if referenced is not None else collect_referenced_media_paths()
    orphans: list[Path] = []

    for path in root.rglob('*'):
        if not path.is_file():
            continue
        if path.name in SKIP_FILENAMES:
            continue
        rel = path.relative_to(root).as_posix()
        if rel not in referenced:
            orphans.append(path)

    return orphans


def cleanup_orphan_media(*, dry_run: bool = False) -> dict:
    referenced = collect_referenced_media_paths()
    orphans = iter_orphan_media_files(referenced)
    removed_files = 0
    freed_bytes = 0

    for path in orphans:
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        if dry_run:
            removed_files += 1
            freed_bytes += size
            continue
        try:
            path.unlink()
            removed_files += 1
            freed_bytes += size
        except OSError:
            continue

    if not dry_run:
        _remove_empty_dirs(Path(settings.MEDIA_ROOT))

    return {
        'referenced_count': len(referenced),
        'orphan_count': len(orphans),
        'removed_count': removed_files,
        'freed_bytes': freed_bytes,
        'dry_run': dry_run,
    }


def _remove_empty_dirs(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted(root.rglob('*'), reverse=True):
        if path.is_dir():
            try:
                next(path.iterdir())
            except StopIteration:
                path.rmdir()
            except OSError:
                pass

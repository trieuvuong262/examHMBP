"""Sinh class diagram (Mermaid) từ Django models.

Chạy trong container web:
    docker compose exec -T web python scripts/gen_class_diagram.py [--out DIR]

Kết quả: 1 file .md cho mỗi app + README.md tổng quan.
"""

import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")

import django  # noqa: E402

django.setup()

from django.apps import apps  # noqa: E402

SKIP_APPS = {"contenttypes", "sessions", "admin", "ckeditor_uploader"}


def class_id(model, current_app=None):
    """Tên class hợp lệ trong Mermaid; thêm tiền tố app khi tham chiếu chéo app."""
    if current_app and model._meta.app_label == current_app:
        return model.__name__
    return f"{model._meta.app_label}_{model.__name__}"


def field_rows(model):
    rows = []
    for f in model._meta.local_fields:
        kind = f.get_internal_type()
        marker = "+"
        if f.primary_key:
            marker = "+"
            kind += " PK"
        elif f.is_relation:
            kind += " FK"
        elif getattr(f, "unique", False):
            kind += " UQ"
        if getattr(f, "null", False):
            kind += "?"
        rows.append(f"    {marker}{kind} {f.name}")
    for f in model._meta.local_many_to_many:
        rows.append(f"    +M2M {f.name}")
    return rows


def relations(model, current_app):
    """(source, arrow, target, label) cho FK / O2O / M2M của model."""
    out = []
    src = class_id(model, current_app)
    for f in model._meta.local_fields:
        if not f.is_relation or f.related_model is None:
            continue
        tgt = class_id(f.related_model, current_app)
        if tgt == src:
            label = f"{f.name} (self)"
        else:
            label = f.name
        arrow = '"1" --> "1"' if f.one_to_one else '"*" --> "1"'
        out.append((src, arrow, tgt, label))
    for f in model._meta.local_many_to_many:
        if f.related_model is None:
            continue
        out.append((src, '"*" <--> "*"', class_id(f.related_model, current_app), f.name))
    return out


def external_models(model_rels, own_names):
    return sorted({t for _, _, t, _ in model_rels if t not in own_names})


def write_app_diagram(app_label, models, out_dir):
    own_names = {class_id(m, app_label) for m in models}
    lines = [
        f"# Class diagram — `{app_label}`",
        "",
        f"{len(models)} model. Class có tiền tố `app_` là model thuộc app khác.",
        "",
        "```mermaid",
        "classDiagram",
        "    direction LR",
    ]

    all_rels = []
    for model in sorted(models, key=lambda m: m.__name__):
        lines.append(f"    class {class_id(model, app_label)} {{")
        lines.extend(field_rows(model) or ["    %% (không có field)"])
        lines.append("    }")
        all_rels.extend(relations(model, app_label))

    ext = external_models(all_rels, own_names)
    if ext:
        lines.append("")
        for name in ext:
            lines.append(f"    class {name} {{")
            lines.append("    +external")
            lines.append("    }")

    if all_rels:
        lines.append("")
        seen = set()
        for src, arrow, tgt, label in all_rels:
            key = (src, arrow, tgt, label)
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"    {src} {arrow} {tgt} : {label}")

    lines.append("```")
    lines.append("")

    path = os.path.join(out_dir, f"{app_label}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path


def write_overview(app_models, cross_app, out_dir):
    lines = [
        "# Class diagram — PortalJustPlay",
        "",
        "Sinh tự động: `docker compose exec -T web python scripts/gen_class_diagram.py`",
        "",
        "## Sơ đồ phụ thuộc giữa các module",
        "",
        "```mermaid",
        "flowchart LR",
    ]
    for app_label, models in sorted(app_models.items()):
        lines.append(f'    {app_label}["{app_label}<br/>{len(models)} model"]')
    lines.append("")
    for (src, tgt), count in sorted(cross_app.items()):
        lines.append(f"    {src} -->|{count}| {tgt}")
    lines.append("```")
    lines.extend(["", "## Chi tiết từng module", "", "| Module | Model | Sơ đồ |", "|---|---|---|"])
    for app_label, models in sorted(app_models.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"| `{app_label}` | {len(models)} | [{app_label}.md](./{app_label}.md) |")
    total = sum(len(m) for m in app_models.values())
    lines.extend(["", f"Tổng: **{len(app_models)} module**, **{total} model**.", ""])

    path = os.path.join(out_dir, "README.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="docs/diagrams/class-diagram")
    parser.add_argument("--apps", default="", help="Danh sách app_label, phân tách bằng dấu phẩy")
    args = parser.parse_args()

    only = {a.strip() for a in args.apps.split(",") if a.strip()}
    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)

    app_models = defaultdict(list)
    for model in apps.get_models():
        label = model._meta.app_label
        if label in SKIP_APPS:
            continue
        if only and label not in only:
            continue
        app_models[label].append(model)

    cross_app = defaultdict(int)
    for label, models in app_models.items():
        for model in models:
            for f in list(model._meta.local_fields) + list(model._meta.local_many_to_many):
                if not f.is_relation or f.related_model is None:
                    continue
                other = f.related_model._meta.app_label
                if other != label and other not in SKIP_APPS:
                    cross_app[(label, other)] += 1

    for label, models in sorted(app_models.items()):
        path = write_app_diagram(label, models, out_dir)
        print(f"  {path}  ({len(models)} model)")

    print(f"  {write_overview(app_models, cross_app, out_dir)}")
    print(f"Done: {len(app_models)} app, {sum(len(m) for m in app_models.values())} model -> {out_dir}")


if __name__ == "__main__":
    main()

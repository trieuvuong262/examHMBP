"""Tự đăng ký vào admin-panel mọi model chưa có ModelAdmin riêng.

Model có ModelAdmin viết tay trong ``<app>/admin.py`` luôn được ưu tiên;
module này chỉ lấp phần còn thiếu với cấu hình mặc định hợp lý.
"""
from django import forms
from django.apps import apps
from django.contrib import admin
from django.db import models

EXCLUDED_APPS = {'contenttypes', 'sessions'}

# Dữ liệu đồng bộ một chiều từ hệ thống ngoài — sửa tay sẽ bị ghi đè.
READONLY_APPS = {'kiotviet'}
EDITABLE_IN_READONLY_APPS = {'kiotviet.kvsyncconfig'}

READONLY_NAME_SUFFIXES = ('Log', 'Snapshot', 'Tombstone', 'ResponseTimeDaily', 'SyncState', 'SyncJob')

SECRET_FIELD_HINTS = ('password', 'secret', 'api_key', 'access_token', 'refresh_token')

CHILD_NAME_SUFFIXES = ('Line', 'Lines', 'Extra', 'Level', 'Option', 'Choice', 'Attachment')

MAX_LIST_DISPLAY = 7
MAX_LIST_FILTER = 5
MAX_SEARCH_FIELDS = 6
MAX_TABULAR_FIELDS = 8


def _is_secret(field):
    name = field.name.lower()
    return isinstance(field, (models.CharField, models.TextField)) and any(h in name for h in SECRET_FIELD_HINTS)


def _is_readonly_model(model):
    label = model._meta.label_lower
    if model._meta.app_label in READONLY_APPS and label not in EDITABLE_IN_READONLY_APPS:
        return True
    return model.__name__.endswith(READONLY_NAME_SUFFIXES)


def _is_singleton(model):
    return callable(getattr(model, 'load', None)) or callable(getattr(model, 'get_solo', None))


def _concrete_fields(model):
    return [f for f in model._meta.concrete_fields if not f.primary_key]


def _relation_fields(model, exclude=()):
    rel = [
        f.name for f in model._meta.get_fields()
        if (f.many_to_one or f.one_to_one or f.many_to_many)
        and f.concrete and f.editable and f.name not in exclude
    ]
    return tuple(rel)


def _list_display(model):
    cols = ['__str__']
    for f in _concrete_fields(model):
        if len(cols) > MAX_LIST_DISPLAY:
            break
        if _is_secret(f) or isinstance(f, (models.TextField, models.JSONField, models.BinaryField)):
            continue
        cols.append(f.name)
    return tuple(cols)


def _list_filter(model):
    filters = []
    for f in _concrete_fields(model):
        if len(filters) >= MAX_LIST_FILTER:
            break
        if isinstance(f, models.BooleanField) or (f.choices and not f.is_relation):
            filters.append(f.name)
    return tuple(filters)


def _search_fields(model):
    names = []
    for f in _concrete_fields(model):
        if len(names) >= MAX_SEARCH_FIELDS:
            break
        if (
            isinstance(f, models.CharField)
            and not f.choices
            and not _is_secret(f)
            and (f.max_length or 0) <= 255
        ):
            names.append(f.name)
    return tuple(names)


def _date_hierarchy(model):
    for name in ('created_at', 'created', 'date'):
        try:
            f = model._meta.get_field(name)
        except Exception:
            continue
        if isinstance(f, (models.DateField, models.DateTimeField)):
            return name
    return None


class SecretPreservingForm(forms.ModelForm):
    """Ẩn giá trị trường bí mật; để trống khi lưu = giữ nguyên giá trị cũ."""

    secret_fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.secret_fields:
            field = self.fields.get(name)
            if field is None:
                continue
            field.widget = forms.PasswordInput(render_value=False, attrs={'autocomplete': 'new-password'})
            field.required = False
            field.help_text = 'Để trống để giữ nguyên giá trị hiện tại.'

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk:
            for name in self.secret_fields:
                if name in self.fields and not cleaned.get(name):
                    cleaned[name] = getattr(self.instance, name)
        return cleaned


def secret_form_for(model):
    secrets = tuple(f.name for f in _concrete_fields(model) if _is_secret(f))
    if not secrets:
        return None
    meta = type('Meta', (), {'model': model, 'fields': '__all__'})
    return type(
        f'{model.__name__}SecretForm',
        (SecretPreservingForm,),
        {'Meta': meta, 'secret_fields': secrets},
    )


def build_inline(model, fk_name):
    editable = [f for f in _concrete_fields(model) if f.editable]
    base = admin.TabularInline if len(editable) <= MAX_TABULAR_FIELDS else admin.StackedInline
    attrs = {
        'model': model,
        'fk_name': fk_name,
        'extra': 0,
        'raw_id_fields': _relation_fields(model, exclude=(fk_name,)),
        'show_change_link': False,
    }
    if base is admin.StackedInline:
        attrs['classes'] = ('collapse',)
    form = secret_form_for(model)
    if form:
        attrs['form'] = form
    return type(f'{model.__name__}AutoInline', (base,), attrs)


def build_model_admin(model, inlines=()):
    list_display = _list_display(model)
    attrs = {
        'list_display': list_display,
        'list_filter': _list_filter(model),
        'search_fields': _search_fields(model),
        'raw_id_fields': _relation_fields(model),
        'list_select_related': tuple(
            n for n in list_display
            if n != '__str__' and model._meta.get_field(n).is_relation
        ),
        'list_per_page': 50,
        'show_full_result_count': False,
        'inlines': list(inlines),
    }
    if not model._meta.ordering:
        attrs['ordering'] = ('-pk',)
    hierarchy = _date_hierarchy(model)
    if hierarchy:
        attrs['date_hierarchy'] = hierarchy
    form = secret_form_for(model)
    if form:
        attrs['form'] = form

    if _is_readonly_model(model):
        attrs['has_add_permission'] = lambda self, request, obj=None: False
        attrs['has_change_permission'] = lambda self, request, obj=None: False
        attrs['has_delete_permission'] = lambda self, request, obj=None: request.user.is_superuser
    elif _is_singleton(model):
        attrs['has_add_permission'] = lambda self, request: not self.model.objects.exists()
        attrs['has_delete_permission'] = lambda self, request, obj=None: False

    return type(f'{model.__name__}AutoAdmin', (admin.ModelAdmin,), attrs)


def _inline_parent(model, candidates):
    """FK CASCADE bắt buộc tới model cha cùng app, tên con bắt đầu bằng tên cha."""
    if _is_readonly_model(model):
        return None
    for f in model._meta.concrete_fields:
        if not f.many_to_one or f.null:
            continue
        parent = f.related_model
        if parent is model or parent not in candidates:
            continue
        if f.remote_field.on_delete is not models.CASCADE:
            continue
        if parent._meta.app_label != model._meta.app_label:
            continue
        name = model.__name__
        if name.startswith(parent.__name__) or name.endswith(CHILD_NAME_SUFFIXES):
            return parent, f.name
    return None


def register_remaining(site=admin.site):
    already_inlined = {i.model for ma in site._registry.values() for i in ma.inlines}
    pending = [
        m for m in apps.get_models()
        if m not in site._registry
        and m not in already_inlined
        and m._meta.app_label not in EXCLUDED_APPS
        and not m._meta.abstract
        and not m._meta.proxy
        and not m._meta.swapped
    ]
    pending_set = set(pending)

    parents = {}
    for m in pending:
        found = _inline_parent(m, pending_set)
        if found:
            parents[m] = found
    has_children = {p for p, _ in parents.values()}
    inline_of = {c: v for c, v in parents.items() if c not in has_children}

    children_by_parent = {}
    for child, (parent, fk_name) in inline_of.items():
        children_by_parent.setdefault(parent, []).append(build_inline(child, fk_name))

    for m in pending:
        if m in inline_of:
            continue
        site.register(m, build_model_admin(m, children_by_parent.get(m, ())))

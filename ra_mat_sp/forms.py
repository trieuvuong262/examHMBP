from __future__ import annotations

from django import forms

from thiet_ke_sp import catalog
from thiet_ke_sp.forms import UserChoiceField, UserMultipleChoiceField, active_users
from thiet_ke_sp.forms import user_field as _tk_user_field
from kho_san_pham.catalog_models import ProductStyle

from . import permissions as perms
from .models import (
    GO_DECISIONS,
    PLAN_DECISIONS,
    ChecklistTemplateItem,
    Decision,
    Importance,
    LaunchPlan,
    LaunchRisk,
    PostLaunchReview,
    RiskSeverity,
    TaskGroup,
    TaskStatus,
)

_INPUT = {'class': 'form-control form-control-sm'}
_SELECT = {'class': 'form-select form-select-sm'}
_DATE = {'class': 'form-control form-control-sm jp-date-vn', 'type': 'date'}
_MONEY = {'class': 'form-control form-control-sm text-end', 'inputmode': 'numeric', 'min': '0', 'step': '1'}
_CHECK = {'class': 'form-check-input'}


def user_field(label: str, **kwargs) -> UserChoiceField:
    field = _tk_user_field(label, **kwargs)
    field.widget.attrs['class'] = 'form-select form-select-sm jp-tksp-user-select'
    return field


def _textarea(rows: int = 3) -> forms.Textarea:
    return forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': rows})


def approver_queryset(current_id=None):
    ids = [u.pk for u in perms.approver_candidates()]
    if current_id:
        ids.append(current_id)
    return active_users().filter(pk__in=ids)


class StyleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        type_label = obj.product_type.name if obj.product_type_id else ''
        return f'{obj.code} · {obj.name or "—"}' + (f' — {type_label}' if type_label else '')


class PlanForm(forms.ModelForm):
    styles = StyleChoiceField(
        queryset=ProductStyle.objects.none(),
        label='Sản phẩm ra mắt (Thư viện sản phẩm)',
        help_text='Chọn Style đã có trong Thư viện sản phẩm.',
        widget=forms.SelectMultiple(attrs={'class': 'form-select form-select-sm jp-tksp-user-select', 'multiple': 'multiple'}),
    )

    class Meta:
        model = LaunchPlan
        fields = [
            'name', 'launch_date', 'coordinator', 'approver', 'scope', 'channels', 'objective',
            'target_customer', 'positioning', 'target_qty', 'target_revenue', 'marketing_budget', 'note',
        ]
        widgets = {
            'name': forms.TextInput(attrs={**_INPUT, 'placeholder': 'VD: Ra mắt BST chạy bộ Hè 2027'}),
            'launch_date': forms.DateInput(attrs=_DATE, format='%Y-%m-%d'),
            'scope': forms.TextInput(attrs={**_INPUT, 'placeholder': 'VD: Toàn quốc / Miền Nam / Online'}),
            'channels': forms.TextInput(attrs={**_INPUT, 'placeholder': 'VD: Cửa hàng, Website, Shopee, Sỉ'}),
            'objective': _textarea(2),
            'target_customer': forms.TextInput(attrs=_INPUT),
            'positioning': _textarea(2),
            'target_qty': forms.NumberInput(attrs=_MONEY),
            'target_revenue': forms.NumberInput(attrs=_MONEY),
            'marketing_budget': forms.NumberInput(attrs=_MONEY),
            'note': _textarea(2),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        plan = self.instance
        from .services import library_styles

        current = [pk for pk in plan.products.values_list('style_id', flat=True) if pk] if plan.pk else []
        self.fields['styles'].queryset = library_styles(current)
        if plan.pk and not self.is_bound:
            self.initial['styles'] = current
        self.fields['coordinator'] = user_field('Người điều phối', required=True)
        self.fields['approver'] = UserChoiceField(
            queryset=approver_queryset(plan.approver_id), required=False, label='Người duyệt (Go/No-Go)',
            empty_label='— Chọn —', widget=forms.Select(attrs={'class': 'form-select form-select-sm jp-tksp-user-select'}),
        )


def owner_choice_rows(selected=None):
    """Danh sách chọn người phụ trách từng nhóm (Thiết lập hoặc từng kế hoạch)."""
    from thiet_ke_sp.permissions import user_avatar_url, user_initial
    from thiet_ke_sp.permissions import avatar_tone_for

    selected = selected or {}
    users = []
    for u in active_users():
        users.append({
            'pk': u.pk, 'name': u.profile.full_name if u.profile else u.get_full_name() or u.username,
            'avatar': user_avatar_url(u), 'initial': user_initial(u), 'tone': avatar_tone_for(u.pk),
        })
    return [
        {'key': key, 'label': label, 'selected': selected.get(key, []), 'users': users}
        for key, label in TaskGroup.choices
    ]


def collaborators_field() -> UserMultipleChoiceField:
    return UserMultipleChoiceField(
        queryset=active_users(), required=False, label='Người phối hợp',
        widget=forms.SelectMultiple(attrs={'class': 'form-select form-select-sm jp-tksp-user-select', 'multiple': 'multiple'}),
    )


class TaskAddForm(forms.Form):
    group = forms.ChoiceField(label='Nhóm', choices=TaskGroup.choices, widget=forms.Select(attrs=_SELECT))
    title = forms.CharField(max_length=255, label='Công việc', widget=forms.TextInput(attrs=_INPUT))
    deliverable = forms.CharField(max_length=255, required=False, label='Kết quả cần có', widget=forms.TextInput(attrs=_INPUT))
    start_date = forms.DateField(required=False, label='Ngày bắt đầu', widget=forms.DateInput(attrs=_DATE))
    due_date = forms.DateField(label='Hạn hoàn thành', widget=forms.DateInput(attrs=_DATE))
    owner = user_field('Người chịu trách nhiệm chính', required=True)
    collaborators = collaborators_field()
    importance = forms.ChoiceField(label='Mức độ', choices=Importance.choices, widget=forms.Select(attrs=_SELECT))
    is_go_blocker = forms.BooleanField(
        required=False, label='Điều kiện bắt buộc Go/No-Go', widget=forms.CheckboxInput(attrs=_CHECK),
    )


class TaskUpdateForm(forms.Form):
    status = forms.ChoiceField(label='Trạng thái', choices=TaskStatus.choices, widget=forms.Select(attrs=_SELECT))
    owner = user_field('Người phụ trách')
    collaborators = collaborators_field()
    start_date = forms.DateField(required=False, label='Ngày bắt đầu', widget=forms.DateInput(attrs=_DATE))
    due_date = forms.DateField(required=False, label='Hạn', widget=forms.DateInput(attrs=_DATE))
    evidence = forms.CharField(required=False, label='Bằng chứng / kết quả', widget=_textarea(2))
    delay_reason = forms.CharField(required=False, label='Lý do trễ / vướng mắc', widget=_textarea(2))


class RiskForm(forms.ModelForm):
    class Meta:
        model = LaunchRisk
        fields = ['group', 'severity', 'description', 'action', 'owner', 'due_date']
        widgets = {
            'group': forms.Select(attrs=_SELECT),
            'severity': forms.Select(attrs=_SELECT),
            'description': _textarea(2),
            'action': _textarea(2),
            'due_date': forms.DateInput(attrs=_DATE, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['owner'] = user_field('Người xử lý', required=True)
        self.fields['severity'].initial = RiskSeverity.MEDIUM


class PlanDecisionForm(forms.Form):
    decision = forms.ChoiceField(
        label='Quyết định', widget=forms.RadioSelect(attrs=_CHECK),
        choices=[(d, Decision(d).label) for d in PLAN_DECISIONS],
    )
    comment = forms.CharField(required=False, label='Ý kiến', widget=_textarea(3))


class GoDecisionForm(forms.Form):
    decision = forms.ChoiceField(
        label='Quyết định', widget=forms.RadioSelect(attrs=_CHECK),
        choices=[(d, Decision(d).label) for d in GO_DECISIONS],
    )
    comment = forms.CharField(required=False, label='Ý kiến', widget=_textarea(3))
    new_launch_date = forms.DateField(required=False, label='Ngày ra mắt mới', widget=forms.DateInput(attrs=_DATE))
    condition_text = forms.CharField(
        required=False, max_length=500, label='Điều kiện phải hoàn thành', widget=forms.TextInput(attrs=_INPUT),
    )
    condition_owner = user_field('Người xử lý điều kiện')
    condition_due = forms.DateField(required=False, label='Hạn xử lý điều kiện', widget=forms.DateInput(attrs=_DATE))


class ReviewForm(forms.ModelForm):
    class Meta:
        model = PostLaunchReview
        fields = ['qty_sold', 'revenue', 'stock_left', 'return_rate', 'feedback', 'findings', 'decision']
        widgets = {
            'qty_sold': forms.NumberInput(attrs=_MONEY),
            'revenue': forms.NumberInput(attrs=_MONEY),
            'stock_left': forms.NumberInput(attrs=_MONEY),
            'return_rate': forms.NumberInput(attrs={**_MONEY, 'step': '0.1', 'max': '100'}),
            'feedback': _textarea(2),
            'findings': _textarea(2),
            'decision': forms.Select(attrs=_SELECT),
        }


class TemplateItemForm(forms.ModelForm):
    product_group = forms.ChoiceField(required=False, label='Chỉ áp dụng cho nhóm SP', widget=forms.Select(attrs=_SELECT))

    class Meta:
        model = ChecklistTemplateItem
        fields = ['offset_days', 'group', 'title', 'deliverable', 'importance', 'is_go_blocker', 'product_group',
                  'sort_order', 'is_active']
        widgets = {
            'offset_days': forms.NumberInput(attrs={**_INPUT, 'step': '1'}),
            'group': forms.Select(attrs=_SELECT),
            'title': forms.TextInput(attrs=_INPUT),
            'deliverable': forms.TextInput(attrs=_INPUT),
            'importance': forms.Select(attrs=_SELECT),
            'sort_order': forms.NumberInput(attrs={**_INPUT, 'min': 0}),
            'is_go_blocker': forms.CheckboxInput(attrs=_CHECK),
            'is_active': forms.CheckboxInput(attrs=_CHECK),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product_group'].choices = [('', 'Mọi nhóm sản phẩm')] + list(catalog.group_choices())
        for field in self.fields.values():
            field.help_text = ''

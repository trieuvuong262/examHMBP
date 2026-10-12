from __future__ import annotations

from django import forms

from thiet_ke_sp import catalog
from thiet_ke_sp.forms import UserChoiceField, active_users, user_field
from thiet_ke_sp.models import ProductDevelopment
from thiet_ke_sp.models import Status as DossierStatus

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

_INPUT = {'class': 'form-control'}
_SELECT = {'class': 'form-select'}
_DATE = {'class': 'form-control jp-date-vn', 'type': 'date'}
_MONEY = {'class': 'form-control text-end', 'inputmode': 'numeric', 'min': '0', 'step': '1'}


def _textarea(rows: int = 3) -> forms.Textarea:
    return forms.Textarea(attrs={'class': 'form-control', 'rows': rows})


def approver_queryset(current_id=None):
    ids = [u.pk for u in perms.approver_candidates()]
    if current_id:
        ids.append(current_id)
    return active_users().filter(pk__in=ids)


class DossierChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        group = catalog.group_label(obj.product_group) if obj.product_group else 'Chưa chọn nhóm'
        return f'{obj.code} · {obj.name} — {group} · {obj.get_status_display()}'


def dossier_queryset(current_ids=()):
    from django.db.models import Q

    return ProductDevelopment.objects.filter(
        Q(pk__in=list(current_ids)) | ~Q(status__in=(DossierStatus.CANCELLED,)),
    ).order_by('-created_at')


class PlanForm(forms.ModelForm):
    dossiers = DossierChoiceField(
        queryset=ProductDevelopment.objects.none(),
        label='Sản phẩm ra mắt (hồ sơ thiết kế)',
        widget=forms.SelectMultiple(attrs={'class': 'form-select jp-tksp-user-select', 'multiple': 'multiple'}),
        help_text='Chọn một hoặc nhiều hồ sơ từ Thiết kế sản phẩm. Checklist mẫu sinh theo nhóm sản phẩm của hồ sơ.',
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
        current = list(plan.products.values_list('dossier_id', flat=True)) if plan.pk else []
        self.fields['dossiers'].queryset = dossier_queryset(current)
        if plan.pk and not self.is_bound:
            self.initial['dossiers'] = current
        self.fields['coordinator'] = user_field('Người điều phối', required=True)
        self.fields['approver'] = UserChoiceField(
            queryset=approver_queryset(plan.approver_id), required=False, label='Người duyệt (Go/No-Go)',
            empty_label='— Chọn —', widget=forms.Select(attrs={'class': 'form-select jp-tksp-user-select'}),
            help_text='Người có quyền Sửa menu «Chờ tôi duyệt» của Kế hoạch ra mắt.',
        )


class TaskAddForm(forms.Form):
    group = forms.ChoiceField(label='Nhóm', choices=TaskGroup.choices, widget=forms.Select(attrs=_SELECT))
    title = forms.CharField(max_length=255, label='Công việc', widget=forms.TextInput(attrs=_INPUT))
    deliverable = forms.CharField(max_length=255, required=False, label='Kết quả cần có', widget=forms.TextInput(attrs=_INPUT))
    due_date = forms.DateField(label='Hạn', widget=forms.DateInput(attrs=_DATE))
    owner = user_field('Người phụ trách', required=True)
    importance = forms.ChoiceField(label='Mức độ', choices=Importance.choices, widget=forms.Select(attrs=_SELECT))
    is_go_blocker = forms.BooleanField(required=False, label='Điều kiện bắt buộc Go/No-Go')


class TaskUpdateForm(forms.Form):
    status = forms.ChoiceField(label='Trạng thái', choices=TaskStatus.choices, widget=forms.Select(attrs=_SELECT))
    owner = user_field('Người phụ trách')
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
        label='Quyết định', widget=forms.RadioSelect,
        choices=[(d, Decision(d).label) for d in PLAN_DECISIONS],
    )
    comment = forms.CharField(required=False, label='Ý kiến', widget=_textarea(3))


class GoDecisionForm(forms.Form):
    decision = forms.ChoiceField(
        label='Quyết định', widget=forms.RadioSelect,
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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product_group'].choices = [('', 'Mọi nhóm sản phẩm')] + list(catalog.group_choices())
